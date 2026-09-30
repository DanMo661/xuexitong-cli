import QtQuick
import QtQuick.Controls.Basic
import "." as Ui

// 悬浮小窗：迷你条(360×64) ↔ 展开卡(360×540)
// 展开卡 = 顶栏 + 标签页(今天/课表/作业/动态) + 页脚
// 视觉纪律：cc-switch 浅色（白卡+灰边分层，主色只点缀当前项/交互态）
Window {
    id: root
    width: 360
    height: card.expanded ? 540 : 64
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint
    color: "transparent"

    // 截图/调试模式入口（app 侧 QMetaObject 调用）
    function toggleMode() { card.expanded = !card.expanded }
    function setTab(i) { if (!card.expanded) card.expanded = true; card.tab = i }
    // 失焦收起右键菜单：点外关闭层收不到窗外点击，菜单会悬到下次点卡内
    onActiveChanged: if (!active) ctxMenu.visible = false

    Connections {
        target: Bridge
        function onTabJumped(i) { root.setTab(i) }
    }

    Behavior on height {
        NumberAnimation {
            duration: 240
            easing.type: Easing.Bezier
            easing.bezierCurve: card.expanded ? Ui.Theme.ccEnter : Ui.Theme.ccExit
        }
    }

    Rectangle {
        id: card
        property bool expanded: false
        property int tab: 0          // 0今天 1课表 2作业 3动态
        anchors.fill: parent
        radius: Ui.Theme.radiusLg
        border.width: 1
        border.color: hover.hovered ? Ui.Theme.primaryBorder : Ui.Theme.border
        Behavior on border.color { ColorAnimation { duration: 300 } }
        color: Ui.Theme.card
        clip: true

        HoverHandler { id: hover }

        // ================= 顶栏 64px：状态点 + 当前/下一节 + 倒计时 + 角标 + 同步 =================
        Item {
            id: topbar
            width: parent.width; height: 64

            MouseArea {
                id: dragArea
                anchors.fill: parent
                property point pressGlobal
                property point pressWindow
                property bool moved
                onPressed: mouse => {
                    pressGlobal = mapToGlobal(mouse.x, mouse.y)
                    pressWindow = Qt.point(root.x, root.y)
                    moved = false
                }
                onPositionChanged: mouse => {
                    const g = mapToGlobal(mouse.x, mouse.y)
                    const dx = g.x - pressGlobal.x, dy = g.y - pressGlobal.y
                    if (Math.abs(dx) + Math.abs(dy) > 5) moved = true
                    if (moved) { root.x = pressWindow.x + dx; root.y = pressWindow.y + dy }
                }
                onReleased: {
                    if (!moved) card.expanded = !card.expanded
                    else Bridge.save_position(root.x, root.y)
                }
            }

            Row {
                anchors.fill: parent
                anchors.leftMargin: 14
                spacing: 10

                // 品牌块 + 右下角状态角标（cc-switch 的 logo+角标模式）
                Rectangle {
                    id: logoTile
                    anchors.verticalCenter: parent.verticalCenter
                    width: 32; height: 32; radius: 10
                    color: Ui.Theme.primary
                    Text {
                        anchors.centerIn: parent
                        text: "学"
                        color: "#FFFFFF"; font.pixelSize: 15
                        font.bold: true
                        font.family: Ui.Theme.fontFamily
                    }
                    // 三态：上课中蓝呼吸 / 30 分钟内要上课橙 / 平时灰
                    readonly property bool soon: !Bridge.active
                                                 && Bridge.soonMinutes >= 0
                                                 && Bridge.soonMinutes < 30
                    Rectangle {
                        x: parent.width - 7; y: parent.height - 7
                        width: 10; height: 10; radius: 5
                        color: Bridge.active ? Ui.Theme.primary
                               : logoTile.soon ? Ui.Theme.warn
                               : Ui.Theme.muted
                        border.width: 2; border.color: Ui.Theme.card
                        SequentialAnimation on opacity {
                            running: (Bridge.active || logoTile.soon) && root.visible
                            alwaysRunToEnd: true
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.4; duration: 300; easing.type: Easing.OutQuad }
                            NumberAnimation { to: 1.0; duration: 300; easing.type: Easing.OutQuad }
                        }
                        Behavior on color { ColorAnimation { duration: 150 } }
                    }
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    width: parent.width - logoTile.width - rightZone.width - 40
                    Text {
                        width: parent.width
                        text: Bridge.title
                        color: Ui.Theme.fg
                        font.pixelSize: 14; font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                        elide: Text.ElideRight
                    }
                    Text {
                        width: parent.width
                        text: Bridge.subtitle
                        color: Ui.Theme.muted
                        font.pixelSize: 11
                        font.family: Ui.Theme.fontFamily
                        elide: Text.ElideRight
                        visible: text !== ""
                    }
                }
            }

            // 右侧功能区（声明在拖拽区之后 → 事件优先，不触发展开）
            Row {
                id: rightZone
                anchors.right: parent.right; anchors.rightMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                Text {
                    visible: Bridge.countdown !== ""
                    anchors.verticalCenter: parent.verticalCenter
                    text: Bridge.countdown
                    color: Bridge.active ? Ui.Theme.primary : Ui.Theme.muted
                    font.pixelSize: 11; font.weight: Font.Medium
                    font.family: Ui.Theme.fontFamily
                }

                Rectangle {
                    visible: Bridge.unread > 0
                    anchors.verticalCenter: parent.verticalCenter
                    width: 30; height: 24; radius: 12
                    color: Ui.Theme.danger
                    Text {
                        anchors.centerIn: parent
                        text: Bridge.unread
                        color: "#FFFFFF"
                        font.pixelSize: 11; font.bold: true
                        font.family: Ui.Theme.fontFamily
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { root.setTab(3); Bridge.action("mark_read") }
                    }
                }

                Rectangle {
                    id: syncBtn
                    anchors.verticalCenter: parent.verticalCenter
                    width: 30; height: 28; radius: Ui.Theme.radiusSm
                    color: "transparent"
                    // hover 底色独立层（透明度动画），图标不被连带淡出
                    Rectangle {
                        anchors.fill: parent; radius: parent.radius
                        color: Ui.Theme.primarySoft
                        border.width: 1; border.color: Ui.Theme.primaryBorder
                    }
                    HoverHandler { id: syncHover }
                    Text {
                        id: syncIcon
                        anchors.centerIn: parent
                        text: "⟳"
                        color: Bridge.scanning ? Ui.Theme.primary
                               : syncHover.hovered ? Ui.Theme.fg : Ui.Theme.muted
                        font.pixelSize: 15
                        font.family: Ui.Theme.fontFamily
                        Behavior on color { ColorAnimation { duration: 150 } }
                        RotationAnimation on rotation {
                            running: Bridge.scanning && root.visible
                            loops: Animation.Infinite
                            from: 0; to: 360; duration: 900
                            alwaysRunToEnd: true
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: Bridge.action("scan_now")
                    }
                }
            }
        }

        // ================= 展开面板 =================
        Item {
            id: panel
            y: 64
            width: parent.width
            height: parent.height - 64
            visible: card.expanded
            clip: true

            // ---- 标签栏：cc-switch 胶囊分段控件（灰胶囊 + 白色浮起激活芯片） ----
            Item {
                id: tabBar
                width: parent.width - 24
                x: 12; height: 42
                Rectangle {
                    id: tabCapsule
                    y: 5; width: parent.width; height: 32
                    radius: 10; color: Ui.Theme.secondary
                }
                // 滑动白色激活芯片（芯片浮在灰胶囊上 = cc-switch segmented）
                Rectangle {
                    id: tabChip
                    y: 8; height: 26; radius: 8
                    width: tabCapsule.width / 4 - 6
                    x: 3 + card.tab * (tabCapsule.width / 4)
                    color: "#FFFFFF"
                    border.width: 1; border.color: Ui.Theme.borderSoft
                    Behavior on x {
                        NumberAnimation {
                            duration: 220; easing.type: Easing.Bezier
                            easing.bezierCurve: Ui.Theme.ccEnter
                        }
                    }
                }
                Repeater {
                    model: ["今天", "课表", "作业", "动态"]
                    delegate: Item {
                        x: index * (tabBar.width / 4)
                        width: tabBar.width / 4; height: 42
                        Text {
                            anchors.centerIn: parent
                            anchors.verticalCenterOffset: 0
                            text: modelData
                            color: card.tab === index ? Ui.Theme.fg : Ui.Theme.muted
                            font.pixelSize: 12
                            font.weight: card.tab === index ? Font.DemiBold : Font.Normal
                            font.family: Ui.Theme.fontFamily
                            Behavior on color { ColorAnimation { duration: 150 } }
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                card.tab = index
                                if (index === 3) Bridge.action("mark_read")
                            }
                        }
                    }
                }
            }

            // ---- 页面容器（每页自管入场动画） ----
            Item {
                id: pages
                y: 42; width: parent.width
                height: parent.height - 42 - 26
                clip: true

                TodayPage {
                    id: pageToday
                    anchors.fill: parent
                    visible: card.tab === 0
                    onJumpToHw: card.tab = 2
                }
                WeekPage {
                    id: pageWeek
                    anchors.fill: parent
                    visible: card.tab === 1
                }
                HwPage {
                    id: pageHw
                    anchors.fill: parent
                    visible: card.tab === 2
                    onOpenDetail: Bridge.action("open_detail_hw")
                }
                EventsPage {
                    id: pageEvents
                    anchors.fill: parent
                    visible: card.tab === 3
                }
            }

            // ---- 页脚 ----
            Text {
                y: parent.height - 23; x: 14; height: 18
                verticalAlignment: Text.AlignVCenter
                text: "上次同步 " + Bridge.lastSync
                color: Ui.Theme.faint
                font.pixelSize: 10; font.family: Ui.Theme.fontFamily
            }
            Text {
                y: parent.height - 23; height: 18
                verticalAlignment: Text.AlignVCenter
                anchors.right: parent.right; anchors.rightMargin: 14
                text: "右键更多 · 点顶栏收起"
                color: Ui.Theme.faint
                font.pixelSize: 10; font.family: Ui.Theme.fontFamily
            }
        }

        // 右键菜单（自绘）：Controls 的 Popup/Menu 在无边框 Tool 窗上
        // 出过"幽灵半开弹窗"（悬在窗外、加宽后左缘探入画面），换成纯 Item
        MouseArea {
            anchors.fill: parent
            enabled: card.expanded        // 迷你条不吃右键：小热区弹菜单只会误触
            acceptedButtons: Qt.RightButton
            onClicked: mouse => {
                ctxMenu.x = Math.max(4, Math.min(mouse.x, card.width - ctxMenu.width - 8))
                ctxMenu.y = Math.max(4, Math.min(mouse.y, card.height - ctxMenu.height - 8))
                ctxMenu.visible = true
            }
        }
        Rectangle {
            id: ctxMenu
            visible: false
            z: 100
            width: 148; height: ctxCol.childrenRect.height + 8
            radius: Ui.Theme.radiusSm
            color: Ui.Theme.card
            border.width: 1; border.color: Ui.Theme.border
            Column {
                id: ctxCol
                anchors.top: parent.top; anchors.topMargin: 4
                anchors.left: parent.left; anchors.leftMargin: 4
                spacing: 0
                CtxItem { label: "检查新动态"; onPick: { ctxMenu.visible = false; Bridge.action("scan_now") } }
                CtxItem { label: "打开详情"; onPick: { ctxMenu.visible = false; Bridge.action("open_detail") } }
                CtxItem { label: "隐藏到托盘"; onPick: { ctxMenu.visible = false; Bridge.action("hide") } }
            }
        }
        // 点菜单外任意处关闭
        MouseArea {
            enabled: ctxMenu.visible
            anchors.fill: parent
            z: 99
            onClicked: ctxMenu.visible = false
        }
    }


