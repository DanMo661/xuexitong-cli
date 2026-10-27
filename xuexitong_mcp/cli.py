# -*- coding: utf-8 -*-
"""xuexitong-cli（短命令 xxt）—— 学习通命令行，只读。

定位：像 bili-cli 之于 B 站——在终端里查课表 / 作业截止 / 考试 / 通知 /
任务点 / 资料下载，不打开浏览器。协议层复用 xuexitong_mcp.client，
凭据走同一个 config.json；本学期范围默认复用桌面助手 store.json 的
课表缓存（没有就现场全学期拉取）。

纪律：只读查询 + 资料下载；不做签到/刷课/答题/提交（红线）。

用法示例：
  xxt status                    # 本机状态（缓存/凭据，零网络；--probe 真探测登录）
  xxt today                     # 今天有什么课
  xxt next                      # 下一节课（含倒计时，跨天跨周找）
  xxt week 12 / week --grid     # 第 12 周课表 / 终端课表网格图
  xxt hw                        # 待交作业截止看板（本学期）
  xxt hw --course 数字信号        # 只看一门课的作业
  xxt hw-ls 数字信号 / hw-info 数字信号 1  # 单门课作业列表 / 单份作业详情
  xxt exam / notice / progress  # 考试 / 通知（--kw 关键词）/ 任务点
  xxt chapters 数字信号处理       # 章节任务点明细（哪章还没刷完）
  xxt materials 数字信号处理 --find 实验
  xxt download 数字信号处理 --find 实验 --dir D:\\dst
  xxt ics -o 课表.ics

行为约定：管道/重定向时查询命令自动切 --json（XXT_TABLE=1 强制表格）；
NO_COLOR/FORCE_COLOR 控制颜色；退出码 0 成功 / 1 一般错 / 2 未登录 /
3 触发 9010 反爬 / 130 Ctrl+C。
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------- 终端基础

_RESET = "\033[0m"
_CODES = {"red": "31", "green": "32", "yellow": "33",
          "blue": "34", "magenta": "35", "cyan": "36", "gray": "90",
          "bold": "1", "dim": "2"}


def _c(text, *styles):
    if not _COLOR:
        return str(text)
    return "".join(f"\033[{_CODES[s]}m" for s in styles) + str(text) + _RESET


def _w(s: str) -> int:
    """显示宽度（全角 2 / 半角 1）——中文表格对齐的根基。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(s))


def _clip(s: str, width: int) -> str:
    """按显示宽度截断加省略号，超长课名别把表格顶穿。"""
    s = str(s)
    if _w(s) <= width:
        return s
    out, used = [], 0
    for ch in s:
        cw = 2 if ord(ch) > 0x2E80 else 1
        if used + cw > width - 2:
            break
        out.append(ch)
        used += cw
    return "".join(out) + "…"


def _pad(s: str, width: int, right: bool = True) -> str:
    gap = max(0, width - _w(s))
    return s + " " * gap if right else " " * gap + s


def _row(cells, widths):
    return "  ".join(_pad(c, w) for c, w in zip(cells, widths)).rstrip()


_COLOR = sys.stdout.isatty()


def _setup_console() -> None:
    global _COLOR
    try:  # Windows 控制台开 ANSI；GBK 控制台换 UTF-8 输出防炸
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
            kernel32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # 颜色开关：NO_COLOR/FORCE_COLOR 标准环境变量（https://no-color.org）
    import os
    if os.environ.get("NO_COLOR"):
        _COLOR = False
    elif os.environ.get("FORCE_COLOR"):
        _COLOR = True


# ---------------------------------------------------------------- 公共数据

def _client():
    from .client import ChaoxingClient
    return ChaoxingClient()


def _login_or_die(cli) -> None:
    r = cli.ensure_login()
    if not r.ok:
        # 服务端文案带"请调用 login 工具"——那是 MCP 的话术，CLI 用户没有
        msg = str(r.msg).replace("（请调用 login 工具或检查 config.json）",
                                 "").replace("（）", "")
        print(_c(f"登录失败：{msg}".rstrip("：: ")), file=sys.stderr)
        print("凭据：config.json（phone/password）或环境变量 "
              "CHAOXING_PHONE / CHAOXING_PASSWORD（与 MCP/桌面助手共用）",
              file=sys.stderr)
        raise SystemExit(2)


def _cached_schedule(max_age_h: float | None = None,
                     path: Path | None = None) -> dict | None:
    """桌面助手的课表缓存（全学期 + 节次表 + 学期锚点），零网络。

    max_age_h 给定时要求 saved_at 距今不超龄（today 用 24h：过期回退网络，
    免得周一还拿周日的"当前周"）；不给则只要有 lessons 就算命中
    （week/ics 查任意周，旧一点的缓存也优于 20+ 请求的全量拉取）。
    path 供单测注入临时 store.json。
    """
    store = path or Path(__file__).resolve().parent.parent / "store.json"
    try:
        d = json.loads(store.read_text(encoding="utf-8"))
        sc = d.get("schedule_cache") or {}
        if not sc.get("lessons"):
            return None
    except Exception:
        return None
    if max_age_h is not None:
        try:
            saved = dt.datetime.fromisoformat(sc.get("saved_at"))
        except (TypeError, ValueError):
            return None
        if (dt.datetime.now() - saved).total_seconds() > max_age_h * 3600:
            return None
    return sc


