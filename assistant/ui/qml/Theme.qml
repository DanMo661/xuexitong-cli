pragma Singleton
import QtQuick

// FLstyle 工具类 token（浅色）——值出自 FLstyle SKILL.md 第 2 节实测表与骨架代码
// （来源应用 1400×1466@150% 真机逐像素实测；本控件 360 宽与其 320 宽卡片同量级，直接取值）。
//
// 设计宪法：结构靠灰阶表面分层，颜色只给状态（选中/成功/警告/错误/一屏唯一主动作）。
//  - 卡片 = 比背景亮一档的填充（白卡浮在 L95 灰页上），不画实线边框
//  - 分隔线/描边 = 前景色低透明（14%），永不实色
//  - 彩色永不爬上背景；状态色只上文字/小图标/小 chip，不满染整卡
//  - 动效只在"值"（颜色/透明度）上渐变，从不在"位置"上做动画
//
// 兼容层：旧 token 名（cardAlt/secondary/border/muted/faint/primary* 等）全部保留，
// 值已换算到 FLstyle，未改到的引用也能直接编过。
QtObject {
    // ================= 表面五级（浅色实测：窗 L95 / 卡白 / 轨 L91 / 井 L88 / 徽章 L87）=================
    readonly property color page: "#F1F1F2"     // 窗口/页面底（最深表面）
    readonly property color card: "#FFFFFF"     // 卡片：比背景亮一档，靠填充分层不靠边框
    readonly property color track: "#E8E8E9"    // 轨/凸块：白卡上变暗一档（分段器轨/输入轨/进度槽/信息条）
    readonly property color well: "#E1E1E2"     // 井/凹槽：承载开关、附属控制的子条（比宿主深一档）
    readonly property color badge: "#DEDEDF"    // 徽章/药丸底：灰底页面上的中性药丸（最亮的中性表面）

    // 旧名兼容映射（勿在新代码使用）
    readonly property color cardAlt: track      // 原页面内衬条 → 轨色
    readonly property color secondary: track    // 原次级底 → 轨色

    // ================= 文字三级 =================
    readonly property color fg: "#1A1C1E"       // 标题/强调
    readonly property color fg2: "#757575"      // 次要
    readonly property color fg3: "#8A8A8E"      // 弱化（页脚/时间戳/占位；对页灰 ≥3:1）
    readonly property color muted: fg2          // 旧名
    readonly property color faint: fg3          // 旧名

    // ================= 线（前景低透明，永不实色）=================
    readonly property color line: Qt.rgba(0.102, 0.110, 0.118, 0.14)      // #1A1C1E @14%
    // line 预混到页灰上的实色。专用：Rectangle.border（实测 150%DPI 下
    // 带 alpha 的 border 会渲染成近黑环，填充不受影响——border 只用实色）
    readonly property color lineSolid: "#D3D4D6"
    readonly property color border: line                                  // 旧名
    readonly property color borderSoft: Qt.rgba(0.102, 0.110, 0.118, 0.08)

    // 悬停底色（比选中更淡的独立层，只做透明度渐变）
    readonly property color hoverOverlay: Qt.rgba(0.910, 0.910, 0.918, 0.55)

    // ================= 主色（种子色引擎产物 HSL(213,75%,48%)，换种子全联动）=================
    readonly property color primary: "#1B6FD8"
    readonly property color primaryDeep: "#1660B8"                            // 按下/强调
    readonly property color primarySoft: Qt.rgba(0.106, 0.435, 0.847, 0.10)   // 淡彩 chip 底
    readonly property color primaryBorder: Qt.rgba(0.106, 0.435, 0.847, 0.40)
    readonly property color accentBright: "#2196F3"                           // 对勾/图标点缀

    // ================= 语义色（固定，不随种子调和）=================
    // success hsl(122,45%,34%) / warning hsl(35,90%,38%) / error hsl(4,90%,48%)
    readonly property color ok: "#307E32"
    readonly property color okSoft: Qt.rgba(0.188, 0.494, 0.196, 0.10)
    readonly property color danger: "#E91B0C"
    readonly property color dangerSoft: Qt.rgba(0.912, 0.106, 0.047, 0.10)
    readonly property color warn: "#B86F0A"
    readonly property color warnSoft: Qt.rgba(0.722, 0.435, 0.039, 0.10)

    // ================= 字号阶（widget 密度：9/10/11/12/13/14/16）=================
    readonly property int fsMicro: 9    // 周次轨时刻、极小注
    readonly property int fsCap: 10     // 说明/时间戳/chip
    readonly property int fsSub: 11     // 次要正文
    readonly property int fsBody: 12    // 正文/分段器
    readonly property int fsTitle: 13   // 分组标题/卡片主文
    readonly property int fsHead: 14    // 迷你条标题
    readonly property int fsPage: 16    // 详情窗页标题

    // ================= 间距阶（4 的倍数，主节奏 8/12/16）=================
    readonly property int sp1: 4
    readonly property int sp2: 8
    readonly property int sp3: 12
    readonly property int sp4: 16
    readonly property int sp5: 20
    readonly property int sp6: 24

    // ================= 圆角阶（chip·输入 8 / 菜单·浮层 12 / 卡片 16；胶囊 = 高的一半）=================
    readonly property int radiusSm: 8
    readonly property int radiusMd: 12
    readonly property int radiusLg: 16

    // ================= 动效（值渐变体系：颜色/透明度，零位移）=================
    // 缓动（cc-switch 系弹簧回弹对，用于窗口/高度等入场预算）
    readonly property var liquidBack: [0.175, 0.885, 0.32, 1.2, 1, 1]
    readonly property var popBack: [0.15, 0.85, 0.35, 1.2, 1, 1]
    readonly property var ccEnter: [0.16, 1, 0.3, 1, 1, 1]
    readonly property var ccExit: [0.4, 0, 1, 1, 1, 1]
    // 时长：hover 即现即灭 / 内容淡入 / 分段器原位迁移
    readonly property int durFast: 120
    readonly property int durFade: 160
    readonly property int durSeg: 200

    readonly property string fontFamily: "Microsoft YaHei UI"
}
