# -*- coding: utf-8 -*-
"""MCP 工具层：把 ChaoxingClient 的结构化数据渲染成可读文本。

工具与旧版单文件版完全同名同参，已注册过的 MCP 客户端配置无需改动。
"""

from __future__ import annotations

import functools

from mcp.server.fastmcp import FastMCP

from .client import ChaoxingClient, strip_tags
from . import __version__

mcp = FastMCP("chaoxing", instructions=(
    "学习通(超星)只读查询工具：课表、课程、资料、作业、考试、章节进度、"
    "通知、云盘、个人资料。本服务只做查询，不提供签到/刷课/答题等任何写入功能。"
    "未登录时所有工具会自动尝试用 config.json 或环境变量里的凭据登录。"
))

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


@functools.lru_cache(maxsize=1)
def _client() -> ChaoxingClient:
    """进程内共享一个客户端（连接复用 + cookie 持久化）。"""
    return ChaoxingClient()


def _fmt(exc: Exception) -> str:
    """把异常压成单行短消息，避免多行噪声进对话。"""
    return " ".join(str(exc).split()) or exc.__class__.__name__


# ---------------------------------------------------------------- 登录 / 资料 / 课表 / 课程

@mcp.tool()
def login(phone: str = "", password: str = "") -> str:
    """登录学习通（手机号+密码），成功后会话持久化到本地，供其他工具使用。
    不传参数时自动使用 config.json 或环境变量 CHAOXING_PHONE/CHAOXING_PASSWORD 中的凭据。"""
    s = _client()
    res = s.login(phone or None, password or None)
    if not res.ok:
        return "登录失败：" + res.msg
    name = ""
    try:
        profile = s.fetch_profile()
        name = profile.get("name") or ""
    except Exception:
        pass
    return f"登录成功：{name or phone or '已配置账号'}"


@mcp.tool()
def get_profile() -> str:
    """查询个人资料：姓名、学校、uid、fid、当前学年学期。
    学习通个人中心的学号字段接口已停用，故不含学号。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        p = s.fetch_profile()
        lines = [f"姓名: {p['name']}", f"学校: {p['school']}",
                 f"uid:  {p['uid']}", f"fid:  {p['fid']}"]
        if p.get("schoolYear"):
            lines.append(f"课表学期: {p['schoolYear']} 学年第 {p['semester']} 学期")
        return "\n".join(lines)
    except Exception as e:
        return f"查询个人资料失败: {_fmt(e)}"


@mcp.tool()
def get_schedule() -> str:
    """查询本学期课表（默认显示当前周）。返回 课程/星期/节次/教室 的可读文本。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        data = s.fetch_schedule()
    except Exception as e:
        return f"课表接口请求失败: {_fmt(e)}"
    cur = data["curriculum"]
    week = cur.get("realCurrentWeek") or cur.get("currentWeek")
    lines = [f"学期 {cur.get('schoolYear')} 第 {cur.get('semester')} 学期 | 当前第 {week} 周 "
             f"| 学号用户 {cur.get('userName')}"]
    rows = []
    for les in data["lessons"]:
        begin = int(les.get("beginNumber") or 0)
        length = int(les.get("length") or 1)
        rows.append({
            "课名": les.get("name") or les.get("displayCourseName") or "?",
            "星期": _WEEKDAYS[int(les.get("dayOfWeek", 0)) % 7],
            "节次": (f"第{begin}-{begin + length - 1}节" if length > 1 else f"第{begin}节"),
            "教室": les.get("location") or "",
            "老师": les.get("teacherName") or "",
            "周次": str(les.get("weeks") or ""),
        })
    rows.sort(key=lambda x: (_WEEKDAYS.index(x["星期"]),
                             int("".join(ch for ch in x["节次"] if ch.isdigit()) or 0)))
    for r in rows:
        lines.append(f"{r['星期']} {r['节次']:>8} | {r['课名']} | {r['教室']} | {r['老师']} | 周{r['周次']}")
    if not rows:
        lines.append("（本学期课表为空）")
    return "\n".join(lines)


@mcp.tool()
def list_courses() -> str:
    """列出我学的全部课程（含课程ID/班级ID/cpi，供资料与作业工具使用）。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        courses = s.fetch_courses()
    except Exception as e:
        return f"课程列表请求失败: {_fmt(e)}"
    lines = [f"共 {len(courses)} 门课（课名 | 老师 | courseid/clazzid/cpi）"]
    for c in sorted(courses, key=lambda c: -int(c["courseid"])):
        lines.append(f"{c['name']} | {c['teacher']} | {c['courseid']}/{c['clazzid']}/{c['cpi']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 资料

@mcp.tool()
def list_materials(course: str, folder_data_id: int = 0, folder_enc: str = "") -> str:
    """列出某门课的资料区文件。course 为课名关键词（如 "实践设计课"）。
    不传 folder 参数返回第一层；返回中每个 [文件夹] 带 dataId/enc，
    再以这两个值调用本工具即可进入该文件夹。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        found = s.find_course(course)
        if not found:
            return f"未找到包含「{course}」的课程，请用 list_courses 查看课名"
        items = s.fetch_materials(found, folder_data_id, folder_enc)
    except Exception as e:
        return f"查询资料失败: {_fmt(e)}"
    where = "第一层" if not folder_data_id else f"文件夹 {folder_data_id}"
    lines = [f"《{found['name']}》资料区（{where}）:"]
    for it in items:
        if it["type"] == "afolder":
            lines.append(f"[文件夹] {it['name']} → 再调本工具: "
                         f"folder_data_id={it['data_id']}, folder_enc={it['enc']}")
        else:
            lines.append(f"[{it['type']}] {it['name']} → "
                         f"download_material(course=课名, data_id={it['data_id']})")
    if not items:
        lines.append("（此层无内容）")
    return "\n".join(lines)


