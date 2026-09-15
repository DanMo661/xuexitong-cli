# -*- coding: utf-8 -*-
"""学习通小助手 —— 学习通（超星）桌面悬浮窗（可选组件）。

风格对齐市面高星桌面组件（Class Widgets / TrafficMonitor）与 Fluent 2 亮色
规范：近白圆角卡片 + 1px 细描边 + 状态色点，默认浅色、右键可切深色。

设计约束：
- 只用标准库 tkinter，零新增依赖；数据层直接复用 client.py（不经 MCP）。
- 渐进渲染：课表秒出；作业截止/通知在后台线程扫完后补上（全课程扫描
  需约 1 分钟，进度以"扫描中"提示）。
- 对账号友好：自动刷新默认 30 分钟，只读查询，与 MCP 同一风控边界。

运行：python -m xuexitong_mcp.widget 或仓库根目录的 学习通小助手.bat
"""

from __future__ import annotations

import datetime as dt
import json
import os
import queue
import threading

# ---------------------------------------------------------------- 纯逻辑（不依赖 tkinter，可单测）

COLLAPSED_LINES = 2  # 收起态正文行数（下一节课 + 作业摘要）


def lesson_rows(lessons: list[dict], curriculum: dict, week: int,
                today: dt.date) -> list[dict]:
    """某周课表条目 → 今天的课程行（含真实上下课时刻）。

    日期 = firstWeekDate（第 1 周周一）+ (week-1)*7 + dayOfWeek-1 天，
    时刻取自服务端 lessonTimeConfigArray（学校真实节次表），不本地猜。
    """
    from .client import ms_to_date, parse_section_times
    first = curriculum.get("firstWeekDate") or curriculum.get("firstWeekDateReal")
    times = parse_section_times(curriculum.get("lessonTimeConfigArray"))
    if not first or not times:
        return []
    first_monday = ms_to_date(first)
    rows: list[dict] = []
    for les in lessons:
        dow = int(les.get("dayOfWeek") or 1)  # 1=周一 … 7=周日
        begin = int(les.get("beginNumber") or 1)
        length = int(les.get("length") or 1)
        day = first_monday + dt.timedelta(days=(int(week or 1) - 1) * 7 + dow - 1)
        if day != today or begin < 1 or begin > len(times):
            continue
        rows.append({
            "name": les.get("name") or "?",
            "location": les.get("location") or "待定",
            "teacher": les.get("teacherName") or "",
            "begin": begin, "length": length,
            "start": dt.datetime.combine(day, times[begin - 1][0]),
            "end": dt.datetime.combine(
                day, times[min(begin + length - 2, len(times) - 1)][1]),
        })
    rows.sort(key=lambda r: r["start"])
    return rows


def pick_current_next(rows: list[dict], now: dt.datetime):
    """返回 (正在上的课, 下一节课)，没有则对应为 None。"""
    current = next((r for r in rows if r["start"] <= now <= r["end"]), None)
    nxt = next((r for r in rows if r["start"] > now), None)
    return current, nxt


def fmt_countdown(delta: dt.timedelta) -> str:
    """倒计时文案：45 分钟 / 3 小时 05 分 / 1 天 3 小时 / 已过期。"""
    minutes = int(delta.total_seconds() // 60)
    if minutes < 0:
        return "已过期"
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, mm = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} 小时 {mm:02d} 分" if mm else f"{hours} 小时"
    days, hh = divmod(hours, 24)
    return f"{days} 天 {hh} 小时" if hh else f"{days} 天"


def _short(exc: Exception) -> str:
    return " ".join(str(exc).split())[:50] or exc.__class__.__name__


