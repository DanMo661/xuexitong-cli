# -*- coding: utf-8 -*-
"""一周课程 → 终端课表网格（纯函数渲染，不打印、不联网、不依赖 cli）。

供 cli.py 的 `xxt week --grid` 接入：

    from xuexitong_mcp.weekgrid import render_week_grid
    text = render_week_grid(rows, week=9, monday=mon, today=today, color=_c)

rows 与 cli._day_rows 输出同构（已按天/时间排序）：
    [(dayOfWeek:int 1..7, start:datetime, end:datetime,
      name:str, location:str, teacher:str)]

color(text, *styles) -> str，styles ∈ {bold, dim, red, green, yellow,
cyan, gray}；传 None 时原样返回文本（纯文本渲染）。
"""

from datetime import datetime, timedelta

TERMINAL_WIDTH = 100   # 7 列课表在该终端宽度内自适应
MIN_COL_WIDTH = 10     # 日列最小显示宽度
TIME_COL_WIDTH = 5     # 左侧时间轨 "HH:MM"
COL_GAP = 2            # 列间两空格（不画竖线框，清爽风格）
DAY_COUNT = 7
MIN_RAIL_ROWS = 3      # 时间轨最少行数（垫太高会产生无内容的空行尾巴）
DAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _w(s):
    """显示宽度：全角 2 / 半角 1（中文表格对齐的根基）。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(s))


def _clip(s, width):
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


def _as_date(v):
    """date|datetime|None → date|None。"""
    if v is None:
        return None
    return v.date() if isinstance(v, datetime) else v


def render_week_grid(rows, week=None, monday=None, today=None, color=None):
    """渲染一周课表网格，返回多行字符串（不 print）。

    - 顶部 `第 N 教学周  MM/DD–MM/DD`：week/monday 任一为 None 就不画周头
    - 时间轨按课程 start.time() 对齐，同一轨行只放开始时刻相同的课；
      跨节次的课纵向合并，中间行画居中的续行符号 │
    - 同天同节次撞课时每门一行缩进显示
    - today 所在列：列头 cyan、课名 bold
    """
    paint = color if color is not None else (lambda text, *styles: text)
    items = [r for r in (rows or []) if 1 <= int(r[0]) <= DAY_COUNT]
    if not items:
        return "本周暂无课程安排"

    monday = _as_date(monday)
    today = _as_date(today)
    if monday is None:
        dow0, s0 = items[0][0], items[0][1]
        monday = s0.date() - timedelta(days=dow0 - 1)

    # ---- 时间轨：出现过的开始时刻去重排序，一个时刻一行（节次） ----
    rail = sorted({r[1].time() for r in items})
    n_rail = max(len(rail), MIN_RAIL_ROWS)

    # ---- 课程落格：覆盖轨行 first..last（start ≤ 轨时刻 < end） ----
    starts = {}   # (col, r) -> [(name, loc)] 开始时刻恰为 rail[r] 的课
    spans = {}    # (col, r) -> 跨到该行的课数（续行符号数）
    for dow, s, e, name, loc, _teacher in items:
        col, t0 = dow - 1, s.time()
        first = rail.index(t0)
        last = first
        while last + 1 < len(rail) and rail[last + 1] < e.time():
            last += 1
        starts.setdefault((col, first), []).append((str(name or "?"),
                                                    str(loc or "")))
        for r in range(first + 1, last + 1):
            spans[(col, r)] = spans.get((col, r), 0) + 1

    today_col = None
    if today is not None:
        for i in range(DAY_COUNT):
            if monday + timedelta(days=i) == today:
                today_col = i
                break

    def cell_lines(col, r):
        """该格逻辑行 [(text, styles, center)]，text 未截断。"""
        lines = [("│", (), True) for _ in range(spans.get((col, r), 0))]
        here = starts.get((col, r), [])
        for name, loc in here:
            bold = ("bold",) if col == today_col else ()
            if len(here) >= 2:   # 撞课：每门一行缩进
                lines.append((" " + name + (f"@{loc}" if loc else ""),
                              bold, False))
            else:
                lines.append((name, bold, False))
                if loc:
                    lines.append((loc, ("dim",), False))
        return lines

    # ---- 列宽自适应：内容最大宽度夹在 [10, 100 宽度内可容纳值] ----
    need = MIN_COL_WIDTH   # 表头 "周一 10/26" 恰为 10，被下限覆盖
    for col in range(DAY_COUNT):
        for r in range(n_rail):
            for text, _st, _c in cell_lines(col, r):
                need = max(need, _w(text))
    max_fit = (TERMINAL_WIDTH - TIME_COL_WIDTH - COL_GAP
               - (DAY_COUNT - 1) * COL_GAP) // DAY_COUNT
    colw = min(need, max_fit)

    def block(text, styles, width, align="left"):
        """截断 + 按显示宽度对齐补空格；着色只包住可见文本。"""
        t = _clip(text, width)
        if align == "right":
            left = max(0, width - _w(t))
        elif align == "center":
            left = max(0, (width - _w(t)) // 2)
        else:
            left = 0
        right = width - left - _w(t)
        return " " * left + paint(t, *styles) + " " * right

    out = []
    if week is not None and monday is not None:
        sunday = monday + timedelta(days=6)
        out.append(f"第 {week} 教学周  {monday:%m/%d}–{sunday:%m/%d}")

    cells = [block("时间", (), TIME_COL_WIDTH, "right")]
    for i in range(DAY_COUNT):
        day = monday + timedelta(days=i)
        cells.append(block(f"{DAY_NAMES[i]} {day:%m/%d}",
                           ("cyan",) if i == today_col else (), colw))
    out.append("  ".join(cells).rstrip())

    for r in range(n_rail):
        cols = [cell_lines(col, r) for col in range(DAY_COUNT)]
        for k in range(max(max(len(ls) for ls in cols), 1)):
            cells = [block(rail[r].strftime("%H:%M") if k == 0 and r < len(rail)
                           else "", (), TIME_COL_WIDTH, "right")]
            for col in range(DAY_COUNT):
                if k < len(cols[col]):
                    text, styles, center = cols[col][k]
                    cells.append(block(text, styles, colw,
                                       "center" if center else "left"))
                else:
                    cells.append(" " * colw)
            out.append("  ".join(cells).rstrip())
    return "\n".join(out)
