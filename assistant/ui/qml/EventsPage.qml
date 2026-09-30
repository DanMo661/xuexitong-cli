import QtQuick
import "." as Ui

// 动态页：巡检事件时间线（新资料/作业/通知/提醒）
Item {
    id: page

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
            spacing: 4

            Item {
                width: parent.width; height: 26
                Text {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    text: "最近动态"
                    color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.DemiBold
                    font.family: Ui.Theme.fontFamily
                }
                Text {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    text: "点击条目看详情"
                    color: Ui.Theme.faint; font.pixelSize: 10
                    font.family: Ui.Theme.fontFamily
                }
            }

            Repeater {
                model: Bridge.events
                delegate: Item {
                    id: evItem
                    width: col.width; height: 46
                    opacity: 0
                    Component.onCompleted: stagger.start()
                    SequentialAnimation {
                        id: stagger
                        PauseAnimation { duration: index * 25 }
                        ParallelAnimation {
                            NumberAnimation { target: evItem; property: "opacity"; to: 1; duration: 160 }
                            NumberAnimation { target: evRow; property: "x"; from: 8; to: 0; duration: 200 }
                        }
                    }

                    Rectangle {
                        id: evRow
                        width: parent.width; height: 44
                        anchors.verticalCenter: parent.verticalCenter
                        radius: Ui.Theme.radiusMd
                        color: "#FFFFFF"
                        border.width: 1; border.color: Ui.Theme.border
                        // hover 高亮独立层：透明度动画，避免 color 插值灰影
                        Rectangle {
                            anchors.fill: parent; radius: parent.radius
                            color: "#FAFAFB"
                            opacity: evHover.hovered ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: 110 } }
                        }
                        HoverHandler { id: evHover }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: Bridge.action("open_detail")
                        }

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 9; anchors.rightMargin: 10
                            spacing: 10

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 3; width: 58
                                // 类型药丸（cc-switch 徽章：淡彩底+深彩字）
                                Rectangle {
                                    width: tagTxt.width + 12; height: 18; radius: 9
                                    color: modelData.priority === "high" ? Ui.Theme.dangerSoft
                                           : modelData.priority === "medium"
                                           ? Qt.rgba(0.788, 0.478, 0.086, 0.12)
                                           : Ui.Theme.secondary
                                    Text {
                                        id: tagTxt
                                        anchors.centerIn: parent
                                        text: modelData.tag
                                        color: modelData.priority === "high" ? Ui.Theme.danger
                                               : modelData.priority === "medium" ? Ui.Theme.warn
                                               : Ui.Theme.muted
                                        font.pixelSize: 10; font.weight: Font.Medium
                                        font.family: Ui.Theme.fontFamily
                                    }
                                }
                                Text {
                                    text: modelData.time
                                    color: Ui.Theme.faint; font.pixelSize: 9
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight; width: parent.width
                                }
                            }

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 1
                                width: parent.width - 58 - 22
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
                                    color: Ui.Theme.fg; font.pixelSize: 11
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                visible: Bridge.events.length === 0
                width: parent.width; height: 80; radius: Ui.Theme.radiusMd
                color: "#FFFFFF"
                border.width: 1; border.color: Ui.Theme.border
                Column {
                    anchors.centerIn: parent; spacing: 4
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "暂无新动态"
                        color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "巡检发现新作业/资料/通知会出现在这里"
                        color: Ui.Theme.faint; font.pixelSize: 10
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }
        }
    }
}