def collect_snapshot(client, now: dt.datetime | None = None,
                     progress=None) -> dict:
    """拉取悬浮窗所需的全部数据，每完成一个板块调用一次 progress(snap, done)。

    板块顺序：课表（快，几秒）→ 作业截止（全课程逐课扫描，约 1 分钟）→
    通知。单板块失败只记 error 不拖垮整卡。
    """
    now = now or dt.datetime.now()
    snap = {"ok": True, "msg": "", "rows": [], "current": None, "next": None,
            "week": None, "deadlines": [], "deadline_total": 0, "overdue": 0,
            "notices": [], "unread": 0, "errors": [], "scanning": False}

    def emit(done: bool) -> None:
        if progress:
            progress(dict(snap), done)

    lg = client.ensure_login()
    if not lg.ok:
        snap["ok"] = False
        snap["msg"] = "未登录（右键 → 刷新 重试）"
        emit(True)
        return snap

    try:  # 课表：默认请求即当前周，日期换算出"今天"的课
        sched = client.fetch_schedule()
        cur = sched["curriculum"]
        week = int(cur.get("realCurrentWeek") or cur.get("currentWeek") or 0)
        snap["week"] = week
        rows = lesson_rows(sched["lessons"], cur, week, now.date())
        snap["rows"] = rows
        snap["current"], snap["next"] = pick_current_next(rows, now)
    except Exception as e:  # noqa: BLE001
        snap["errors"].append("课表: " + _short(e))
    emit(False)

    snap["scanning"] = True
    emit(False)
    try:  # 作业截止：全课程扫描（慢），只对未提交的逐份取详情
        overview = client.fetch_deadline_overview()
        snap["deadline_total"] = len(overview)
        snap["overdue"] = sum(1 for r in overview
                              if r["deadline_dt"] and r["deadline_dt"].date() < now.date())
        snap["deadlines"] = overview[:3]
        snap["scanning"] = False
    except Exception as e:  # noqa: BLE001
        snap["scanning"] = False
        snap["errors"].append("作业: " + _short(e))
    emit(False)

    try:  # 通知：最近 3 条
        items = client.fetch_notices(limit=3)
        notices = []
        for it in items:
            t = (it.get("title") or "").strip()
            notices.append({"title": t[:37] + "…" if len(t) > 38 else t,
                            "time": (it.get("completeTime") or "")[5:16],
                            "unread": not it.get("isread")})
        snap["notices"] = notices
        snap["unread"] = sum(1 for n in notices if n["unread"])
    except Exception as e:  # noqa: BLE001
        snap["errors"].append("通知: " + _short(e))
    emit(True)
    return snap


# ---------------------------------------------------------------- 主题（亮色默认，参照 Fluent 2 亮色 token + GitHub 状态色）

THEMES = {
    "light": {
        "card": "#FBFBFD", "border": "#D9DEE6", "trans": "#010203",
        "fg": "#1B1F27", "sub": "#6B7280", "sep": "#E8EAEF",
        "hover": "#ECEEF2", "icon": "#4A5058",
        "blue": "#0969DA", "green": "#1A7F37",
        "red": "#CF222E", "yellow": "#9A6700",
    },
    "dark": {
        "card": "#1E1F24", "border": "#33363D", "trans": "#010203",
        "fg": "#E8EAED", "sub": "#9AA0A6", "sep": "#33363D",
        "hover": "#2E3038", "icon": "#C5C9D0",
        "blue": "#8AB4F8", "green": "#81C995",
        "red": "#F28B82", "yellow": "#FDD663",
    },
}


