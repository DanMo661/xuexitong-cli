import QtQuick
import QtQuick.Controls.Basic
import "." as Ui

// 动态页：巡检事件时间线（新资料/作业/通知/提醒）
// FLstyle：白卡浮灰页无描边；类型药丸 = 淡彩底+深彩字（状态色只上 chip）
Item {
    id: page

    onVisibleChanged: if (visible) fade.restart()

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
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
            implicitWidth: 4
            contentItem: Rectangle {
                radius: 2; color: Ui.Theme.badge
            }
        }

        Column {
            id: col
            x: 12; width: parent.width - 24
            spacing: 4

            // 分组标题（13px 灰、带小图标）+ 右侧说明
            Item {
                width: parent.width; height: 26
                Row {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Glyphs {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 12; height: 12; thickness: 2
                        kind: 3   // Pulse
                        color: Ui.Theme.fg2
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "最近动态"
                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                }
                Text {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    text: "点击条目看详情"
                    color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                    font.family: Ui.Theme.fontFamily
                }
            }

            Repeater {
                model: Bridge.events
                delegate: Item {
                    id: evItem
                    width: col.width
                    // 有附加信息（出分分数/考试时间）的条目高一档
                    readonly property bool hasDetail:
                        (modelData.detail || "") !== ""
                    height: hasDetail ? 58 : 46
                    opacity: 0
                    Component.onCompleted: stagger.start()
                    SequentialAnimation {
                        id: stagger
                        // 封顶 8 个：20 条列表拖到 500ms+ 会"半场定格"（截图/快扫都踩过）
                        PauseAnimation { duration: Math.min(index, 8) * 25 }
                        NumberAnimation { target: evItem; property: "opacity"; to: 1; duration: 160 }
                    }

                    Rectangle {
                        id: evRow
                        width: parent.width
                        height: evItem.hasDetail ? 56 : 44
                        anchors.verticalCenter: parent.verticalCenter
                        radius: Ui.Theme.radiusLg
                        color: "#FFFFFF"
                        // hover 高亮独立层：透明度动画，避免 color 插值灰影
                        Rectangle {
                            anchors.fill: parent; radius: parent.radius
                            color: Ui.Theme.hoverOverlay
                            opacity: evHover.hovered ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: Ui.Theme.durFast } }
                        }
                        HoverHandler { id: evHover }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: Bridge.action("open_detail")
                        }

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10
                            spacing: 10

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 3; width: 58
                                // 类型药丸：淡彩底+深彩字
                                Rectangle {
                                    width: tagTxt.width + 12; height: 18; radius: 9
                                    color: modelData.priority === "high" ? Ui.Theme.dangerSoft
                                           : modelData.priority === "medium"
                                           ? Ui.Theme.warnSoft
                                           : Ui.Theme.track
                                    Text {
                                        id: tagTxt
                                        anchors.centerIn: parent
                                        text: modelData.tag
                                        color: modelData.priority === "high" ? Ui.Theme.danger
                                               : modelData.priority === "medium" ? Ui.Theme.warn
                                               : Ui.Theme.fg2
                                        font.pixelSize: Ui.Theme.fsCap; font.weight: Font.Medium
                                        font.family: Ui.Theme.fontFamily
                                    }
                                }
                                Text {
                                    text: modelData.time
                                    color: Ui.Theme.fg3; font.pixelSize: 9
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
                                    color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: modelData.title
                                    color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsSub
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                                // 附加信息行：短值（出分/开考）主色点睛，长文回灰。
                                // detail 可能是带换行的通知正文——必须压成单行再
                                // elide（elide 只截行宽不截行数，多行会把卡片
                                // 撑爆溢出、从后面卡片的间隙里漏出来）
                                Text {
                                    visible: evItem.hasDetail
                                    width: parent.width
                                    text: {
                                        const s = (modelData.detail || "")
                                            .replace(/\s+/g, " ").trim()
                                        return s
                                    }
                                    color: text.length <= 16
                                           ? Ui.Theme.primary : Ui.Theme.fg2
                                    font.pixelSize: Ui.Theme.fsCap
                                    font.weight: Font.Medium
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }

            // 空态（FLstyle：图标井 + 粗标题 + 副文）
            Rectangle {
                visible: Bridge.events.length === 0
                width: parent.width; height: 88; radius: Ui.Theme.radiusLg
                color: "#FFFFFF"
                Column {
                    anchors.centerIn: parent; spacing: 6
                    Item {
                        width: 32; height: 32
                        anchors.horizontalCenter: parent.horizontalCenter
                        Rectangle {
                            anchors.fill: parent; radius: 16; color: Ui.Theme.primarySoft
                        }
                        Glyphs {
                            anchors.centerIn: parent
                            width: 14; height: 14; thickness: 2.4
                            kind: 3   // Pulse
                            color: Ui.Theme.primary
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "暂无新动态"
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "巡检发现新作业/资料/通知会出现在这里"
                        color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }
        }
    }
}
