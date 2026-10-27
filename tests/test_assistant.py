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


def test_timeline_sorts_across_time_formats():
    """时间线倒排要兼容 isoformat("T") 和空格分隔两种时间串。"""
    s = _store()
    s._data["timeline"] = [
        {"kind": "material", "title": "上午的资料", "time": "2026-10-14 09:00:00"},
        {"kind": "classup", "title": "下午的预备铃", "time": "2026-10-14T08:00:00"},
        {"kind": "notice", "title": "昨晚通知", "time": "2026-10-13 22:00:00"},
    ]
    titles = [e["title"] for e in s.timeline()]
    # 同一天里 09:00 必须排在 08:00 前（裸字符串比较会把 T 分隔的排前面）
    assert titles == ["上午的资料", "下午的预备铃", "昨晚通知"], titles


def test_timeline_dedup_includes_course():
    """去重键含 course：两门课同日传同名文件，第二条不能被吞。"""
    s = _store()
    s._data["timeline"] = []
    s.append_timeline({"kind": "material", "course": "课A",
                       "title": "HW1.pptx", "time": "2026-10-14 10:00:00"})
    s.append_timeline({"kind": "material", "course": "课B",
                       "title": "HW1.pptx", "time": "2026-10-14 11:00:00"})
    s.append_timeline({"kind": "material", "course": "课A",
                       "title": "HW1.pptx", "time": "2026-10-14 12:00:00"})
    # 课B 的同名文件不能被课A 吞掉；课A 自己当天重复的仍要去重
    titles = sorted(e["course"] for e in s.timeline())
    assert titles == ["课A", "课B"], titles


def test_parse_send_time_variants():
    from assistant.watcher import _parse_send_time
    assert _parse_send_time("") == 0.0
    assert _parse_send_time(None) == 0.0
    assert _parse_send_time("乱串") == 0.0
    # 数字与数字字符串两种毫秒时间戳都要认
    assert abs(_parse_send_time(1788105600000) - 1788105600.0) < 1
    assert abs(_parse_send_time("1788105600000") - 1788105600.0) < 1
    t = _parse_send_time("2026-10-14 16:00:00")
    assert t > 1.7e9 and t < 2.2e9


def test_progress_active_only_and_exams_term_filter():
    """用户规矩：任务点/考试都以本学期为主——往年课不扫不报。"""
    import calendar
    from datetime import timedelta
    from assistant.watcher import Watcher
    s = _store()
    monday = NOW.date() - timedelta(days=NOW.weekday())
    s.set_schedule({"curriculum": {
        "firstWeekDate": calendar.timegm(monday.timetuple()) * 1000,
        "maxWeek": 20, "lessonTimeConfigArray": ["8:00-8:50"]},
        "lessons": []})
    s._data["courses"] = {"111|1": {"active": True}, "999|2": {"active": False}}

    class FakeClient:
        def fetch_courses(self):
            return [{"name": "本学期", "courseid": "111", "clazzid": "1"},
                    {"name": "往年课", "courseid": "999", "clazzid": "2"}]

        def fetch_chapters(self, co, with_nodes=False):
            return {"progress": (1, 5)}

        def fetch_exams(self):
            nxt = NOW + timedelta(days=7)
            return [
                ["", "新考试", f"{nxt:%Y-%m-%d} 10:00 至 {nxt:%Y-%m-%d} 11:00",
                 "60", "未开始", "未交", "---", "", ""],
                ["", "旧考试", "2025-06-01 10:00 至 2025-06-01 11:00",
                 "60", "已结束", "未交", "---", "", ""],
            ]

    w = Watcher(FakeClient(), s, probe_download=False)
    assert w.refresh_progress() is True
    names = [r["course"] for r in s.get_progress()]
    assert names == ["本学期"], names      # 往年课不扫、不进缓存
    w._scan_exams()
    exams = [r["name"] for r in s.get_exams()]
    assert exams == ["新考试"], exams       # 学期开始前的考试不入库


def test_progress_view_dedups_same_course_two_classes():
    from assistant.snapshot import progress_view
    v = progress_view([
        {"course": "数字信号处理", "done": 3, "total": 10},
        {"course": "数字信号处理", "done": 10, "total": 10},
    ], active_names={"数字信号处理"})
    # 同课两班只留更完整那行：列表一行、缺口不翻倍
    assert len(v["rows"]) == 1 and v["rows"][0]["left"] == 0
    assert v["totalLeft"] == 0


def test_cli_helpers_and_parser():
    """CLI 纯函数层：CJK 宽度/截断/子命令装配（不碰网络）。"""
    from xuexitong_mcp import cli
    assert cli._w("数字信号处理") == 12      # 6 全角 = 12
    assert cli._w("HW1") == 3
    assert cli._pad("ab", 5) == "ab   "
    # 截断按显示宽度：8 全角字宽 16 → 限 10 留 8 + 省略号
    assert cli._w(cli._clip("数字信号处理_DSP", 10)) <= 10
    assert cli._clip("abc", 10) == "abc"
    p = cli.build_parser()
    a = p.parse_args(["today"])
    assert a.fn is cli.cmd_today
    a = p.parse_args(["materials", "数图", "--find", "实验"])
    assert a.course == "数图" and a.find == "实验"
    a = p.parse_args(["exam", "--all"])
    assert a.all is True


