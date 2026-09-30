import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "." as Ui

// 详情窗：动态/作业/考试/通知/设置 —— 与悬浮小窗同一套 cc-switch 体系
Window {
    id: root
    width: 460; height: 600
    minimumWidth: 420; minimumHeight: 520
    title: "学习通小助手 · 详情"
    color: "#FFFFFF"

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
                        color: Ui.Theme.fg; font.pixelSize: 16
                        font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        text: "动态、作业、考试、通知和设置都在这"
                        color: Ui.Theme.muted; font.pixelSize: 11
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }
            // 刷新按钮锚右：副标题变长也不会把它推出窗口
            Rectangle {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: refreshTxt.width + 22; height: 30; radius: 8
                color: Ui.Theme.secondary
                // 作业/考试/通知三页才有刷新（考试页的考试数据、任务点各自页内刷）
                visible: bar.currentIndex >= 1 && bar.currentIndex <= 3
                Text {
                    id: refreshTxt
                    anchors.centerIn: parent; text: "⟳ 刷新"
                    color: Ui.Theme.fg; font.pixelSize: 12
                    font.weight: Font.Medium
                    font.family: Ui.Theme.fontFamily
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (bar.currentIndex === 1) DBridge.refreshHw()
                        else if (bar.currentIndex === 2) DBridge.refreshExtra("exams")
                        else if (bar.currentIndex === 3) DBridge.refreshExtra("notices")
                    }
                }
            }
        }

        // 胶囊分段标签（同小窗）
        Rectangle {
            id: bar
            property int currentIndex: 0
            width: parent.width; height: 34; radius: 10
            color: Ui.Theme.secondary
            Rectangle {
                id: chip
                y: 3; height: 28; radius: 8
                width: bar.width / 5 - 6
                x: 3 + bar.currentIndex * (bar.width / 5)
                color: "#FFFFFF"
                border.width: 1; border.color: Ui.Theme.borderSoft
                Behavior on x {
                    NumberAnimation {
                        duration: 220; easing.type: Easing.Bezier
                        easing.bezierCurve: Ui.Theme.ccEnter
                    }
                }
            }
            Row {
                anchors.fill: parent
                Repeater {
                    model: ["动态", "作业", "考试", "通知", "设置"]
                    delegate: Item {
                        width: bar.width / 5; height: bar.height
                        Text {
                            anchors.centerIn: parent; text: modelData
                            color: bar.currentIndex === index ? Ui.Theme.fg : Ui.Theme.muted
                            font.pixelSize: 12
                            font.weight: bar.currentIndex === index ? Font.DemiBold : Font.Normal
                            font.family: Ui.Theme.fontFamily
                            Behavior on color { ColorAnimation { duration: 150 } }
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

    // ===== 保存提示条 =====
    Rectangle {
        id: toast
        visible: toastTxt.text !== ""
        anchors.top: head.bottom; anchors.topMargin: 8
        anchors.left: head.left; anchors.right: head.right
        height: 30; radius: 8
        color: Ui.Theme.primarySoft
        Text {
            id: toastTxt
            anchors.centerIn: parent
            color: Ui.Theme.primary; font.pixelSize: 11
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
                        width: tlCol.width; height: 52
                        radius: Ui.Theme.radiusMd
                        color: "#FFFFFF"
                        border.width: 1; border.color: Ui.Theme.border
                        // 左：课程色块
                        Rectangle {
                            x: 10; anchors.verticalCenter: parent.verticalCenter
                            width: 36; height: 36; radius: 10
                            color: modelData.cbg || Ui.Theme.secondary
                            border.width: 1; border.color: Ui.Theme.border
                            Text {
                                anchors.centerIn: parent
                                text: modelData.course.length > 0 ? modelData.course[0] : "?"
                                color: modelData.cfg || Ui.Theme.muted
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
                                color: Ui.Theme.muted; font.pixelSize: 10
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight
                            }
                            Text {
                                width: parent.width
                                text: modelData.title
                                color: Ui.Theme.fg; font.pixelSize: 12
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
                                       : Ui.Theme.secondary
                                Text {
                                    id: tlTag
                                    anchors.centerIn: parent; text: modelData.tag
                                    color: modelData.priority === "high" ? Ui.Theme.danger : Ui.Theme.muted
                                    font.pixelSize: 10; font.weight: Font.Medium
                                    font.family: Ui.Theme.fontFamily
                                }
                            }
                            Text {
                                text: modelData.time
                                color: Ui.Theme.faint; font.pixelSize: 9
                                font.family: Ui.Theme.fontFamily
                            }
                        }
                    }
                }
                Rectangle {
                    visible: DBridge.timeline.length === 0
                    width: parent.width; height: 90; radius: Ui.Theme.radiusMd
                    color: "#FFFFFF"; border.width: 1; border.color: Ui.Theme.border
                    Text {
                        anchors.centerIn: parent
                        text: "还没有动态，检查到新作业/资料/通知会出现在这里"
                        color: Ui.Theme.muted; font.pixelSize: 12
                        font.family: Ui.Theme.fontFamily
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
                    width: parent.width; height: 56; radius: Ui.Theme.radiusMd
                    color: Ui.Theme.dangerSoft
                    Text {
                        anchors.centerIn: parent
                        text: "作业获取失败，点右上「⟳ 刷新」重试"
                        color: Ui.Theme.danger; font.pixelSize: 12
                        font.family: Ui.Theme.fontFamily
                    }
                }
                Rectangle {
                    visible: !DBridge.hwFailed && DBridge.hw.length === 0
                    width: parent.width; height: 90; radius: Ui.Theme.radiusMd
                    color: "#FFFFFF"; border.width: 1; border.color: Ui.Theme.border
                    Text {
                        anchors.centerIn: parent
                        text: "没有待交的作业 ✓"
                        color: Ui.Theme.ok; font.pixelSize: 13
                        font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                }
                Repeater {
                    model: DBridge.hw
                    delegate: Rectangle {
                        width: hwCol.width; height: 64
                        radius: Ui.Theme.radiusMd
                        color: "#FFFFFF"
                        border.width: 1; border.color: Ui.Theme.border
                        opacity: (modelData.urgency === "expired"
                                  || modelData.urgency === "unknown") ? 0.62 : 1
                        Rectangle {
                            x: 10; anchors.verticalCenter: parent.verticalCenter
                            width: 36; height: 36; radius: 10
                            color: modelData.cbg || Ui.Theme.secondary
                            border.width: 1; border.color: Ui.Theme.border
                            Text {
                                anchors.centerIn: parent
                                text: modelData.course.length > 0 ? modelData.course[0] : "?"
                                color: modelData.cfg || Ui.Theme.muted
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
                                color: Ui.Theme.faint; font.pixelSize: 10
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight
                            }
                            Text {
                                width: parent.width
                                text: modelData.title
                                color: Ui.Theme.fg; font.pixelSize: 12
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
                                color: Ui.Theme.muted; font.pixelSize: 11
                                font.family: Ui.Theme.fontFamily
                            }
                            Text {
                                text: modelData.remainText
                                color: modelData.urgency === "high" ? Ui.Theme.danger
                                       : modelData.urgency === "mid" ? Ui.Theme.warn
                                       : Ui.Theme.muted
                                font.pixelSize: 11; font.weight: Font.Medium
                                font.family: Ui.Theme.fontFamily
                            }
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
                anchors.bottomMargin: 10
                anchors.left: parent.left; anchors.right: parent.right
                contentWidth: width
                contentHeight: setCol.height + 8
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
                width: parent.width; spacing: 10

                // 常规
                Rectangle {
                    width: parent.width; radius: Ui.Theme.radiusMd
                    color: "#FFFFFF"; border.width: 1; border.color: Ui.Theme.border
                    height: genCol.height + 24
                    Column {
                        id: genCol
                        x: 14; y: 12; width: parent.width - 28; spacing: 10
                        Text {
                            text: "常规"
                            color: Ui.Theme.fg; font.pixelSize: 13
                            font.weight: Font.DemiBold
                            font.family: Ui.Theme.fontFamily
                        }
                        Row {
                            spacing: 8
                            Item {
                                width: 96; height: 36
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "巡检间隔"; color: Ui.Theme.muted
                                    font.pixelSize: 12; font.family: Ui.Theme.fontFamily
                                }
                            }
                            Rectangle {
                                width: 130; height: 34; radius: 8
                                color: Ui.Theme.secondary
                                border.width: 1; border.color: Ui.Theme.border
                                Row {
                                    anchors.centerIn: parent; spacing: 10
                                    Rectangle {
                                        width: 24; height: 24; radius: 6
                                        color: minusHover.hovered ? "#E4E4E7" : "transparent"
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
                                        color: Ui.Theme.fg; font.pixelSize: 12
                                        font.family: Ui.Theme.fontFamily
                                    }
                                    Rectangle {
                                        width: 24; height: 24; radius: 6
                                        color: plusHover.hovered ? "#E4E4E7" : "transparent"
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
                        SetRow {
                            label: "免打扰时段"
                            Field {
                                width: 160; text: setFlick.dnd
                                onTextChanged: setFlick.dnd = text
                            }
                        }
                        SetRow {
                            label: "桌面弹窗"
                            Switch {
                                checked: setFlick.toastOn
                                onToggled: setFlick.toastOn = checked
                            }
                        }
                        SetRow {
                            label: "开机自启"
                            Switch {
                                checked: setFlick.autostart
                                onToggled: setFlick.autostart = checked
                            }
                        }
                    }
                }

                // 邮件提醒
                Rectangle {
                    width: parent.width; radius: Ui.Theme.radiusMd
                    color: "#FFFFFF"; border.width: 1; border.color: Ui.Theme.border
                    height: mailCol.height + 24
                    Column {
                        id: mailCol
                        x: 14; y: 12; width: parent.width - 28; spacing: 10
                        Text {
                            text: "邮件提醒"
                            color: Ui.Theme.fg; font.pixelSize: 13
                            font.weight: Font.DemiBold
                            font.family: Ui.Theme.fontFamily
                        }
                        SetRow {
                            label: "重要事项发邮件"
                            Switch {
                                checked: setFlick.emailOn
                                onToggled: setFlick.emailOn = checked
                            }
                        }
                        SetRow {
                            label: "收件邮箱"
                            Field {
                                width: 200; text: setFlick.emailTo
                                placeholder: "someone@qq.com"
                                onTextChanged: setFlick.emailTo = text
                            }
                        }
                        SetRow {
                            label: "SMTP 服务器"
                            Field {
                                width: 200; text: setFlick.smtpHost
                                placeholder: "smtp.qq.com"
                                onTextChanged: setFlick.smtpHost = text
                            }
                        }
                        SetRow {
                            label: "发件账号"
                            Field {
                                width: 200; text: setFlick.smtpUser
                                onTextChanged: setFlick.smtpUser = text
                            }
                        }
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

            // 常驻保存按钮：不跟滚动，永远可见
            Rectangle {
                id: saveBtn
                anchors.bottom: parent.bottom
                anchors.left: parent.left; anchors.right: parent.right
                height: 44; radius: Ui.Theme.radiusMd
                color: saveHover.hovered ? Ui.Theme.primaryDeep : Ui.Theme.primary
                Behavior on color { ColorAnimation { duration: 120 } }
                HoverHandler { id: saveHover }
                Text {
                    anchors.centerIn: parent; text: "保存设置"
                    color: "#FFFFFF"; font.pixelSize: 13; font.weight: Font.DemiBold
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
    component SetRow: Row {
        property string label
        default property alias _slot: slot.data
        spacing: 8
        Item {
            width: 96; height: 36
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: parent.parent.label
                color: Ui.Theme.muted; font.pixelSize: 12
                font.family: Ui.Theme.fontFamily
            }
        }
        Item { id: slot; width: childrenRect.width; height: 36 }
    }

    component Field: TextField {
        property string placeholder
        placeholderText: placeholder
        color: Ui.Theme.fg; font.pixelSize: 12
        font.family: Ui.Theme.fontFamily
        selectByMouse: true
        implicitHeight: 34
        background: Rectangle {
            radius: 8; color: Ui.Theme.secondary
            border.width: 1; border.color: Ui.Theme.border
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