@mcp.tool()
def download_material(course: str, data_id: int, save_dir: str, filename: str = "") -> str:
    """下载资料区文件到本地。course 为课名关键词（同 list_materials），
    data_id 来自 list_materials 的返回；save_dir 为绝对路径。大文件流式写盘。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        found = s.find_course(course)
        if not found:
            return f"未找到包含「{course}」的课程"
        res = s.download_material(found, data_id, save_dir, filename)
    except Exception as e:
        return f"下载失败: {_fmt(e)}"
    return f"已保存: {res['path']} ({res['size']} 字节)"


# ---------------------------------------------------------------- 作业 / 考试 / 章节

@mcp.tool()
def list_homework(course: str) -> str:
    """查询某门课的作业列表（作业名/提交状态/完成进度）。
    course 为课名关键词（如 "数字电路"）。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        found = s.find_course(course)
        if not found:
            return f"未找到包含「{course}」的课程，请用 list_courses 查看课名"
        data = s.fetch_homework(found)
    except Exception as e:
        return f"查询作业失败: {_fmt(e)}"
    lines = [f"《{found['name']}》作业列表:"]
    if data["progress"]:
        lines.append(f"完成进度: {data['progress'][0]}/{data['progress'][1]}")
    for it in data["items"]:
        lines.append(f"- {it['title']} | {it['status'] or '状态未知'}")
    if not data["items"]:
        lines.append("（本课程暂无作业）")
    return "\n".join(lines)


@mcp.tool()
def list_exams() -> str:
    """查询考试列表（全校全部考试安排）：名称/时间/时长/考试状态/作答状态/分数。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        rows = s.fetch_exams()
    except Exception as e:
        return f"查询考试列表失败: {_fmt(e)}"
    lines = [f"共 {len(rows)} 场考试（名称 | 时间 | 时长min | 考试状态 | 作答状态 | 分数 | 方式）"]
    for tds in rows:
        lines.append(f"{tds[1]} | {tds[2]} | {tds[3]} | {tds[4]} | {tds[5]} | {tds[6]} | {tds[7]}")
    if not rows:
        lines.append("（无考试安排）")
    return "\n".join(lines)


@mcp.tool()
def list_chapters(course: str) -> str:
    """查询某门课的章节列表与任务点完成进度（学习进度统计）。
    course 为课名关键词。返回章节树和每个小节的任务点状态。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        found = s.find_course(course)
        if not found:
            return f"未找到包含「{course}」的课程，请用 list_courses 查看课名"
        data = s.fetch_chapters(found)
    except Exception as e:
        return f"查询章节失败: {_fmt(e)}"
    lines = [f"《{found['name']}》章节与任务点进度:"]
    if data["progress"]:
        done, total = data["progress"]
        pct = f"（{done * 100 // total}%）" if total else ""
        lines.append(f"总进度: 已完成任务点 {done}/{total}{pct}")
    if data["nodes"]:
        lines.extend(text for _, text in data["nodes"])
    else:
        lines.append("（本课程无章节内容）")
    return "\n".join(lines)


# ---------------------------------------------------------------- 通知 / 云盘

@mcp.tool()
def list_notices(unread_only: bool = False, limit: int = 20) -> str:
    """查询通知中心（收件箱）：作业/考试/教师/学校通知。
    unread_only=True 只看未读；limit 控制返回条数（每条含标题/发送人/时间/正文摘要）。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        items = s.fetch_notices(limit=limit, unread_only=unread_only)
    except Exception as e:
        return f"查询通知失败: {_fmt(e)}"
    lines = [f"通知中心（共取到 {len(items)} 条{', 仅未读' if unread_only else ''}）:"]
    for it in items:
        read_mark = "" if it.get("isread") else "[未读] "
        title = (it.get("title") or "").strip()
        content = strip_tags(it.get("content") or "")[:80]
        lines.append(f"- {read_mark}{title} | {it.get('createrName')} | {it.get('completeTime')}"
                     + (f"\n  摘要: {content}" if content else ""))
    if not items:
        lines.append("（无通知）")
    return "\n".join(lines)


@mcp.tool()
def list_pan_files(folder_id: str = "") -> str:
    """列出个人云盘文件。不传 folder_id 返回根目录；文件夹条目带 id，
    以该 id 作为 folder_id 再调本工具即可进入子文件夹。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        data = s.fetch_pan_files(folder_id)
    except Exception as e:
        return f"查询云盘失败: {_fmt(e)}"
    lines = [f"个人云盘（{data['where']}，共 {data['total']} 项）:"]
    for it in data["items"]:
        if it["kind"] == "file":
            lines.append(f"[文件] {it['name']} | {it['size']}")
        else:
            lines.append(f"[文件夹] {it['name']} → 再调本工具: folder_id={it['id']}")
    if not data["items"]:
        lines.append("（此层无内容）")
    return "\n".join(lines)


def main() -> None:
    """stdio 入口（python -m chaoxing_mcp / chaoxing-mcp 命令）。"""
    mcp.run()


if __name__ == "__main__":
    main()
