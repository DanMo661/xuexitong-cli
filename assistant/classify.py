# -*- coding: utf-8 -*-
"""新增内容判定：把巡检到的原始条目分级，决定要不要打扰用户。

分级原则（宁缺勿滥——通知轰炸比漏一条资料更毁体验）：
  high   作业/考试/DDL/老师通知 → Toast 弹窗 + 红点
  medium 可疑的课件/文件更新   → 只进小窗时间线，红点
  low    普通课件、一般通知     → 只进时间线
"""
import os
import re
import tempfile
import zipfile

# 文件名里的作业信号（不分大小写）
_HW_FILE_PAT = re.compile(r"(hw|homework|作业|实验|报告|大作业|上机|习题|试卷|考试)", re.I)
# 文件内容里的作业信号（用于 office 文档正文二次确认）
_HW_TEXT_PAT = re.compile(r"(作业|截止|提交|deadline|ddl|上交|上交至|发送至)", re.I)
# 通知标题里的高优信号
_NOTICE_HIGH_PAT = re.compile(r"(作业|考试|截止|提醒|打回|补考|重修|重要|紧急)", re.I)


def classify_material(filename: str, course: str = "") -> dict:
    """资料区新增文件的分级。文件名即信号，够用就不读内容。"""
    name = os.path.basename(filename)
    ext = os.path.splitext(name)[1].lower()
    if _HW_FILE_PAT.search(name):
        return {"tag": "作业", "priority": "high",
                "reason": f"文件名含作业信号：{name}"}
    if ext in (".pptx", ".docx") and _HW_FILE_PAT.search(course or ""):
        # 课程名带"实验/实践"的课，新文件默认值得看一眼
        return {"tag": "资料", "priority": "medium",
                "reason": "实践类课程有新文件"}
    if ext in (".pptx", ".pdf", ".docx", ".doc"):
        return {"tag": "资料", "priority": "medium",
                "reason": "课件/文档更新"}
    if ext in (".png", ".jpg", ".jpeg", ".zip", ".rar"):
        return {"tag": "资料", "priority": "low", "reason": "附件/压缩包"}
    return {"tag": "资料", "priority": "low", "reason": "其他文件"}


def classify_homework(title: str, status: str) -> dict:
    """作业列表新增条目：一律 high（作业本身就是信号）。"""
    return {"tag": "作业", "priority": "high", "reason": f"新作业：{title}"}


def classify_notice(title: str, sender: str = "", content: str = "") -> dict:
    """通知中心新条目：老师发的、带作业/考试字样的 high。"""
    if _NOTICE_HIGH_PAT.search(title or ""):
        return {"tag": "通知", "priority": "high", "reason": "标题含作业/考试字样"}
    if sender and sender not in ("学习通知", "系统通知"):
        return {"tag": "通知", "priority": "medium", "reason": f"{sender} 老师发布"}
    return {"tag": "通知", "priority": "low", "reason": "一般通知"}


def material_is_homeworkish(file_path: str, max_bytes: int = 8 << 20) -> bool | None:
    """对下载到本地的 pptx 做正文二次确认：前几张 slide 有作业字样则 True。

    返回 None 表示无法判断（不是 pptx / 读取失败），调用方维持原分级。
    """
    if not file_path.lower().endswith(".pptx") or not os.path.exists(file_path):
        return None
    if os.path.getsize(file_path) > max_bytes:
        return None
    try:
        with zipfile.ZipFile(file_path) as z:
            slides = sorted(n for n in z.namelist()
                            if re.match(r"ppt/slides/slide\d+\.xml$", n))[:3]
            for n in slides:
                xml = z.read(n).decode("utf-8", errors="ignore")
                texts = re.findall(r"<a:t>([^<]*)</a:t>", xml)
                if _HW_TEXT_PAT.search(" ".join(texts)):
                    return True
        return False
    except Exception:
        return None



def probe_dir() -> str:
    d = os.path.join(tempfile.gettempdir(), "xxt_probe")
    os.makedirs(d, exist_ok=True)
    return d
