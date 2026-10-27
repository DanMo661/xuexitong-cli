# -*- coding: utf-8 -*-
"""xuexitong-cli 纯逻辑单元测试。

零依赖可直接运行：  python tests/run_tests.py
也可用 pytest：     pytest tests/ -v
（不发起任何网络请求，只测解析与加解密等纯函数。）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xuexitong_mcp.client import (  # noqa: E402
    aes_encrypt, aes_decrypt, build_ics, compress_weeks, escape_ics,
    expand_weeks, hidden_value, is_antispider_location, is_homework_pending,
    ms_to_date, nearest_datetime_for, parse_cd_filename, parse_courses,
    parse_homework_detail, parse_materials, parse_section_times,
    sanitize_filename, strip_tags, week_in_schedule,
)
from xuexitong_mcp.widget import (  # noqa: E402
    ellipsize, fmt_countdown, lesson_rows, pick_current_next)
from datetime import date, datetime, timedelta  # noqa: E402

# ---------------------------------------------------------------- AES 加解密

COURSE_HTML = """
<div class="course">
  <a href="/visit/stucoursemiddle?courseid=247085333&clazzid=114514&cpi=319461"
     class="stucoursemiddle">
    <span class="course-name" title="机器学习综合设计">机器学习综合设计</span>
    <p class="overHidden2">黄一桂</p>
  </a>
  <a href="/visit/stucoursemiddle?courseid=247085333&clazzid=114514&cpi=319461">
    重复链接应去重
  </a>
  <a href="/visit/stucoursemiddle?courseid=100&clazzid=200&cpi=300">
    <span class="course-name" title="数字电路">数字电路</span>
    <p class="overHidden2">李老师</p>
  </a>
