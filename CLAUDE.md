# Xuexitong-mcp 项目规范（v2.1 桌面小窗产品化）

## 定位

学习通桌面助手：MCP 服务器（agent 侧数据接口）+ 常驻桌面小窗（用户侧产品）。
核心承诺：**用户不再打开学习通 App/网页**，消息、作业、资料更新自动送达。

## 分层架构

```
xuexitong_mcp/
  client.py      # 协议层（成熟，勿大改）：登录/课表/作业/资料/通知/进度
  widget.py      # 课表纯函数（lesson_rows 等；不认 weeks 串，见 snapshot.week_lessons）
  server.py      # MCP 服务器（16 工具），只依赖 client
assistant/
  app.py         # 主程序：QML 小窗 + 托盘 + 巡检 worker + 60s 心跳
  watcher.py     # 巡检引擎：定时全量扫描 → 增量对比 → 分级告警
  store.py       # 状态库：基线/时间线/课表缓存/DDL缓存/提醒状态/已读（全锁化）
  classify.py    # 新增内容判定：作业/DDL/通知/资料，关键词+文件内容
  reminders.py   # DDL 渐进提醒 + 预备铃（check_classup）
  notify.py      # 通知通道：Windows Toast + 可选邮件
  snapshot.py    # 快照组装：今日课（week_lessons 按周过滤！）/周网格/DDL 视图
  ui/
    app 装配 QML 引擎；bridge.py=数据桥；detail.py=详情窗(QWidget)；theme.py=详情窗色板
    qml/         # Main.qml(壳) + TodayPage/WeekPage/HwPage/EventsPage + Theme 单例
```

## 硬约束

- **只读**：对学习通只做查询，绝无签到/刷课/答题类写入
- **凭据**：config.json / session_cookies.json / settings.json / store.json /
  widget_geometry.json 不进 git；SMTP 授权码只进
  `C:\Users\Administrator\.zcode\credentials.md`，代码里读配置文件
- **巡检风控**："温和人类"水平（默认 30 分钟一轮，全量每天 ≤2 次）；
  一轮扫描只拉一次全学期课表（watcher 拉，快照层只读缓存）
- **UI 框架**：PySide6 + QML（小窗）+ QWidget（详情窗）；tkinter widget.py 仅兼容入口
- **打包**：PyInstaller onedir，产物 dist/ 不进 git；自用走 venv + bat

## UI 规范（v2.1 定稿，浅色）

- **色板 = cc-switch 浅色 tokens**（源码 src/index.css）：白卡 #FFFFFF、
  边框 #E4E4E7、主色 #1F8FFF 只点缀当前项/交互态、muted #6E6E76、
  danger #EF4444；改色先读 `docs/调研-桌面课程小组件-20260928.md`
- **小窗结构**：迷你条(360×64)点击展开(360×540)=顶栏+四标签页
  （今天/课表/作业/动态）+页脚；课程行手风琴展开；周网格今天列高亮
- **动效**：进场弹 220-260ms（BezierCurve ccEnter/popBack）、退场快 150ms、
  spring 3.5/0.14；模型级数据不变不重发信号（防每分钟闪烁）
- **课表数据纪律**：全学期缓存按 `weeks` 周次串过滤后才喂 lesson_rows
  （`snapshot.week_lessons`），空周=真空（考试周不显示幽灵课）

## 代码约定

- 中文注释；函数 docstring 一句话说明干什么
- 巡检/通知逻辑必须可在无 GUI 环境跑（headless 模式，便于测试）
- UI 文案与通知文案：学生口吻，不用"本机/经检验"式机器腔
- 网络只在 worker 线程（trigger Signal 触发，绝不直调 do_scan）；
  UI 线程只做纯缓存计算

## 验证

- `python tests/run_tests.py`：协议层单测（保持全绿）
- `python -m assistant.watch --once --headless`：单轮巡检冒烟
- `python -m assistant.app --screenshot out.png`：迷你+四页截图（屏幕合成，
  产物 out_mini/t0..t3.png）
- UI 改动后截图过视觉复检；发布前跑 nitpick 新用户实测