def test_client_exam_rows_parse():
    from xuexitong_mcp.client import parse_exam_rows
    rows = parse_exam_rows([
        ["", "图论试卷", "2026-12-19 09:00 至 2026-12-30 22:00",
         "180", "未开始", "未交", "---", "未设置终端", ""],
        ["", "坏行", "时间乱写", "60", "", "", "", ""],
    ])
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "图论试卷" and r["durationMin"] == "180"
    assert f"{r['start']:%Y-%m-%d %H:%M}" == "2026-12-19 09:00"


def test_notices_cache_fields_and_read():
    # int 型毫秒 sendTime 不炸缓存写入（nitpick R2 B1）
    s = _store()
    s.set_notices([{"uuid": "u1", "title": "T", "createrName": "师",
                    "sendTime": 1788105600000, "isread": "0", "content": "c"}])
    row = s.get_notices()[0]
    assert row["time"].count("-") == 2 and ":" in row["time"]  # 已转日期串
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
    """时间红线：node 内按进度走；课间空档贴下节课上沿；
    本周之外/教学日之外不画。"""
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
    # 9:30 落在第二节（9:00-9:45）→ 1 + 30/45（用节次表真实下课时间）
    assert abs(g["nowLine"] - (1 + 30 / 45)) < 0.01, g["nowLine"]
    assert g["currentNode"] == 1
    # 课间空档（9:45-10:00）：红线钉在第三节上沿（网格线上），不消失
    g_gap = week_grid(_S(), offset=0, now=NOW.replace(hour=9, minute=50))
    assert g_gap["nowLine"] == 2.0 and g_gap["currentNode"] == -1
    # 非本周视图不画线
    g2 = week_grid(_S(), offset=1, now=NOW.replace(hour=9, minute=30))
    assert g2["nowLine"] == -1
    # 教学前（早 6 点）不画线
    g3 = week_grid(_S(), offset=0, now=NOW.replace(hour=6, minute=0))
    assert g3["nowLine"] == -1 and g3["currentNode"] == -1
    # 空缓存 → week=0（UI 显示"学期未同步"，别装第 1 周）
    class _Empty:
        def get_schedule(self):
            return {}
    assert week_grid(_Empty(), offset=0, now=NOW)["week"] == 0


def test_week_grid_fixed_rail_and_colors():
    """节次轨恒铺到晚上（没晚课也留行）+ 起止双时刻 + 课程顺序配色不撞。"""
    from datetime import timedelta
    from assistant.snapshot import (COURSE_COLORS, course_colors,
                                    week_grid)

    class _S:
        def get_schedule(self):
            import calendar
            monday = NOW.date() - timedelta(days=NOW.weekday())
            times = ["8:00-8:50"] + [f"{h}:00-{h}:50" for h in range(9, 22 + 1)]
            return {"curriculum": {
                "firstWeekDate": calendar.timegm(monday.timetuple()) * 1000,
                "maxWeek": 20,
                "lessonTimeConfigArray": times,
            }, "lessons": [
                {"name": "甲", "dayOfWeek": 3, "beginNumber": 1, "length": 2,
                 "weeks": "1-20", "location": "北主楼101"},
                {"name": "乙", "dayOfWeek": 4, "beginNumber": 1, "length": 2,
                 "weeks": "1-20", "location": ""}]}

    g = week_grid(_S(), offset=0, now=NOW)
    # 白天的课只到第 2 节，但轨恒铺到第 11 节（≈21:50），单页不滚动
    assert len(g["nodeLabels"]) == 11
    assert g["nodeTimes"][4] == "12:00" and g["nodeTimesEnd"][4] == "12:50"
    assert len(g["nodeTimesEnd"]) == 11 and g["nodeTimesEnd"][0] == "08:50"
    # 顺序配色：两门课不同色；颜色池 ≥12 色
    names = {b["name"]: (b["bg"], b["fg"]) for b in g["blocks"]}
    assert names["甲"] != names["乙"]
    assert len(COURSE_COLORS) >= 12
    m = course_colors([{"name": n} for n in ["甲", "乙", "甲"]])
    assert set(m.values()) == {names["甲"], names["乙"]}
    # 脏数据 dayOfWeek=8/0 不炸网格、不产块（0 别静默落进周一列）
    class _Bad:
        def get_schedule(self):
            return {"curriculum": _S().get_schedule()["curriculum"], "lessons": [
                {"name": "坏课8", "dayOfWeek": 8, "beginNumber": 1,
                 "length": 2, "weeks": "1-20", "location": ""},
                {"name": "坏课0", "dayOfWeek": 0, "beginNumber": 1,
                 "length": 2, "weeks": "1-20", "location": ""}]}
    g2 = week_grid(_Bad(), offset=0, now=NOW)
    assert g2["blocks"] == []
    # curWeek 字段存在（QML 翻周同步依赖）
    assert g["curWeek"] >= 1