</div>
"""

MATERIAL_HTML = """
<dt onclick="toOpen('%E5%AE%9E%E9%AA%8C%E6%8C%87%E5%AF%BC%E4%B9%A6','doc',10001,'x','','',0,0,'','abc123')">x</dt>
<dt onclick="toOpen('%E8%AF%BE%E4%BB%B6%E5%A4%B9','afolder',20002,'x','','',0,0,'','enc456')">x</dt>
"""


def test_aes_roundtrip():
    for text in ("13800138000", "p@ss w0rd!", "中文密码", "a"):
        assert aes_decrypt(aes_encrypt(text)) == text


def test_aes_output_is_b64_of_cbc_padding():
    raw = aes_encrypt("abc")
    import base64
    data = base64.b64decode(raw)          # base64 合法
    assert len(data) % 16 == 0            # CBC 块对齐（3 字节明文 + PKCS7 补齐 16 字节）
    assert len(data) == 16
    # 确定性：同一输入永远得到同一密文（key/iv 固定，服务端才能解）
    assert aes_encrypt("abc") == raw


def test_strip_tags():
    html = '<div><script>evil()</script><style>.x{}</style>通知<b>正文</b>&nbsp;！</div>'
    assert strip_tags(html) == "通知 正文 ！".replace("  ", " ") or "evil" not in strip_tags(html)
    assert "script" not in strip_tags(html)


def test_hidden_value():
    page = '<input type="hidden" id="workEnc" value="ABC123" /><input id="enc" value="xyz">'
    assert hidden_value(page, "workEnc") == "ABC123"
    assert hidden_value(page, "enc") == "xyz"
    assert hidden_value(page, "missing") == ""


def test_parse_courses():
    courses = parse_courses(COURSE_HTML)
    assert len(courses) == 2  # 重复链接去重
    assert courses[0]["name"] == "机器学习综合设计"
    assert courses[0]["teacher"] == "黄一桂"
    assert courses[0]["courseid"] == "247085333"
    assert courses[1]["name"] == "数字电路"


def test_parse_materials():
    items = parse_materials(MATERIAL_HTML)
    assert items[0] == {"type": "doc", "name": "实验指导书",
                        "data_id": 10001, "enc": "abc123"}
    assert items[1]["type"] == "afolder"
    assert items[1]["enc"] == "enc456"


def test_parse_cd_filename():
    # 裸 UTF-8 字节（学习通 CDN 的实际行为）
    raw_name = "实验指导书.pdf".encode("utf-8").decode("latin-1")
    assert parse_cd_filename(f"attachment; filename*=UTF-8''{raw_name}") == "实验指导书.pdf"
    # 标准引号形式
    assert parse_cd_filename('attachment; filename="report.pdf"') == "report.pdf"
    # 无文件名
    assert parse_cd_filename("attachment") == ""


def test_sanitize_filename():
    assert sanitize_filename("  实验指导书.pdf ") == "实验指导书.pdf"
    # 防路径穿越
    assert "/" not in sanitize_filename("../../etc/passwd")
    assert "\\" not in sanitize_filename("..\\..\\win.ini")
    assert sanitize_filename("") == "download.bin"
    assert sanitize_filename("...") == "download.bin"
    assert len(sanitize_filename("长" * 500)) <= 120


def test_week_in_schedule():
    assert week_in_schedule("1,2,3", 2)
    assert not week_in_schedule("1,2,3", 4)
    assert week_in_schedule("1-16", 16)
    assert not week_in_schedule("1-16", 17)
    assert week_in_schedule("1-5,8,10-12", 11)
    assert week_in_schedule("1-5,8,10-12", 8)
    assert not week_in_schedule("1-5,8,10-12", 6)
    # 容错：空/乱格式不抛异常
    assert not week_in_schedule("", 1)
    assert not week_in_schedule("abc", 1)


HOMEWORK_DETAIL_HTML = """
<html><head><title>作业详情</title></head><body>
<div>作业详情</div> <h2>实验4 整体调试实验报告</h2>
<span>题量: 1</span> <span>满分: 100</span>
<span>作答时间: 06-21 18:51 至 07-01 18:51</span>
<div>智能分析 68 分</div>
</body></html>
"""


def test_parse_homework_detail():
    d = parse_homework_detail(HOMEWORK_DETAIL_HTML)
    assert d["title"] == "实验4 整体调试实验报告"
    assert d["question_count"] == 1
    assert d["full_score"] == 100
    assert d["start_time"] == "06-21 18:51"
    assert d["deadline"] == "07-01 18:51"
    assert d["score"] == "68"
    # 空页面不抛异常，字段为 None
    d2 = parse_homework_detail("<html></html>")
    assert d2["title"] is None and d2["deadline"] is None


# ---------------------------------------------------------------- v1.2.0 新功能

def test_expand_weeks():
    assert expand_weeks("1,2,3") == [1, 2, 3]
    assert expand_weeks("1-4") == [1, 2, 3, 4]
    assert expand_weeks("1-3,5,8-9") == [1, 2, 3, 5, 8, 9]
    # 去重与容错
    assert expand_weeks("2,2,2") == [2]
    assert expand_weeks("") == []
    assert expand_weeks("abc") == []
    # 与 week_in_schedule 结论一致
    for w in range(1, 18):
        assert (w in expand_weeks("1-5,8,10-12")) == week_in_schedule("1-5,8,10-12", w)


def test_compress_weeks():
    # expand 的逆运算
    assert compress_weeks([1, 2, 3]) == "1-3"
    assert compress_weeks([1, 2, 3, 5, 8, 9]) == "1-3,5,8-9"
    assert compress_weeks([4]) == "4"
    assert compress_weeks([]) == ""
    # 去重 + 乱序
    assert compress_weeks([3, 1, 2, 2]) == "1-3"
    # 与 expand 严格互逆
    for s in ("1-16", "1-5,8,10-12", "3", "1,3,5"):
        assert compress_weeks(expand_weeks(s)) == s


def test_ms_to_date():
    # 探索实测：2026-2027-1 学期第 1 周周一 = 1788105600000 ms（北京时区）
    assert ms_to_date(1788105600000) == date(2026, 8, 31)
    assert ms_to_date(1788105600000).weekday() == 0  # 周一


def test_parse_section_times():
    times = parse_section_times(["8:00-8:50", "9:00-9:50", "22:00-22:50"])
    assert times[0][0].hour == 8 and times[0][0].minute == 0
    assert times[0][1].hour == 8 and times[0][1].minute == 50
    assert times[2][0].hour == 22
    assert parse_section_times(None) == []
    assert parse_section_times(["垃圾"]) == []


def test_nearest_datetime_for():
    today = date(2026, 9, 15)
    # 普通未来截止
    assert nearest_datetime_for("12-30 23:59", today) is not None
    assert nearest_datetime_for("12-30 23:59", today).year == 2026
    # 跨年：1 月截止应补成下一年
    d = nearest_datetime_for("01-10 09:00", today)
    assert d is not None and d.year == 2027
    # 刚过去几天的（如 09-10）补成今年
    assert nearest_datetime_for("09-10 08:00", today).year == 2026
    # 非法输入
    assert nearest_datetime_for("垃圾", today) is None
    assert nearest_datetime_for("13-40 25:00", today) is None


def test_is_homework_pending():
    # 已提交（含待批阅/已批阅）与已完成不算未完成
    for s in ("已完成", "待批阅", "已批阅", "已提交", "已批改"):
        assert not is_homework_pending(s), s
    # 待提交/未提交/进行中/已截止/空 都算需要关注
    for s in ("待提交", "未提交", "进行中", "已截止", "", None):
        assert is_homework_pending(s), repr(s)


def test_escape_ics():
    assert escape_ics("a;b,c") == r"a\;b\,c"
    assert escape_ics("行1\n行2") == r"行1\n行2"
    assert escape_ics(" back \\ slash") == " back \\\\ slash"


def test_widget_helpers():
    # 今天的课：第 1 周周二（2026-09-01）第 1-2 节 8:00-9:50
    curriculum = {
        "firstWeekDate": 1788105600000,
        "lessonTimeConfigArray": ["8:00-8:50", "9:00-9:50", "10:10-11:00"],
    }
    lessons = [{"name": "数字信号处理", "location": "北主楼402", "teacherName": "张",
                "dayOfWeek": 2, "beginNumber": 1, "length": 2}]
    rows = lesson_rows(lessons, curriculum, 1, date(2026, 9, 1))
    assert len(rows) == 1
    assert rows[0]["start"] == datetime(2026, 9, 1, 8, 0)
    assert rows[0]["end"] == datetime(2026, 9, 1, 9, 50)
    # 不是今天的课（周三）查不到
    assert lesson_rows(lessons, curriculum, 1, date(2026, 9, 2)) == []
    # 缺关键字段返回空列表不抛异常
    assert lesson_rows(lessons, {}, 1, date(2026, 9, 1)) == []
    # 正在上/下一节判定
    cur, nxt = pick_current_next(rows, datetime(2026, 9, 1, 8, 30))
    assert cur is rows[0] and nxt is None
    cur, nxt = pick_current_next(rows, datetime(2026, 9, 1, 7, 30))
    assert cur is None and nxt is rows[0]
    cur, nxt = pick_current_next(rows, datetime(2026, 9, 1, 11, 0))
    assert cur is None and nxt is None

    # 倒计时文案
    assert fmt_countdown(timedelta(minutes=45)) == "45 分钟"
    assert fmt_countdown(timedelta(hours=3)) == "3 小时"
    assert fmt_countdown(timedelta(hours=3, minutes=5)) == "3 小时 05 分"
    assert fmt_countdown(timedelta(days=1, hours=3)) == "1 天 3 小时"
    assert fmt_countdown(timedelta(minutes=-2)) == "已过期"

    # 按显示宽度截断（全角2/半角1）
    assert ellipsize("短标题") == "短标题"
    r = ellipsize("《数字电路与逻辑设计》具体座位安排附件下载地址与注意事项说明")
    assert r.endswith("…") and len(r) <= 27  # 限 50 单位 ≈ 25 全角字 + …
    assert ellipsize("abcdefgh", 10) == "abcdefgh"


def test_build_ics():
    curriculum = {
        "firstWeekDate": 1788105600000,  # 2026-08-31（周一）
        "lessonTimeConfigArray": ["8:00-8:50", "9:00-9:50", "10:10-11:00"],
    }
    lessons = [{
        "name": "测试课程;甲", "location": "北主楼,604", "teacherName": "张三",
        "dayOfWeek": 2, "beginNumber": 1, "length": 2, "weeks": "1-2",
        "lessonId": 999,
    }]
    ics = build_ics(lessons, curriculum, cal_name="我的;课表")
    # RFC 5545：CRLF 行尾；VEVENT 每周一条
    assert ics.count("\r\n") > 10 and "\r\nBEGIN:VEVENT" in ics
    assert ics.count("BEGIN:VEVENT") == 2
    # 第 1 周周二（dayOfWeek=2）= 2026-09-01，第 1-2 节 8:00 → 9:50
    assert "DTSTART:20260901T080000" in ics
    assert "DTEND:20260901T095000" in ics
    # 第 2 周周二 = 2026-09-08
    assert "DTSTART:20260908T080000" in ics
    # 文本转义与日历名
    assert r"SUMMARY:测试课程\;甲" in ics
    assert r"LOCATION:北主楼\,604" in ics
    assert "X-WR-CALNAME:我的\\;课表" in ics
    # 30 分钟前提醒
    assert "TRIGGER:-PT30M" in ics
    # 缺关键字段时明确报错而不是生成空日历
    try:
        build_ics(lessons, {"lessonTimeConfigArray": ["8:00-8:50"]})
        raise SystemExit("缺少 firstWeekDate 应报错")
    except RuntimeError:
        pass


# ---------------------------------------------------------------- v1.3.x CLI 新逻辑

COURSE_HTML_V2 = """
<a href="https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268423854&clazzid=157979904&cpi=412061369&ismooc2=1&v=2" target="_blank">
  <span class="course-name overHidden2" style="word-break: break-all;" title="新能源汽车发展">新能源汽车发展</span>