// 右键菜单条目
component CtxItem: Rectangle {
    property string label
    signal pick()
    width: 140; height: 34
    radius: 6
    color: ciHover.hovered ? Ui.Theme.secondary : "transparent"
    Behavior on color { ColorAnimation { duration: 100 } }
    HoverHandler { id: ciHover }
    Text {
        anchors.left: parent.left; anchors.leftMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: label
        color: Ui.Theme.fg; font.pixelSize: 12
        font.family: Ui.Theme.fontFamily
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: pick()
    }
}

    Component.onCompleted: {
        const p = Bridge.initial_position()
        // 存档有效（在屏幕内）才用；否则默认主屏右上角
        if (p[0] >= 0 && p[0] < Screen.width - 100 && p[1] >= 0
                && p[1] < Screen.height - 80) {
            root.x = p[0]; root.y = p[1]
        } else {
            root.x = Screen.width - root.width - 40
            root.y = 80
        }
        enterAnim.start()
    }
    ParallelAnimation {
        id: enterAnim
        NumberAnimation { target: card; property: "opacity"; from: 0; to: 1; duration: 150 }
        SpringAnimation {
            target: card; property: "scale"
            from: 0.94; to: 1.0
            spring: 3.5; damping: 0.14; epsilon: 0.005
        }
    }
}
