# -*- coding: utf-8 -*-
"""assistant 侧纯逻辑单元测试（考试/出分/任务点/通知/状态基线）。

零网络依赖，直接运行：  python tests/test_assistant.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.classify import classify_exam, classify_hw_status  # noqa: E402
from assistant.snapshot import (exam_summary, exams_view, notices_view,  # noqa: E402
                                parse_exam_rows, progress_view)
from assistant.store import Store  # noqa: E402

NOW = datetime(2026, 9, 30, 12, 0)


def _exam_row(name, start, end, dur="120", status="未开始",
              answer="未交", score="---", mode="学习通"):
    return ["x", name, f"{start} 至 {end}", dur, status, answer, score, mode, "x"]


# ---------------------------------------------------------------- 考试解析

def test_parse_exam_rows():
    rows = parse_exam_rows([
        _exam_row("数字图像处理", "2026-10-12 14:00", "2026-10-12 16:00"),
        ["x"],                                    # 列数不足 → 跳过
        _exam_row("坏时间", "随时", " anytime "),   # 无时间 → 跳过
        _exam_row("跨天考试", "2026-10-12 09:00", "2026-10-13 18:00"),
    ], now=NOW)
    assert len(rows) == 2
    r = rows[0]
    assert r["name"] == "数字图像处理"
    assert r["start"] == datetime(2026, 10, 12, 14, 0)
    assert r["end"] == datetime(2026, 10, 12, 16, 0)
    assert r["durationMin"] == "120" and r["mode"] == "学习通"
    # 无"至"尾巴时 end 兜底为 start
    r2 = parse_exam_rows([_exam_row("单点", "2026-10-12 14:00", None)], now=NOW)
    assert r2[0]["end"] == r2[0]["start"]


def test_exams_view_ordering_and_labels():
    rows = parse_exam_rows([
        _exam_row("已结束A", "2026-06-01 09:00", "2026-06-01 11:00"),
        _exam_row("已结束B", "2026-09-01 09:00", "2026-09-01 11:00"),
        _exam_row("今天考", "2026-09-30 14:00", "2026-09-30 16:00"),
        _exam_row("下周考", "2026-10-07 09:00", "2026-10-07 11:00"),
        _exam_row("进行中", "2026-09-30 10:00", "2026-09-30 12:30"),
    ], now=NOW)
    view = exams_view(rows, now=NOW)
    assert [v["name"] for v in view] == ["进行中", "今天考", "下周考", "已结束B", "已结束A"]
    assert view[0]["state"] == "ongoing"
    assert view[1]["daysLabel"] == "今天"
    assert view[2]["daysLabel"] == "7 天后"
    assert view[3]["state"] == "done" and view[3]["daysLabel"] == ""
    # 已结束按最近在前
    assert view[3]["name"] == "已结束B"


def test_exam_summary():
    view = exams_view(parse_exam_rows([
        _exam_row("今天考", "2026-09-30 14:00", "2026-09-30 16:00"),
        _exam_row("下周考", "2026-10-07 09:00", "2026-10-07 11:00"),
    ], now=NOW), now=NOW)
    text, cnt = exam_summary(view)
    assert "今天考" in text and cnt == 2
    # 全结束 → 空横幅
    done = exams_view(parse_exam_rows(
        [_exam_row("旧", "2026-06-01 09:00", "2026-06-01 11:00")], now=NOW), now=NOW)
    assert exam_summary(done) == ("", 0)
    # 进行中 → 报结束时间
    live = exams_view(parse_exam_rows(
        [_exam_row("进行中", "2026-09-30 10:00", "2026-09-30 12:30")], now=NOW), now=NOW)
    text, _ = exam_summary(live)
    assert "进行中" in text and "12:30" in text


# ---------------------------------------------------------------- 出分判定

def test_classify_hw_status():
    assert classify_hw_status("", "已交") is None          # 首见无 old
    assert classify_hw_status("已交", "已交") is None        # 无变化
    g = classify_hw_status("待批阅", "已完成")
    assert g["tag"] == "出分" and g["priority"] == "high"
    g2 = classify_hw_status("未交", "已批阅")
    assert g2["tag"] == "出分"
    back = classify_hw_status("已交", "未交")
    assert back["priority"] == "medium" and "打回" in back["reason"]
    low = classify_hw_status("未交", "已交")
    assert low["priority"] == "low"   # 自己刚交完，别弹


def test_classify_exam():
    v = classify_exam("数字图像处理")
    assert v["priority"] == "high" and v["tag"] == "考试"


# ---------------------------------------------------------------- Store 基线

def _store() -> Store:
    return Store(os.path.join(tempfile.gettempdir(),
                              f"t_store_{os.getpid()}.json"))


def test_diff_hw_status():
    s = _store()
    # 首见：建基线不报
    assert s.diff_hw_status("c1", {"HW1": "未交", "HW2": "待批阅"}) == []
    # 出分
    ch = s.diff_hw_status("c1", {"HW1": "未交", "HW2": "已完成"})
    assert ch == [("HW2", "待批阅", "已完成")]
    # 新作业首见仍不报（那是 diff_homework 的活）
    assert s.diff_hw_status("c1", {"HW1": "未交", "HW2": "已完成", "HW3": "未交"}) == []
    # 打回
    ch2 = s.diff_hw_status("c1", {"HW1": "未交", "HW2": "已完成", "HW3": "已交"})
    assert ch2 == [("HW3", "未交", "已交")]


def test_diff_exams():
    s = _store()
    # 首见建基线
    assert s.diff_exams(["a|10-01", "b|10-02"]) == []
    assert s.diff_exams(["a|10-01", "b|10-02", "c|10-03"]) == ["c|10-03"]
    # 考试改时间 = 新 key，会再报一次（合理：时间变了该知道）
    assert s.diff_exams(["a|10-05", "b|10-02", "c|10-03"]) == ["a|10-05"]


def test_notices_cache_roundtrip():
    s = _store()
    s.set_notices([
        {"title": "通知1", "sender": "张老师", "time": "2026-09-30 10:00:00",
         "isread": 0, "content": "x" * 300},
        {"title": "通知2", "sender": "学习通知", "time": "2026-09-29T09:00:00",
         "isread": 1, "content": "hi"},
    ])
    rows = s.get_notices()
    assert len(rows) == 2
    assert rows[0]["unread"] is True and rows[0]["content"] == "x" * 160
    assert rows[1]["unread"] is False and rows[1]["time"] == "2026-09-29 09:00"


def test_progress_cache_date():
    s = _store()
    assert s.progress_date == ""
    s.set_progress([{"course": "A", "done": 1, "total": 2, "error": None}])
    assert s.progress_date == datetime.now().strftime("%Y-%m-%d")
    assert s.get_progress()[0]["done"] == 1


# ---------------------------------------------------------------- 视图

def test_progress_view_filter_and_sort():
    rows = [
        {"course": "数字图像处理", "done": 8, "total": 10, "error": None},
        {"course": "模拟电子技术", "done": 10, "total": 10, "error": None},
        {"course": "往年旧课", "done": 0, "total": 5, "error": None},
        {"course": "实践课(无章节)", "done": None, "total": None, "error": "无进度数据"},
    ]
    v = progress_view(rows, active_names={"数字图像处理", "模拟电子技术",
                                          "实践课(无章节)"})
    names = [r["course"] for r in v["rows"]]
    # 往年课被滤掉；未完成在前、全完成次之、无数据垫底
    assert names == ["数字图像处理", "模拟电子技术", "实践课(无章节)"]
    assert v["totalLeft"] == 2 and v["coursesLeft"] == 1
    assert v["rows"][1]["left"] == 0 and v["rows"][2]["done"] is None


def test_notices_view():
    out = notices_view([{"title": "t", "sender": "s", "time": "x",
                         "unread": True, "content": "c"}])
    assert out[0]["unread"] is True and out[0]["title"] == "t"


# ----------------------------------------------------------------

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
    print(f"assistant tests: {len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run_all())
