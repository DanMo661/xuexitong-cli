# -*- coding: utf-8 -*-
"""学习通（超星）HTTP 客户端：会话管理、登录、全部数据接口。

本模块只负责"取数据并解析成结构化对象"，不负责文案渲染——
MCP 工具层的可读文本输出见 server.py。

所有请求自动携带本地持久化 cookie；遇到登录态失效会自动重登录并重试一次。
凭据解析优先级：显式参数 > 环境变量 CHAOXING_PHONE/CHAOXING_PASSWORD > config.json。
"""

from __future__ import annotations

import base64
import html as html_mod
import json
import os
import re
import time
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import unquote
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# ---------------------------------------------------------------- 常量

TIMEOUT = 20.0            # 常规接口超时（秒）
DOWNLOAD_TIMEOUT = (10.0, 120.0)  # 下载：(连接, 读取) 分别限时
LOGIN_STATE_TTL = 300.0   # 登录探测结果缓存 5 分钟，减少每工具一次的探测请求
COURSES_CACHE_TTL = 300.0  # 课程列表缓存 5 分钟（同一对话内反复查课名免重复拉全页）

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36")
AES_KEY = AES_IV = b"u2oh6Vu^HWe4_AES"

URL_LOGIN = "https://passport2.chaoxing.com/fanyalogin"
URL_BASE = "https://i.chaoxing.com/base"
URL_SCHEDULE = "https://kb.chaoxing.com/pc/curriculum/getMyLessons"
URL_COURSELIST = "https://mooc2-ans.chaoxing.com/mooc2-ans/visit/courselistdata"
URL_STUMIDDLE = "https://mooc1.chaoxing.com/visit/stucoursemiddle"
URL_DATALIST = "https://mooc2-ans.chaoxing.com/mooc2-ans/coursedata/stu-datalist"
URL_DOWNLOAD = "https://mooc1.chaoxing.com/coursedata/downloadData"
URL_WORKLIST = "https://mooc1.chaoxing.com/mooc2/work/list"
URL_EXAMLIST = "https://mooc1-api.chaoxing.com/exam-ans/exam/test/examcode/examlist"
URL_CHAPTER = "https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse"
URL_NOTICELIST = "https://notice.chaoxing.com/pc/notice/getNoticeList"
URL_PAN_INDEX = "https://pan-yz.cldisk.com/pcuserpan/index"
URL_PAN_LIST = "https://pan-yz.cldisk.com/opt/listres"

LOGIN_MARKERS = ("passport2.chaoxing.com/login", "用户登录")


# ---------------------------------------------------------------- 纯函数（可独立单测）

def aes_encrypt(text: str) -> str:
    """学习通登录参数的 AES-128-CBC/PKCS7 加密 + base64（key=iv 固定值）。"""
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return base64.b64encode(cipher.encrypt(pad(text.encode("utf-8"), 16))).decode()


def aes_decrypt(b64_text: str) -> str:
    """逆运算（单测校验用，业务流程用不到）。"""
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    raw = base64.b64decode(b64_text)
    return unpad(cipher.decrypt(raw), 16).decode("utf-8")


def strip_tags(text: str) -> str:
    """去掉 script/style/HTML 标签并压缩空白，得到可读纯文本。"""
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html_mod.unescape(" ".join(text.split()))


def hidden_value(page_html: str, input_id: str) -> str:
    """提取页面里 <input type="hidden" id="X" value="Y"> 的 value。"""
    m = re.search(r'id="%s"[^>]*value="([^"]*)"' % input_id, page_html) or \
        re.search(r'value="([^"]*)"[^>]*id="%s"' % input_id, page_html)
    return m.group(1) if m else ""


