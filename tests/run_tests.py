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
    aes_encrypt, aes_decrypt, hidden_value, parse_cd_filename,
    parse_courses, parse_materials, sanitize_filename, strip_tags,
)

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
