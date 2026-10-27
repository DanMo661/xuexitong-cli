import QtQuick
import "." as Ui

// 作业页：DDL 看板（左缘紧迫度竖条 + 剩余时间色），点击进详情窗；
// 右键单卡：在学习通打开 / 不再提醒
// FLstyle：白卡浮灰页无描边；紧迫度只上竖条/文字/chip，不满染整卡
Item {
    id: page
    signal openDetail()
    // 右键菜单当前指向的卡（菜单项要用它的 url/course/title）
    property var menuCard: null

    // 待办数（过期/截止未知不算，它们已沉底淡化）
    readonly property int pendingCount: {
        let n = 0
        for (let i = 0; i < Bridge.ddlRows.length; i++) {
            const u = Bridge.ddlRows[i].urgency
            if (u !== "expired" && u !== "unknown") n++
        }
        return n
    }

    onVisibleChanged: {
        if (visible) fade.restart()
        else hwMenu.visible = false
    }

    // 内容入场：只做透明度渐变（零位移）
    NumberAnimation {
        id: fade
        target: page; property: "opacity"; from: 0; to: 1; duration: Ui.Theme.durFade
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 14
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: col
            x: 12; width: parent.width - 24
            spacing: 8

            // 分组标题（FLstyle：13px 灰、卡外上方、带小图标）
            Item {
                width: parent.width; height: 26
                Row {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Glyphs {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 12; height: 12; thickness: 2
                        kind: 2   // Doc
                        color: Ui.Theme.fg2
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "待办截止"
                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                }
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: cntTxt.width + 16; height: 20; radius: 10
                    color: Ui.Theme.badge
                    visible: page.pendingCount > 0
                    Text {
                        id: cntTxt
                        anchors.centerIn: parent
                        text: page.pendingCount + " 项待交"
                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }

            Repeater {
                model: Bridge.ddlRows
                delegate: Rectangle {
                    id: hwCard
                    width: col.width; height: 56
                    radius: Ui.Theme.radiusLg
                    // 已过期/截止未知沉底且淡化：它们不是"待办"
                    readonly property real endOpacity:
                        (modelData.urgency === "expired"
                         || modelData.urgency === "unknown") ? 0.62 : 1
                    color: "#FFFFFF"
                    readonly property color urgencyColor:
                        modelData.urgency === "high" ? Ui.Theme.danger
                        : modelData.urgency === "mid" ? Ui.Theme.warn
                        : modelData.urgency === "expired" ? Ui.Theme.fg3
                        : Ui.Theme.primary
                    // 左缘紧迫度竖条（与考试卡/截止横幅同一套语义）
                    Rectangle {
                        x: 0; width: 3
                        anchors.top: parent.top; anchors.topMargin: 10
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 10
                        radius: 1.5
                        color: hwCard.urgencyColor
                    }
                    HoverHandler { id: hwHover }
                    Rectangle {
                        anchors.fill: parent; radius: parent.radius
                        color: Ui.Theme.hoverOverlay
                        opacity: hwHover.hovered ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: Ui.Theme.durFast } }
                    }
                    opacity: 0
                    Component.onCompleted: stagger.start()
                    SequentialAnimation {
                        id: stagger
                        PauseAnimation { duration: Math.min(index, 8) * 30 }
                        NumberAnimation {
                            target: hwCard; property: "opacity"
                            to: hwCard.endOpacity; duration: 180
                        }
                    }

                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: 10; anchors.rightMargin: 12
                        spacing: 9

                        // 课程色徽章（课程身份色，28 小方章）
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
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
                            anchors.verticalCenter: parent.verticalCenter; spacing: 3
                            width: parent.width - 28 - 100 - 22
                            Text {
                                text: modelData.course
                                color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight; width: parent.width
                            }
                            Text {
                                text: modelData.title
                                color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody; font.weight: Font.Medium
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight; width: parent.width
                                wrapMode: Text.WrapAnywhere; maximumLineCount: 2
                            }
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter; spacing: 3
                            Text {
                                text: modelData.deadlineLabel
                                color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsSub
                                font.family: Ui.Theme.fontFamily
                            }
                            Text {
                                text: modelData.remainText
                                color: hwCard.urgencyColor
                                font.pixelSize: Ui.Theme.fsSub; font.weight: Font.Medium
                                font.family: Ui.Theme.fontFamily
                            }
                        }
                    }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: page.openDetail()
                    }
                    // 右键单卡菜单（自绘：Controls 弹窗在无边框 Tool 窗上有幽灵半开前科）
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.RightButton
                        onClicked: mouse => {
                            page.menuCard = modelData
                            // delegate 在 Flickable 里，坐标换到 page 系
                            const p = mapToItem(page, mouse.x, mouse.y)
                            hwMenu.x = Math.max(4, Math.min(
                                p.x, page.width - hwMenu.width - 8))
                            hwMenu.y = Math.max(4, Math.min(
                                p.y, page.height - hwMenu.height - 8))
                            hwMenu.visible = true
                        }
                    }
                }
            }

            // 已忽略条目的恢复入口（不忽略就别占地方；轨色信息条）
            Rectangle {
                visible: Bridge.ignoredHw > 0
                width: parent.width; height: 34; radius: Ui.Theme.radiusSm
                color: Ui.Theme.track
                Text {
                    anchors.centerIn: parent
                    text: "已隐藏 " + Bridge.ignoredHw + " 条不打算交的作业 · 点击恢复"
                    color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                    font.family: Ui.Theme.fontFamily
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: Bridge.action("hw_unignore_all")
                }
            }

            // 空态（FLstyle：图标井 + 粗标题 + 副文）
            Rectangle {
                visible: Bridge.ddlRows.length === 0
                width: parent.width; height: 88; radius: Ui.Theme.radiusLg
                color: "#FFFFFF"
                Column {
                    anchors.centerIn: parent; spacing: 6
                    Item {
                        width: 32; height: 32
                        anchors.horizontalCenter: parent.horizontalCenter
                        Rectangle {
                            anchors.fill: parent; radius: 16; color: Ui.Theme.okSoft
                        }
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
                        text: "数据随每轮巡检更新"
                        color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }
        }
    }

    // 单卡右键菜单（z 高于遮罩）
    Rectangle {
        id: hwMenu
        visible: false
        z: 100
        width: 168; height: hwMenuCol.childrenRect.height + 8
        radius: Ui.Theme.radiusMd
        color: Ui.Theme.card
        border.width: 1; border.color: Ui.Theme.lineSolid
        Column {
            id: hwMenuCol
            anchors.top: parent.top; anchors.topMargin: 4
            anchors.left: parent.left; anchors.leftMargin: 4
            spacing: 0
            HwMenuItem {
                label: "在学习通打开"
                onPick: {
                    hwMenu.visible = false
                    if (page.menuCard)
                        Bridge.openHw(page.menuCard.url || page.menuCard.courseUrl || "",
                                      page.menuCard.course,
                                      page.menuCard.title)
                }
            }
            HwMenuItem {
                label: "不再提醒这份作业"
                onPick: {
                    hwMenu.visible = false
                    if (page.menuCard)
                        Bridge.ignoreHw(page.menuCard.course, page.menuCard.title,
                                        page.menuCard.url || "")
                }
            }
        }
    }
    // 点菜单外关闭（滚轮也算"移开"——菜单悬空错位比关掉更糟）
    MouseArea {
        enabled: hwMenu.visible
        anchors.fill: parent
        z: 99
        onClicked: hwMenu.visible = false
        onWheel: hwMenu.visible = false
    }

    component HwMenuItem: Rectangle {
        property string label
        signal pick()
        width: 160; height: 32
        radius: 6
        color: hmiHover.hovered ? Ui.Theme.track : "transparent"
        Behavior on color { ColorAnimation { duration: 100 } }
        HoverHandler { id: hmiHover }
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
}