def parse_courses(html: str) -> list[dict]:
    """从 courselistdata 页面 HTML 解析课程列表。

    返回 [{name, teacher, courseid, clazzid, cpi}]，按出现顺序去重。
    """
    courses, seen = [], set()
    for m in re.finditer(r"stucoursemiddle\?courseid=(\d+)&clazzid=(\d+)&cpi=(\d+)", html):
        cid, clazz, cpi = m.groups()
        if (cid, clazz, cpi) in seen:
            continue
        seen.add((cid, clazz, cpi))
        seg = html[m.end():m.end() + 1600]
        nm = re.search(r'course-name[^>]*title="([^"]+)"', seg)
        teacher = ""
        for pm in re.finditer(r'<p class="overHidden2"[^>]*>([^<]{2,15})</p>', seg):
            txt = pm.group(1).strip()
            if txt and txt != (nm.group(1) if nm else ""):
                teacher = txt
                break
        courses.append({
            "name": html_mod.unescape(nm.group(1)) if nm else "?",
            "teacher": html_mod.unescape(teacher),
            "courseid": cid, "clazzid": clazz, "cpi": cpi,
        })
    return courses


def parse_materials(html: str) -> list[dict]:
    """解析资料区 datalist 页面，返回 [{type, name, data_id, enc}]。

    type 为 "afolder"（文件夹，enc 用于下钻）或文件类型名（如 doc/pdf/ppt）。
    """
    items = []
    for m in re.finditer(
            r"<dt onclick=\"toOpen\('([^']*)','([^']*)',(\d+),'([^']*)',\s*"
            r"'([^']*)','([^']*)',([^,]+),([^,]+),'([^']*)','([^']*)'", html):
        raw_name, dtype, dataid, fenc = m.group(1), m.group(2), m.group(3), m.group(10)
        items.append({"type": dtype, "name": unquote(raw_name),
                      "data_id": int(dataid), "enc": fenc})
    return items


def parse_cd_filename(content_disposition: str) -> str:
    """从 Content-Disposition 还原文件名。

    学习通 CDN 的 filename* 常是"裸 UTF-8 字节"而非标准百分号编码，
    requests 按 latin-1 解码后需还原 bytes 再按 utf-8 解一次。
    """
    m = re.search(r"filename\*=(?:UTF-8|utf-8)''([^;]+)", content_disposition)
    if not m:
        m = re.search(r'filename="?([^";]+)"?', content_disposition)
    if not m:
        return ""
    raw = m.group(1).strip()
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return unquote(raw)


def sanitize_filename(name: str, fallback: str = "download.bin") -> str:
    """把服务器给的文件名清理成安全的本地文件名（防路径穿越与非法字符）。"""
    name = name.strip().strip(".").replace("..", "_")
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = " ".join(name.split())
    return (name or fallback)[:120]


def week_in_schedule(weeks_str: str, week: int) -> bool:
    """课表 lessons 的 weeks 字段（"1,2,3" / "1-16" / "1-5,8,10-12"）是否包含 week。"""
    for part in str(weeks_str or "").split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            if a.strip().isdigit() and b.strip().isdigit() and int(a) <= week <= int(b):
                return True
        elif part.isdigit() and int(part) == week:
            return True
    return False


def parse_homework_detail(html: str) -> dict:
    """从作业详情页（mooc-ans/mooc2/work/task）提取结构化信息。

    页面为服务端渲染 + 前端填充混合，strip 后文本形如：
    "作业详情 实验4 整体调试实验报告 题量: 1 满分: 100
     作答时间: 06-21 18:51 至 07-01 18:51 智能分析 68 分 ..."
    解析不到的字段保持 None（不同题型页面结构有差异，尽力而为不报错）。
    """
    text = strip_tags(html)
    out = {"title": None, "question_count": None, "full_score": None,
           "start_time": None, "deadline": None, "score": None}
    # 标题夹在最后一个"作业详情"标记与"题量"之间（页面 <title> 也含"作业详情"，
    # 所以不能直接取第一个标记）
    m = re.search(r"题量[:：]", text)
    if m:
        head = text[:m.start()]
        k = head.rfind("作业详情")
        if k >= 0:
            title = head[k + 4:].strip()
            if title:
                out["title"] = title
    m = re.search(r"题量[:：]\s*(\d+)", text)
    if m:
        out["question_count"] = int(m.group(1))
    m = re.search(r"满分[:：]\s*(\d+)", text)
    if m:
        out["full_score"] = int(m.group(1))
    m = re.search(r"作答时间[:：]\s*(\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2})\s*至\s*"
                  r"(\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2})", text)
    if m:
        out["start_time"], out["deadline"] = m.group(1), m.group(2)
    m = (re.search(r"智能分析\s*(\d+(?:\.\d+)?)\s*分", text)
         or re.search(r"(?:得分|总评|成绩|批阅)[:：]?\s*(\d+(?:\.\d+)?)\s*分", text))
    if m:
        out["score"] = m.group(1)
    return out


