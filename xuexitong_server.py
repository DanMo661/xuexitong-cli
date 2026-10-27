# -*- coding: utf-8 -*-
r"""直接运行入口（兼容旧 MCP 配置写法）。

旧版 MCP 配置直接指向本文件；实际实现已重构为 xuexitong_mcp/ 包
（client.py 接口层 + server.py 工具层），行为与旧单文件版兼容。
新装推荐用 `pip install .` 后运行 `xuexitong-mcp` 或 `python -m xuexitong_mcp`。

工具总览（16 个，全部只读查询）：
    login            登录并持久化会话
    get_profile      个人资料（姓名/学校/uid/fid）
    get_schedule     本学期课表（可选按周过滤；周过滤时显示真实日期）
    export_schedule_ics  课表导出 .ics 日历（学校真实节次时间，含课前提醒）
    list_courses     我学的课程列表
    list_materials   课程资料区（支持文件夹下钻）
    find_materials   资料区按关键词递归搜索
    download_material 下载资料文件（流式写盘）
    list_homework    课程作业列表（含提交状态与进度）
    get_homework_detail 单份作业详情（题量/满分/作答起止时间/得分）
    get_homework_deadlines 全课程未交作业截止看板（按紧急排序）
    list_exams       全校考试安排
    list_chapters    课程章节与任务点完成进度
    get_progress_overview 全课程任务点进度总览（未完成多的在前）
    list_notices     通知中心（支持关键词搜索/未读过滤）
    list_pan_files   个人云盘文件列表

凭据三种来源（优先级从高到低）：
    1. login 工具参数
    2. 环境变量 CHAOXING_PHONE / CHAOXING_PASSWORD
    3. 同目录 config.json：{"phone": "...", "password": "..."}（不入 git）
"""

from xuexitong_mcp.server import main

if __name__ == "__main__":
    main()
