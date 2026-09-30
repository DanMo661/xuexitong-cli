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
from assistant.snapshot import (ddl_view, exam_summary, exams_view,  # noqa: E402
                                notices_view, parse_exam_rows,
                                progress_view)
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
    text, sub, cnt, ongoing = exam_summary(view)
    assert "今天考" in text and "14:00" in text and sub == ""
    assert cnt == 2 and not ongoing
    # 全结束 → 空横幅
    done = exams_view(parse_exam_rows(
        [_exam_row("旧", "2026-06-01 09:00", "2026-06-01 11:00")], now=NOW), now=NOW)
    assert exam_summary(done) == ("", "", 0, False)
    # 进行中 → 主行放结束时间（360px 塞不下全名+状态+时间），课程名挪副行
    live = exams_view(parse_exam_rows(
        [_exam_row("进行中", "2026-09-30 10:00", "2026-09-30 12:30")], now=NOW), now=NOW)
    text, sub, cnt, ongoing = exam_summary(live)
    assert "进行中" in text and "12:30" in text
    assert sub == "《进行中》" and ongoing


def test_exams_cache_roundtrip_via_save():
    """P0 回归：set_exams 存 datetime → save() 落盘 → 重读 → exams_view 不炸。"""
    import json as _json
    s = _store()
    s.set_exams(parse_exam_rows(
        [_exam_row("缓存考", "2026-10-12 14:00", "2026-10-12 16:00")], now=NOW))
    s.save()   # datetime 未转 iso 时这里直接 TypeError
    with open(s.path, encoding="utf-8") as f:
        raw = _json.load(f)   # 文件本身必须是合法 JSON（曾截断在 "start": 处）
    assert raw["exams_cache"]["rows"][0]["start"] == "2026-10-12T14:00:00"
    s2 = Store(s.path)
    view = exams_view(s2.get_exams(), now=NOW)
    assert view[0]["name"] == "缓存考" and view[0]["state"] == "upcoming"


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
    # 瞬态空状态不入基线：真实状态到来时照常报（Judge A P2-4）
    s2 = _store()
    s2.diff_hw_status("c9", {"HW": ""})
    assert s2.diff_hw_status("c9", {"HW": "已完成"}) == []   # 空没入基线，首见不报
    s2.diff_hw_status("c9", {"HW": "已完成"})
    assert s2.diff_hw_status("c9", {"HW": "已批阅"}) == [("HW", "已完成", "已批阅")]


def test_diff_exams():
    s = _store()
    # 首见建基线
    assert s.diff_exams(["a|10-01", "b|10-02"]) == []
    assert s.diff_exams(["a|10-01", "b|10-02", "c|10-03"]) == ["c|10-03"]
    # 考试改时间 = 新 key，会再报一次（合理：时间变了该知道）
    assert s.diff_exams(["a|10-05", "b|10-02", "c|10-03"]) == ["a|10-05"]


def test_notices_cache_fields_and_read():
    """真实字段 sendTime/createrName/isread('0'/'1' 字符串)（Judge A P1-1/2）。"""
    s = _store()
    s.set_notices([
        {"title": "通知1", "createrName": "张老师",
         "sendTime": "2026-09-30 10:00:00", "isread": "0",
         "uuid": "u1", "content": "x" * 600},
        {"title": "通知2", "createrName": "学习通知",
         "sendTime": "2026-09-29T09:00:00", "isread": "1",
         "uuid": "u2", "content": "hi"},
    ])
    rows = s.get_notices()
    assert rows[0]["unread"] is True and rows[0]["sender"] == "张老师"
    assert rows[0]["time"] == "2026-09-30 10:00" and len(rows[0]["content"]) == 500
    assert rows[0]["key"] == "u1|通知1"
    assert rows[1]["unread"] is False and rows[1]["time"] == "2026-09-29 09:00"
    # 本地已读：服务端未读但看过了 → 红点消
    s.mark_notice_read("u1|通知1")
    assert s.get_notices()[0]["unread"] is False
    # 重拉后本地已读仍生效
    s.set_notices([
        {"title": "通知1", "createrName": "张老师",
         "sendTime": "2026-09-30 10:00:00", "isread": "0",
         "uuid": "u1", "content": "x"}])
    assert s.get_notices()[0]["unread"] is False


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
        {"course": "尔雅网课", "done": 1, "total": 30, "error": None},
        {"course": "实践课(无章节)", "done": None, "total": None, "error": "无进度数据"},
    ]
    v = progress_view(rows, active_names={"数字图像处理", "模拟电子技术",
                                          "实践课(无章节)"})
    names = [r["course"] for r in v["rows"]]
    # 往年课不进主列表也不进 other（没在课表且不在 other 未完成组？——不，
    # 往年课有未完成，会进 otherRows；主列表只有课表内三课
    assert names == ["数字图像处理", "模拟电子技术", "实践课(无章节)"]
    assert v["totalLeft"] == 2 and v["coursesLeft"] == 1
    assert v["rows"][1]["left"] == 0 and v["rows"][2]["done"] is None
    assert v["hasData"] is True
    # otherRows：不在课表但有未完成的课（网课+往年课），按缺口排序
    assert [r["course"] for r in v["otherRows"]] == ["尔雅网课", "往年旧课"]
    # 全是 error 行时 hasData=False（"全部完成✓"不会误报）
    v2 = progress_view([{"course": "A", "done": None, "total": None,
                         "error": "x"}])
    assert v2["hasData"] is False and v2["otherRows"] == []
    # done>total 防溢出
    v3 = progress_view([{"course": "B", "done": 12, "total": 10, "error": None}])
    assert v3["rows"][0]["pct"] == 100