</a>
<p class="margint10 line2 color2" title="五邑大学智慧教学系统">五邑大学智慧教学系统</p>
<p class="line2 color3" title="李昌明">李昌明</p>
"""


def test_parse_courses_teacher_line2_color3():
    """2026 版课程列表：老师在 <p class="line2 color3" title="X">（color2 是学校）。"""
    courses = parse_courses(COURSE_HTML_V2)
    assert len(courses) == 1
    assert courses[0]["teacher"] == "李昌明"
    assert courses[0]["courseid"] == "268423854"
    # 旧版 overHidden2 结构仍兼容（run_tests 顶部的 COURSE_HTML 已覆盖）


def test_is_antispider_location():
    assert is_antispider_location("https://mooc1.chaoxing.com/antispiderShowVerify.ac")
    assert is_antispider_location("/antispiderShowVerify.ac")
    assert not is_antispider_location("https://pan-yz.cldisk.com/r/123")
    assert not is_antispider_location("")
    assert not is_antispider_location(None)


def test_cached_schedule_freshness():
    """today 的 24h 新鲜度判定：<24h 命中、>=24h 过期、无 saved_at 不命中、
    不给 max_age_h 时只要有 lessons 就命中（week/ics 语义）。"""
    import json as _json
    import tempfile
    from pathlib import Path
    from xuexitong_mcp import cli as xcli

    def make(saved_at):
        fd, name = tempfile.mkstemp(suffix=".json")
        os.close(fd)   # Windows：不关句柄，后续写/删同一路径会 WinError 32
        f = Path(name)
        sc = {"lessons": [{"name": "x", "dayOfWeek": 1}],
              "curriculum": {"firstWeekDate": 1788105600000}}
        if saved_at is not None:
            sc["saved_at"] = saved_at
        f.write_text(_json.dumps({"schedule_cache": sc}), encoding="utf-8")
        return f

    now = datetime.now()
    fresh = make(now.strftime("%Y-%m-%dT%H:%M:%S"))
    stale = make((now - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%S"))
    nosaved = make(None)
    missing = Path(tempfile.mkdtemp()) / "nope.json"
    try:
        assert xcli._cached_schedule(max_age_h=24, path=fresh) is not None
        assert xcli._cached_schedule(max_age_h=24, path=stale) is None
        assert xcli._cached_schedule(max_age_h=24, path=nosaved) is None
        assert xcli._cached_schedule(path=missing) is None
        # 无龄限：过期缓存也命中（week/ics 用）
        assert xcli._cached_schedule(path=stale) is not None
    finally:
        for f in (fresh, stale, nosaved):
            f.unlink(missing_ok=True)


def test_current_week_derived_from_first_week_date():
    """教学周由 firstWeekDate 推导（缓存的 realCurrentWeek 是存盘时的值），
    越界回退服务端周数。"""
    from xuexitong_mcp import cli as xcli
    cur = {"firstWeekDate": 1788105600000, "maxWeek": 25}  # 2026-08-31 周一
    assert xcli._current_week({"curriculum": cur}, date(2026, 10, 26)) == 9
    assert xcli._current_week({"curriculum": cur}, date(2026, 8, 31)) == 1
    # 学期末之后按 maxWeek 封顶 → 回退服务端字段
    fallback = {"curriculum": {"firstWeekDate": 1788105600000,
                               "maxWeek": 16, "realCurrentWeek": 12}}
    assert xcli._current_week(fallback, date(2027, 3, 1)) == 12
    # 无锚点日期：直接用服务端周数
    assert xcli._current_week(
        {"curriculum": {"currentWeek": 7}}, date(2026, 10, 26)) == 7


def test_json_output_format():
    """--json 输出契约：datetime → "YYYY-MM-DD HH:MM"、无颜色码、UTF-8 中文原样。"""
    import io
    import json as _json
    from contextlib import redirect_stdout
    from xuexitong_mcp import cli as xcli

    buf = io.StringIO()
    with redirect_stdout(buf):
        xcli._print_json([{"start": xcli._jdt(datetime(2026, 10, 26, 14, 0)),
                           "name": "电磁场与微波技术", "deadline": xcli._jdt(None)}])
    out = buf.getvalue()
    assert "\033[" not in out                      # 无颜色码
    data = _json.loads(out)
    assert data[0]["start"] == "2026-10-26 14:00"   # 统一时间格式
    assert data[0]["deadline"] is None
    assert data[0]["name"] == "电磁场与微波技术"     # ensure_ascii=False


def run_all() -> int:
    """零依赖测试运行器。"""
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"ERROR {name}: {e.__class__.__name__}: {e}")
    print(f"\n{failed} failed" if failed else "\n全部通过")
    return failed


if __name__ == "__main__":
    rc = 1 if run_all() else 0
    # 两个独立测试文件（assistant 侧 / weekgrid 侧）一并串跑
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    for extra in ("test_assistant.py", "test_weekgrid.py"):
        r = subprocess.run([sys.executable, os.path.join(here, extra)])
        rc = rc or r.returncode
    sys.exit(rc)
