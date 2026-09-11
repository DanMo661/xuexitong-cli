# chaoxing-mcp

学习通（超星）MCP Server —— 把你的课表、作业、考试、章节进度、通知、云盘接进任意 MCP 客户端（ZCode / Claude Desktop / Cursor 等）。

**只读查询**。本项目只做信息聚合查询，不提供也不会提供自动签到、自动刷课、自动答题等任何写入/作弊功能——那是红线，请自行去上课。

全部接口均经真实账号实测验证（2026-09）。

## 工具列表（11 个）

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `login` | 登录并持久化会话 | `phone`, `password` |
| `get_profile` | 个人资料（姓名/学校/uid/fid/学年学期） | 无 |
| `get_schedule` | 本学期课表（周次/节次/教室/老师） | 无 |
| `list_courses` | 我学的全部课程（含 courseid/clazzid/cpi） | 无 |
| `list_materials` | 课程资料区文件列表，支持文件夹逐层下钻 | `course`，`folder_data_id?`，`folder_enc?` |
| `download_material` | 下载资料文件到本地 | `course`, `data_id`, `save_dir`, `filename?` |
| `list_homework` | 课程作业列表（名称/提交状态/完成进度） | `course` |
| `list_exams` | 全校考试安排（时间/时长/状态/分数） | 无 |
| `list_chapters` | 课程章节树 + 任务点完成进度 | `course` |
| `list_notices` | 通知中心（作业/考试/教师/学校通知，含未读标记） | `unread_only?`, `limit?` |
| `list_pan_files` | 个人云盘文件列表，支持文件夹下钻 | `folder_id?` |

### 用法示例

```text
用户: 我这周有哪些课？
 → get_schedule()

用户: 数字电路这门课还有什么作业没交？
 → list_homework(course="数字电路")

用户: 马克思的课我学到哪了？
 → list_chapters(course="马克思主义基本原理")
   → 总进度: 已完成任务点 0/26（0%）……

用户: 有什么新通知？
 → list_notices(unread_only=true, limit=10)

用户: 把老师传的课件下载到 D:\课件
 → list_materials(course="数字电路") → download_material(course="数字电路", data_id=..., save_dir="D:\\课件")
```

## 安装

```bash
git clone https://github.com/DanMo661/chaoxing-mcp.git
cd chaoxing-mcp
pip install -r requirements.txt   # requests / pycryptodome / mcp
```

Python >= 3.10。也可以安装为命令（可选）：

```bash
pip install .        # 之后得到 chaoxing-mcp 命令，等价于 python -m chaoxing_mcp
```

## 凭据配置（三选一，优先级从高到低）

1. **调用 `login` 工具时传入** `phone` / `password` 参数
2. **环境变量** `CHAOXING_PHONE` / `CHAOXING_PASSWORD`（推荐服务器场景，凭据不落盘）
3. **`config.json`**（与代码同目录）：

```bash
copy config.example.json config.json   # Linux: cp
# 编辑 config.json 填入 phone / password
```

## MCP 客户端配置

三种写法任选其一：

```jsonc
// 1. 源码直接运行（clone 后免安装）
{ "command": "python", "args": ["D:/path/to/chaoxing-mcp/chaoxing_server.py"] }

// 2. 模块方式运行
{ "command": "python", "args": ["-m", "chaoxing_mcp"], "cwd": "D:/path/to/chaoxing-mcp" }

// 3. pip install . 之后用命令名
{ "command": "chaoxing-mcp" }
```

外层按客户端惯例包一层：ZCode 写在 `~/.zcode/cli/config.json` 的 `mcp.servers` 下，Claude Desktop 写在 `claude_desktop_config.json` 的 `mcpServers` 下。Windows 下 `command` 建议写 python 绝对路径（如 `D:/Python/python.exe`）。

## 会话与安全设计

- `config.json`（凭据）与 `session_cookies.json`（登录态）均在 `.gitignore` 中排除，**绝不入库**。
- cookie 持久化跨进程复用，失效自动重登；登录态探测结果缓存 5 分钟，减少每工具一次的探测请求。
- 网络层带指数退避重试（429/502/503/504）；下载走流式写盘，大文件不占内存；服务器文件名经安全化处理（防路径穿越）。

## 注意事项

- **风控**：学习通对高频请求有风控。本工具不主动加请求间隔（由 MCP 客户端调用频率天然决定），请不要用它做批量爬取、定时轮询间隔过短等操作。账号是自己的，封了别哭。
- **只读声明**：所有工具均为 GET/查询语义，不提交任何表单。自动签到/刷课/答题类需求请绕行。
- **cookie 失效**：会自动重登；若密码改了记得更新 config.json。
- **课程匹配**：`course` 参数为课名模糊关键词（如 "数字电路"），多门课命中时取第一个匹配，建议先 `list_courses` 确认课名。

## 技术原理（逆向备忘）

<details>
<summary>点开查看各接口协议细节</summary>

### 功能地图

登录后 `GET https://i.chaoxing.com/base`，左侧菜单每个功能的 `dataurl` 属性即入口：

| 菜单 | dataurl 域 |
|---|---|
| 课表 | kb.chaoxing.com |
| 互动 | mooc2-ans.chaoxing.com/visit/interaction |
| 通知 | notice.chaoxing.com/pc/notice/myNotice |
| 消息 | im.chaoxing.com/webim/me |
| 云盘 | pan-yz.cldisk.com/pcuserpan/index |
| 考试列表 | mooc1-api.chaoxing.com/exam/.../examlist |
| 通讯录 | contactsyd.chaoxing.com |

### 登录

