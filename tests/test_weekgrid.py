# -*- coding: utf-8 -*-
"""weekgrid 纯逻辑单元测试（xxt week --grid 的渲染层）。

零网络依赖，直接运行：  python tests/test_weekgrid.py
"""
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xuexitong_mcp.weekgrid import render_week_grid, _w  # noqa: E402

MON = date(2026, 10, 26)   # 第 9 周周一


def _r(dow, sh, sm, name, loc="", eh=None, em=None, teacher=""):
    """造一条与 cli._day_rows 同构的行。"""
    day = 26 + dow - 1
    s = datetime(2026, 10, day, sh, sm)
    e = datetime(2026, 10, day, sh if eh is None else eh,
                 sm if em is None else em)
    return (dow, s, e, name, loc, teacher)


def _mark(text, *styles):
    """测试用 color：把样式包成可断言的标记。"""
    return f"<{'+'.join(styles)}>{text}</>" if styles else text


def test_basic_render_exact():
    rows = [_r(2, 8, 0, "大学英语", "外语楼B201", 9, 40)]
    text = render_week_grid(rows, week=None, monday=MON, today=None,
                            color=None)
    lines = text.split("\n")
    assert lines[0] == (" 时间  周一 10/26  周二 10/27  周三 10/28"
                        "  周四 10/29  周五 10/30  周六 10/31  周日 11/01")
    assert lines[1] == "08:00" + " " * 14 + "大学英语"
    assert lines[2] == " " * 19 + "外语楼B201"
    # 时间轨最少 3 行（MIN_RAIL_ROWS=3）：剩余 2 行是空轨道行（nitpick：
    # 垫 5 行会出无内容空行尾巴）
    assert lines[3:] == ["", ""]
    assert all(ln == ln.rstrip() for ln in lines)   # 行尾无空格
    assert max(_w(ln) for ln in lines) <= 100       # 100 终端宽度内


def test_week_header_and_monday_derive():
    rows = [_r(2, 8, 0, "大学英语", "外语楼B201", 9, 40)]
    with_week = render_week_grid(rows, week=8, monday=MON)
    assert with_week.split("\n")[0] == "第 8 教学周  10/26–11/01"
    assert "周一 10/26" in with_week.split("\n")[1]
    # monday=None 时从课程日期推导，仍然出日期表头
    derived = render_week_grid(rows, week=None, monday=None)
    assert derived.split("\n")[0].startswith(" 时间")   # 无周头
    assert "周二 10/27" in derived.split("\n")[0]


def test_today_column_highlight():
    rows = [_r(3, 14, 0, "大学英语", "外语楼B201", 15, 40)]   # 周三
    text = render_week_grid(rows, week=9, monday=MON,
                            today=date(2026, 10, 28), color=_mark)
    assert "<cyan>周三 10/28</>" in text          # 列头 cyan
    assert "<bold>大学英语</>" in text            # 今天列课名 bold
    assert "<dim>外语楼B201</>" in text           # 地点 dim
    assert "<cyan>周一" not in text               # 其他列不高亮
    assert text.count("<bold>") == 1


def test_span_merge_with_continuation():
    rows = [
        _r(1, 8, 0, "大学物理", "教3-201", 11, 40),   # 周一 8:00–11:40 跨两节
        _r(2, 10, 0, "程序设计", "机房2", 11, 40),
    ]
    text = render_week_grid(rows, week=None, monday=MON)
    assert text.count("│") == 1                    # 恰一个续行符号
    assert text.count("大学物理") == 1              # 合并后课名只出现一次
    cont = [ln for ln in text.split("\n") if "│" in ln][0]
    assert cont.find("│") == 5 + 2 + 4             # 列宽 10 → 居中在偏移 4
    assert "程序设计" in cont                      # 同轨行他列正常显示
    assert "08:00" in text and "10:00" in text


def test_conflict_two_in_one_cell():
    rows = [
        _r(1, 8, 0, "化学", "K201", 9, 40),
        _r(1, 8, 0, "物理", "K202", 9, 40),        # 同天同节次撞课
    ]
    text = render_week_grid(rows, week=None, monday=MON)
    assert " 化学@K201" in text and " 物理@K202" in text   # 各占一行且缩进
    hit = [ln for ln in text.split("\n") if "化学" in ln or "物理" in ln]
    assert len(hit) == 2                            # 两门分处两行
    assert text.count("化学") == 1 and text.count("物理") == 1


def test_empty_rows_hint():
    for args in ({}, {"week": 9, "monday": MON, "today": MON}):
        text = render_week_grid([], color=None, **args)
        assert "\n" not in text and text.strip()    # 单行非空提示


def test_color_none_is_plain():
    rows = [_r(3, 14, 0, "大学英语", "外语楼B201", 15, 40)]
    text = render_week_grid(rows, week=9, monday=MON,
                            today=date(2026, 10, 28), color=None)
    assert "\x1b" not in text                       # 无 ANSI 转义
    assert "大学英语" in text and "14:00" in text


def test_col_width_adaptive():
    narrow = render_week_grid([_r(1, 8, 0, "化学", "K201", 9, 40)],
                              week=None, monday=MON)
    # 短课名 → 列宽取下限 10，整表 5+2+7*10+12 = 89
    assert max(_w(ln) for ln in narrow.split("\n")) == 89
    h = narrow.split("\n")[0]                       # 相邻列名间距 = 列宽+2
    assert _w(h[h.find("周一"):h.find("周二")]) == 10 + 2
    wide = render_week_grid(
        [_r(1, 8, 0, "毛泽东思想和中国特色社会主义理论体系概论", "主楼E102", 9, 40)],
        week=None, monday=MON)
    lines = wide.split("\n")
    width = max(_w(ln) for ln in lines)
    assert 89 < width <= 100                        # 撑宽但仍在 100 内
    h2 = lines[0]
    assert _w(h2[h2.find("周一"):h2.find("周二")]) == 11 + 2   # 列宽拉到 11
    assert "…" in wide and "毛泽东" in wide         # 超长课名截断


def test_min_rail_rows():
    rows = [_r(1, 8, 0, "化学", "K201", 9, 40),
            _r(2, 10, 0, "物理", "K202", 11, 40)]   # 只出现 2 个节次
    text = render_week_grid(rows, week=None, monday=MON)
    lines = text.split("\n")
    # MIN_RAIL_ROWS=3：表头 + 两节×两行 + 1 空轨行，不再垫出空行尾巴
    assert len(lines) == 1 + 2 + 2 + 1
    assert lines[1].startswith("08:00") and lines[3].startswith("10:00")
    assert lines[5:] == [""]


def run_all() -> int:
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__} {e}")
    print(f"weekgrid tests: {len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run_all())
