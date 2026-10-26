# -*- coding: utf-8 -*-
"""xuexitong-cli（短命令 xxt）—— 学习通命令行，只读。

定位：像 bili-cli 之于 B 站——在终端里查课表 / 作业截止 / 考试 / 通知 /
任务点 / 资料下载，不打开浏览器。协议层复用 xuexitong_mcp.client，
凭据走同一个 config.json；本学期范围默认复用桌面助手 store.json 的
课表缓存（没有就现场全学期拉取）。

纪律：只读查询 + 资料下载；不做签到/刷课/答题/提交（红线）。

用法示例：
  xxt today                     # 今天有什么课
  xxt week 12                   # 第 12 周课表
  xxt hw                        # 待交作业截止看板（本学期）
  xxt exam / notice / progress  # 考试 / 通知 / 任务点
  xxt materials 数字信号处理 --find 实验
  xxt download 数字信号处理 --find 实验 --dir D:\\dst
  xxt ics -o 课表.ics
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
    """全学期课表：优先缓存，否则现场拉（冷启动 20+ 请求，十几秒）。"""
    return _cached_schedule() or cli.fetch_schedule_full()


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
    print(_row(["姓名", p.get("name", "?")], [8, 40]))
    print(_row(["学校", p.get("school", "?")], [8, 40]))
    print(_row(["uid", p.get("uid", "?")], [8, 40]))
    return 0


def cmd_courses(a) -> int:
    cli = _client()
    _login_or_die(cli)
    names = _active_names(_term_schedule(cli))
    rows = cli.fetch_courses()
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
    cached = sc is not None
    if not cached:   # 缓存缺失/过期才走网络（回退路径）
        cli = _client()
        _login_or_die(cli)
        sc = cli.fetch_schedule()
    cur = sc.get("curriculum", {})
    from .client import ms_to_date, expand_weeks
    fw = cur.get("firstWeekDate")
    today = dt.date.today()
    if cached:
        # 全学期缓存：按今天日期推教学周（realCurrentWeek 是存盘时的值），
        # 再按 weeks 串筛出本周的课——全程零网络
        week = _current_week(sc, today)
    else:
        week = int(cur.get("realCurrentWeek") or cur.get("currentWeek") or 0)
    lessons = [l for l in sc.get("lessons", [])
               if not l.get("weeks") or week in expand_weeks(l["weeks"])]
    monday = ms_to_date(int(fw)) + dt.timedelta(days=(week - 1) * 7) if fw \
        else today - dt.timedelta(days=today.weekday())
    times = _lesson_times(sc)
    rows = [r for r in _day_rows(lessons, times, monday)
            if r[1].date() == today]
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
        print(_row([f"{s:%H:%M}-{e:%H:%M}", _clip(name, 28), loc, tea], widths), state)
    return 0


def cmd_week(a) -> int:
    cli = _client()
    _login_or_die(cli)
    sc = _term_schedule(cli)      # 缓存优先：任意周查询用全学期数据
    cur = sc.get("curriculum", {})
    from .client import ms_to_date
    week = a.week or int(cur.get("realCurrentWeek")
                         or cur.get("currentWeek") or 1)
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
              f"{_pad(loc, 16)}{tea}")
    return 0


def cmd_hw(a) -> int:
    cli = _client()
    _login_or_die(cli)
    names = _active_names(_term_schedule(cli)) if not a.all_courses else None
    rows = cli.fetch_deadline_overview(only_courses=names)
    if a.json:
        _print_json([
            {"course": r["course"], "title": r["title"], "status": r["status"],
             "deadline": _jdt(r.get("deadline_dt")) or r.get("deadline"),
             "url": r.get("url") or ""}
            for r in rows])
        return 0
    if not rows:
        print(_c("没有待交的作业 ✓", "green"))
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


def cmd_notice(a) -> int:
    cli = _client()
    _login_or_die(cli)
    if a.limit < 1:
        _stderr("--limit 至少为 1")
        return 1
    items = cli.fetch_notices(limit=a.limit, unread_only=a.unread)
    if a.json:
        _print_json([
            {"title": (it.get("title") or "").strip(),
             "sender": it.get("createrName") or it.get("sender") or "",
             "time": str(it.get("sendTime") or "")[:19],
             "unread": str(it.get("isread", "1")) == "0",
             "content": it.get("content") or ""}
            for it in items])
        return 0
    if not items:
        print(_c("没有通知", "green"))
        return 0
    for it in items:
        unread = str(it.get("isread", "1")) == "0"
        head = _c("●", "cyan") if unread else _c("·", "gray")
        title = (it.get("title") or "").strip()
        sender = it.get("createrName") or it.get("sender") or ""
        t = str(it.get("sendTime") or "")[:16]
        print(f"{head} {title}")
        print(_c(f"   {sender} · {t}", "dim"))
    return 0


def cmd_progress(a) -> int:
    cli = _client()
    _login_or_die(cli)
    names = _active_names(_term_schedule(cli)) if not a.all_courses else None
    rows = cli.fetch_progress_overview(only_courses=names)
    # 同课两班去重（保更完整一行）
    best: dict[str, dict] = {}
    for r in rows:
        old = best.get(r["course"])
        if old is None or ((r.get("done") or -1), (r.get("total") or -1)) > \
                ((old.get("done") or -1), (old.get("total") or -1)):
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
    # （CLI 零依赖承诺），且缓存命中时省 20+ 请求
    cli = _client()
    _login_or_die(cli)
    from .client import build_ics
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

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xxt", description="学习通命令行（只读）",
        epilog="凭据：与 MCP/桌面助手共用的 config.json"
               "（包安装目录旁）或 CHAOXING_PHONE/CHAOXING_PASSWORD 环境变量。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("whoami", help="我是谁（姓名/学校/uid）")
    s.set_defaults(fn=cmd_whoami)

    s = sub.add_parser("courses", help="课程列表（★=本学期）")
    s.set_defaults(fn=cmd_courses)

    s = sub.add_parser("today", help="今天的课")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_today)

    s = sub.add_parser("week", help="整周课表")
    s.add_argument("week", nargs="?", type=int, help="周数（缺省本周）")
    s.set_defaults(fn=cmd_week)

    s = sub.add_parser("hw", help="待交作业截止看板（本学期）")
    s.add_argument("--all-courses", action="store_true",
                   help="不过滤往年课（默认只看本学期）")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_hw)

    s = sub.add_parser("exam", help="考试安排（本学期）")
    s.add_argument("--all", action="store_true", help="显示全部（含往年）")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_exam)

    s = sub.add_parser("notice", help="通知中心")
    s.add_argument("--unread", action="store_true", help="只看未读")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_notice)

    s = sub.add_parser("progress", help="任务点进度（本学期）")
    s.add_argument("--all-courses", action="store_true", help="全部课")
    s.add_argument("--json", action="store_true", help="输出 JSON（脚本/agent 友好）")
    s.set_defaults(fn=cmd_progress)

    s = sub.add_parser("materials", help="课程资料区")
    s.add_argument("course", help="课名关键词")
    s.add_argument("--find", default="", help="递归搜索关键词")
    s.add_argument("--depth", type=int, default=3)
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
    s.set_defaults(fn=cmd_pan)

    s = sub.add_parser("ics", help="导出全学期课表 .ics")
    s.add_argument("-o", "--output", default="课表.ics")
    s.set_defaults(fn=cmd_ics)
    return p


def main(argv=None) -> int:
    _setup_console()
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print()
        return 130
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(_c(f"出错了：{e}", "red"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