`POST https://passport2.chaoxing.com/fanyalogin`，uname/password 均为 AES-128-CBC 加密（key=iv=`u2oh6Vu^HWe4_AES`，PKCS7 填充，base64 输出）。成功响应 `{"status": true}`。手机端域名 `passport2-app.chaoxing.com` 已 NXDOMAIN。

### 课表

`POST https://kb.chaoxing.com/pc/curriculum/getMyLessons` → `data.lessonArray`（课名=name、教室=location、老师=teacherName、节次=beginNumber+length、星期=dayOfWeek）。

### 课程列表

`GET mooc2-ans.chaoxing.com/mooc2-ans/visit/courselistdata?courseType=1&courseFid=<fid>`；课名在链接**后方**的 `course-name` span 的 title 里。fid 从 base 页 JS 变量提取。

### 资料与下载

- 列表：`GET mooc2-ans.chaoxing.com/mooc2-ans/coursedata/stu-datalist?courseid&clazzid&cpi&ut=s`；文件夹下钻加 `&dataId=<id>&enc=<onclick 里的 enc>`。
- 下载：`GET mooc1.chaoxing.com/coursedata/downloadData?dataId&classId&cpi&courseId&ut=s`（四件套缺一不可）→ 302 → `d0.cldisk.com` 直链，**必须带 `Referer: https://pan-yz.chaoxing.com/`** 否则 403。CDN 的 filename* 是裸 UTF-8 字节（非标），需 latin-1→utf-8 修复。

### 作业（enc 已解）

课程中间页 `GET mooc1.chaoxing.com/visit/stucoursemiddle?courseid&clazzid&cpi&ismooc2=1&v=2` 服务端渲染了一组隐藏 `<input>`：

```html
<input type="hidden" id="enc"     value="..."/>  <!-- 页面通用 enc -->
<input type="hidden" id="openc"   value="..."/>
<input type="hidden" id="oldenc"  value="..."/>
<input type="hidden" id="workEnc" value="..."/>  <!-- 作业 tab 专用 -->
<input type="hidden" id="examEnc" value="..."/>  <!-- 课程考试 tab 专用 -->
```

作业列表 `GET mooc1.chaoxing.com/mooc2/work/list?courseId&classId&cpi&ut=s&openc&enc=<workEnc>&t=<毫秒时间戳>&stuenc=<页面enc>&isdisplaytable=2`，**enc 必须用 workEnc 而非页面 enc**，且需要 t 和 stuenc 伴随参数，否则"无权限"。作业条目在 `<li onclick="goTask(this);" data="...">` 里，含名称/状态/跳转 URL。

### 考试列表

`GET https://mooc1-api.chaoxing.com/exam-ans/exam/test/examcode/examlist`（dataurl 里不带 exam-ans 的旧路径会 302 到这里）。服务端直接渲染 `<tr class="dataTr">` 表格：编号/名称/时间/时长/考试状态/作答状态/分数/方式。

### 章节与任务点

`GET mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse?courseid&clazzid&cpi&enc=<页面enc>&openc&fromMiddle=1&ut=s`。服务端渲染章节树：

- 总进度：`已完成任务点: <span>N</span>/M`
- 一级章：`catalog_num` 序号 + `catalog_name` 的 `span title`
- 二级节：`chapter_item` + `catalog_sbar` 编号；状态在 `catalog_task`：`icon_yiwanc`=已完成、`catalog_points_yi` 数字=N 个待完成、无标记=未开放

### 通知中心

`POST https://notice.chaoxing.com/pc/notice/getNoticeList`，form 参数 type/notice_type/lastValue/sort 等，游标翻页用返回的 `notices.lastGetId`。条目字段：title/content/createrName/completeTime/isread。

### 云盘

`GET https://pan-yz.cldisk.com/pcuserpan/index` 页面里的 JS 常量：`const encstr`、`const rootdir`、`const currentPuid`。列表 API：`GET pan-yz.cldisk.com/opt/listres?puid&shareid=0&parentId=<rootdir或文件夹id>&page=1&size=100&enc=<encstr>`（带 Referer）。返回 `list[]`（isfile/name/filesize/id）与 `totalCount`。encstr 含时间戳签名，每次会话需重新从 index 页提取。

### 个人资料

base 页：姓名（`aria-label="账号：X"`）、学校（`#siteName` title）、uid/fid（JS 变量）。学号接口 `contactsyd.chaoxing.com/pc/user/getUserInfo` 已停用（"接口已停用"）。

</details>

## 已知限制

- **成绩单页**：`stat2-ans.chaoxing.com/study-data/index` 对程序化访问返回 403（尝试了页面 enc/oldenc/Referer 组合均被拒），暂无法查询课程成绩统计。替代：考试分数见 `list_exams` 的分数列，作业状态见 `list_homework`。
- **学号**：个人资料接口已停用，`get_profile` 不含学号。
- **课程公告**：无独立接口，已并入 `list_notices`（教师通知标题通常带课程名）。
- **消息（IM）**：`im.chaoxing.com/webim/me` 是 WebSocket 应用，程序化访问返回错误页，未支持。
- **作业截止时间**：work/list 服务端渲染不含截止时间字段，需要点进作业详情页（其 URL 亦带独立 enc），暂不解析。
- 非学历教育/继续教育等特殊账号体系未验证。

## 项目结构

```
chaoxing_mcp/
├── client.py    # 接口层：会话 / 登录 / 重试 / 页面解析（返回结构化数据）
├── server.py    # MCP 工具层：结构化数据 → 可读文本
└── __main__.py  # python -m chaoxing_mcp 入口
chaoxing_server.py  # 兼容旧配置的直接运行入口
tests/run_tests.py  # 纯逻辑单测（零依赖：python tests/run_tests.py，也兼容 pytest）
pyproject.toml      # pip install . 打包配置
```

## License

MIT (c) Wu Jiale
