# -*- coding: utf-8 -*-
"""学习通桌面悬浮窗（可选组件）。

风格参考市面高星悬浮窗工具（TrafficMonitor 等）：
置顶半透明深色圆角卡片，彩色状态点区分状态，可拖动、右键菜单、点击展开。

设计约束：
- 只用标准库 tkinter，零新增依赖；数据层直接复用 client.py（不经 MCP）。
- 渐进渲染：课表秒出；作业截止/通知在后台线程扫完后补上（全课程扫描
  需 1~3 分钟，进度以"扫描中"提示）。
- 对账号友好：自动刷新默认 30 分钟，只读查询，与 MCP 同一风控边界。

运行：python -m chaoxing_mcp.widget 或仓库根目录的 启动悬浮窗.bat
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

    板块顺序：课表（快，几秒）→ 作业截止（全课程逐课扫描，1~3 分钟）→
    通知。单板块失败只记 error 不拖垮整卡。
    """
    now = now or dt.datetime.now()
    snap = {"ok": True, "msg": "", "rows": [], "current": None, "next": None,
            "week": None, "deadlines": [], "deadline_total": 0, "overdue": 0,
            "notices": [], "errors": [], "scanning": False}

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
        snap["notices"] = [{"title": (it.get("title") or "").strip()[:38],
                            "time": (it.get("completeTime") or "")[5:16],
                            "unread": not it.get("isread")} for it in items]
    except Exception as e:  # noqa: BLE001
        snap["errors"].append("通知: " + _short(e))
    emit(True)
    return snap


# ---------------------------------------------------------------- UI

CARD = "#1E1F24"      # 卡片底色
TRANS = "#010203"     # 抠透明用的色键
FG = "#E8EAED"        # 主文字
SUB = "#9AA0A6"       # 次要文字
BLUE = "#8AB4F8"      # 下一节课
GREEN = "#81C995"     # 正在上课 / 正常
RED = "#F28B82"       # 已过期 / 出错
YELLOW = "#FDD663"    # 临近截止
SEP = "#33363D"       # 分隔线
BTN_HOVER = "#2E3038"
W = 316               # 卡片宽度


