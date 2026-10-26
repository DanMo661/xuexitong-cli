import QtQuick
import QtQuick.Controls.Basic
import "." as Ui

// 悬浮小窗：迷你条(360×64) ↔ 展开卡(360×540)
// 展开卡 = 顶栏 + 标签页(今天/课表/作业/动态) + 页脚
// 视觉纪律：FLstyle 浅色（灰页 L95 + 白卡分层，无实线边框；
// 主色只给选中段/交互态/品牌点，绝不铺大色块）
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
        // 窗口缘 = 低透明线的预混实色（border 不吃透明色，见 Theme.lineSolid 注）
        border.width: 1
        border.color: Ui.Theme.lineSolid
        color: Ui.Theme.page          // 窗口表面 = L95 页灰；卡片内容浮白
        clip: true

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
                    snapAnim.stop()   // 磁吸滑行中再抓 = 立即接管
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
                    else topbar._snapToEdges()   // 嵌套对象里只认组件根，函数要 id 限定
                }
            }

            function _snapToEdges() {
                // 贴边磁吸：24px 内吸附最近屏幕边（Class Widgets 手感的简化版）
                const m = 24
                let tx = root.x, ty = root.y
                if (root.x < m) tx = 0
                else if (root.x + root.width > Screen.width - m)
                    tx = Screen.width - root.width
                if (root.y < m) ty = 0
                if (tx === root.x && ty === root.y) {
                    Bridge.save_position(root.x, root.y)
                    return
                }
                snapAnim.stop()
                snapAnim.tx = tx; snapAnim.ty = ty
                snapAnim.start()
            }

            ParallelAnimation {
                id: snapAnim
                property real tx: 0
                property real ty: 0
                NumberAnimation {
                    target: root; property: "x"; to: snapAnim.tx
                    duration: 200; easing.type: Easing.Bezier
                    easing.bezierCurve: Ui.Theme.ccEnter
                }
                NumberAnimation {
                    target: root; property: "y"; to: snapAnim.ty
                    duration: 200; easing.type: Easing.Bezier
                    easing.bezierCurve: Ui.Theme.ccEnter
                }
                onStopped: Bridge.save_position(root.x, root.y)
            }

            Row {
                anchors.fill: parent
                anchors.leftMargin: 14
                spacing: 10

                // 品牌块 + 右下角状态角标（品牌点 = 主色允许的少数位置之一）
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
                        x: parent.width - 8; y: parent.height - 8
                        width: 12; height: 12; radius: 6
                        color: Bridge.active ? Ui.Theme.primary
                               : logoTile.soon ? Ui.Theme.warn
                               : Ui.Theme.fg2
                        border.width: 2; border.color: Ui.Theme.page
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
                        font.pixelSize: Ui.Theme.fsHead; font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                        elide: Text.ElideRight
                    }
                    Text {
                        width: parent.width
                        text: Bridge.subtitle
                        color: Ui.Theme.fg2
                        font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                        elide: Text.ElideRight
                        visible: text !== ""
                    }
                }
            }

            // 右侧功能区（声明在拖拽区之后 → 事件优先，不触发展开）
            Row {
                id: rightZone
                anchors.right: parent.right; anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                // 倒计时是唯一跳动数值 → tabular nums，数字宽度恒定不抖
                Text {
                    visible: Bridge.countdown !== ""
                    anchors.verticalCenter: parent.verticalCenter
                    text: Bridge.countdown
                    color: Bridge.active ? Ui.Theme.primary : Ui.Theme.fg2
                    font.pixelSize: Ui.Theme.fsSub; font.weight: Font.DemiBold
                    font.family: Ui.Theme.fontFamily
                    font.features: { "tnum": 1 }
                }

                Rectangle {
                    visible: Bridge.unread > 0
                    anchors.verticalCenter: parent.verticalCenter
                    width: 30; height: 22; radius: 11
                    color: Ui.Theme.danger
                    Text {
                        anchors.centerIn: parent
                        text: Bridge.unread
                        color: "#FFFFFF"
                        font.pixelSize: Ui.Theme.fsCap; font.bold: true
                        font.family: Ui.Theme.fontFamily
                        font.features: { "tnum": 1 }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { root.setTab(3); Bridge.action("mark_read") }
                    }
                }

                // 同步钮 = 图标井：中性井底 + 强调色图形（暗底亮图形）
                Rectangle {
                    id: syncBtn
                    anchors.verticalCenter: parent.verticalCenter
                    width: 30; height: 30; radius: Ui.Theme.radiusSm
                    color: Ui.Theme.well
                    HoverHandler { id: syncHover }
                    Text {
                        id: syncIcon
                        anchors.centerIn: parent
                        text: "⟳"
                        color: Bridge.scanning ? Ui.Theme.primary
                               : syncHover.hovered ? Ui.Theme.primary
                               : Ui.Theme.fg2
                        font.pixelSize: 15
                        font.family: Ui.Theme.fontFamily
                        Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
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

        // 顶栏/面板分隔线（展开才画；前景低透明，不实色）
        Rectangle {
            visible: card.expanded
            y: 64; width: parent.width; height: 1
            color: Ui.Theme.line
        }

        // 全局右键菜单（自绘）：Controls 的 Popup/Menu 在无边框 Tool 窗上
        // 出过"幽灵半开弹窗"（悬在窗外、加宽后左缘探入画面），换成纯 Item。
        // 必须声明在 panel 之前：兄弟层后声明者在上面，放后面会吃掉
        // HwPage 作业卡自己的右键菜单（事件永远到不了卡片）
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

        // ================= 展开面板 =================
        Item {
            id: panel
            y: 64
            width: parent.width
            height: parent.height - 64
            visible: card.expanded
            clip: true

            // ---- 标签栏：FLstyle 分段器（灰轨 + 选中段实心主色胶囊白字，
            // 原位淡入淡出迁移，无滑动 thumb；每段带小图标）----
            Item {
                id: tabBar
                width: parent.width - 24
                x: 12; height: 40
                // 轨：白底灰页上"往中灰方向"一档（L91）
                Rectangle {
                    y: 4; width: parent.width; height: 32
                    radius: 16; color: Ui.Theme.card
                    // FLstyle 分段器范式：白色容器卡，段各自有胶囊底
                }
                Repeater {
                    // 下标即 Glyphs 图标种类：0=Dot 今天 1=Grid 课表 2=Doc 作业 3=Pulse 动态
                    model: ["今天", "课表", "作业", "动态"]
                    delegate: Item {
                        x: index * (tabBar.width / 4)
                        width: tabBar.width / 4; height: 40
                        readonly property bool sel: card.tab === index
                        // 选中段：实心主色全圆胶囊；迁移 = 颜色原位渐变（150~250ms）
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.width - 8; height: 24
                            radius: 12
                            color: sel ? Ui.Theme.primary : Ui.Theme.track
                            Behavior on color { ColorAnimation { duration: Ui.Theme.durSeg } }
                        }
                        Row {
                            anchors.centerIn: parent
                            spacing: 4
                            Glyphs {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 10; height: 10; thickness: 2
                                kind: index
                                color: sel ? "#FFFFFF" : Ui.Theme.fg2
                                Behavior on color { ColorAnimation { duration: Ui.Theme.durSeg } }
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData
                                color: sel ? "#FFFFFF" : Ui.Theme.fg2
                                font.pixelSize: Ui.Theme.fsBody
                                font.weight: sel ? Font.DemiBold : Font.Normal
                                font.family: Ui.Theme.fontFamily
                                Behavior on color { ColorAnimation { duration: Ui.Theme.durSeg } }
                            }
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

            // ---- 页面容器（根级导航 = 硬切；页内入场只做透明度渐变，零位移） ----
            Item {
                id: pages
                y: 40; width: parent.width
                height: parent.height - 40 - 26
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
                color: Ui.Theme.fg3
                font.pixelSize: 10; font.family: Ui.Theme.fontFamily
            }
            Text {
                y: parent.height - 23; height: 18
                verticalAlignment: Text.AlignVCenter
                anchors.right: parent.right; anchors.rightMargin: 14
                text: "右键更多 · 点顶栏收起"
                color: Ui.Theme.fg3
                font.pixelSize: 10; font.family: Ui.Theme.fontFamily
            }
        }

        // 右键菜单浮层本体（z:100 盖一切）
        Rectangle {
            id: ctxMenu
            visible: false
            z: 100
            width: 148; height: ctxCol.childrenRect.height + 8
            radius: Ui.Theme.radiusMd
            color: Ui.Theme.card
            border.width: 1; border.color: Ui.Theme.lineSolid
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
    color: ciHover.hovered ? Ui.Theme.track : "transparent"
    Behavior on color { ColorAnimation { duration: 100 } }
    HoverHandler { id: ciHover }
    Text {
        anchors.left: parent.left; anchors.leftMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: label
        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody
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
