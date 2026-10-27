import QtQuick
import "." as Ui

// 纯形状拼装的功能图标（FLstyle：卡头与分段器每段都带小图标，
// 纯文字卡头"差一口气"）。不用字体 glyph——字体缺字不可控，
// 矩形/圆环的坐标是确定性的，任何机器渲染一致。
//
// 规格：默认 10×10，线宽 thickness=2；颜色由调用方给
// （选中态白、常态灰、激活态主色）。
Item {
    id: g

    // 图标种类（调用方用数字常量：0=dot 1=grid 2=doc 3=pulse 4=clock 5=bell 6=sliders 7=check 8=list 9=cap 10=pin）
    readonly property int kindDot: 0      // 今天：实心圆
    readonly property int kindGrid: 1     // 课表：2×2 方格
    readonly property int kindDoc: 2      // 作业：三行文本条
    readonly property int kindPulse: 3    // 动态：脉冲柱
    readonly property int kindClock: 4    // 考试：圆环表盘
    readonly property int kindBell: 5     // （弃用：与表盘 10px 下同形）
    readonly property int kindSliders: 6  // 设置：三档滑杆
    readonly property int kindCheck: 7    // 完成：对勾
    readonly property int kindList: 8     // 通知：圆点列表（点+行×2，与表盘拉开区分）
    readonly property int kindCap: 9      // 学仕帽（品牌 glyph：45°菱形板+帽檐+流苏点）
    readonly property int kindPin: 10     // 图钉（标题栏置顶钮：圆头+斜杆）
    readonly property int kindMail: 11    // 信封（邮件提醒：方框描边+V 形封口）

    property int kind: 0   // 默认 kindDot（"Dot" 不是合法标识符，写 0 防 ReferenceError）
    property color color: Ui.Theme.fg2
    property real thickness: 2.0

    readonly property real gap: Math.max(1, Math.round(width * 0.16))
    readonly property real cell: width * 0.36
    readonly property real knobSize: thickness * 2.2

    // ---- 今天：实心圆 ----
    Rectangle {
        visible: g.kind === g.kindDot
        width: Math.round(g.width * 0.62); height: width; radius: width / 2
        anchors.centerIn: parent
        color: g.color
    }

    // ---- 课表：2×2 方格 ----
    Column {
        visible: g.kind === g.kindGrid
        anchors.centerIn: parent
        spacing: Math.max(1, Math.round(g.width * 0.14))
        Row {
            spacing: parent.spacing
            Rectangle { width: g.cell; height: g.cell; radius: 1; color: g.color }
            Rectangle { width: g.cell; height: g.cell; radius: 1; color: g.color }
        }
        Row {
            spacing: parent.spacing
            Rectangle { width: g.cell; height: g.cell; radius: 1; color: g.color }
            Rectangle { width: g.cell; height: g.cell; radius: 1; color: g.color }
        }
    }

    // ---- 作业：三行文本条（上两行长、末行短）----
    Column {
        visible: g.kind === g.kindDoc
        anchors.centerIn: parent
        spacing: Math.max(1.5, thickness * 0.9)
        Rectangle { width: g.width; height: g.thickness; radius: g.thickness / 2; color: g.color }
        Rectangle { width: g.width; height: g.thickness; radius: g.thickness / 2; color: g.color }
        Rectangle { width: g.width * 0.55; height: g.thickness; radius: g.thickness / 2; color: g.color }
    }

    // ---- 动态：脉冲柱（低-高-中，底对齐；定位器子项不锚定，包 Item 再锚）----
    Row {
        visible: g.kind === g.kindPulse
        anchors.centerIn: parent
        spacing: g.gap
        Item {
            width: g.thickness; height: g.height
            Rectangle { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                        width: g.thickness; height: g.height * 0.5; radius: g.thickness / 2; color: g.color }
        }
        Item {
            width: g.thickness; height: g.height
            Rectangle { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                        width: g.thickness; height: g.height; radius: g.thickness / 2; color: g.color }
        }
        Item {
            width: g.thickness; height: g.height
            Rectangle { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                        width: g.thickness; height: g.height * 0.72; radius: g.thickness / 2; color: g.color }
        }
    }

    // ---- 考试：圆环表盘（border 圆 + 两根指针）----
    Rectangle {
        visible: g.kind === g.kindClock
        anchors.centerIn: parent
        width: g.width; height: g.height; radius: width / 2
        color: "transparent"
        border.width: g.thickness; border.color: g.color
        // 分针：从圆心竖直向上
        Rectangle {
            x: parent.width / 2 - g.thickness / 2
            y: g.thickness + 1
            width: g.thickness; height: g.height * 0.26
            radius: g.thickness / 2; color: g.color
        }
        // 时针：从圆心水平向右
        Rectangle {
            x: parent.width / 2
            y: parent.height / 2 - g.thickness / 2
            width: g.width * 0.2; height: g.thickness
            radius: g.thickness / 2; color: g.color
        }
    }

    // ---- 通知：圆环 + 中心实心点 ----
    Rectangle {
        visible: g.kind === g.kindBell
        anchors.centerIn: parent
        width: g.width; height: g.height; radius: width / 2
        color: "transparent"
        border.width: g.thickness; border.color: g.color
        Rectangle {
            anchors.centerIn: parent
            width: g.width * 0.3; height: width; radius: width / 2
            color: g.color
        }
    }

    // ---- 通知：圆点列表（点 + 短行 × 2；行高一致无需锚定）----
    Column {
        visible: g.kind === g.kindList
        anchors.centerIn: parent
        spacing: Math.max(1.5, g.thickness * 0.9)
        Row {
            spacing: g.gap
            Rectangle { width: g.thickness; height: g.thickness
                        radius: g.thickness / 2; color: g.color }
            Rectangle { width: g.width - g.thickness - g.gap; height: g.thickness
                        radius: g.thickness / 2; color: g.color }
        }
        Row {
            spacing: g.gap
            Rectangle { width: g.thickness; height: g.thickness
                        radius: g.thickness / 2; color: g.color }
            Rectangle { width: (g.width - g.thickness - g.gap) * 0.62; height: g.thickness
                        radius: g.thickness / 2; color: g.color }
        }
    }

    // ---- 设置：三档滑杆（半透明杆 + 错位实心旋钮）----
    Column {
        visible: g.kind === g.kindSliders
        anchors.centerIn: parent
        spacing: Math.max(1.5, thickness)
        Repeater {
            model: [0.12, 0.52, 0.32]
            delegate: Item {
                width: g.width; height: g.knobSize
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width; height: g.thickness * 0.8
                    radius: height / 2; color: g.color; opacity: 0.5
                }
                Rectangle {
                    x: parent.width * modelData - g.knobSize / 2
                    anchors.verticalCenter: parent.verticalCenter
                    width: g.knobSize; height: g.knobSize; radius: g.knobSize / 2
                    color: g.color
                }
            }
        }
    }

    // ---- 完成：对勾（两段绕左端旋转的矩形：短边下行 +45°、长边上扬 -45°）----
    Item {
        visible: g.kind === g.kindCheck
        anchors.centerIn: parent
        width: g.width; height: g.height
        // 短边：左上起，下行到勾底
        Rectangle {
            x: g.width * 0.06
            y: g.height * 0.50 - g.thickness / 2
            width: g.width * 0.40; height: g.thickness
            radius: g.thickness / 2; color: g.color
            transformOrigin: Item.Left
            rotation: 45
        }
        // 长边：勾底起，上扬到右上
        Rectangle {
            x: g.width * 0.34
            y: g.height * 0.50 - g.thickness / 2 - g.width * 0.02
            width: g.width * 0.60; height: g.thickness
            radius: g.thickness / 2; color: g.color
            transformOrigin: Item.Left
            rotation: -45
        }
    }

    // ---- 学仕帽（品牌 glyph）：45° 菱形帽板 + 横帽檐 + 中心流苏点 ----
    Item {
        visible: g.kind === g.kindCap
        anchors.centerIn: parent
        width: g.width; height: g.height
        // 帽板：正方形旋转 45°（对角线 = width）
        Rectangle {
            anchors.centerIn: parent
            y: parent.height * 0.08
            width: g.width * 0.66; height: g.width * 0.66
            radius: 1; color: g.color
            rotation: 45
        }
        // 帽檐：板下一条横向圆角短杆
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height * 0.62 - g.thickness / 2
            width: g.width * 0.72; height: g.thickness
            radius: g.thickness / 2; color: g.color
        }
        // 流苏：帽板中心一颗小点
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height * 0.40
            width: g.thickness * 0.9; height: g.thickness * 0.9
            radius: g.thickness * 0.45; color: g.color
        }
    }

    // ---- 图钉（标题栏置顶钮）：圆头 + 左斜杆 ----
    Item {
        visible: g.kind === g.kindPin
        anchors.centerIn: parent
        width: g.width; height: g.height
        // 杆：从左下到中上（绕底端旋转的竖杆）
        Rectangle {
            x: parent.width * 0.30
            y: parent.height * 0.30
            width: g.thickness * 0.9; height: parent.height * 0.52
            radius: g.thickness * 0.45; color: g.color
            transformOrigin: Item.Bottom
            rotation: 45
        }
        // 头：右上实心圆
        Rectangle {
            x: parent.width * 0.42; y: parent.height * 0.10
            width: parent.width * 0.48; height: parent.width * 0.48
            radius: width / 2; color: g.color
        }
    }

    // ---- 信封：圆角方框描边 + 两侧下斜的 V 形封口 ----
    Item {
        visible: g.kind === g.kindMail
        anchors.centerIn: parent
        width: g.width; height: g.height * 0.8
        Rectangle {
            anchors.fill: parent
            radius: 1.5
            color: "transparent"
            border.width: g.thickness * 0.8; border.color: g.color
        }
        // 左翼：从左上往中下斜（绕左端 -35°）
        Rectangle {
            x: 1; y: g.height * 0.14
            width: g.width * 0.52; height: g.thickness * 0.8
            radius: g.thickness * 0.4; color: g.color
            transformOrigin: Item.Left
            rotation: 32
        }
        // 右翼：从右上往中下斜（绕右端 -32°）
        Rectangle {
            x: g.width * 0.48 - 1; y: g.height * 0.14
            width: g.width * 0.52; height: g.thickness * 0.8
            radius: g.thickness * 0.4; color: g.color
            transformOrigin: Item.Right
            rotation: -32
        }
    }
}