# ---------------------------------------------------------------- 客户端

@dataclass
class AuthResult:
    ok: bool
    msg: str


class ChaoxingClient:
    """学习通 Web 端接口客户端（只读）。

    会话cookie 持久化到 config_dir/session_cookies.json，跨进程复用免登录。
    """

    def __init__(self, config_dir: str | None = None,
                 phone: str | None = None, password: str | None = None,
                 timeout: float = TIMEOUT):
        if config_dir is None:
            # 默认凭据目录：仓库根目录（config.example.json 所在层）优先，
            # 其次包目录本身——兼容两种放置习惯，向上都不会再远
            pkg_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(pkg_dir)
            config_dir = next(
                (d for d in (root_dir, pkg_dir)
                 if os.path.exists(os.path.join(d, "config.json"))), root_dir)
        self.config_dir = config_dir
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.cookie_file = os.path.join(self.config_dir, "session_cookies.json")
        self.timeout = timeout
        self._explicit_phone = phone
        self._explicit_password = password
        self._login_checked_at = 0.0  # 登录探测缓存时间戳
        self._courses_cache: list[dict] | None = None
        self._courses_cache_at = 0.0
        self.session = self._build_session()

    # ---------------- 会话与登录 ----------------

    def _build_session(self) -> requests.Session:
        """带 UA、重试策略与本地 cookie 的会话。"""
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        retry = Retry(total=2, backoff_factor=0.5,
                      status_forcelist=(429, 502, 503, 504),
                      allowed_methods=frozenset(["GET", "POST"]))
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, encoding="utf-8") as f:
                    s.cookies.update(json.load(f))
            except Exception:
                pass
        return s

    def _load_credentials(self) -> tuple[str | None, str | None]:
        """凭据来源：显式参数 > 环境变量 > config.json。"""
        phone = self._explicit_phone or os.environ.get("CHAOXING_PHONE")
        password = self._explicit_password or os.environ.get("CHAOXING_PASSWORD")
        if phone and password:
            return phone, password
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, encoding="utf-8") as f:
                    cfg = json.load(f)
                return cfg.get("phone"), cfg.get("password")
            except Exception:
                pass
        return None, None

    def _save_cookies(self) -> None:
        try:
            cookies = {c.name: c.value for c in self.session.cookies}
            with open(self.cookie_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f)
        except Exception:
            pass

    def login(self, phone: str | None = None, password: str | None = None) -> AuthResult:
        """账号密码登录；成功后 cookie 持久化并刷新登录探测缓存。"""
        if not phone or not password:
            phone, password = self._load_credentials()
        if not phone or not password:
            return AuthResult(False, "未提供凭据（config.json / 环境变量 / 参数均无）")
        r = self.session.post(
            URL_LOGIN,
            data={
                "fid": "-1",
                "uname": aes_encrypt(phone),
                "password": aes_encrypt(password),
                "refer": "https%3A%2F%2Fi.chaoxing.com",
                "t": "true",
                "forbidotherlogin": "0",
                "validate": "",
                "doubleFactorLogin": "0",
                "independentId": "0",
            },
            timeout=self.timeout,
        )
        try:
            body = r.json()
            ok = body.get("status") is True
            msg = body.get("msg2") or ("登录成功" if ok else "登录失败(账号密码错误或需验证码)")
        except Exception:
            ok, msg = False, "登录响应异常: " + r.text[:120]
        if ok:
            self._save_cookies()
            self._login_checked_at = time.time()
        return AuthResult(ok, msg)

    def ensure_login(self, force: bool = False) -> AuthResult:
        """cookie 有效则直接用；否则用已配置凭据登录。force=True 跳过探测缓存。"""
        if not force and time.time() - self._login_checked_at < LOGIN_STATE_TTL:
            return AuthResult(True, "cookie 有效")
        try:
            r = self.session.get(URL_BASE, timeout=self.timeout)
            if not any(marker in r.url or marker in r.text for marker in LOGIN_MARKERS):
                self._login_checked_at = time.time()
                return AuthResult(True, "cookie 有效")
        except Exception:
            pass
        res = self.login()
        if res.ok:
            return res
        return AuthResult(False, "未登录且自动登录失败：" + res.msg +
                                "（请调用 login 工具或检查 config.json）")

    # ---------------- HTTP（登录态失效自动重登一次） ----------------

    def _is_login_redirect(self, resp: requests.Response) -> bool:
        return any(marker in resp.url or marker in resp.text for marker in LOGIN_MARKERS)

    def get(self, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", self.timeout)
        r = self.session.get(url, **kw)
        if self._is_login_redirect(r):
            if self.ensure_login(force=True).ok:
                r = self.session.get(url, **kw)
        return r

    def post(self, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", self.timeout)
        r = self.session.post(url, **kw)
        if self._is_login_redirect(r):
            if self.ensure_login(force=True).ok:
                r = self.session.post(url, **kw)
        return r

    # ---------------- 数据接口（返回结构化数据） ----------------

    def fetch_courses(self, refresh: bool = False) -> list[dict]:
        """我学的课程列表（带 5 分钟缓存；refresh=True 强制重新拉取）。"""
        now = time.time()
        if (not refresh and self._courses_cache is not None
                and now - self._courses_cache_at < COURSES_CACHE_TTL):
            return self._courses_cache
        base = self.get(URL_BASE).text
        m = (re.search(r'"fid"\s*:\s*"?(\d+)"?', base)
             or re.search(r"var fid = '(\d+)'", base))
        fid = m.group(1) if m else "427"
        r = self.get(URL_COURSELIST, params={
            "courseType": 1, "courseFid": fid,
            "courseTeacherid": 0, "courseOrderBy": 0})
        self._courses_cache = parse_courses(r.text)
        self._courses_cache_at = now
        return self._courses_cache

    def find_course(self, keyword: str) -> dict | None:
        """按课名关键词匹配一门课（精确同名优先，否则取第一个包含者）。

        注意必须先扫精确、再扫包含：若单循环无 break 一路扫到底，
        best 会被后面的命中覆盖，多门课同名时返回最后一门而非第一门
        （旧版单文件版就带着这个 bug，v1.1.0 修复）。
        """
        courses = self.fetch_courses()
        for c in courses:
            if keyword == c["name"]:
                return c
        for c in courses:
            if keyword in c["name"]:
                return c
        return None

    def fetch_course_page(self, c: dict) -> str:
        """课程中间页 HTML（stucoursemiddle），含 enc/openc/workEnc 等隐藏域。"""
        return self.get(URL_STUMIDDLE, params={
            "courseid": c["courseid"], "clazzid": c["clazzid"], "cpi": c["cpi"],
            "ismooc2": 1, "v": 2}).text

    def fetch_profile(self) -> dict:
        """个人资料：姓名/学校/uid/fid/学期信息。"""
        base = self.get(URL_BASE).text
        name = (re.search(r'aria-label="账号：([^"<]{1,20})"', base)
                or re.search(r"账号：([^<\s]{1,20})", base))
        school = re.search(r'id="siteName"[^>]*title="([^"]+)"', base)
        uid = re.search(r"var uid =\s*'?(\d+)'?", base)
        fid = (re.search(r'"fid"\s*:\s*"?(\d+)"?', base)
               or re.search(r"var fid = '(\d+)'", base))
        profile = {
            "name": name.group(1) if name else "?",
            "school": school.group(1) if school else "?",
            "uid": uid.group(1) if uid else "?",
            "fid": fid.group(1) if fid else "?",
        }
        try:
            cur = self.post(URL_SCHEDULE, data={}).json().get("data", {}).get("curriculum") or {}
            if cur.get("userName"):
                profile["schoolYear"] = cur.get("schoolYear")
                profile["semester"] = cur.get("semester")
        except Exception:
            pass
        return profile

    def fetch_schedule(self) -> dict:
        """本学期课表：{curriculum: {...}, lessons: [...]}。"""
        j = self.post(URL_SCHEDULE, data={}).json()
        if j.get("result") != 1:
            raise RuntimeError("课表接口返回失败: " + str(j.get("msg")))
        data = j.get("data") or {}
        return {"curriculum": data.get("curriculum") or {},
                "lessons": data.get("lessonArray") or []}

    def fetch_materials(self, c: dict, folder_data_id: int = 0, folder_enc: str = "") -> list[dict]:
        """课程资料区文件列表（folder_data_id+folder_enc 下钻子文件夹）。"""
        params = {"courseid": c["courseid"], "clazzid": c["clazzid"],
                  "cpi": c["cpi"], "ut": "s"}
        if folder_data_id:
            params.update({"dataId": folder_data_id, "enc": folder_enc})
        r = self.get(URL_DATALIST, params=params)
        return parse_materials(r.text)

    def download_material(self, c: dict, data_id: int, save_dir: str,
                          filename: str = "") -> dict:
        """流式下载资料文件，返回 {path, size}。

        流程：downloadData 拿 302 签名 URL → 带 pan-yz Referer 请求 CDN
        （缺 Referer 会 403）→ 边下边写盘，不把大文件整个读进内存。
        """
        r = self.get(URL_DOWNLOAD, params={
            "dataId": data_id, "classId": c["clazzid"], "cpi": c["cpi"],
            "courseId": c["courseid"], "ut": "s"}, allow_redirects=False)
        if r.status_code != 302:
            raise RuntimeError(f"下载接口返回 {r.status_code}（dataId 可能不属于该课程）")
        cdn = r.headers.get("Location")
        if not cdn:
            raise RuntimeError("下载接口未返回 CDN 地址")
        os.makedirs(save_dir, exist_ok=True)
        cd = ""
        total = 0
        with self.session.get(cdn, headers={"Referer": "https://pan-yz.chaoxing.com/"},
                              stream=True, timeout=DOWNLOAD_TIMEOUT) as r2:
            if r2.status_code != 200:
                raise RuntimeError(f"CDN 下载失败: HTTP {r2.status_code}")
            cd = r2.headers.get("Content-Disposition", "")
            fname = filename or parse_cd_filename(cd) or f"{data_id}.bin"
            path = os.path.join(save_dir, sanitize_filename(fname))
            with open(path, "wb") as f:
                for chunk in r2.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
        return {"path": path, "size": total}

    def fetch_homework(self, c: dict) -> dict:
        """作业列表：{progress: (done,total)|None,
        items: [{index, title, status, url}]}，url 供 fetch_homework_detail 使用。

        作业列表的 enc 用课程页隐藏域 workEnc（页面 enc 不通用）。
        """
        page = self.fetch_course_page(c)
        work_enc = hidden_value(page, "workEnc")
        openc = hidden_value(page, "openc")
        page_enc = hidden_value(page, "enc")
        if not work_enc:
            raise RuntimeError("课程页未生成作业签名（workEnc），可能未开放作业功能")
        r = self.get(URL_WORKLIST, params={
            "courseId": c["courseid"], "classId": c["clazzid"], "cpi": c["cpi"],
            "ut": "s", "openc": openc, "enc": work_enc,
            "t": int(time.time() * 1000), "stuenc": page_enc, "isdisplaytable": 2})
        html = r.text
        if "没有此页面访问权限" in html:
            raise RuntimeError("作业页签名校验失败（动态 enc），请稍后重试")
        m_prog = re.search(r"<span>(\d+)/(\d+)</span>\s*</div>\s*</div>", html)
        items = re.findall(
            r'<li onclick="goTask\(this\);" data="([^"]+)"[\s\S]*?'
            r'<p class="overHidden2 fl">([^<]+)</p>[\s\S]*?<p class="status fl">([^<]*)</p>', html)
        return {
            "progress": (int(m_prog.group(1)), int(m_prog.group(2))) if m_prog else None,
            "items": [{"index": i + 1, "title": t.strip(), "status": s.strip(),
                       "url": unquote(u)}
                      for i, (u, t, s) in enumerate(items)],
        }

    def fetch_homework_detail(self, c: dict, index: int) -> dict:
        """按列表序号取单份作业的详情（题量/满分/作答起止时间/得分）。

        详情 URL 来自作业列表条目的 data 属性（work/task 页，带独立 enc，
        复用列表接口返回的 url 即可，无需再拼签名）。
        """
        items = self.fetch_homework(c)["items"]
        if not 1 <= index <= len(items):
            raise IndexError(f"作业序号越界：该课程共 {len(items)} 份作业")
        item = items[index - 1]
        if not item["url"].startswith("http"):
            raise RuntimeError("该作业无详情链接（可能未开放）")
        detail = parse_homework_detail(self.get(item["url"]).text)
        detail["index"] = index
        detail["status"] = item["status"]
        if not detail.get("title"):
            detail["title"] = item["title"]
        return detail

    def fetch_exams(self) -> list[list[str]]:
        """全校考试安排表（每行已去掉 HTML 标签的单元格文本）。"""
        r = self.get(URL_EXAMLIST)
        rows = []
        for row in re.findall(r'<tr[^>]*class="dataTr"[^>]*>([\s\S]*?)</tr>', r.text):
            tds = [html_mod.unescape(re.sub(r"<[^>]+>", "", td)).strip()
                   for td in re.findall(r"<td[^>]*>([\s\S]*?)</td>", row)]
            if len(tds) >= 9:
                rows.append(tds)
        return rows

    def fetch_chapters(self, c: dict) -> dict:
        """章节与任务点进度：{progress: (done,total)|None,
        nodes: [(level, text)]，level 0=一级章 1=二级小节}。"""
        page = self.fetch_course_page(c)
        page_enc = hidden_value(page, "enc")
        openc = hidden_value(page, "openc")
        r = self.get(URL_CHAPTER, params={
            "courseid": c["courseid"], "clazzid": c["clazzid"], "cpi": c["cpi"],
            "enc": page_enc, "openc": openc, "fromMiddle": 1, "ut": "s",
            "t": int(time.time() * 1000)})
        html = r.text
        if "没有此页面访问权限" in html:
            raise RuntimeError("章节页签名校验失败，请稍后重试")
        progress = None
        m_prog = re.search(r"已完成任务点:\s*<span[^>]*>(\d+)</span>/(\d+)", html)
        if m_prog:
            progress = (int(m_prog.group(1)), int(m_prog.group(2)))
        nodes: list[tuple[int, str]] = []
        # 一级章节（带序号的大章）
        chapter_titles = {}
        for m in re.finditer(
                r'<div class="catalog_num fl"><span><i><em[^>]*>(\d+)</em></i></span></div>\s*'
                r'<div class="catalog_name newCatalog_name"[^>]*>\s*<a class="clicktitle">\s*'
                r'<span title="([^"]*)"', html):
            chapter_titles[m.start()] = (m.group(1), html_mod.unescape(m.group(2)))
        # 二级小节（chapter_item，含任务点状态）
        sections = []
        for m in re.finditer(r'<div class="chapter_item"[^>]*title="([^"]*)"', html):
            seg = html[m.start():m.start() + 2200]
            end = seg.find("</li>")
            seg = seg[:end] if end > 0 else seg
            num = re.search(r'<span class="catalog_sbar">([\d.]+)</span>', seg)
            if not num:
                continue  # 一级章节自身的 chapter_item 外壳
            if "icon_yiwanc" in seg:
                status = "已完成"
            else:
                mp = re.search(r'<span class="catalog_points_yi">(\d+)</span>', seg)
                status = f"{mp.group(1)}个待完成" if mp else (
                    "未开放" if "暂未开放" in seg else "无任务点")
            sections.append((m.start(), num.group(1),
                             html_mod.unescape(m.group(1)), status))
        # 按文档顺序合并
        events = [(pos, 0, f"{num}. {title}") for pos, (num, title) in chapter_titles.items()]
        events += [(pos, 1, f"   {num} {title} | {status}")
                   for pos, num, title, status in sections]
        nodes = [(lvl, text) for _, lvl, text in sorted(events)]
        return {"progress": progress, "nodes": nodes}

    def fetch_notices(self, limit: int = 20, unread_only: bool = False) -> list[dict]:
        """通知中心列表（按 limit 翻页拉取，最多 5 页）。"""
        items, last_id = [], ""
        for _ in range(5):
            r = self.post(URL_NOTICELIST, data={
                "type": 0, "notice_type": 0, "lastValue": last_id, "sort": 0,
                "folderUUID": "", "kw": "", "startTime": "", "endTime": "",
                "gKw": "", "gName": "", "year": "", "tag": "", "fidsCode": "",
                "filterSenderPuids": "", "filterTags": ""})
            j = r.json()
            if not j.get("status"):
                raise RuntimeError("通知接口返回失败: " + str(j.get("msg") or j)[:120])
            data = j.get("notices") or {}
            page_items = data.get("list") or []
            items.extend(page_items)
            last_id = data.get("lastGetId") or ""
            if not page_items or data.get("lastPage") or len(items) >= limit:
                break
        if unread_only:
            items = [it for it in items if not it.get("isread")]
        return items[:limit]

    def fetch_pan_files(self, folder_id: str = "") -> dict:
        """个人云盘文件列表：{where, total, items: [{kind,name,size,id}]}。

        encstr/rootdir 每次会话都变，需从云盘首页提取。
        """
        index = self.get(URL_PAN_INDEX).text
        encstr = re.search(r'const encstr = "([0-9a-f]+)"', index)
        rootdir = re.search(r'const rootdir = "(\d+)"', index)
        puid = re.search(r'const currentPuid = "(\d+)"', index)
        if not (encstr and rootdir and puid):
            raise RuntimeError("云盘首页解析失败（签名字段缺失）")
        parent = folder_id or rootdir.group(1)
        r = self.get(URL_PAN_LIST, params={
            "puid": puid.group(1), "shareid": 0, "parentId": parent,
            "page": 1, "size": 100, "enc": encstr.group(1),
            "filterType": "", "orderField": "", "orderType": ""},
            headers={"Referer": URL_PAN_INDEX})
        j = r.json()
        lst = j.get("list") or []
        items = []
        for it in lst:
            if it.get("isfile"):
                size = it.get("filesize") or 0
                size_h = f"{size / 1048576:.1f}MB" if size >= 1048576 else f"{size / 1024:.0f}KB"
                items.append({"kind": "file", "name": it.get("name") or "?",
                              "size": size_h, "id": None})
            else:
                items.append({"kind": "folder", "name": it.get("name") or "?",
                              "size": None, "id": str(it.get("id"))})
        return {"where": "根目录" if not folder_id else f"文件夹 {folder_id}",
                "total": j.get("totalCount", len(lst)), "items": items}
