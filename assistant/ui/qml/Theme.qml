pragma Singleton
import QtQuick

// cc-switch 浅色色板（源码 src/index.css 原始 tokens 换算 hex）
// 纪律：主色 #1F8FFF 只出现在当前项/交互态/品牌点，绝不铺大色块
QtObject {
    // 卡片与文字
    readonly property color card: "#FFFFFF"
    readonly property color cardAlt: "#F7F7F8"      // 页面内衬/次级底
    readonly property color fg: "#0A0A0B"
    readonly property color muted: "#6E6E76"
    readonly property color faint: "#A0A0A6"

    // 线与主色
    readonly property color border: "#E4E4E7"
    readonly property color borderSoft: "#EFEFF1"
    readonly property color secondary: "#F4F4F5"
    readonly property color primary: "#1F8FFF"
    readonly property color primaryDeep: "#1377DD"   // 按下/强调态
    readonly property color primarySoft: Qt.rgba(0.122, 0.561, 1.0, 0.10)
    readonly property color primaryBorder: Qt.rgba(0.122, 0.561, 1.0, 0.40)

    // 语义色
    readonly property color ok: "#16A34A"
    readonly property color danger: "#EF4444"
    readonly property color dangerSoft: Qt.rgba(0.937, 0.267, 0.267, 0.10)
    readonly property color warn: "#C97A16"

    // 缓动（cc-switch：入场慢出弹、离场快；CW2 液态回弹）
    readonly property var liquidBack: [0.175, 0.885, 0.32, 1.2, 1, 1]
    readonly property var popBack: [0.15, 0.85, 0.35, 1.2, 1, 1]
    readonly property var ccEnter: [0.16, 1, 0.3, 1, 1, 1]
    readonly property var ccExit: [0.4, 0, 1, 1, 1, 1]

    // 圆角层级
    readonly property int radiusSm: 8
    readonly property int radiusMd: 12
    readonly property int radiusLg: 14

    readonly property string fontFamily: "Microsoft YaHei UI"
}
