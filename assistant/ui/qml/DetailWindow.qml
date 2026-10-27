import QtQuick
import QtQuick.Layouts
import QtQuick.Effects
import QtQuick.Controls.Basic
import "." as Ui

// 详情窗：动态/作业/考试/通知/设置
// FLstyle：无框自绘标题栏（右窗控：置顶/缩小/关闭）+ 灰轨分段器 +
// 白卡浮灰页（无实线描边）+ 设置分组列表卡范式。
//
// 窗口模型（单窗口在场）：本窗在场时小窗退场；「缩小/关闭」都以退场动效
// 收掉本窗 → Python visibleChanged 把小窗按原状态唤回（缩小=变小窗）。
Window {
    id: root
    width: 492; height: 656          // 卡 460×624 + 四周 16 阴影呼吸边
    flags: Qt.FramelessWindowHint | Qt.Window
           | (root.pinned ? Qt.WindowStaysOnTopHint : 0)
    color: "transparent"
    title: "学习通小助手 · 详情"

    property bool pinned: false

    function setTab(i) { bar.currentIndex = i }

    // ===== 开关窗动效（值渐变；退场播完才真隐藏 → Python 恢复小窗）=====
    function requestOpen() {
        exitAnim.stop()
        if (!root.visible) root.visible = true
        enterAnim.restart()
    }
    function requestClose() {
        if (!root.visible || exitAnim.running) return
        enterAnim.stop()
        exitAnim.restart()
    }
    onVisibleChanged: if (visible) enterAnim.restart()
    // 系统级关闭（Alt+F4 等）拦下，走统一退场
    onClosing: close => { close.accepted = false; root.requestClose() }
    // 任务栏/系统最小化 = 变回小窗，不在任务栏挂机
    onVisibilityChanged: if (visibility === Window.Minimized) root.requestClose()

    // 阴影（金样实测：很轻——0 3 10 rgba(0,0,0,0.06) 量级）
    RectangularShadow {
        anchors.fill: card
        radius: card.radius
        color: "#000000"
        opacity: 0.07
        blur: 14
        spread: 2
        offset: Qt.vector2d(0, 4)
    }

    // ===== 卡片本体（透明窗里的圆角卡）=====
    Rectangle {
        id: card
        x: 16; y: 16
        width: root.width - 32; height: root.height - 32
        radius: Ui.Theme.radiusLg
        color: Ui.Theme.page
        border.width: 1; border.color: Ui.Theme.lineSolid
        clip: true

        // ================= 自绘标题栏（金样：左极简，右窗控紧排）=================
        Item {
            id: titleBar
            width: parent.width; height: 40

            MouseArea {
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
            }

            Row {
                anchors.left: parent.left; anchors.leftMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Logo {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24; height: 24
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "学习通小助手"
                    color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle
                    font.weight: Font.DemiBold
                    font.family: Ui.Theme.fontFamily
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: Bridge.dateLabel !== ""
                    text: "· " + (Bridge.weekLabel !== ""
                          ? Bridge.dateLabel + " " + Bridge.weekLabel
                          : Bridge.dateLabel)
                    color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                    font.family: Ui.Theme.fontFamily
                }
            }

            // 右窗控：刷新井 + 置顶 + 缩小 + 关闭（热区宽 32 紧排）
            Row {
                anchors.right: parent.right; anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                WinBtn {
                    kind: "refresh"
                    busy: DBridge.refreshing
                    onClicked: {
                        if (bar.currentIndex === 0) Bridge.action("scan_now")
                        else if (bar.currentIndex === 1) DBridge.refreshHw()
                        else if (bar.currentIndex === 2) DBridge.refreshExtra("exams_progress")
                        else if (bar.currentIndex === 3) DBridge.refreshExtra("notices")
                    }
                }
                WinBtn {
                    kind: "pin"
                    active: root.pinned
                    onClicked: root.pinned = !root.pinned
                }
                WinBtn { kind: "min"; onClicked: root.requestClose() }
                WinBtn { kind: "close"; onClicked: root.requestClose() }
            }
        }

        // 标题栏/内容分隔线（前景低透明，不实色）
        Rectangle {
            y: titleBar.height; width: parent.width; height: 1
            color: Ui.Theme.line
        }

        // ================= 分段标签 =================
        // FLstyle 分段器实测范式：白色 Stadium 容器 + 未选中段=窗口底色
        // 药丸（靠白容器显形）+ 选中段实心主色胶囊白字；原位迁移无滑动
        Rectangle {
            id: bar
            property int currentIndex: 0
            x: 14; y: titleBar.height + 10
            width: parent.width - 28; height: 36; radius: 18
            color: Ui.Theme.card
            // 下标 ≠ 图标种类：这里显式配对 [kind, label]
            // kinds: 3=Pulse 2=Doc 4=Clock 8=List(通知) 6=Sliders
            readonly property var items: [[3, "动态"], [2, "作业"], [4, "考试"], [8, "通知"], [6, "设置"]]
            Row {
                anchors.fill: parent
                Repeater {
                    model: bar.items
                    delegate: Item {
                        width: bar.width / 5; height: bar.height
                        readonly property bool sel: bar.currentIndex === index
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.width - 8; height: 28; radius: 14
                            color: sel ? Ui.Theme.primary : Ui.Theme.page
                            Behavior on color { ColorAnimation { duration: Ui.Theme.durSeg } }
                        }
                        Row {
                            anchors.centerIn: parent
                            spacing: 4
                            Glyphs {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 10; height: 10; thickness: 2
                                kind: modelData[0]
                                color: sel ? "#FFFFFF" : Ui.Theme.fg2
                                Behavior on color { ColorAnimation { duration: Ui.Theme.durSeg } }
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData[1]
                                color: sel ? "#FFFFFF" : Ui.Theme.fg2
                                font.pixelSize: Ui.Theme.fsBody
                                font.weight: sel ? Font.DemiBold : Font.Normal
                                font.family: Ui.Theme.fontFamily
                                Behavior on color { ColorAnimation { duration: Ui.Theme.durSeg } }
                            }
                        }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: bar.currentIndex = index
                        }
                    }
                }
            }
        }

        // ===== 保存提示条（主色淡底胶囊，浮在页面区上）=====
        Rectangle {
            id: toast
            z: 10
            visible: toastTxt.text !== ""
            anchors.top: bar.bottom; anchors.topMargin: 8
            anchors.left: bar.left; anchors.right: bar.right
            height: 30; radius: 15
            color: Ui.Theme.primarySoft
            Text {
                id: toastTxt
                anchors.centerIn: parent
                color: Ui.Theme.primary; font.pixelSize: Ui.Theme.fsCap
                font.family: Ui.Theme.fontFamily
            }
            Timer {
                id: toastHide
                interval: 2500
                onTriggered: toastTxt.text = ""
            }
        }

        // ===== 页面区 =====
        StackLayout {
            id: pages
            currentIndex: bar.currentIndex
            anchors.top: bar.bottom; anchors.topMargin: 12
            anchors.bottom: parent.bottom; anchors.bottomMargin: 14
            anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin: 14; anchors.rightMargin: 14

            // ---------- 动态 ----------
            Item {
                id: pgDyn
                onVisibleChanged: if (visible) dynFade.restart()
                NumberAnimation {
                    id: dynFade
                    target: pgDyn; property: "opacity"
                    from: 0; to: 1; duration: Ui.Theme.durFade
                }
                Flickable {
                    anchors.fill: parent
                    contentWidth: width
                    contentHeight: tlCol.height + 8
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded; implicitWidth: 4
                        contentItem: Rectangle { radius: 2; color: Ui.Theme.badge }
                    }
                    Column {
                        id: tlCol
                        width: parent.width; spacing: 8
                        Repeater {
                            model: DBridge.timeline
                            delegate: Rectangle {
                                id: tlCard
                                width: tlCol.width
                                readonly property bool hasDetail:
                                    (modelData.detail || "") !== ""
                                height: hasDetail ? 64 : 52
                                radius: Ui.Theme.radiusLg
                                color: "#FFFFFF"
                                opacity: 0
                                Component.onCompleted: tlStagger.start()
                                SequentialAnimation {
                                    id: tlStagger
                                    PauseAnimation { duration: Math.min(index, 8) * 30 }
                                    NumberAnimation {
                                        target: tlCard; property: "opacity"
                                        to: 1; duration: 160
                                    }
                                }
                                HoverHandler { id: tlHover }
                                Rectangle {
                                    anchors.fill: parent; radius: parent.radius
                                    color: Ui.Theme.hoverOverlay
                                    opacity: tlHover.hovered ? 1 : 0
                                    Behavior on opacity { NumberAnimation { duration: Ui.Theme.durFast } }
                                }
                                // 左：课程色徽章（课程身份色，28 小方章）
                                Rectangle {
                                    x: 10; anchors.verticalCenter: parent.verticalCenter
                                    width: 28; height: 28; radius: 8
                                    color: modelData.cbg || Ui.Theme.track
                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData.course.length > 0 ? modelData.course[0] : "?"
                                        color: modelData.cfg || Ui.Theme.fg2
                                        font.pixelSize: 12; font.bold: true
                                        font.family: Ui.Theme.fontFamily
                                    }
                                }
                                // 中：课程名 + 标题
                                Column {
                                    anchors.left: parent.left; anchors.leftMargin: 46
                                    anchors.right: tlRight.left; anchors.rightMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2
                                    Text {
                                        width: parent.width
                                        text: modelData.course
                                        color: Ui.Theme.fg2; font.pixelSize: 10
                                        font.family: Ui.Theme.fontFamily
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        text: modelData.title
                                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody
                                        font.family: Ui.Theme.fontFamily
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        visible: tlCard.hasDetail
                                        width: parent.width
                                        // detail 可能是带换行的通知正文——压成单行
                                        // 再 elide（elide 只截行宽不截行数，多行
                                        // 会撑爆卡片从后面卡片的间隙漏出来）
                                        text: {
                                            const s = (modelData.detail || "")
                                                .replace(/\s+/g, " ").trim()
                                            return s
                                        }
                                        // 附加信息行：短值（得分/开考时间）给主色
                                        // 点睛，长文（通知正文摘要）回灰
                                        color: text.length <= 16
                                               ? Ui.Theme.primary : Ui.Theme.fg2
                                        font.pixelSize: 10
                                        font.weight: Font.Medium
                                        font.family: Ui.Theme.fontFamily
                                        elide: Text.ElideRight
                                    }
                                }
                                // 右：药丸 + 时间
                                Column {
                                    id: tlRight
                                    anchors.right: parent.right; anchors.rightMargin: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 3
                                    Rectangle {
                                        width: tlTag.width + 12; height: 18; radius: 9
                                        color: modelData.priority === "high" ? Ui.Theme.dangerSoft
                                               : Ui.Theme.track
                                        Text {
                                            id: tlTag
                                            anchors.centerIn: parent; text: modelData.tag
                                            color: modelData.priority === "high" ? Ui.Theme.danger : Ui.Theme.fg2
                                            font.pixelSize: 10; font.weight: Font.Medium
                                            font.family: Ui.Theme.fontFamily
                                        }
                                    }
                                    Text {
                                        text: modelData.time
                                        color: Ui.Theme.fg3; font.pixelSize: 9
                                        font.family: Ui.Theme.fontFamily
                                    }
                                }
                            }
                        }
                        // 空态（图标井 + 粗标题 + 副文）
                        Rectangle {
                            visible: DBridge.timeline.length === 0
                            width: parent.width; height: 96; radius: Ui.Theme.radiusLg
                            color: "#FFFFFF"
                            Column {
                                anchors.centerIn: parent; spacing: 6
                                Item {
                                    width: 32; height: 32
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    Rectangle { anchors.fill: parent; radius: 16; color: Ui.Theme.primarySoft }
                                    Glyphs {
                                        anchors.centerIn: parent
                                        width: 14; height: 14; thickness: 2.4
                                        kind: 3
                                        color: Ui.Theme.primary
                                    }
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "还没有动态"
                                    color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                                    font.family: Ui.Theme.fontFamily
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "检查到新作业/资料/通知会出现在这里"
                                    color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                                    font.family: Ui.Theme.fontFamily
                                }
                            }
                        }
                    }
                }
            }

            // ---------- 作业 ----------
            Item {
                id: pgHw
                onVisibleChanged: if (visible) hwFade.restart()
                NumberAnimation {
                    id: hwFade
                    target: pgHw; property: "opacity"
                    from: 0; to: 1; duration: Ui.Theme.durFade
                }
                Flickable {
                    anchors.fill: parent
                    contentWidth: width
                    contentHeight: hwCol.height + 8
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded; implicitWidth: 4
                        contentItem: Rectangle { radius: 2; color: Ui.Theme.badge }
                    }
                    Column {
                        id: hwCol
                        width: parent.width; spacing: 8
                        Rectangle {
                            visible: DBridge.hwFailed
                            width: parent.width; height: 56; radius: Ui.Theme.radiusLg
                            color: Ui.Theme.dangerSoft
                            Text {
                                anchors.centerIn: parent
                                text: "作业获取失败，点右上「⟳ 刷新」重试"
                                color: Ui.Theme.danger; font.pixelSize: Ui.Theme.fsBody
                                font.family: Ui.Theme.fontFamily
                            }
                        }
                        // 空态：成功语义（图标井 + 粗标题 + 副文）
                        Rectangle {
                            visible: !DBridge.hwFailed && DBridge.hw.length === 0
                                     && DBridge.hwIgnored === 0
                            width: parent.width; height: 96; radius: Ui.Theme.radiusLg
                            color: "#FFFFFF"
                            Column {
                                anchors.centerIn: parent; spacing: 6
                                Item {
                                    width: 32; height: 32
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    Rectangle { anchors.fill: parent; radius: 16; color: Ui.Theme.okSoft }
                                    Glyphs {
                                        anchors.centerIn: parent
                                        width: 14; height: 14; thickness: 2.4
                                        kind: 7
                                        color: Ui.Theme.ok
                                    }
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "没有待交的作业"
                                    color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                                    font.family: Ui.Theme.fontFamily
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "都交完了，真省心"
                                    color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                                    font.family: Ui.Theme.fontFamily
                                }
                            }
                        }
                        Repeater {
                            model: DBridge.hw
                            delegate: Rectangle {
                                id: hwCard
                                width: hwCol.width; height: 64
                                radius: Ui.Theme.radiusLg
                                color: "#FFFFFF"
                                opacity: (modelData.urgency === "expired"
                                          || modelData.urgency === "unknown") ? 0.62 : 1
                                readonly property color urgencyColor:
                                    modelData.urgency === "high" ? Ui.Theme.danger
                                    : modelData.urgency === "mid" ? Ui.Theme.warn
                                    : modelData.urgency === "expired" ? Ui.Theme.fg3
                                    : Ui.Theme.primary
                                // 左缘紧迫度竖条
                                Rectangle {
                                    x: 0; width: 3
                                    anchors.top: parent.top; anchors.topMargin: 14
                                    anchors.bottom: parent.bottom; anchors.bottomMargin: 14
                                    radius: 1.5
                                    color: hwCard.urgencyColor
                                }
                                HoverHandler { id: hwCardHover }
                                // 悬停操作钮：去交（开学习通）/ ✕（从看板隐藏）
                                Row {
                                    anchors.top: parent.top; anchors.topMargin: 4
                                    anchors.right: parent.right; anchors.rightMargin: 6
                                    spacing: 4
                                    Rectangle {
                                        visible: hwCardHover.hovered
                                        width: goTxt.width + 12; height: 18; radius: 9
                                        color: Ui.Theme.primarySoft
                                        Text {
                                            id: goTxt
                                            anchors.centerIn: parent; text: "去交 ↗"
                                            color: Ui.Theme.primary
                                            font.pixelSize: 9; font.weight: Font.Medium
                                            font.family: Ui.Theme.fontFamily
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: DBridge.openHw(
                                                modelData.url || modelData.courseUrl || "",
                                                modelData.course, modelData.title)
                                        }
                                    }
                                    Rectangle {
                                        visible: hwCardHover.hovered
                                        width: 18; height: 18; radius: 9
                                        color: Ui.Theme.track
                                        Text {
                                            anchors.centerIn: parent; text: "✕"
                                            color: Ui.Theme.fg2
                                            font.pixelSize: 9
                                            font.family: Ui.Theme.fontFamily
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: DBridge.ignoreHw(
                                                modelData.course, modelData.title,
                                                modelData.url || "")
                                        }
                                    }
                                }
                                Rectangle {
                                    x: 10; anchors.verticalCenter: parent.verticalCenter
                                    width: 28; height: 28; radius: 8
                                    color: modelData.cbg || Ui.Theme.track
                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData.course.length > 0 ? modelData.course[0] : "?"
                                        color: modelData.cfg || Ui.Theme.fg2
                                        font.pixelSize: 12; font.bold: true
                                        font.family: Ui.Theme.fontFamily
                                    }
                                }
                                Column {
                                    anchors.left: parent.left; anchors.leftMargin: 46
                                    anchors.right: hwRight.left; anchors.rightMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 3
                                    Text {
                                        width: parent.width
                                        text: modelData.course
                                        color: Ui.Theme.fg3; font.pixelSize: 10
                                        font.family: Ui.Theme.fontFamily
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        text: modelData.title
                                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody
                                        font.weight: Font.Medium
                                        font.family: Ui.Theme.fontFamily
                                        elide: Text.ElideRight
                                        wrapMode: Text.WrapAnywhere
                                        maximumLineCount: 2
                                    }
                                }
                                Column {
                                    id: hwRight
                                    anchors.right: parent.right; anchors.rightMargin: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 3
                                    Text {
                                        text: modelData.deadlineLabel
                                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsSub
                                        font.family: Ui.Theme.fontFamily
                                    }
                                    Text {
                                        text: modelData.remainText
                                        color: modelData.urgency === "high" ? Ui.Theme.danger
                                               : modelData.urgency === "mid" ? Ui.Theme.warn
                                               : Ui.Theme.fg2
                                        font.pixelSize: Ui.Theme.fsSub; font.weight: Font.Medium
                                        font.family: Ui.Theme.fontFamily
                                    }
                                }
                            }
                        }
                        // 忽略恢复条（有隐藏才出现；沉底，别挡新作业；轨色信息条）
                        Rectangle {
                            visible: DBridge.hwIgnored > 0
                            width: parent.width; height: 34; radius: Ui.Theme.radiusSm
                            color: Ui.Theme.track
                            Text {
                                anchors.centerIn: parent
                                text: "已隐藏 " + DBridge.hwIgnored
                                      + " 条作业（不打算交的）· 点击全部恢复"
                                color: Ui.Theme.fg2; font.pixelSize: 10
                                font.family: Ui.Theme.fontFamily
                            }
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: DBridge.unignoreAll()
                            }
                        }
                    }
                }
            }

            // ---------- 考试 ----------
            ExamPage {
            }

            // ---------- 通知 ----------
            NoticePage {
            }

            // ---------- 设置（滚动区 + 常驻保存按钮）----------
            Item {
                id: setPage

                Flickable {
                    id: setFlick
                    anchors.top: parent.top; anchors.bottom: saveBtn.top
                    anchors.bottomMargin: 16
                    anchors.left: parent.left; anchors.right: parent.right
                    contentWidth: width
                    contentHeight: setCol.height + 28
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded; implicitWidth: 4
                        contentItem: Rectangle { radius: 2; color: Ui.Theme.badge }
                    }

                    // 表单状态（挂 Flickable 上；保存时打包回 DBridge）
                    property string theme
                    property int interval
                    property bool toastOn
                    property string dnd
                    property bool autostart
                    property bool emailOn
                    property string emailTo
                    property string smtpHost
                    property string smtpUser
                    property string smtpPass

                    Component.onCompleted: {
                        const s = DBridge.settings
                        theme = s.theme || "light"
                        interval = s.scan_interval_min || 30
                        toastOn = s.toast_enabled !== false
                        dnd = s.dnd || "23:00-07:30"
                        autostart = s.autostart === true
                        emailOn = s.email_enabled === true
                        emailTo = s.email_to || ""
                        smtpHost = s.smtp_host || ""
                        smtpUser = s.smtp_user || ""
                        smtpPass = s.smtp_pass || ""
                    }

                    Column {
                        id: setCol
                        width: parent.width; spacing: 8

                        // 分组标题在卡外上方（FLstyle：13px 灰、卡外、带小图标）
                        Item {
                            width: parent.width; height: 24
                            Row {
                                anchors.left: parent.left; anchors.bottom: parent.bottom
                                anchors.bottomMargin: 4
                                spacing: 6
                                Glyphs {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 12; height: 12; thickness: 2
                                    kind: 6   // Sliders
                                    color: Ui.Theme.fg2
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "常规"
                                    color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsTitle
                                    font.weight: Font.Medium
                                    font.family: Ui.Theme.fontFamily
                                }
                            }
                        }

                        // 常规
                        Rectangle {
                            width: parent.width; radius: Ui.Theme.radiusLg
                            color: "#FFFFFF"
                            height: genCol.height + 16
                            Column {
                                id: genCol
                                x: 14; y: 8; width: parent.width - 28; spacing: 0

                                Row {
                                    width: parent.width; height: 44
                                    Item {
                                        width: 96; height: parent.height
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: "巡检间隔"; color: Ui.Theme.fg
                                            font.pixelSize: Ui.Theme.fsBody; font.family: Ui.Theme.fontFamily
                                        }
                                    }
                                    // 步进器 = 输入轨（白卡上变暗一档），按钮 hover 井色
                                    Rectangle {
                                        width: 130; height: 32; radius: Ui.Theme.radiusSm
                                        color: Ui.Theme.track
                                        anchors.verticalCenter: parent.verticalCenter
                                        Row {
                                            anchors.centerIn: parent; spacing: 10
                                            Rectangle {
                                                width: 24; height: 24; radius: Ui.Theme.radiusSm - 2
                                                color: minusHover.hovered ? Ui.Theme.well : "transparent"
                                                Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
                                                HoverHandler { id: minusHover }
                                                Text {
                                                    anchors.centerIn: parent; text: "−"
                                                    color: Ui.Theme.fg; font.pixelSize: 14
                                                    font.family: Ui.Theme.fontFamily
                                                }
                                                MouseArea {
                                                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                    onClicked: setFlick.interval = Math.max(5, setFlick.interval - 5)
                                                }
                                            }
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: setFlick.interval + " 分钟"
                                                color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody
                                                font.family: Ui.Theme.fontFamily
                                                font.features: { "tnum": 1 }
                                            }
                                            Rectangle {
                                                width: 24; height: 24; radius: Ui.Theme.radiusSm - 2
                                                color: plusHover.hovered ? Ui.Theme.well : "transparent"
                                                Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
                                                HoverHandler { id: plusHover }
                                                Text {
                                                    anchors.centerIn: parent; text: "+"
                                                    color: Ui.Theme.fg; font.pixelSize: 14
                                                    font.family: Ui.Theme.fontFamily
                                                }
                                                MouseArea {
                                                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                    onClicked: setFlick.interval = Math.min(240, setFlick.interval + 5)
                                                }
                                            }
                                        }
                                    }
                                }
                                SetSep {}
                                SetRow {
                                    label: "免打扰时段"
                                    Field {
                                        width: 160; text: setFlick.dnd
                                        onTextChanged: setFlick.dnd = text
                                    }
                                }
                                SetSep {}
                                SetRow {
                                    label: "桌面弹窗"
                                    SetSwitch {
                                        checked: setFlick.toastOn
                                        onToggled: setFlick.toastOn = checked
                                    }
                                }
                                SetSep {}
                                SetRow {
                                    label: "开机自启"
                                    SetSwitch {
                                        checked: setFlick.autostart
                                        onToggled: setFlick.autostart = checked
                                    }
                                }
                                SetSep {}
                                SetRow {
                                    label: "快捷键"
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Alt+Shift+C 唤起/隐藏小窗"
                                        color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                                        font.family: Ui.Theme.fontFamily
                                    }
                                }
                                SetSep {}
                                SetRow {
                                    label: "课表到手机"
                                    // 白卡上的次级按钮 = 轨色胶囊
                                    Rectangle {
                                        width: icsTxt.width + 22; height: 28; radius: 14
                                        color: Ui.Theme.track
                                        Text {
                                            id: icsTxt
                                            anchors.centerIn: parent
                                            text: "导出日历 (.ics)"
                                            color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsCap
                                            font.family: Ui.Theme.fontFamily
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: DBridge.exportIcs()
                                        }
                                    }
                                }
                            }
                        }

                        // 分组标题在卡外上方（与上一卡间隔 = 列隙 8 + 标题行高）
                        Item {
                            width: parent.width; height: 32
                            Row {
                                anchors.left: parent.left; anchors.bottom: parent.bottom
                                anchors.bottomMargin: 4
                                spacing: 6
                                Glyphs {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 12; height: 12; thickness: 2
                                    kind: 11   // Mail
                                    color: Ui.Theme.fg2
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "邮件提醒"
                                    color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsTitle
                                    font.weight: Font.Medium
                                    font.family: Ui.Theme.fontFamily
                                }
                            }
                        }

                        // 邮件提醒
                        Rectangle {
                            width: parent.width; radius: Ui.Theme.radiusLg
                            color: "#FFFFFF"
                            height: mailCol.height + 16
                            Column {
                                id: mailCol
                                x: 14; y: 8; width: parent.width - 28; spacing: 0
                                SetRow {
                                    label: "重要事项发邮件"
                                    SetSwitch {
                                        checked: setFlick.emailOn
                                        onToggled: setFlick.emailOn = checked
                                    }
                                }
                                SetSep {}
                                SetRow {
                                    label: "收件邮箱"
                                    Field {
                                        width: 200; text: setFlick.emailTo
                                        placeholder: "someone@qq.com"
                                        onTextChanged: setFlick.emailTo = text
                                    }
                                }
                                SetSep {}
                                SetRow {
                                    label: "SMTP 服务器"
                                    Field {
                                        width: 200; text: setFlick.smtpHost
                                        placeholder: "smtp.qq.com"
                                        onTextChanged: setFlick.smtpHost = text
                                    }
                                }
                                SetSep {}
                                SetRow {
                                    label: "发件账号"
                                    Field {
                                        width: 200; text: setFlick.smtpUser
                                        onTextChanged: setFlick.smtpUser = text
                                    }
                                }
                                SetSep {}
                                SetRow {
                                    label: "授权码"
                                    Field {
                                        width: 200; text: setFlick.smtpPass
                                        echoMode: TextInput.Password
                                        onTextChanged: setFlick.smtpPass = text
                                    }
                                }
                            }
                        }
                    }
                }   // Flickable setFlick 到此关闭（saveBtn 必须是它的兄弟）

                // 常驻保存按钮：一屏唯一主动作 = 实心主色胶囊，不跟滚动
                Rectangle {
                    id: saveBtn
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left; anchors.right: parent.right
                    height: 42; radius: 21
                    color: saveHover.hovered ? Ui.Theme.primaryDeep : Ui.Theme.primary
                    Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
                    HoverHandler { id: saveHover }
                    Text {
                        anchors.centerIn: parent; text: "保存设置"
                        color: "#FFFFFF"; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                    }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: DBridge.saveSettings({
                            "theme": setFlick.theme,
                            "scan_interval_min": setFlick.interval,
                            "toast_enabled": setFlick.toastOn,
                            "dnd": setFlick.dnd,
                            "autostart": setFlick.autostart,
                            "email_enabled": setFlick.emailOn,
                            "email_to": setFlick.emailTo,
                            "smtp_host": setFlick.smtpHost,
                            "smtp_user": setFlick.smtpUser,
                            "smtp_pass": setFlick.smtpPass,
                        })
                    }
                }
            }
        }

        // ===== 内联组件 =====
        // 行内分隔线：前景低透明，永不实色；两侧内缩不触卡边
        component SetSep: Rectangle {
            x: 16; width: parent.width - 32; height: 1
            color: Ui.Theme.line
        }

        component SetRow: Row {
            property string label
            default property alias _slot: slot.data
            spacing: 8
            Item {
                width: 96; height: 44
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: parent.parent.label
                    color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody
                    font.family: Ui.Theme.fontFamily
                }
            }
            Item { id: slot; width: childrenRect.width; height: 44 }
        }

        component Field: TextField {
            id: field
            property string placeholder
            placeholderText: placeholder
            placeholderTextColor: Ui.Theme.fg3
            color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody
            font.family: Ui.Theme.fontFamily
            selectByMouse: true
            implicitHeight: 34
            leftPadding: 10; rightPadding: 10
            background: Rectangle {
                // 输入 = 轨（白卡上变暗一档）；聚焦 = 实心主色描边
                radius: 17; color: Ui.Theme.track
                border.width: field.activeFocus ? 2 : 0
                border.color: Ui.Theme.primary
                Behavior on border.width { NumberAnimation { duration: Ui.Theme.durFast } }
            }
        }

        // FLstyle 开关：ON 轨=主色白滑块；OFF 轨=灰轨灰旋钮（迁移只做颜色渐变）
        component SetSwitch: Switch {
            id: sw
            indicator: Rectangle {
                implicitWidth: 48; implicitHeight: 28; radius: 14
                color: sw.checked ? Ui.Theme.primary : Ui.Theme.track
                Behavior on color { ColorAnimation { duration: 120 } }
                Rectangle {
                    width: 22; height: 22; radius: 11
                    y: (parent.height - height) / 2
                    x: sw.checked ? parent.width - width - 3 : 3
                    color: sw.checked ? "#FFFFFF" : Ui.Theme.fg3
                    Behavior on x { NumberAnimation { duration: 120 } }
                }
            }
        }

        // 标题栏窗控钮：宽热区（32×28）无边钮，hover 才显底；
        // 关闭钮 hover = 实心红底白图标（Windows 惯例，金样建议）
        component WinBtn: Rectangle {
            id: wb
            property string kind          // refresh / pin / min / close
            property bool active: false   // pin 激活态
            property bool busy: false     // refresh 旋转
            signal clicked()
            width: kind === "refresh" ? 32 : 32; height: 28
            radius: 7
            color: wbHover.hovered
                   ? (kind === "close" ? Ui.Theme.danger : Ui.Theme.well)
                   : "transparent"
            Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
            HoverHandler { id: wbHover }
            readonly property color glyph: kind === "close" && wbHover.hovered
                   ? "#FFFFFF"
                   : wb.busy || wb.active ? Ui.Theme.primary : Ui.Theme.fg2
            // 刷新：⟳ 字符（实机渲染已验证）
            Text {
                visible: wb.kind === "refresh"
                anchors.centerIn: parent; text: "⟳"
                color: wb.glyph
                font.pixelSize: 13
                font.family: Ui.Theme.fontFamily
                Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
                RotationAnimation on rotation {
                    running: wb.busy
                    loops: Animation.Infinite
                    from: 0; to: 360; duration: 900
                    alwaysRunToEnd: true
                }
            }
            Glyphs {
                visible: wb.kind === "pin"
                anchors.centerIn: parent
                width: 12; height: 12; thickness: 2
                kind: 10
                color: wb.active || wbHover.hovered ? Ui.Theme.fg : Ui.Theme.fg2
                Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
            }
            // 最小化：横杆
            Rectangle {
                visible: wb.kind === "min"
                anchors.centerIn: parent
                width: 10; height: 2; radius: 1
                color: wbHover.hovered ? Ui.Theme.fg : Ui.Theme.fg2
                Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
            }
            // 关闭：两根 45° 交叉杆拼 ✕（绕中心旋转，45/-45 才是叉不是加号）
            Item {
                visible: wb.kind === "close"
                anchors.centerIn: parent
                width: 10; height: 10
                Rectangle {
                    anchors.centerIn: parent
                    width: 10; height: 1.8; radius: 0.9
                    color: wb.glyph
                    Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
                    rotation: 45
                }
                Rectangle {
                    anchors.centerIn: parent
                    width: 10; height: 1.8; radius: 0.9
                    color: wb.glyph
                    Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
                    rotation: -45
                }
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: wb.clicked()
            }
        }

        // 保存成功后自动收起详情窗（提示闪一下再关，失败则留着改）
        Timer {
            id: saveCloseTimer
            interval: 800
            onTriggered: root.requestClose()
        }

        Connections {
            target: DBridge
            function onTabRequested(i) { root.setTab(i) }
            function onSettingsApplied(msg) {
                toastTxt.text = msg
                toastHide.restart()
                if (msg === "已保存") saveCloseTimer.restart()
            }
        }
    }

    // ===== 开关窗动效本体（值渐变：透明度 + 轻缩放）=====
    ParallelAnimation {
        id: enterAnim
        NumberAnimation {
            target: card; property: "opacity"; from: 0; to: 1; duration: 160
            easing.type: Easing.Bezier; easing.bezierCurve: Ui.Theme.ccEnter
        }
        NumberAnimation {
            target: card; property: "scale"; from: 0.97; to: 1; duration: 200
            easing.type: Easing.Bezier; easing.bezierCurve: Ui.Theme.ccEnter
        }
    }
    SequentialAnimation {
        id: exitAnim
        ParallelAnimation {
            NumberAnimation {
                target: card; property: "opacity"; to: 0; duration: 110
                easing.type: Easing.Bezier; easing.bezierCurve: Ui.Theme.ccExit
            }
            NumberAnimation {
                target: card; property: "scale"; to: 0.98; duration: 110
                easing.type: Easing.Bezier; easing.bezierCurve: Ui.Theme.ccExit
            }
        }
        onStopped: root.visible = false   // → Python visibleChanged → 恢复小窗
    }
}