def _term_schedule(cli) -> dict:
    """全学期课表：优先缓存，否则现场拉（冷启动 20+ 请求，十几秒）。

    冷拉结果回写 store.json 的 schedule_cache——CLI-only 用户（没装桌面
    助手）第二次起也是零网络；RMW 只动这一个键，失败静默（并发写竞态
    不值得为它炸命令）。
    """
    sc = _cached_schedule()
    if sc is not None:
        return sc
    sc = cli.fetch_schedule_full()
    try:
        store = Path(__file__).resolve().parent.parent / "store.json"
        d = json.loads(store.read_text(encoding="utf-8")) \
            if store.exists() else {}
        sc["saved_at"] = dt.datetime.now().isoformat(timespec="seconds")
        d["schedule_cache"] = sc
        tmp = store.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(store)
    except Exception:
        pass
    return sc


def _active_names(sc: dict) -> set[str]:
    # 空串是"任何课名都包含它"的通配符，必须剔除
    return {n for n in ((l.get("name") or "").strip()
                        for l in sc.get("lessons", [])) if n}


def _stderr(msg) -> None:
    print(_c(msg, "red"), file=sys.stderr)


def _term_start(sc: dict):
    from .client import ms_to_date
    fw = (sc.get("curriculum") or {}).get("firstWeekDate")
    return ms_to_date(int(fw)) if fw else None


def _current_week(sc: dict, today: dt.date) -> int:
    """由 firstWeekDate 推今天的教学周（缓存里的 realCurrentWeek 是存盘时
    的值，缓存越周会错；日期推导永远对），异常时回退服务端周数。"""
    from .client import ms_to_date
    fw = (sc.get("curriculum") or {}).get("firstWeekDate")
    if fw:
        w = (today - ms_to_date(int(fw))).days // 7 + 1
        maxw = int(sc.get("curriculum", {}).get("maxWeek") or 0)
        if w >= 1 and (not maxw or w <= maxw):
            return w
    cur = sc.get("curriculum", {})
    return int(cur.get("realCurrentWeek") or cur.get("currentWeek") or 0)


# ---------------------------------------------------------------- JSON 输出

def _jdt(d) -> str | None:
    """datetime → "YYYY-MM-DD HH:MM"（None 透传），--json 统一时间格式。"""
    return f"{d:%Y-%m-%d %H:%M}" if d else None


