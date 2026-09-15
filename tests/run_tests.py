# -*- coding: utf-8 -*-
"""chaoxing-mcp 纯逻辑单元测试。

零依赖可直接运行：  python tests/run_tests.py
也可用 pytest：     pytest tests/ -v
（不发起任何网络请求，只测解析与加解密等纯函数。）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chaoxing_mcp.client import (  # noqa: E402
    aes_encrypt, aes_decrypt, build_ics, compress_weeks, escape_ics,
    expand_weeks, hidden_value, is_homework_pending, ms_to_date,
    nearest_datetime_for, parse_cd_filename, parse_courses,
    parse_homework_detail, parse_materials, parse_section_times,
    sanitize_filename, strip_tags, week_in_schedule,
)
from datetime import date  # noqa: E402

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
    sys.exit(1 if run_all() else 0)