def test_notices_view():
    out = notices_view([{"title": "t", "sender": "s", "time": "x",
                         "unread": True, "content": "c"}])
    assert out[0]["unread"] is True and out[0]["title"] == "t"


def test_hw_ignore_roundtrip():
    s = _store()
    s.set_deadlines([
        {"course": "数字图像处理", "title": "实验四", "status": "未交",
         "url": "https://x/chaoxing/work/1", "deadline": None,
         "deadline_dt": NOW + timedelta(days=2)},
        {"course": "机器学习", "title": "HW1", "status": "未交",
         "url": "", "deadline": None, "deadline_dt": None},
    ])
    rows = ddl_view(s.get_deadlines(), ignores=[])
    assert rows[0]["url"] == "https://x/chaoxing/work/1"
    assert rows[1]["url"] == "" and rows[1]["urgency"] == "unknown"
    s.ignore_hw("数字图像处理", "实验四", "https://x/chaoxing/work/1")
    rows = ddl_view(s.get_deadlines(), ignores=s.hw_ignores())
    assert [r["title"] for r in rows] == ["HW1"]   # 被忽略的从看板消失
    assert s.unignore_hw_all() == 1
    assert len(ddl_view(s.get_deadlines(), ignores=s.hw_ignores())) == 2
    # 无 url 形态的忽略也要能拦住带 url 的行（缓存升级防漂移）
    s.ignore_hw("数字图像处理", "实验四")
    rows = ddl_view(s.get_deadlines(), ignores=s.hw_ignores())
    assert [r["title"] for r in rows] == ["HW1"]
    assert s.unignore_hw_all() == 1
    # 同课同名不同 url：不连坐
    s.set_deadlines([
        {"course": "C", "title": "第三章作业", "status": "未交",
         "url": "https://a", "deadline": None,
         "deadline_dt": NOW + timedelta(days=1)},
        {"course": "C", "title": "第三章作业", "status": "未交",
         "url": "https://b", "deadline": None,
         "deadline_dt": NOW + timedelta(days=2)},
    ])
    s.ignore_hw("C", "第三章作业", "https://a")
    rows = ddl_view(s.get_deadlines(), ignores=s.hw_ignores())
    assert len(rows) == 1 and rows[0]["url"] == "https://b"


def test_deadline_cache_carries_urls():
    s = _store()
    s.set_deadlines([
        {"course": "C", "title": "T", "status": "未交",
         "url": "https://work", "courseUrl": "https://course",
         "deadline": "10-01 10:00", "deadline_dt": NOW + timedelta(days=1)},
    ])
    r = s.get_deadlines()[0]
    assert r["url"] == "https://work" and r["courseUrl"] == "https://course"
    view = ddl_view(s.get_deadlines())[0]
    assert view["url"] == "https://work"
    assert view["courseUrl"] == "https://course"


def test_week_grid_now_line():
    """时间红线：node 内进度 → nowLine 行坐标（本周才显示，其他周 -1）。"""
    from datetime import timedelta
    from assistant.snapshot import week_grid

    class _S:   # 只需要 get_schedule 的鸭子类型
        def get_schedule(self):
            import calendar
            monday = NOW.date() - timedelta(days=NOW.weekday())
            return {"curriculum": {
                "firstWeekDate": calendar.timegm(monday.timetuple()) * 1000,
                "maxWeek": 20,
                "lessonTimeConfigArray": ["8:00-8:45", "9:00-9:45",
                                          "10:00-10:45"],
            }, "lessons": [
                {"name": "A", "dayOfWeek": 3, "beginNumber": 1, "length": 3,
                 "weeks": "1-20", "location": ""}]}

    g = week_grid(_S(), offset=0, now=NOW.replace(hour=9, minute=30))
    # 9:30 落在第二节（9:00 起，下节 10:00 起）→ 1 + 30/60 = 1.5
    assert abs(g["nowLine"] - 1.5) < 0.01, g["nowLine"]
    assert g["currentNode"] == 1
    # 非本周视图不画线
    g2 = week_grid(_S(), offset=1, now=NOW.replace(hour=9, minute=30))
    assert g2["nowLine"] == -1
    # 教学前（早 6 点）不画线
    g3 = week_grid(_S(), offset=0, now=NOW.replace(hour=6, minute=0))
    assert g3["nowLine"] == -1 and g3["currentNode"] == -1


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
