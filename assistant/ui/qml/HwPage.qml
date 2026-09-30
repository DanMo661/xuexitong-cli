import QtQuick
import "." as Ui

// 作业页：DDL 看板（紧迫度色条 + 剩余时间），点击进详情窗
Item {
    id: page
    signal openDetail()

    // 待办数（过期/截止未知不算，它们已沉底淡化）
    readonly property int pendingCount: {
        let n = 0
        for (let i = 0; i < Bridge.ddlRows.length; i++) {
            const u = Bridge.ddlRows[i].urgency
            if (u !== "expired" && u !== "unknown") n++
        }
        return n
    }

    onVisibleChanged: if (visible) enter.restart()

    ParallelAnimation {
        id: enter
        NumberAnimation { target: page; property: "opacity"; from: 0; to: 1; duration: 160 }
        NumberAnimation {
            target: page; property: "x"; from: 10; to: 0; duration: 220
            easing.type: Easing.Bezier; easing.bezierCurve: Ui.Theme.ccEnter
        }
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

            Item {
                width: parent.width; height: 26
                Text {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    text: "待办截止"
                    color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.DemiBold
                    font.family: Ui.Theme.fontFamily
                }
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: cntTxt.width + 16; height: 20; radius: 10
                    color: Ui.Theme.secondary
                    visible: page.pendingCount > 0
                    Text {
                        id: cntTxt
                        anchors.centerIn: parent
                        text: page.pendingCount + " 项待交"
                        color: Ui.Theme.muted; font.pixelSize: 10
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }

            Repeater {
                model: Bridge.ddlRows
                delegate: Rectangle {
                    id: hwCard
                    width: col.width; height: 56
                    radius: Ui.Theme.radiusMd
                    // 已过期/截止未知沉底且淡化：它们不是"待办"
                    readonly property real endOpacity:
                        (modelData.urgency === "expired"
                         || modelData.urgency === "unknown") ? 0.62 : 1
                    color: "#FFFFFF"
                    border.width: 1; border.color: Ui.Theme.border
                    HoverHandler { id: hwHover }
                    Rectangle {
                        anchors.fill: parent; radius: parent.radius
                        color: "#FAFAFB"
                        opacity: hwHover.hovered ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: 110 } }
                    }
                    readonly property color urgencyColor:
                        modelData.urgency === "high" ? Ui.Theme.danger
                        : modelData.urgency === "mid" ? Ui.Theme.warn
                        : modelData.urgency === "expired" ? Ui.Theme.faint
                        : Ui.Theme.primary
                    opacity: 0
                    Component.onCompleted: stagger.start()
                    SequentialAnimation {
                        id: stagger
                        PauseAnimation { duration: index * 30 }
                        NumberAnimation {
                            target: hwCard; property: "opacity"
                            to: hwCard.endOpacity; duration: 180
                        }
                    }

                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: 9; anchors.rightMargin: 12
                        spacing: 10

                        // 课程色块（cc-switch logo tile 等效物）
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
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
                            anchors.verticalCenter: parent.verticalCenter; spacing: 3
                            width: parent.width - 36 - 100 - 24
                            Text {
                                text: modelData.course
                                color: Ui.Theme.faint; font.pixelSize: 10
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight; width: parent.width
                            }
                            Text {
                                text: modelData.title
                                color: Ui.Theme.fg; font.pixelSize: 12; font.weight: Font.Medium
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight; width: parent.width
                                wrapMode: Text.WrapAnywhere; maximumLineCount: 2
                            }
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3
                            Text {
                                text: modelData.deadlineLabel
                                color: Ui.Theme.muted; font.pixelSize: 11
                                font.family: Ui.Theme.fontFamily
                            }
                            Text {
                                text: modelData.remainText
                                color: hwCard.urgencyColor
                                font.pixelSize: 11; font.weight: Font.Medium
                                font.family: Ui.Theme.fontFamily
                            }
                        }
                    }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: page.openDetail()
                    }
                }
            }

            Rectangle {
                visible: Bridge.ddlRows.length === 0
                width: parent.width; height: 80; radius: Ui.Theme.radiusMd
                color: "#FFFFFF"
                border.width: 1; border.color: Ui.Theme.border
                Column {
                    anchors.centerIn: parent; spacing: 4
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "没有待交的作业"
                        color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "数据随每轮巡检更新"
                        color: Ui.Theme.faint; font.pixelSize: 10
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }
        }
    }
}