# ---------------------------------------------------------------- CLI 纯逻辑

def _fake_sc(first_monday, lessons):
    """合成全学期课表缓存：firstWeekDate 用 UTC 04:00 的 ms 保证
    ms_to_date 落回同一天（CN 时区正午）。"""
    from datetime import time as dtime
    from xuexitong_mcp.client import ms_to_date
    from xuexitong_mcp import cli as xxt
    ms = int(datetime(first_monday.year, first_monday.month,
                      first_monday.day, 4, 0).timestamp() * 1000)
    assert ms_to_date(ms) == first_monday   # 时区前提自证，翻车先炸这里
    return {
        "saved_at": "2026-10-27T10:00:00",
        "lessons": lessons,
        "curriculum": {
            "firstWeekDate": ms, "maxWeek": 20,
            "lessonTimeConfigArray": ["8:00-8:50", "9:00-9:50",
                                      "10:10-11:00", "14:00-14:50"],
        },
    }


def _lesson(name, dow, begin, length, weeks):
    return {"name": name, "dayOfWeek": dow, "beginNumber": begin,
            "length": length, "weeks": weeks, "location": "教三",
            "teacherName": "张三"}


def test_cli_next_lesson_same_day_and_next_week():
    from xuexitong_mcp import cli as xxt
    fw = datetime(2026, 9, 7).date()          # 第 1 周周一
    sc = _fake_sc(fw, [
        _lesson("信号", 1, 1, 2, "1-20"),      # 周一 8:00-9:50
        _lesson("物理", 1, 4, 1, "1-20"),      # 周一 14:00-14:50
        _lesson("毛概", 5, 1, 2, "1-20"),      # 周五 8:00
    ])
    # 周一（第8周）早上 7:00 → 信号 8:00（今天）
    now = datetime(2026, 10, 26, 7, 0)
    hit = xxt._next_lesson(sc, now)
    assert hit and hit[0] == 0 and hit[3] == "信号"
    assert hit[1] == datetime(2026, 10, 26, 8, 0)
    # 周一 12:00（上午两节已过）→ 物理 14:00（今天下午）
    hit = xxt._next_lesson(sc, datetime(2026, 10, 26, 12, 0))
    assert hit and hit[0] == 0 and hit[3] == "物理"
    # 周五 9:30（信号进行中不算，取未来）→ 下周一信号，days_ahead=3
    hit = xxt._next_lesson(sc, datetime(2026, 10, 30, 9, 30))
    assert hit and hit[0] == 3 and hit[3] == "信号"
    assert hit[1] == datetime(2026, 11, 2, 8, 0)


def test_cli_next_lesson_weeks_filter_and_none():
    from xuexitong_mcp import cli as xxt
    fw = datetime(2026, 9, 7).date()
    # 只有第 2 周有课，现在第 8 周 → 14 天内无课
    sc = _fake_sc(fw, [_lesson("单周课", 1, 1, 2, "2")])
    assert xxt._next_lesson(sc, datetime(2026, 10, 26, 7, 0)) is None
    # 第 2 周周一（9/14）早上查 → 当天 8:00 命中
    hit = xxt._next_lesson(sc, datetime(2026, 9, 14, 7, 0))
    assert hit and hit[3] == "单周课" and hit[0] == 0
    # weeks 串 "2,10"：第 10 周周一 = 11/09，距 10/26 恰 14 天 =
    # 地平线边界最后一天，必须能命中（逗号周次语法同步覆盖）
    sc2 = _fake_sc(fw, [_lesson("双段课", 1, 1, 1, "2,10")])
    hit = xxt._next_lesson(sc2, datetime(2026, 10, 26, 7, 0))
    assert hit and hit[3] == "双段课" and hit[0] == 14
    assert hit[1].date() == datetime(2026, 11, 9).date()
    # 第 10 周周三（11/11，16 天后）超出地平线 → None（旧断言的错误预期）
    sc3 = _fake_sc(fw, [_lesson("超界课", 3, 1, 1, "10")])
    assert xxt._next_lesson(sc3, datetime(2026, 10, 26, 7, 0)) is None


def test_cli_fmt_countdown():
    from xuexitong_mcp import cli as xxt
    assert xxt._fmt_countdown(45) == "45 分钟"
    assert xxt._fmt_countdown(60) == "1 小时"
    assert xxt._fmt_countdown(89) == "1 小时 29 分"
    assert xxt._fmt_countdown(1440) == "1 天"
    assert xxt._fmt_countdown(1500) == "1 天 1 小时"


def test_cli_today_rows_zero_network_shape():
    from xuexitong_mcp import cli as xxt
    fw = datetime(2026, 9, 7).date()
    sc = _fake_sc(fw, [
        _lesson("信号", 2, 1, 2, "1-20"),      # 周二 8:00
        _lesson("无周串", 2, 4, 1, ""),         # 无 weeks=恒有
    ])
    rows = xxt._today_rows(sc)
    # 只有当 query 日是周二才会命中；此处只验证结构不炸 + 排序
    assert all(r[1] <= r[2] for r in rows)


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