class Widget:
    AUTO_REFRESH_MS = 30 * 60 * 1000  # 自动刷新 30 分钟（对账号友好）
    CLOCK_TICK_MS = 20 * 1000         # 时刻文案每 20s 重排（倒计时自己会走）
    W = 328                           # 卡片宽度

    def __init__(self, client):
        import tkinter as tk
        self.tk = tk
        self.client = client
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.expanded = False
        self.animating = False
        self.snap: dict | None = None
        self._drag = None
        self._last_h = 0
        self._blink = False

        cfg = self._load_config()
        self.theme_name = cfg.get("theme") if cfg.get("theme") in THEMES else "light"
        self.topmost = bool(cfg.get("topmost", True))

        root = tk.Tk()
        self.root = root
        self.var_topmost = tk.BooleanVar(value=self.topmost)
        root.overrideredirect(True)
        root.attributes("-topmost", self.topmost)
        root.attributes("-transparentcolor", THEMES[self.theme_name]["trans"])
        # 亮色不透明（半透明会在浅色背景上透出底层文字鬼影），深色保留通透感
        root.attributes("-alpha", 1.0 if self.theme_name == "light" else 0.94)
        root.title("学习通小助手")

        self.cv = tk.Canvas(root, width=self.W, height=90,
                            bg=THEMES[self.theme_name]["trans"],
                            highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)

        self.header = tk.Frame(self.cv, bg=THEMES[self.theme_name]["card"])
        self.body = tk.Frame(self.cv, bg=THEMES[self.theme_name]["card"])
        self._hw = self.cv.create_window(16, 8, window=self.header, anchor="nw")
        self._bw = None

        self._build_header()
        self._bind_drag(self.header)
        self.cv.bind("<Button-1>", self._press)
        self.cv.bind("<B1-Motion>", self._motion)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Button-3>", self._menu)

        self._place_initial(cfg)
        self._render(changed_only=False)  # 先画空卡，数据到了再填
        self.refresh(manual=True)

        root.after(200, self._poll_queue)
        root.after(self.CLOCK_TICK_MS, self._tick)
        root.after(self.AUTO_REFRESH_MS, self._auto)

    # ---------- 主题 ----------

    @property
    def T(self) -> dict:
        return THEMES[self.theme_name]

    def _switch_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.root.attributes("-transparentcolor", self.T["trans"])
        self.root.attributes("-alpha", 1.0 if self.theme_name == "light" else 0.94)
        self._save_config()
        self._render(changed_only=False)

    # ---------- 布局 ----------

    def _build_header(self):
        tk = self.tk
        T = self.T
        for wdg in self.header.winfo_children():
            wdg.destroy()
        self.dot = tk.Label(self.header, text="●", bg=T["card"], fg=T["green"],
                            font=("Segoe UI", 9))
        self.dot.pack(side="left", padx=(0, 6))
        title = tk.Label(self.header, text="学习通小助手", bg=T["card"], fg=T["fg"],
                         font=("Microsoft YaHei UI", 10, "bold"))
        title.pack(side="left")
        self._bind_drag(title)
        self.badge = tk.Label(self.header, text="", bg=T["card"], fg=T["blue"],
                              font=("Microsoft YaHei UI", 8, "bold"))
        self.badge.pack(side="left", padx=(6, 0))
        self.week_lbl = tk.Label(self.header, text="", bg=T["card"], fg=T["sub"],
                                 font=("Microsoft YaHei UI", 8))
        self.week_lbl.pack(side="left", padx=(8, 0))
        self._bind_drag(self.week_lbl)

        def btn(text, cmd, bold=False):
            # 字体用雅黑自有字形（Segoe UI 的 ▾/✕ 在部分环境缺字形，渲染成破图）
            font = (("Segoe UI", 10, "bold") if bold
                    else ("Microsoft YaHei UI", 9))
            b = tk.Label(self.header, text=text, bg=T["card"], fg=T["icon"],
                         width=2, font=font, cursor="hand2")
            b.bind("<Enter>", lambda e: b.config(fg=T["fg"], bg=T["hover"]))
            b.bind("<Leave>", lambda e: b.config(fg=T["icon"], bg=T["card"]))
            b.bind("<Button-1>", lambda e: cmd())
            return b

        self.b_refresh = btn("↻", lambda: self.refresh(manual=True), bold=True)
        self.b_refresh.pack(side="right", padx=(2, 0))
        self.b_close = btn("×", self._quit)
        self.b_close.pack(side="right")
        self.b_toggle = btn("▼", self._toggle)
        self.b_toggle.pack(side="right")

    def _body_rows(self) -> list[dict]:
        """生成正文行：dict(kind, color, bold, small, text)，kind=sep 画分隔线，
        kind=bar 画当前课程左侧的强调竖条。"""
        T = self.T
        out: list[dict] = []
        snap = self.snap
        now = dt.datetime.now()
        if not snap:
            return [dict(color=T["sub"], bold=False, small=False, text="正在连接学习通…")]
        if not snap["ok"]:
            return [dict(color=T["red"], bold=False, small=False, text=snap["msg"])]

        def row(color, text, bold=False, small=False, kind="text"):
            out.append(dict(kind=kind, color=color, bold=bold, small=small, text=text))

        cur, nxt = snap["current"], snap["next"]
        if cur:
            mins = (cur["end"] - now).seconds // 60
            row(T["green"], f"正在上课 · {cur['name']}", bold=True)
            row(T["sub"], f"{cur['start']:%H:%M}-{cur['end']:%H:%M}  {cur['location']}  ·  剩 {mins} 分钟", small=True)
        elif nxt:
            row(T["blue"], f"下一节 {nxt['start']:%H:%M} · {nxt['name']}", bold=True)
            row(T["sub"], f"{nxt['location']}  ·  {fmt_countdown(nxt['start'] - now)}后上课", small=True)
        elif snap["rows"]:
            row(T["green"], "今天课程已结束 ✓")
        else:
            row(T["green"], "今天无课 ✓")

        total, over = snap["deadline_total"], snap["overdue"]
        if snap["scanning"]:
            row(T["sub"], "正在扫描作业截止…")
        elif total:
            soon = any(r["deadline_dt"] and dt.timedelta() <= r["deadline_dt"] - now <= dt.timedelta(days=2)
                       for r in snap["deadlines"])
            row(T["yellow"] if (over or soon) else T["green"],
                f"待交作业 {total} 项" + ("，有过期未交！" if over else ""))
            for r in snap["deadlines"]:
                d = r["deadline_dt"]
                when = fmt_countdown(d - now) if d else "截止未知"
                color = T["red"] if (d and d < now) else (
                    T["yellow"] if d and d - now <= dt.timedelta(days=2) else T["sub"])
                row(color, f"· {r['title'][:14]}  {when}", small=True)
        else:
            row(T["green"], "没有待交作业 ✓")

        if not self.expanded:
            return out[:COLLAPSED_LINES + 1]
        # ---- 展开区 ----
        out.append(dict(kind="sep"))
        row(T["sub"], f"今日课程 · 第{snap['week'] or '?'}周")
        if snap["rows"]:
            for r in snap["rows"]:
                label = f"{r['start']:%H:%M}  {r['name'][:12]}  {r['location'][:10]}"
                if cur and r is cur:
                    row(T["green"], label, bold=True, kind="bar")
                elif r["start"] < now:
                    row(T["sub"], f"· {label}")
                else:
                    row(T["fg"], f"○ {label}")
        else:
            row(T["sub"], "（无）")
        out.append(dict(kind="sep"))
        row(T["sub"], "最新通知")
        for n in snap["notices"]:
            color = T["blue"] if n["unread"] else T["sub"]
            mark = "●" if n["unread"] else "·"
            row(color, f"{mark} {n['title']}  {n['time']}", small=not n["unread"])
        if not snap["notices"]:
            row(T["sub"], "（无）")
        for e in snap["errors"][:2]:
            row(T["red"], "! " + e, small=True)
        return out

    def _render(self, changed_only: bool = True):
        """按 _body_rows 重建正文并自适应卡片高度（高度动画在 _animate_to）。"""
        tk = self.tk
        T = self.T
        for wdg in self.body.winfo_children():
            wdg.destroy()
        rows = self._body_rows()
        for it in rows:
            if it.get("kind") == "sep":
                tk.Frame(self.body, bg=T["sep"], height=1).pack(fill="x", pady=(6, 4))
                continue
            holder = tk.Frame(self.body, bg=T["card"])
            if it.get("kind") == "bar":  # 当前课程的强调竖条
                tk.Frame(holder, bg=T["green"], width=3).pack(side="left", fill="y",
                                                              padx=(0, 6), pady=1)
            lbl = tk.Label(holder, text=it["text"], bg=T["card"], fg=it["color"],
                           anchor="w",
                           font=("Microsoft YaHei UI", 8 if it["small"] else 9,
                                 "bold" if it["bold"] else "normal"))
            lbl.pack(side="left", fill="x")
            holder.pack(fill="x", pady=1)
            for w in (holder, lbl):
                w.bind("<Button-1>", lambda e: self._toggle())
        self.root.update_idletasks()
        h = 8 + self.header.winfo_reqheight() + 5
        if rows:
            h += self.body.winfo_reqheight() + 4
        self._update_header_static()
        self._animate_to(h, instant=not changed_only)

    def _update_header_static(self):
        """周次与未读徽标（不重建 header，避免每次刷新闪一下）。"""
        snap = self.snap
        if not snap or not snap.get("ok"):
            self.week_lbl.config(text="")
            self.badge.config(text="")
            return
        self.week_lbl.config(text=f"第{snap['week'] or '?'}周")
        unread = snap.get("unread") or 0
        self.badge.config(text=f"{unread} 条未读" if unread else "")

    def _paint(self, h: int):
        """重画圆角卡片底板（近白卡片 + 1px 细描边）。

        canvas 高度比卡片多留 2px：否则底边描边像素会被窗口边界裁掉，
        卡片落在浅色背景上时下边缘会"消失"。
        """
        cv = self.cv
        T = self.T
        cv.delete("card")
        cv.config(height=h + 2)
        w, r = self.W, 18  # smooth 多边形的视觉圆角约为参数的一半，18≈视觉 10px
        pts = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h, r, h,
               0, h, 0, h - r, 0, r, 0, 0]
        cv.create_polygon(pts, smooth=True, fill=T["card"], outline=T["border"],
                          width=1, tags="card")
        cv.tag_lower("card")
        cv.itemconfigure(self._hw, width=w - 28)  # 头部右缘贴到卡片右侧留 12px
        if self._bw is not None:
            cv.delete(self._bw)
        if self.body.winfo_children():
            self._bw = cv.create_window(18, 8 + self.header.winfo_reqheight() + 4,
                                        window=self.body, anchor="nw",
                                        width=w - 36)
        else:
            self._bw = None

    def _animate_to(self, h_target: int, instant: bool = False):
        """卡片高度过渡（展开/收起约 120ms 六步插值）；高度不变时不动，防闪烁。"""
        if h_target == self._last_h:
            return
        if instant or self.animating or abs(h_target - self._last_h) < 8:
            self._apply_height(h_target)
            return

        def step(i: int, h0: int):
            self._apply_height(h0 + (h_target - h0) * i // 6)
            if i < 6:
                self.root.after(16, lambda: step(i + 1, h0))
            else:
                self.animating = False
        self.animating = True
        step(1, self._last_h)

    def _apply_height(self, h: int):
        self._paint(h)
        self.root.geometry(f"{self.W}x{h + 2}")  # +2 同 _paint，保住底边描边
        self._last_h = h

    # ---------- 数据 ----------

    def refresh(self, manual: bool = False):
        if self.busy:
            return
        self.busy = True
        if manual:  # 清缓存，强制走网络
            self.client._courses_cache_at = 0.0
            self.client._hw_cache.clear()

        def work():
            try:
                collect_snapshot(self.client, progress=self._on_progress)
            except Exception as e:  # noqa: BLE001
                self.q.put(({"ok": False, "msg": _short(e)}, True))
        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, snap: dict, done: bool):
        self.q.put((snap, done))

    def _auto(self):
        self.refresh()
        self.root.after(self.AUTO_REFRESH_MS, self._auto)

    def _poll_queue(self):
        try:
            while True:
                snap, done = self.q.get_nowait()
                if done:
                    self.busy = False
                self.snap = snap
                self._render()
        except queue.Empty:
            pass
        self.root.after(300, self._poll_queue)

    def _tick(self):
        if self.snap and self.snap.get("ok"):
            now = dt.datetime.now()
            nxt = self.snap.get("next")
            urgent = bool(nxt and dt.timedelta() <= nxt["start"] - now <= dt.timedelta(minutes=10))
            urgent = urgent or (self.snap.get("overdue") or 0) > 0
            if urgent:  # 呼吸点：临近上课/有过期作业时红黄交替
                self._blink = not self._blink
                self.dot.config(fg=self.T["red"] if self._blink else self.T["yellow"])
            else:
                self._status_color()
            self._render()
        self.root.after(self.CLOCK_TICK_MS, self._tick)

    def _status_color(self):
        snap = self.snap
        if not snap:
            return
        color = self.T["green"]
        if not snap["ok"] or snap["errors"]:
            color = self.T["red"]
        elif snap.get("deadline_total"):
            overdue = snap.get("overdue") or 0
            color = self.T["yellow"] if overdue else self.T["green"]
        self.dot.config(fg=color)

    # ---------- 交互 ----------

    def _toggle(self):
        if self.animating:
            return
        self.expanded = not self.expanded
        self.b_toggle.config(text="▲" if self.expanded else "▼")
        self._render()

    def _quit(self):
        self._save_config()
        self.root.destroy()

    def _menu(self, event=None):
        tk = self.tk
        T = self.T
        m = tk.Menu(self.root, tearoff=0, bg=T["card"], fg=T["fg"],
                    activebackground=T["hover"], activeforeground=T["fg"], bd=0)
        m.add_command(label="刷新数据", command=lambda: self.refresh(manual=True))
        m.add_command(label="展开 / 收起", command=self._toggle)
        m.add_separator()
        m.add_checkbutton(label="窗口置顶", onvalue=True, offvalue=False,
                          variable=self.var_topmost, command=self._flip_topmost)
        m.add_command(label="切换浅色 / 深色", command=self._switch_theme)
        m.add_separator()
        m.add_command(label="退出", command=self._quit)
        m.tk_popup(event.x_root, event.y_root)

    def _flip_topmost(self):
        self.topmost = not self.topmost
        self.var_topmost.set(self.topmost)
        self.root.attributes("-topmost", self.topmost)

    def _bind_drag(self, wdg):
        for seq, fn in (("<Button-1>", self._press), ("<B1-Motion>", self._motion),
                        ("<ButtonRelease-1>", self._release)):
            wdg.bind(seq, fn, add="+")

    def _press(self, event):
        self._drag = {"x": event.x, "y": event.y, "moved": False,
                      "wx": self.root.winfo_x(), "wy": self.root.winfo_y()}

    def _motion(self, event):
        if not self._drag:
            return
        dx = event.x - self._drag["x"]
        dy = event.y - self._drag["y"]
        if abs(dx) + abs(dy) > 4:
            self._drag["moved"] = True
        if self._drag["moved"]:
            self.root.geometry(f"+{self._drag['wx'] + dx}+{self._drag['wy'] + dy}")

    def _release(self, event):
        if self._drag and not self._drag["moved"]:
            self._toggle()  # 点击（未拖动）切换展开；↻/✕/▾ 按钮有自己的点击处理
        elif self._drag:
            self._save_config()
        self._drag = None

    # ---------- 配置持久化 ----------

    def _config_file(self) -> str:
        return os.path.join(self.client.config_dir, "widget_config.json")

    def _load_config(self) -> dict:
        for path in (self._config_file(),
                     os.path.join(self.client.config_dir, "widget_pos.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
        return {}

    def _place_initial(self, cfg: dict):
        x, y = cfg.get("x"), cfg.get("y")
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            x = y = None
        if x is None or not (0 <= x < self.root.winfo_screenwidth() - 100):
            x = self.root.winfo_screenwidth() - self.W - 48
            y = 110
        self.root.geometry(f"+{x}+{y}")

    def _save_config(self):
        try:
            with open(self._config_file(), "w", encoding="utf-8") as f:
                json.dump({"x": self.root.winfo_x(), "y": self.root.winfo_y(),
                           "theme": self.theme_name, "topmost": self.topmost}, f)
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def main(config_dir: str | None = None) -> None:
    """入口：python -m xuexitong_mcp.widget / xuexitong-assistant 命令。"""
    try:  # Windows 高分屏文字发虚的通用解法
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    from .client import ChaoxingClient
    Widget(ChaoxingClient(config_dir=config_dir)).run()


if __name__ == "__main__":
    main()
