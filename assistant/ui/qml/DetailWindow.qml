import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "." as Ui

// 详情窗：动态/作业/考试/通知/设置
// FLstyle：窗底 = L95 页灰；内容 = 白卡浮灰页（无实线描边）；
// 分段器 = 灰轨 + 选中段实心主色胶囊（原位迁移）；设置 = 分组列表卡范式
// （分组标题 13px 灰在卡外上方、行间低透明分隔线、行内主文字/次文字）
Window {
    id: root
    width: 460; height: 600
    minimumWidth: 420; minimumHeight: 520
    title: "学习通小助手 · 详情"
    color: Ui.Theme.page

    function setTab(i) { bar.currentIndex = i }

    // ===== 头部（品牌块 + 标题 + 刷新）=====
    Column {
        id: head
        anchors.top: parent.top; anchors.topMargin: 14
        anchors.left: parent.left; anchors.right: parent.right
        anchors.leftMargin: 16; anchors.rightMargin: 16
        spacing: 12

        Item {
            width: parent.width; height: 34
            Row {
                anchors.left: parent.left
                spacing: 10
                Rectangle {
                    width: 34; height: 34; radius: 10
                    color: Ui.Theme.primary
                    Text {
                        anchors.centerIn: parent; text: "学"
                        color: "#FFFFFF"; font.pixelSize: 16; font.bold: true
                        font.family: Ui.Theme.fontFamily
                    }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter; spacing: 1
                    Text {
                        text: "详情"
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsPage
                        font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        text: "动态、作业、考试、通知和设置都在这"
                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }
            // 刷新按钮锚右：白卡胶囊浮在灰页上（中性按钮，主色只给图标）
            Rectangle {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: refreshGlyph.width + refreshTxt.width + 22; height: 30; radius: 15
                color: Ui.Theme.card
                // 作业/考试/通知三页页内刷；动态页走全局巡检（同一按钮
                // 保持头部一致，别让"动态页右上角缺一块"）
                visible: bar.currentIndex >= 0 && bar.currentIndex <= 3
                Row {
                    anchors.centerIn: parent; spacing: 5
                    Text {
                        id: refreshGlyph
                        text: "⟳"
                        color: Ui.Theme.primary; font.pixelSize: 12
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        id: refreshTxt
                        text: "刷新"
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody
                        font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (bar.currentIndex === 0) Bridge.action("scan_now")
                        else if (bar.currentIndex === 1) DBridge.refreshHw()
                        else if (bar.currentIndex === 2) DBridge.refreshExtra("exams_progress")
                        else if (bar.currentIndex === 3) DBridge.refreshExtra("notices")
                    }
                }
            }
        }

        // 分段标签（同小窗）：灰轨 + 选中段实心主色 + 每段小图标
        Rectangle {
            id: bar
            property int currentIndex: 0
            width: parent.width; height: 36; radius: 18
            color: Ui.Theme.card   // 白容器分段器（与主窗一致）
            // 下标 ≠ 图标种类：这里显式配对 [kind, label]
            // kinds: 2=Doc 3=Pulse 4=Clock 8=List(通知,别用 Bell——与表盘同形) 6=Sliders
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
                            width: parent.width - 8; height: 26; radius: 13
                            color: sel ? Ui.Theme.primary : Ui.Theme.track
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
    }

    // ===== 保存提示条（主色淡底胶囊）=====
    Rectangle {
        id: toast
        z: 10   // 盖在页面区上（StackLayout 声明在后，不提层会被白卡压住）
        visible: toastTxt.text !== ""
        anchors.top: head.bottom; anchors.topMargin: 8
        anchors.left: head.left; anchors.right: head.right
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
        anchors.top: head.bottom; anchors.topMargin: 12
        anchors.bottom: parent.bottom; anchors.bottomMargin: 14
        anchors.left: parent.left; anchors.right: parent.right
        anchors.leftMargin: 16; anchors.rightMargin: 16

        // ---------- 动态 ----------
        Flickable {
            contentWidth: width
            contentHeight: tlCol.height + 8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
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
                        // 左：课程色块（课程身份色）
                        Rectangle {
                            x: 10; anchors.verticalCenter: parent.verticalCenter
                            width: 36; height: 36; radius: 10
                            color: modelData.cbg || Ui.Theme.track
                            Text {
                                anchors.centerIn: parent
                                text: modelData.course.length > 0 ? modelData.course[0] : "?"
                                color: modelData.cfg || Ui.Theme.fg2
                                font.pixelSize: 15; font.bold: true
                                font.family: Ui.Theme.fontFamily
                            }
                        }
                        // 中：课程名 + 标题（锚定左右，不再用算术宽度）
                        Column {
                            anchors.left: parent.left; anchors.leftMargin: 58
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
                                text: modelData.detail
                                color: Ui.Theme.primary; font.pixelSize: 10
                                font.weight: Font.Medium
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight
                            }
                        }
                        // 右：药丸 + 时间（贴右缘）
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
                                kind: 3   // Pulse
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

        // ---------- 作业 ----------
        Flickable {
            contentWidth: width
            contentHeight: hwCol.height + 8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
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
                                kind: 7   // Check
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
                        // 悬停操作钮：去交（开学习通）/ ✕（从看板隐藏）——
                        // 摸得着的动作比藏右键里直白
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
                            width: 36; height: 36; radius: 10
                            color: modelData.cbg || Ui.Theme.track
                            Text {
                                anchors.centerIn: parent
                                text: modelData.course.length > 0 ? modelData.course[0] : "?"
                                color: modelData.cfg || Ui.Theme.fg2
                                font.pixelSize: 15; font.bold: true
                                font.family: Ui.Theme.fontFamily
                            }
                        }
                        Column {
                            anchors.left: parent.left; anchors.leftMargin: 58
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
                anchors.bottomMargin: 14
                anchors.left: parent.left; anchors.right: parent.right
                contentWidth: width
                contentHeight: setCol.height + 20
                clip: true
                boundsBehavior: Flickable.StopAtBounds

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

                // 分组标题在卡外上方（FLstyle 分组列表范式）
                Item {
                    width: parent.width; height: 22
                    Text {
                        anchors.left: parent.left; anchors.bottom: parent.bottom
                        text: "常规"
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
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
                    width: parent.width; height: 30
                    Text {
                        anchors.left: parent.left; anchors.bottom: parent.bottom
                        text: "邮件提醒"
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
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
                height: 44; radius: 22
                color: saveHover.hovered ? Ui.Theme.primaryDeep : Ui.Theme.primary
                Behavior on color { ColorAnimation { duration: 120 } }
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

    // ===== 内联组件 =====
    // 行内分隔线：前景低透明，永不实色
    component SetSep: Rectangle {
        x: 16; width: parent.width - 32; height: 1   // 两侧内缩，不触卡边
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
        placeholderTextColor: Ui.Theme.fg3   // 占位符比已填值再淡一档，别同灰
        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody
        font.family: Ui.Theme.fontFamily
        selectByMouse: true
        implicitHeight: 34
        leftPadding: 10; rightPadding: 10
        background: Rectangle {
            // 输入 = 轨（白卡上变暗一档）；聚焦 = 实心主色描边（border 不吃透明色）
            radius: 17; color: Ui.Theme.track   // 胶囊输入（高 34 的一半）
            border.width: field.activeFocus ? 2 : 0
            border.color: Ui.Theme.primary
            Behavior on border.width { NumberAnimation { duration: Ui.Theme.durFast } }
        }
    }

    // FLstyle 开关：ON 轨=主色白滑块；OFF 轨=灰轨（迁移只做颜色渐变）
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
                color: sw.checked ? "#FFFFFF" : Ui.Theme.fg3   // OFF 灰旋钮
                Behavior on x { NumberAnimation { duration: 120 } }
            }
        }
    }

    // 保存成功后自动收起详情窗（提示闪一下再关，失败则留着改）
    Timer {
        id: saveCloseTimer
        interval: 800
        onTriggered: root.close()
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

}