class Widget:
    AUTO_REFRESH_MS = 30 * 60 * 1000  # 自动刷新 30 分钟（对账号友好）
    CLOCK_TICK_MS = 30 * 1000         # 时刻文案每 30s 重排（倒计时自己会走）

    def __init__(self, client):
        import tkinter as tk
        self.tk = tk
        self.client = client
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.expanded = False
        self.topmost = True
        self.snap: dict | None = None
        self._drag = None

        root = tk.Tk()
        self.root = root
        self.var_topmost = tk.BooleanVar(value=True)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", TRANS)
        root.attributes("-alpha", 0.94)
        root.title("学习通悬浮窗")

        self.cv = tk.Canvas(root, width=W, height=100, bg=TRANS,
                            highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)

        # 卡片各层容器（画布上层窗口）
        self.header = tk.Frame(self.cv, bg=CARD)
        self.body = tk.Frame(self.cv, bg=CARD)
        self._hw = self.cv.create_window(14, 6, window=self.header, anchor="nw")
        self._bw = None

        self._build_header()
        self._bind_drag(self.header)
        self.cv.bind("<Button-1>", self._press)
        self.cv.bind("<B1-Motion>", self._motion)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Button-3>", self._menu)
        self.header.bind("<Button-3>", self._menu)

        self._place_initial()
        self._render_text_only()  # 先画空卡，数据到了再填
        self.refresh(manual=True)

        root.after(200, self._poll_queue)
        root.after(self.CLOCK_TICK_MS, self._tick)
        root.after(self.AUTO_REFRESH_MS, self._auto)

    # ---------- 布局 ----------

    def _build_header(self):
        tk = self.tk
        for wdg in self.header.winfo_children():
            wdg.destroy()
        self.dot = tk.Label(self.header, text="●", bg=CARD, fg=SUB,
                            font=("Segoe UI", 9))
        self.dot.pack(side="left", padx=(0, 6))
        title = tk.Label(self.header, text="学习通", bg=CARD, fg=FG,
                         font=("Microsoft YaHei UI", 10, "bold"))
        title.pack(side="left")
        self._bind_drag(title)

        def btn(text, cmd):
            b = tk.Label(self.header, text=text, bg=CARD, fg=SUB, width=2,
                         font=("Segoe UI", 10), cursor="hand2")
            b.bind("<Enter>", lambda e: b.config(fg=FG, bg=BTN_HOVER))
            b.bind("<Leave>", lambda e: b.config(fg=SUB, bg=CARD))
            b.bind("<Button-1>", lambda e: cmd())
            return b

        self.b_refresh = btn("↻", lambda: self.refresh(manual=True))
        self.b_refresh.pack(side="right", padx=(2, 0))
        self.b_close = btn("✕", self._quit)
        self.b_close.pack(side="right")
        self.b_toggle = btn("▾", self._toggle)
        self.b_toggle.pack(side="right")

    def _body_rows(self) -> list[tuple]:
        """根据当前 snap 生成正文行：(颜色, 加粗, 文本, 小号?)。"""
        tk_rows: list[tuple] = []
        snap = self.snap
        now = dt.datetime.now()
        if not snap:
            return [(SUB, False, "正在连接学习通…", False)]
        if not snap["ok"]:
            return [(RED, False, snap["msg"], False)]
        # 下一节课 / 正在上
        cur, nxt = snap["current"], snap["next"]
        if cur:
            tk_rows.append((GREEN, True,
                            f"正在上课 {cur['start']:%H:%M}-{cur['end']:%H:%M}  {cur['name']}", False))
            tk_rows.append((SUB, False, f"{cur['location']}  ·  {(cur['end'] - now).seconds // 60} 分钟后下课", True))
        elif nxt:
            cd = fmt_countdown(nxt["start"] - now)
            tk_rows.append((BLUE, True,
                            f"下一节 {nxt['start']:%H:%M}  {nxt['name']}", False))
            tk_rows.append((SUB, False, f"{nxt['location']}  ·  {cd}后上课", True))
        elif snap["rows"]:
            tk_rows.append((GREEN, False, "今天课程已结束 ✓", False))
        else:
            tk_rows.append((SUB, False, "今天无课 ✓", False))
        # 作业
        total, over = snap["deadline_total"], snap["overdue"]
        if snap["scanning"]:
            tk_rows.append((SUB, False, "⏳ 待交作业扫描中…", False))
        elif total:
            mark = YELLOW if over else GREEN
            tk_rows.append((mark, False, f"⏰ 待交作业 {total} 项" + (f"（{over} 项已过期！）" if over else ""), False))
            for r in snap["deadlines"]:
                d = r["deadline_dt"]
                when = fmt_countdown(d - now) if d else "截止未知"
                mark2 = RED if (d and d < now) else (YELLOW if d and (d - now).days < 2 else SUB)
                tk_rows.append((mark2, False, f"· {r['title'][:16]}  {when}", True))
        else:
            tk_rows.append((GREEN, False, "⏰ 没有待交作业 ✓", False))
        if not self.expanded:
            return tk_rows[:COLLAPSED_LINES + 1]
        # ---- 展开区 ----
        tk_rows.append((SEP, False, "SEP", False))
        tk_rows.append((SUB, False, "今日课程", False))
        if snap["rows"]:
            for r in snap["rows"]:
                mark, color = "○", SUB
                if cur and r is cur:
                    mark, color = "●", GREEN
                elif r["start"] < now:
                    mark = "·"
                tk_rows.append((color, False,
                                f"{mark} {r['start']:%H:%M}-{r['end']:%H:%M}  {r['name'][:14]}  {r['location']}", False))
        else:
            tk_rows.append((SUB, False, "（无）", False))
        tk_rows.append((SEP, False, "SEP", False))
        tk_rows.append((SUB, False, "最新通知", False))
        for n in snap["notices"]:
            pre = "[未读] " if n["unread"] else ""
            tk_rows.append((BLUE if n["unread"] else SUB, False, f"· {pre}{n['title']}  {n['time']}", False))
        if not snap["notices"]:
            tk_rows.append((SUB, False, "（无）", False))
        for e in snap["errors"][:2]:
            tk_rows.append((RED, False, "! " + e, True))
        return tk_rows

    def _render_text_only(self):
        """按 _body_rows 重建正文并自适应卡片高度。"""
        tk = self.tk
        for wdg in self.body.winfo_children():
            wdg.destroy()
        rows = self._body_rows()
        for color, bold, text, small in rows:
            if text == "SEP":
                tk.Frame(self.body, bg=SEP, height=1).pack(fill="x", pady=(5, 3))
                continue
            lbl = tk.Label(self.body, text=text, bg=CARD, fg=color, anchor="w",
                           font=("Microsoft YaHei UI", 8 if small else 9, "bold" if bold else "normal"))
            lbl.pack(fill="x", pady=1)
            lbl.bind("<Button-1>", lambda e: self._toggle())
        self.root.update_idletasks()
        h = 6 + self.header.winfo_reqheight() + 6
        if rows:
            h += self.body.winfo_reqheight() + 8
        self._paint(h)
        self.root.geometry(f"{W}x{h}")

    def _paint(self, h: int):
        """重画圆角卡片底板。"""
        cv = self.cv
        cv.delete("card")
        r = 14
        cv.config(height=h)
        pts = [r, 0, W - r, 0, W, 0, W, r, W, h - r, W, h, W - r, h, r, h,
               0, h, 0, h - r, 0, r, 0, 0]
        cv.create_polygon(pts, smooth=True, fill=CARD, outline=CARD, tags="card")
        cv.tag_lower("card")
        cv.itemconfigure(self._hw, width=W - 76)
        if self._bw is not None:
            cv.delete(self._bw)
        if self.body.winfo_children():
            self._bw = cv.create_window(16, 6 + self.header.winfo_reqheight() + 4,
                                        window=self.body, anchor="nw",
                                        width=W - 32)
        else:
            self._bw = None

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
                self._render_text_only()
                self._status_color()
        except queue.Empty:
            pass
        self.root.after(300, self._poll_queue)

    def _tick(self):
        if self.snap and self.snap.get("ok"):
            self._render_text_only()
        self.root.after(self.CLOCK_TICK_MS, self._tick)

    def _status_color(self):
        snap = self.snap
        if not snap:
            return
        color = GREEN if snap["ok"] and not snap["errors"] else RED
        overdue = snap.get("overdue") or 0
        if snap["ok"] and overdue:
            color = YELLOW
        self.dot.config(fg=color)

    # ---------- 交互 ----------

    def _toggle(self):
        self.expanded = not self.expanded
        self.b_toggle.config(text="▴" if self.expanded else "▾")
        self._render_text_only()

    def _quit(self):
        self._save_pos()
        self.root.destroy()

    def _menu(self, event=None):
        tk = self.tk
        m = tk.Menu(self.root, tearoff=0, bg=CARD, fg=FG,
                    activebackground=BTN_HOVER, activeforeground=FG, bd=0)
        m.add_command(label="刷新数据", command=lambda: self.refresh(manual=True))
        m.add_command(label="展开/收起", command=self._toggle)
        m.add_checkbutton(label="窗口置顶", onvalue=True, offvalue=False,
                          variable=self.var_topmost,
                          command=self._flip_topmost)
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
            self._save_pos()
        self._drag = None

    # ---------- 位置记忆 ----------

    def _pos_file(self) -> str:
        return os.path.join(self.client.config_dir, "widget_pos.json")

    def _place_initial(self):
        x = y = None
        try:
            with open(self._pos_file(), encoding="utf-8") as f:
                pos = json.load(f)
            x, y = int(pos["x"]), int(pos["y"])
        except Exception:
            pass
        if x is None or not (0 <= x < self.root.winfo_screenwidth() - 100):
            x = self.root.winfo_screenwidth() - W - 48
            y = 110
        self.root.geometry(f"+{x}+{y}")

    def _save_pos(self):
        try:
            with open(self._pos_file(), "w", encoding="utf-8") as f:
                json.dump({"x": self.root.winfo_x(), "y": self.root.winfo_y()}, f)
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def main(config_dir: str | None = None) -> None:
    """入口：python -m chaoxing_mcp.widget / chaoxing-widget 命令。"""
    try:  # Windows 高分屏文字发虚的通用解法
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    from .client import ChaoxingClient
    Widget(ChaoxingClient(config_dir=config_dir)).run()


if __name__ == "__main__":
    main()
