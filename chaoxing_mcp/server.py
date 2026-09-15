# -*- coding: utf-8 -*-
"""MCP 工具层：把 ChaoxingClient 的结构化数据渲染成可读文本。

工具与旧版单文件版完全同名同参，已注册过的 MCP 客户端配置无需改动。
"""

from __future__ import annotations

import functools
import os
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP

from .client import (ChaoxingClient, strip_tags, week_in_schedule, ms_to_date)
from . import __version__

mcp = FastMCP("chaoxing", instructions=(
    "学习通(超星)只读查询工具：课表（含真实日期/导出 .ics 日历）、课程、资料（递归搜索）、"
    "作业（含截止时间/得分/全课程截止看板）、考试、章节进度（含全课程进度总览）、"
    "通知（含关键词搜索）、云盘、个人资料。本服务只做查询，"
    "不提供签到/刷课/答题等任何写入功能。未登录时所有工具会自动尝试用 "
    "config.json 或环境变量里的凭据登录。"
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
def get_schedule(week: int = 0) -> str:
    """查询本学期课表。week 不传或传 0 返回全学期汇总（同一节课合并成
    周次区间；首次需逐周拉取，稍慢，结果缓存 10 分钟）；传周数（如 3）
    只返回第 3 周的课，并给出每个安排的真实日期。
    星期按服务端协议"周一=1"解释（用下发 day 字段交叉验证过）。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        data = s.fetch_schedule(week) if week else s.fetch_schedule_full()
    except Exception as e:
        return f"课表接口请求失败: {_fmt(e)}"
    cur = data["curriculum"]
    week_now = cur.get("realCurrentWeek") or cur.get("currentWeek")
    head = (f"学期 {cur.get('schoolYear')} 第 {cur.get('semester')} 学期 | "
            f"当前第 {week_now} 周 | 学号用户 {cur.get('userName')}")
    first_monday = None
    try:
        if cur.get("firstWeekDate"):
            first_monday = ms_to_date(cur["firstWeekDate"])
    except Exception:
        pass
    if first_monday and week_now:
        span0 = first_monday + timedelta(days=(int(week_now) - 1) * 7)
        head += f" | 本周 {span0:%m-%d} ~ {span0 + timedelta(days=6):%m-%d}"
    if week:
        head += f" | 筛选：第 {week} 周"
        if not first_monday:
            head += "（缺学期起始日，无法显示日期）"
    else:
        head += " | 全学期汇总"
    lines = [head]
    rows = []
    for les in data["lessons"]:
        weeks_str = str(les.get("weeks") or "")
        if week and not week_in_schedule(weeks_str, week):
            continue
        begin = int(les.get("beginNumber") or 0)
        length = int(les.get("length") or 1)
        dow = int(les.get("dayOfWeek") or 1)  # 1=周一 … 7=周日
        weekday = _WEEKDAYS[(dow - 1) % 7]
        when = ""
        if week and first_monday:
            when = f"{first_monday + timedelta(days=(week - 1) * 7 + dow - 1):%m-%d} "
        rows.append({
            "课名": les.get("name") or les.get("displayCourseName") or "?",
            "星期": weekday,
            "节次": (f"第{begin}-{begin + length - 1}节" if length > 1 else f"第{begin}节"),
            "教室": les.get("location") or "",
            "老师": les.get("teacherName") or "",
            "周次": weeks_str,
            "when": when,
        })
    rows.sort(key=lambda x: (_WEEKDAYS.index(x["星期"]),
                             int("".join(ch for ch in x["节次"] if ch.isdigit()) or 0)))
    for r in rows:
        lines.append(f"{r['when']}{r['星期']} {r['节次']:>8} | {r['课名']} | "
                     f"{r['教室']} | {r['老师']} | 周{r['周次']}")
    if not rows:
        lines.append(f"（第 {week} 周无课）" if week else "（本学期课表为空）")
    return "\n".join(lines)


@mcp.tool()
def export_schedule_ics(save_dir: str, filename: str = "课表.ics") -> str:
    """把本学期课表导出为 .ics 日历文件（可导入手机/电脑日历 App），
    覆盖全学期所有周次的课。日期与上下课钟点均取自学校在服务端配置的
    学期起始日与真实节次表，每节课自带 30 分钟前提醒。save_dir 为绝对路径。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        from .client import build_ics
        data = s.fetch_schedule_full()
        ics = build_ics(data["lessons"], data["curriculum"],
                        cal_name=f"课表-{data['curriculum'].get('schoolYear', '')}")
    except Exception as e:
        return f"生成日历失败: {_fmt(e)}"
    try:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, filename)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(ics)
    except Exception as e:
        return f"写入文件失败: {_fmt(e)}"
    events = ics.count("BEGIN:VEVENT")
    return (f"已导出: {path}\n共 {events} 节课（含 30 分钟前提醒）。"
            f"导入日历 App 时选择该文件即可；时间为学校节次表的真实上下课时间。")


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
def find_materials(course: str, keyword: str, max_depth: int = 2) -> str:
    """在课程资料区按关键词递归搜索文件/文件夹名（不分大小写），
    最多下钻 max_depth 层。返回相对路径与下载提示，省去一层层翻文件夹。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        found = s.find_course(course)
        if not found:
            return f"未找到包含「{course}」的课程，请用 list_courses 查看课名"
        hits = s.fetch_materials_recursive(found, keyword, max(1, max_depth))
    except Exception as e:
        return f"搜索资料失败: {_fmt(e)}"
    lines = [f"《{found['name']}》资料区搜索「{keyword}」: 命中 {len(hits)} 项"]
    for it in hits:
        if it["type"] == "afolder":
            lines.append(f"[文件夹] {it['path']} → 可用 list_materials 进入后逐个下载")
        else:
            lines.append(f"[{it['type']}] {it['path']} → "
                         f"download_material(course=课名, data_id={it['data_id']})")
    if not hits:
        lines.append("（无命中，可加大 max_depth 或换关键词）")
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
    """查询某门课的作业列表（序号/作业名/提交状态/完成进度）。
    course 为课名关键词（如 "数字电路"）。要看某份作业的截止时间和得分，
    用返回的序号调用 get_homework_detail。"""
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
        lines.append(f"{it['index']:>2}. {it['title']} | {it['status'] or '状态未知'}")
    if not data["items"]:
        lines.append("（本课程暂无作业）")
    else:
        lines.append("提示: 需要某份作业的截止时间/得分时，"
                     "调用 get_homework_detail(course=课名, index=序号)")
    return "\n".join(lines)


@mcp.tool()
def get_homework_detail(course: str, index: int) -> str:
    """查询单份作业的详情：题量 / 满分 / 作答起止时间（含截止时间）/ 得分。
    course 为课名关键词；index 为 list_homework 返回的作业序号（从 1 起）。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        found = s.find_course(course)
        if not found:
            return f"未找到包含「{course}」的课程，请用 list_courses 查看课名"
        d = s.fetch_homework_detail(found, index)
    except IndexError as e:
        return str(e) + "，请先调用 list_homework 查看有效序号"
    except Exception as e:
        return f"查询作业详情失败: {_fmt(e)}"
    lines = [f"《{found['name']}》作业 {index}: {d['title'] or '?'}",
             f"状态: {d['status'] or '未知'}"]
    if d["question_count"] is not None:
        lines.append(f"题量: {d['question_count']}")
    if d["full_score"] is not None:
        lines.append(f"满分: {d['full_score']}")
    if d["start_time"] or d["deadline"]:
        lines.append(f"作答时间: {d['start_time'] or '?'} 至 {d['deadline'] or '?'}"
                     + ("（已截止）" if d["deadline"] else ""))
    if d["score"] is not None:
        lines.append(f"得分: {d['score']}")
    return "\n".join(lines)


@mcp.tool()
def get_homework_deadlines(course: str = "", horizon_days: int = 90) -> str:
    """待完成作业截止看板：扫全部课程（或 course 指定一门）里尚未提交的作业，
    逐份取截止时间，按「未来（近→远）→ 已过期 → 截止未知」排序。
    已完成/已提交（待批阅）的不计入；horizon_days 只看未来 N 天内截止的。
    需要逐份请求详情页，课程多时耗时较长。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        rows = s.fetch_deadline_overview(course or None, horizon_days)
    except Exception as e:
        return f"查询截止看板失败: {_fmt(e)}"
    today = datetime.now().date()
    lines = [f"待完成作业 {len(rows)} 项"
             + (f"（课程筛选：{course}）" if course else "（全部课程）") + ":"]
    for r in rows:
        if r["deadline_dt"] is not None:
            delta = (r["deadline_dt"].date() - today).days
            when = (f"{r['deadline']}（剩 {delta} 天）" if delta >= 0
                    else f"{r['deadline']}（已过期 {-delta} 天）")
        elif r["deadline"]:
            when = f"{r['deadline']}（截止时间解析失败）"
        else:
            when = "截止未知（详情页未给出）"
        lines.append(f"{when} | {r['course']} | {r['title']} | {r['status']}")
    if not rows:
        lines.append("（没有未完成的作业）")
    return "\n".join(lines)


@mcp.tool()
def get_progress_overview() -> str:
    """全部课程的章节任务点完成进度一览，按未完成任务点数从多到少排序，
    快速发现哪门课还剩任务没完成。单门课的逐章明细用 list_chapters。
    需逐课请求章节页，课程多时耗时较长。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        rows = s.fetch_progress_overview()
    except Exception as e:
        return f"查询进度总览失败: {_fmt(e)}"
    rows.sort(key=lambda r: (r["total"] - r["done"]) if r["done"] is not None else -1,
              reverse=True)
    lines = [f"全课程任务点进度（{len(rows)} 门课，未完成多的在前）:"]
    ok_cnt = 0
    for r in rows:
        if r["done"] is None:
            lines.append(f"{r['course']} | {r['error'] or '无进度数据'}")
        else:
            done, total = r["done"], r["total"]
            pct = f"{done * 100 // total}%" if total else "-"
            mark = "✓" if done == total else " "
            lines.append(f"{mark}{r['course']} | {done}/{total}（{pct}）未完成 {total - done}")
            ok_cnt += 1
    if ok_cnt == 0:
        lines.append("（没有任何课程返回进度数据）")
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
def list_notices(unread_only: bool = False, limit: int = 20, keyword: str = "") -> str:
    """查询通知中心（收件箱）：作业/考试/教师/学校通知。
    keyword 在客户端按标题+正文过滤（搜索范围=最近约 100 条，服务端
    不支持关键词参数）；unread_only=True 只看未读；limit 控制返回条数
    （每条含标题/发送人/时间/正文摘要，摘要 160 字）。"""
    s = _client()
    lg = s.ensure_login()
    if not lg.ok:
        return lg.msg
    try:
        items = s.fetch_notices(limit=limit, unread_only=unread_only, keyword=keyword)
    except Exception as e:
        return f"查询通知失败: {_fmt(e)}"
    lines = [f"通知中心（共取到 {len(items)} 条"
             + (", 仅未读" if unread_only else "")
             + (f", 关键词「{keyword}」" if keyword else "") + "）:"]
    for it in items:
        read_mark = "" if it.get("isread") else "[未读] "
        title = (it.get("title") or "").strip()
        content = strip_tags(it.get("content") or "")[:160]
        imgs = len(it.get("imgs") or [])
        lines.append(f"- {read_mark}{title} | {it.get('createrName')} | {it.get('completeTime')}"
                     + (f"（附图 {imgs} 张）" if imgs else "")
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