def _print_json(items) -> None:
    print(json.dumps(items, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 命令

def cmd_whoami(a) -> int:
    cli = _client()
    _login_or_die(cli)
    p = cli.fetch_profile()
    if a.json:
        _print_json({"name": p.get("name"), "school": p.get("school"),
                     "uid": p.get("uid")})
        return 0
    print(_row(["姓名", p.get("name", "?")], [8, 40]))
    print(_row(["学校", p.get("school", "?")], [8, 40]))
    print(_row(["uid", p.get("uid", "?")], [8, 40]))
    return 0


def cmd_status(a) -> int:
    """本机状态一览：默认零网络（缓存年龄/凭据配置/学期锚点）。"""
    root = Path(__file__).resolve().parent.parent
    sc = _cached_schedule()
    info: dict = {"root": str(root)}
    info["config"] = (root / "config.json").exists()
    ck = root / "session_cookies.json"
    info["cookies"] = ck.exists()
    if ck.exists():
        try:
            info["cookies_age_h"] = round(
                (dt.datetime.now() - dt.datetime.fromtimestamp(ck.stat().st_mtime)).total_seconds() / 3600, 1)
        except OSError:
            pass
    if sc:
        today = dt.date.today()
        info["schedule_cache"] = sc.get("saved_at")
        info["week"] = _current_week(sc, today)
        ts = _term_start(sc)
        info["term_start"] = f"{ts:%Y-%m-%d}" if ts else None
        info["lessons"] = len(sc.get("lessons") or [])
    if a.probe:
        cli = _client()
        r = cli.ensure_login()
        info["login_ok"] = bool(r.ok)
        if r.ok:
            p = cli.fetch_profile()
            info["name"] = p.get("name")
    if a.json:
        _print_json(info)
        return 0
    print(_c("xuexitong-cli 状态", "bold"))
    print(_row(["凭据 config.json", "已配置 ✓" if info["config"] else "缺失"], [18, 40]))
    ck_s = "无（首次登录会生成）"
    if info.get("cookies"):
        ck_s = f"存在（{info.get('cookies_age_h', '?')} 小时前保存）"
    print(_row(["会话 cookies", ck_s], [18, 40]))
    if sc:
        print(_row(["课表缓存", f"{info.get('lessons', 0)} 节课，存于 {info.get('schedule_cache')}"], [18, 40]))
        print(_row(["当前教学周", f"第 {info.get('week', '?')} 周（学期始 {info.get('term_start')}）"], [18, 40]))
    else:
        print(_row(["课表缓存", "无（跑一次 today/week 自动建立）"], [18, 40]))
    if "login_ok" in info:
        print(_row(["登录探测", "OK：" + str(info.get("name")) if info["login_ok"] else "失败"], [18, 40]))
    else:
        print(_c("  （--probe 可真探测登录态，默认零网络）", "dim"))
    return 0


def cmd_courses(a) -> int:
    cli = _client()
    _login_or_die(cli)
    names = _active_names(_term_schedule(cli))
    rows = cli.fetch_courses()
    if a.json:
        _print_json([
            {"name": c["name"], "teacher": c.get("teacher") or "",
             "courseid": c["courseid"], "clazzid": c["clazzid"],
             "active": c["name"] in names}
            for c in rows])
        return 0
    print(_c(f"共 {len(rows)} 门课（★=本学期课表内）", "dim"))
    has_teacher = any(c.get("teacher") for c in rows)
    for c in rows:
        star = c["name"] in names
        tag = _c("★", "green") if star else " "
        line = f"{tag} {_pad(_clip(c['name'], 32), 34)}"
        if has_teacher:
            line += _pad(c.get("teacher") or "", 16)
        line += _c(f"{c['courseid']}/{c['clazzid']}", "dim")
        print(line)
    return 0


def _lesson_times(sc: dict):
    from .client import parse_section_times
    return parse_section_times(
        (sc.get("curriculum") or {}).get("lessonTimeConfigArray"))


def _day_rows(lessons, times, monday: dt.date):
    """一周课程 → [(dayIdx, 开始时刻, 结束, 课名, 地点, 老师)]。"""
    out = []
    for l in lessons:
        dow = int(l.get("dayOfWeek") or 1)
        begin = int(l.get("beginNumber") or 1)
        length = int(l.get("length") or 1)
        if not 1 <= dow <= 7 or begin < 1 or begin > len(times):
            continue
        day = monday + dt.timedelta(days=dow - 1)
        s = dt.datetime.combine(day, times[begin - 1][0])
        e = dt.datetime.combine(
            day, times[min(begin + length - 2, len(times) - 1)][1])
        out.append((dow, s, e, l.get("name") or "?",
                    l.get("location") or "", l.get("teacherName") or ""))
    out.sort(key=lambda r: (r[0], r[1]))
    return out


def cmd_today(a) -> int:
    sc = _cached_schedule(max_age_h=24)
    if sc is None:   # 缓存缺失/过期才走网络（回退路径）
        cli = _client()
        _login_or_die(cli)
        sc = cli.fetch_schedule()
    today = dt.date.today()
    # 全学期缓存按日期推教学周（realCurrentWeek 是存盘时的值会过期）；
    # 单周回退格式在 _current_week 内部回退到服务端周数
    week = _current_week(sc, today)
    rows = _today_rows(sc)
    if a.json:
        now = dt.datetime.now()
        _print_json([
            {"start": _jdt(s), "end": _jdt(e), "name": name,
             "location": loc, "teacher": tea,
             "state": "进行中" if s <= now <= e else ("已结束" if e < now else "未开始")}
            for _, s, e, name, loc, tea in rows])
        return 0
    wd = "一二三四五六日"[today.weekday()]
    print(_c(f"{today:%Y-%m-%d} 周{wd}", "bold"),
          _c(f"第 {week} 教学周", "cyan"))
    if not rows:
        print(_c("今天没有课 ✓", "green"))
        return 0
    widths = [11, 30, 18, 10]
    now = dt.datetime.now()
    for _, s, e, name, loc, tea in rows:
        state = _c("进行中", "green") if s <= now <= e else (
            _c("已结束", "gray") if e < now else "")
        print(_row([f"{s:%H:%M}-{e:%H:%M}", _clip(name, 28),
                    _clip(loc, 16), _clip(tea, 10)], widths), state)
    return 0


def _today_rows(sc: dict):
    """今天的课行（_day_rows 同构），供 today/next 复用。"""
    from .client import ms_to_date, expand_weeks
    cur = sc.get("curriculum", {})
    today = dt.date.today()
    week = _current_week(sc, today)
    lessons = [l for l in sc.get("lessons", [])
               if not l.get("weeks") or week in expand_weeks(l["weeks"])]
    fw = cur.get("firstWeekDate")
    monday = ms_to_date(int(fw)) + dt.timedelta(days=(week - 1) * 7) if fw \
        else today - dt.timedelta(days=today.weekday())
    times = _lesson_times(sc)
    return [r for r in _day_rows(lessons, times, monday)
            if r[1].date() == today]


def _fmt_countdown(minutes: int) -> str:
    """分钟数 → 人话倒计时（89→"1 小时 29 分"）。"""
    if minutes < 60:
        return f"{minutes} 分钟"
    if minutes < 1440:
        h, m = divmod(minutes, 60)
        return f"{h} 小时 {m} 分" if m else f"{h} 小时"
    d, m = divmod(minutes, 1440)
    h = m // 60
    return f"{d} 天 {h} 小时" if h else f"{d} 天"


def _next_lesson(sc: dict, now: dt.datetime, horizon_days: int = 14):
    """从现在起 14 天内的下一节课（跨天跨周；全学期缓存零网络）。

    返回 (days_ahead, start, end, name, location, teacher) 或 None。
    """
    from .client import ms_to_date, expand_weeks
    cur = sc.get("curriculum", {})
    today = now.date()
    base_week = _current_week(sc, today)
    if base_week < 1:
        return None
    fw = cur.get("firstWeekDate")
    times = _lesson_times(sc)
    for off in range(0, horizon_days + 1):
        day = today + dt.timedelta(days=off)
        week = base_week + (off + today.weekday()) // 7
        monday = ms_to_date(int(fw)) + dt.timedelta(days=(week - 1) * 7) \
            if fw else day - dt.timedelta(days=day.weekday())
        lessons = [l for l in sc.get("lessons", [])
                   if not l.get("weeks") or week in expand_weeks(l["weeks"])]
        rows = [r for r in _day_rows(lessons, times, monday)
                if r[1].date() == day and r[1] > now]
        if rows:
            _, s, e, name, loc, tea = rows[0]
            return off, s, e, name, loc, tea
    return None


def cmd_next(a) -> int:
    sc = _cached_schedule(max_age_h=24)
    if sc is None:
        cli = _client()
        _login_or_die(cli)
        sc = cli.fetch_schedule()   # 单周格式也能看今天/明天
    now = dt.datetime.now()
    hit = _next_lesson(sc, now)
    if a.json:
        if not hit:
            _print_json(None)
            return 0
        off, s, e, name, loc, tea = hit
        _print_json({"name": name, "start": _jdt(s), "end": _jdt(e),
                     "location": loc, "teacher": tea, "daysAhead": off,
                     "minutesLeft": int((s - now).total_seconds() // 60)})
        return 0
    if not hit:
        print(_c("未来两周没有课（假期/课表未排）✓", "green"))
        return 0
    off, s, e, name, loc, tea = hit
    when = "今天" if off == 0 else ("明天" if off == 1 else f"{off} 天后")
    wd = "一二三四五六日"[s.weekday()]
    line = (f"{_c(name, 'bold')}  {s:%H:%M}-{e:%H:%M}"
            f"（{when} 周{wd} {s:%m/%d}）")
    tail = " · ".join(x for x in (loc, tea) if x)
    if tail:
        line += f" · {tail}"
    print(line)
    print("还有 " + _c(_fmt_countdown(
        int((s - now).total_seconds() // 60)), "cyan"))
    return 0


def cmd_week(a) -> int:
    # 缓存命中就不发登录探测（today/next 同款零网络路径）
    sc = _cached_schedule()
    if sc is None:
        cli = _client()
        _login_or_die(cli)
        sc = _term_schedule(cli)   # 冷拉并回写缓存
    cur = sc.get("curriculum", {})
    from .client import ms_to_date
    # 缺省周与 today/next 同哲学：日期推导，不吃存盘时的 realCurrentWeek 旧值
    week = a.week or _current_week(sc, dt.date.today()) or 1
    maxw = int(cur.get("maxWeek") or 0)
    if a.week is not None and a.week < 1:
        _stderr("周数从 1 开始")
        return 1
    if maxw and a.week is not None and a.week > maxw:
        _stderr(f"这个学期只有 {maxw} 周（当前第 {week} 周）")
        return 1
    fw = cur.get("firstWeekDate")
    monday = ms_to_date(int(fw)) + dt.timedelta(days=(week - 1) * 7) if fw \
        else dt.date.today() - dt.timedelta(days=dt.date.today().weekday())
    times = _lesson_times(sc)
    # 周课过滤：合并课表 lessons 带 weeks 串才过滤，单周格式原样用
    from .client import expand_weeks
    lessons = [l for l in sc.get("lessons", [])
               if not l.get("weeks") or week in expand_weeks(l["weeks"])]
    rows = _day_rows(lessons, times, monday)
    if a.json:
        _print_json([
            {"date": f"{s:%Y-%m-%d}", "start": f"{s:%H:%M}", "end": f"{e:%H:%M}",
             "name": name, "location": loc, "teacher": tea}
            for _, s, e, name, loc, tea in rows])
        return 0
    if a.grid:
        from .weekgrid import render_week_grid
        print(render_week_grid(rows, week=week, monday=monday,
                               today=dt.date.today(), color=_c))
        return 0
    print(_c(f"第 {week} 教学周", "bold"),
          _c(f"{monday:%m/%d} – {monday + dt.timedelta(days=6):%m/%d}", "cyan"))
    if not rows:
        print(_c("这一周没有课", "green"))
        return 0
    last_dow = 0
    for dow, s, e, name, loc, tea in rows:
        if dow != last_dow:
            day = monday + dt.timedelta(days=dow - 1)
            wd = "一二三四五六日"[dow - 1]
            mark = _c(" ·今天", "cyan") if day == dt.date.today() else ""
            print(_c(f"周{wd} {day:%m/%d}", "yellow"), mark)
            last_dow = dow
        print(f"  {s:%H:%M}-{e:%H:%M}  {_pad(_clip(name, 24), 24)}"
              f"{_pad(_clip(loc, 14), 14)}{tea}")
    return 0


def cmd_hw(a) -> int:
    cli = _client()
    _login_or_die(cli)
    names = _active_names(_term_schedule(cli)) if not a.all_courses else None
    if a.course and names is not None:
        # --course 下推到 only_courses：只扫匹配的课，别为看一门课付全学期
        # 的逐课作业请求（数字信号 → 含它的课名集合，复用双向包含的语义
        # 就交给客户端 only_courses 的包含匹配）
        kw = a.course.casefold()
        names = {n for n in names if kw in n.casefold()} or None
        if names is None:
            _stderr(f"本学期课表里没有包含「{a.course}」的课"
                    f"（--all-courses 可看全部课）")
            return 1
    rows = cli.fetch_deadline_overview(only_courses=names)
    if a.course:
        kw = a.course.casefold()
        rows = [r for r in rows if kw in str(r["course"]).casefold()]
    if a.json:
        _print_json([
            {"course": r["course"], "title": r["title"], "status": r["status"],
             "deadline": _jdt(r.get("deadline_dt")) or r.get("deadline"),
             "url": r.get("url") or ""}
            for r in rows])
        return 0
    if not rows:
        what = f"「{a.course}」" if a.course else ""
        print(_c(f"没有待交的作业 {what}✓", "green"))
        return 0
    now = dt.datetime.now()
    widths = [16, 12, 22, 40]
    print(_row(["截止", "剩余", "课程", "作业"], widths))
    for r in rows:
        d = r.get("deadline_dt")
        if d is None:
            dl, left = "未知", _c("—", "gray")
        else:
            dl = f"{d:%m-%d %H:%M}"
            delta = (d - now).total_seconds()
            if delta < 0:
                left = _c("已过期", "red")
            elif delta < 86400:
                left = _c(f"{int(delta // 3600)} 小时", "red")
            elif delta < 3 * 86400:
                left = _c(f"{int(delta // 86400)} 天", "yellow")
            else:
                left = f"{int(delta // 86400)} 天"
        print(_row([dl, left, _clip(r["course"], 22), _clip(r["title"], 40)], widths))
    return 0


def _hw_status_style(status: str) -> tuple[str, str]:
    """作业状态 → (显示文本, 颜色)：空=未知(灰)；已交(已完成/待批阅)=绿；
    未交=黄；已截止(未交)=红。"""
    from .client import is_homework_pending
    s = (status or "").strip()
    if not s:
        return "未知", "gray"
    if not is_homework_pending(s):
        return s, "green"
    return (s, "red") if "已截止" in s else (s, "yellow")


def _hw_ls_lines(data: dict) -> list[str]:
    """作业列表数据 → 表格行（表头 + 每份一行：序号/作业/状态）。纯渲染零网络。"""
    widths = [4, 36, 10]
    lines = [_row(["序号", "作业", "状态"], widths)]
    for it in data.get("items") or []:
        st, color = _hw_status_style(it.get("status"))
        lines.append((_pad(str(it.get("index") or "?"), widths[0])
                      + "  " + _pad(_clip(it.get("title") or "?", widths[1]),
                                    widths[1])
                      + "  " + _c(_pad(st, widths[2]), color)).rstrip())
    return lines


def cmd_hw_ls(a) -> int:
    cli = _client()
    _login_or_die(cli)
    c = cli.find_course(a.course)
    if not c:
        _stderr(f"未找到包含「{a.course}」的课程")
        return 1
    data = cli.fetch_homework(c)
    items = data.get("items") or []
    if a.json:
        prog = data.get("progress")
        _print_json({
            "course": c["name"],
            "progress": {"done": prog[0], "total": prog[1]} if prog else None,
            "items": [{"index": it["index"], "title": it["title"],
                       "status": it["status"] or "", "url": it["url"] or ""}
                      for it in items]})
        return 0
    head = f"作业 {len(items)} 份"
    if data.get("progress"):
        head += f"（进度 {data['progress'][0]}/{data['progress'][1]}）"
    print(_c(c["name"], "bold"), _c(head, "cyan"))
    if not items:
        print(_c("（没有作业）", "dim"))
        return 0
    for line in _hw_ls_lines(data):
        print(line)
    print(_c("\n详情：xxt hw-info 课程名 序号", "dim"))
    return 0


def _hw_info_lines(d: dict) -> list[str]:
    """作业详情 dict → 键值展示行（缺字段 → "—"；时间单边不拼"至"）。纯渲染零网络。"""
    def v(key):
        s = d.get(key)
        return str(s) if s not in (None, "") else "—"
    st, color = _hw_status_style(d.get("status"))
    start, end = d.get("start_time"), d.get("deadline")
    span = f"{start} 至 {end}" if start and end else (start or end or "—")
    rows = [
        ("作业", _clip(v("title"), 56)),
        ("状态", _c(st, color)),
        ("题量", v("question_count")),
        ("满分", v("full_score")),
        ("作答时间", span),
        ("得分", v("score")),
    ]
    return [_row([k, val], [10, 44]) for k, val in rows]


def cmd_hw_info(a) -> int:
    cli = _client()
    _login_or_die(cli)
    if a.index < 1:
        _stderr("序号从 1 开始")
        return 1
    c = cli.find_course(a.course)
    if not c:
        _stderr(f"未找到包含「{a.course}」的课程")
        return 1
    try:
        d = cli.fetch_homework_detail(c, a.index)
    except IndexError as e:
        _stderr(str(e))
        return 1
    if a.json:
        _print_json({
            "course": c["name"], "index": d["index"], "status": d["status"],
            "title": d.get("title"), "questionCount": d.get("question_count"),
            "fullScore": d.get("full_score"), "startTime": d.get("start_time"),
            "deadline": d.get("deadline"), "score": d.get("score")})
        return 0
    print(_c(c["name"], "bold"), _c(f"第 {d['index']} 份作业", "cyan"))
    for line in _hw_info_lines(d):
        print(line)
    return 0


def cmd_exam(a) -> int:
    cli = _client()
    _login_or_die(cli)
    from .client import parse_exam_rows
    rows = parse_exam_rows(cli.fetch_exams())
    sc = _cached_schedule()
    start = _term_start(sc) if sc else None
    if start and not a.all:
        rows = [r for r in rows if r["start"].date() >= start]
    if a.json:
        _print_json([
            {"name": r["name"], "start": _jdt(r["start"]), "end": _jdt(r["end"]),
             "durationMin": r["durationMin"], "status": r["status"],
             "answer": r["answer"], "score": r["score"], "mode": r["mode"]}
            for r in rows])
        return 0
    if start and not a.all:
        print(_c(f"（只显示 {start:%Y-%m-%d} 开学后的考试；--all 看全部）",
                 "dim"))
    elif not start and not a.all:
        # 无课表缓存 → 学期过滤静默失效，明说（跑一次 today/week 会建缓存）
        print(_c("（无课表缓存，学期过滤未生效，往年考试也在内；"
                 "先跑一次 xxt today 建缓存）", "dim"))
    if not rows:
        print(_c("没有考试安排", "green"))
        return 0
    widths = [22, 17, 8, 10]
    # --all 混排多个学年，时间列带两位年份才分得清往年今年
    tfmt = "%y-%m-%d %H:%M" if a.all else "%m-%d %H:%M"
    print(_row(["考试", "时间", "时长", "状态"], widths))
    for r in rows:
        print(_row([_clip(r["name"], 22), f"{r['start']:{tfmt}}",
                    f"{r['durationMin']}分",
                    _clip(r.get("status") or "?", 10)], widths))
    return 0


def _notice_time(it) -> str:
    """sendTime 三形态归一 → "YYYY-MM-DD HH:MM"：
    标准字符串 / 毫秒时间戳（int）/ 数字字符串（assistant 侧同款防御）。"""
    v = it.get("sendTime")
    s = str(v or "")
    if s.isdigit() and len(s) >= 13:
        try:
            return dt.datetime.fromtimestamp(int(s) / 1000).strftime(
                "%Y-%m-%d %H:%M")
        except (OverflowError, OSError, ValueError):
            return s
    return s[:16]


def cmd_notice(a) -> int:
    cli = _client()
    _login_or_die(cli)
    if a.limit < 1:
        _stderr("--limit 至少为 1")
        return 1
    items = cli.fetch_notices(limit=a.limit, unread_only=a.unread,
                              keyword=a.kw or "")
    if a.json:
        _print_json([
            {"title": (it.get("title") or "").strip(),
             "sender": it.get("createrName") or it.get("sender") or "",
             "time": _notice_time(it),
             "unread": str(it.get("isread", "1")) == "0",
             "content": it.get("content") or ""}
            for it in items])
        return 0
    if not items:
        what = f"含「{a.kw}」的" if a.kw else ""
        print(_c(f"没有{what}通知", "green"))
        return 0
    for it in items:
        unread = str(it.get("isread", "1")) == "0"
        head = _c("●", "cyan") if unread else _c("·", "gray")
        title = (it.get("title") or "").strip()
        sender = it.get("createrName") or it.get("sender") or ""
        print(f"{head} {title}")
        print(_c(f"   {sender} · {_notice_time(it)}", "dim"))
        if a.full:
            body = (it.get("content") or "").strip()
            if body:
                # 源正文常有成片空行（网页排版残留），压成单空行
                out, prev_blank = [], False
                for ln in body.splitlines():
                    blank = not ln.strip()
                    if blank and prev_blank:
                        continue
                    out.append(ln)
                    prev_blank = blank
                for ln in out:
                    print(f"   {ln}".rstrip())
                print()
    return 0


def cmd_progress(a) -> int:
    cli = _client()
    _login_or_die(cli)
    names = _active_names(_term_schedule(cli)) if not a.all_courses else None
    rows = cli.fetch_progress_overview(only_courses=names)
    # 同课两班去重：total 优先（10/10 已完成的班不该压掉 3/20 还差 17 个的班，
    # 旧键序 done 优先会让这门课从待办看板整个消失）
    best: dict[str, dict] = {}
    for r in rows:
        old = best.get(r["course"])
        if old is None or ((r.get("total") or -1), (r.get("done") or -1)) > \
                ((old.get("total") or -1), (old.get("done") or -1)):
            best[r["course"]] = r
    todo = [(n, r) for n, r in best.items()
            if r.get("total") and r["total"] > (r.get("done") or 0)]
    todo.sort(key=lambda x: -(x[1]["total"] - (x[1]["done"] or 0)))
    if a.json:
        _print_json([
            {"course": name, "done": r.get("done") or 0, "total": r["total"],
             "left": r["total"] - (r.get("done") or 0)}
            for name, r in todo])
        return 0
    if not todo:
        print(_c("任务点全部完成 ✓", "green"))
        return 0
    for name, r in todo:
        done, total = r.get("done") or 0, r["total"]
        left = total - done
        n = 14
        filled = round(done * n / total)
        bar = _c("█" * filled, "green") + _c("░" * (n - filled), "gray")
        print(f"{_pad(_clip(name, 28), 30)} {bar} {done}/{total} "
              + _c(f"差 {left} 个", "yellow" if left < 5 else "red"))
    return 0


def cmd_materials(a) -> int:
    cli = _client()
    _login_or_die(cli)
    c = cli.find_course(a.course)
    if not c:
        _stderr(f"未找到包含「{a.course}」的课程")
        return 1
    items = cli.fetch_materials_recursive(
        c, a.find or "", max_depth=a.depth) if a.find else \
        cli.fetch_materials(c)
    if a.json:
        _print_json(items)
        return 0
    if not items:
        print(_c("（空）", "dim"))
        return 0
    for it in items:
        kind = it.get("type", "")
        idtag = _c(f"[{it.get('data_id')}]", "dim")
        icon = _c("📁", "") if kind == "afolder" else "📄"
        print(f"{icon} {it.get('name')}  {idtag}")
    print(_c("\n下载：xxt download 课程名 --id 编号（或 --find 关键词）",
             "dim"))
    return 0


def cmd_chapters(a) -> int:
    """章节任务点明细——"这门课到底还剩哪几个视频没刷"。"""
    cli = _client()
    _login_or_die(cli)
    c = cli.find_course(a.course)
    if not c:
        _stderr(f"未找到包含「{a.course}」的课程")
        return 1
    data = cli.fetch_chapters(c)
    prog = data.get("progress")
    nodes = data.get("nodes") or []
    if a.json:
        _print_json({
            "course": c["name"],
            "progress": ({"done": prog[0], "total": prog[1]}
                         if prog else None),
            "nodes": [{"level": lvl, "text": t} for lvl, t in nodes],
        })
        return 0
    print(_c(c["name"], "bold"),
          _c(f"任务点 {prog[0]}/{prog[1]}" if prog else "（无总进度）", "cyan"))
    if prog:
        n = 16
        filled = round(prog[0] * n / max(prog[1], 1))
        bar = _c("█" * filled, "green") + _c("░" * (n - filled), "gray")
        left = prog[1] - prog[0]
        tail = _c(f" 差 {left} 个", "red") if left else _c(" 全部完成 ✓", "green")
        print(f"{bar}{tail}")
    # --todo 只看没完成的：跳过"已完成"小节；一级章没小节待办时也不必出
    todo_only = a.todo
    shown = 0
    for lvl, text in nodes:
        pending = "待完成" in text
        if todo_only:
            if lvl == 0:
                continue          # 汇总行不含状态，todo 模式只出待办小节
            if not pending:
                continue
        if lvl == 0:
            print(_c(text, "yellow"))
        elif pending:
            print(_c(text, "red"))
        elif "已完成" in text:
            if not todo_only:
                print(_c(text, "dim"))
        else:
            if not todo_only:
                print(text)
        shown += 1
    if not shown:
        done_all = bool(prog) and prog[0] >= prog[1]
        print(_c("没有待完成的任务点 ✓" if done_all else "（没有章节内容）",
                 "green" if done_all else "dim"))
    elif todo_only:
        n_left = sum(1 for lvl, t in nodes if lvl == 1 and "待完成" in t)
        print(_c(f"\n共 {n_left} 个小节有待完成任务点", "dim"))
    return 0


def _try_download(cli, c: dict, data_id: int, save: str, name: str,
                  code: str = ""):
    """下载；9010 反爬拦截时按需引导人工验证码（不自动识码）。"""
    try:
        return cli.download_material(c, data_id, save, name)
    except RuntimeError as e:
        if "9010" not in str(e):
            raise
    # 反爬拦截：验证码必须人工识读（程序不自动 OCR，那是反爬要防的滥用）
    cap = str(Path.home() / ".xxt_captcha.png")
    if code:
        # --code 是针对上一次存的图提交（取图会换新图作废旧码，别再取）
        pass
    else:
        if not cli.fetch_antispider_captcha(cap):
            _stderr("取反爬验证码图片失败，稍后再试")
            return None
        try:
            if sys.stdin.isatty():
                print(_c(f"触发学习通反爬拦截，验证码已存 {cap}（打开看图）",
                         "yellow"))
                for _ in range(3):
                    code = input("输入图中 4 位验证码（回车放弃）: ").strip()
                    if not code:
                        return None
                    if len(code) == 4:
                        break
                if len(code) != 4:
                    return None
        except EOFError:
            code = ""
        if not code:
            _stderr(f"触发学习通反爬拦截（9010）。验证码图片已存：{cap}\n"
                    f"打开图片识读后重跑，加 --code 四位码 参数提交")
            return None
    if not cli.submit_antispider_captcha(code):
        cli.fetch_antispider_captcha(cap)   # 换一张新图供下次尝试
        _stderr(f"验证码不对或已跨会话失效（验证码与取图会话绑定）。"
                f"最稳路径：在本机终端直接跑 xxt download（交互输入验证码）。"
                f"已换新图：{cap}")
        return None
    return cli.download_material(c, data_id, save, name)


def cmd_download(a) -> int:
    cli = _client()
    _login_or_die(cli)
    c = cli.find_course(a.course)
    if not c:
        _stderr(f"未找到包含「{a.course}」的课程")
        return 1
    if not a.id and not a.find:
        _stderr("要 --id 编号或 --find 关键词（先 xxt materials 看看）")
        return 1
    hit = None
    # --id 时先查顶层（1 个请求就够），没有再递归下钻——一律 DFS 会为
    # 顶层文件白付整棵资料树的请求，还受 50 条命中封顶牵连
    if a.id:
        for it in cli.fetch_materials(c):
            if it.get("data_id") == a.id:
                hit = it
                break
    if hit is None:
        items = cli.fetch_materials_recursive(c, a.find or "", max_depth=4)
        for it in items:
            if (a.id and it.get("data_id") == a.id) or \
               (not a.id and a.find and a.find in it.get("name", "")):
                hit = it
                break
    if not hit:
        _stderr("没找到匹配的文件（先 xxt materials 看看）")
        return 1
    save = str(Path(a.dir).resolve())
    out = _try_download(cli, c, hit["data_id"], save, hit["name"], a.code)
    if not out:
        return 1
    print(_c(f"已下载：{out['path']}（{out['size'] // 1024} KB）", "green"))
    return 0


def cmd_pan(a) -> int:
    cli = _client()
    _login_or_die(cli)
    d = cli.fetch_pan_files(a.folder)
    if a.json:
        _print_json(d)
        return 0
    rows = d.get("items") if isinstance(d, dict) else d
    where = d.get("where", "?") if isinstance(d, dict) else "?"
    print(_c(f"{where}（{len(rows or [])} 项）", "dim"))
    for f in rows or []:
        kind = f.get("kind") or f.get("type") or ""
        size = f"  {_pad(f.get('size') or '-', 8)}" if kind != "folder" else ""
        print(f"{'📁' if kind == 'folder' else '📄'} "
              f"{f.get('name') or f.get('title')}{size}  "
              + _c(f"[{f.get('id', '')}]", "dim"))
    if any((f.get("kind") == "folder" for f in rows or [])):
        print(_c("下钻：xxt pan 文件夹id", "dim"))
    return 0


def cmd_ics(a) -> int:
    # 直接用 client.build_ics + 课表缓存：import server 会连带 FastMCP
    # （CLI 零依赖承诺），且缓存命中时省 20+ 请求（含登录探测）
    from .client import build_ics
    sc = _cached_schedule()
    if sc is None:
        cli = _client()
        _login_or_die(cli)
        sc = _term_schedule(cli)
    ics = build_ics(sc.get("lessons", []), sc.get("curriculum", {}),
                    cal_name=f"课表-{sc.get('curriculum', {}).get('schoolYear', '')}")
    path = Path(a.output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ics, encoding="utf-8", newline="")
    print(_c(f"已导出：{path}（{ics.count('BEGIN:VEVENT')} 节课，"
             f"含 30 分钟前提醒）", "green"))
    return 0


# ---------------------------------------------------------------- 装配

def _cli_version() -> str:
    try:
        from importlib.metadata import version
        return version("xuexitong-cli")
    except Exception:
        return "2.0.0"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xxt", description="学习通命令行（只读）",
        epilog="凭据：与 MCP/桌面助手共用的 config.json"
               "（包安装目录旁）或 CHAOXING_PHONE/CHAOXING_PASSWORD 环境变量。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version",
                   version=f"xuexitong-cli {_cli_version()}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("whoami", help="我是谁（姓名/学校/uid）")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_whoami)

    s = sub.add_parser("status", help="本机状态（缓存/登录凭据，默认零网络）")
    s.add_argument("--probe", action="store_true",
                   help="真探测一次登录态（1~2 个请求）")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("courses", help="课程列表（★=本学期）")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_courses)

    s = sub.add_parser("today", help="今天的课")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_today)

    s = sub.add_parser("next", help="下一节课（含倒计时，最多看 14 天）")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_next)

    s = sub.add_parser("week", help="整周课表")
    s.add_argument("week", nargs="?", type=int, help="周数（缺省本周）")
    s.add_argument("--grid", action="store_true", help="终端课表网格图")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_week)

    s = sub.add_parser("hw", help="待交作业截止看板（本学期）")
    s.add_argument("--all-courses", action="store_true",
                   help="不过滤往年课（默认只看本学期）")
    s.add_argument("--course", default="",
                   help="只看课名包含关键词的作业")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_hw)

    s = sub.add_parser("hw-ls", help="单门课的作业列表")
    s.add_argument("course", help="课名关键词")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_hw_ls)

    s = sub.add_parser("hw-info", help="单份作业详情（题量/满分/时间/得分）")
    s.add_argument("course", help="课名关键词")
    s.add_argument("index", type=int, help="作业序号（hw-ls 输出里的序号）")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_hw_info)

    s = sub.add_parser("exam", help="考试安排（本学期）")
    s.add_argument("--all", action="store_true", help="显示全部（含往年）")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_exam)

    s = sub.add_parser("notice", help="通知中心")
    s.add_argument("--unread", action="store_true", help="只看未读")
    s.add_argument("--full", action="store_true", help="显示通知正文")
    s.add_argument("--kw", default="", help="按关键词过滤（标题+正文）")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_notice)

    s = sub.add_parser("progress", help="任务点进度（本学期）")
    s.add_argument("--all-courses", action="store_true", help="全部课")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_progress)

    s = sub.add_parser("chapters", help="章节任务点明细（哪章还没刷完）")
    s.add_argument("course", help="课名关键词")
    s.add_argument("--todo", action="store_true",
                   help="只看有待任务点的小节")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_chapters)

    s = sub.add_parser("materials", help="课程资料区")
    s.add_argument("course", help="课名关键词")
    s.add_argument("--find", default="", help="递归搜索关键词")
    s.add_argument("--depth", type=int, default=3)
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_materials)

    s = sub.add_parser("download", help="下载资料（只读下载，不改数据）")
    s.add_argument("course", help="课名关键词")
    s.add_argument("--id", type=int, default=0, help="data_id（materials 输出里的编号）")
    s.add_argument("--find", default="", help="按文件名关键词取第一个匹配")
    s.add_argument("--dir", default=".", help="保存目录")
    s.add_argument("--code", default="", help="反爬验证码（触发 9010 拦截后人工识读传入）")
    s.set_defaults(fn=cmd_download)

    s = sub.add_parser("pan", help="个人云盘")
    s.add_argument("folder", nargs="?", default="", help="文件夹 id（留空根目录）")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_pan)

    s = sub.add_parser("ics", help="导出全学期课表 .ics")
    s.add_argument("-o", "--output", default="课表.ics")
    s.set_defaults(fn=cmd_ics)
    return p


def main(argv=None) -> int:
    _setup_console()
    args = build_parser().parse_args(argv)
    # 管道消费自动 JSON（对标 tamnd/bili-cli：非 TTY 默认机器格式）；
    # XXT_TABLE=1 可强制表格。带 --json 的命令才翻转。
    import os
    if (not sys.stdout.isatty() and hasattr(args, "json")
            and os.environ.get("XXT_TABLE") is None):
        args.json = True
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print()
        return 130
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(_c(f"出错了：{e}", "red"), file=sys.stderr)
        # 退出码语义：0 成功 / 1 一般错误 / 2 未登录 / 3 触发 9010 反爬
        # / 130 Ctrl+C——脚本和 agent 可精确分支
        return 3 if "9010" in str(e) else 1


if __name__ == "__main__":
    raise SystemExit(main())
