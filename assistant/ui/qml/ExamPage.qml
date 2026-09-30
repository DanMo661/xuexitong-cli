import QtQuick
import "." as Ui

// 考试页：考试安排卡片（进行中/倒计时/已结束）+ 任务点完成度
Item {
    id: page
    property int filterUnread: 0   // 占位保持组件签名一致（未用）

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
        contentHeight: col.height + 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: col
            width: parent.width; spacing: 8

            // ---- 考试列表头 ----
            Item {
                width: parent.width; height: 26
                Text {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    text: "考试安排"
                    color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.DemiBold
                    font.family: Ui.Theme.fontFamily
                }
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: cntTxt.width + 16; height: 20; radius: 10
                    color: Ui.Theme.secondary
                    visible: col.liveCount > 0
                    Text {
                        id: cntTxt
                        anchors.centerIn: parent
                        text: col.liveCount + " 场待考"
                        color: Ui.Theme.muted; font.pixelSize: 10
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }

            readonly property int liveCount: {
                let n = 0
                for (let i = 0; i < DBridge.exams.length; i++)
                    if (DBridge.exams[i].state !== "done") n++
                return n
            }

            Repeater {
                model: DBridge.exams
                delegate: Rectangle {
                    id: exCard
                    width: col.width; height: 58
                    radius: Ui.Theme.radiusMd
                    color: "#FFFFFF"
                    border.width: 1
                    border.color: exCard.isLive && modelData.state === "ongoing"
                                   ? Ui.Theme.danger : Ui.Theme.border
                    readonly property bool isLive: modelData.state !== "done"
                    opacity: modelData.state === "done" ? 0.55 : 1
                    // 左色条：进行中红 / 未考按天数黄蓝 / 已结束灰
                    Rectangle {
                        x: 10; anchors.verticalCenter: parent.verticalCenter
                        width: 3; height: 30; radius: 1.5
                        color: modelData.state === "ongoing" ? Ui.Theme.danger
                               : modelData.state === "done" ? Ui.Theme.faint
                               : modelData.days <= 3 ? Ui.Theme.warn
                               : Ui.Theme.primary
                    }
                    Column {
                        x: 24; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                        width: parent.width - 24 - pill.width - 28
                        Text {
                            width: parent.width
                            text: modelData.name
                            color: Ui.Theme.fg; font.pixelSize: 12
                            font.weight: Font.Medium
                            font.family: Ui.Theme.fontFamily
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            text: modelData.startLabel + " 开考 · "
                                  + modelData.durationMin + " 分钟"
                                  + (modelData.mode && modelData.mode !== "未设置终端"
                                     ? " · " + modelData.mode : "")
                            color: Ui.Theme.muted; font.pixelSize: 10
                            font.family: Ui.Theme.fontFamily
                            elide: Text.ElideRight
                        }
                    }
                    Rectangle {
                        id: pill
                        anchors.right: parent.right; anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        width: pillTxt.width + 14; height: 22; radius: 11
                        color: modelData.state === "ongoing" ? Ui.Theme.dangerSoft
                               : modelData.state === "done" ? Ui.Theme.secondary
                               : modelData.days <= 3 ? Ui.Theme.warnSoft
                               : Ui.Theme.primarySoft
                        Text {
                            id: pillTxt
                            anchors.centerIn: parent
                            text: modelData.state === "ongoing" ? "进行中"
                                  : modelData.state === "done" ? "已结束"
                                  : modelData.daysLabel
                            color: modelData.state === "ongoing" ? Ui.Theme.danger
                                   : modelData.state === "done" ? Ui.Theme.faint
                                   : modelData.days <= 3 ? Ui.Theme.warn
                                   : Ui.Theme.primary
                            font.pixelSize: 10; font.weight: Font.Medium
                            font.family: Ui.Theme.fontFamily
                        }
                    }
                }
            }

            Rectangle {
                visible: DBridge.exams.length === 0
                width: parent.width; height: 72; radius: Ui.Theme.radiusMd
                color: "#FFFFFF"; border.width: 1; border.color: Ui.Theme.border
                Column {
                    anchors.centerIn: parent; spacing: 4
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "暂无考试安排"
                        color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "有新考试会弹提醒"
                        color: Ui.Theme.faint; font.pixelSize: 10
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }

            // ---- 任务点完成度 ----
            Item {
                width: parent.width; height: 30
                Text {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    text: "任务点完成度"
                    color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.DemiBold
                    font.family: Ui.Theme.fontFamily
                }
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: 64; height: 24; radius: Ui.Theme.radiusSm
                    color: Ui.Theme.secondary
                    border.width: 1; border.color: Ui.Theme.borderSoft
                    Text {
                        anchors.centerIn: parent; text: "⟳"
                        color: pgHover.hovered ? Ui.Theme.fg : Ui.Theme.muted
                        font.pixelSize: 12; font.family: Ui.Theme.fontFamily
                    }
                    HoverHandler { id: pgHover }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: DBridge.refreshExtra("progress")
                    }
                }
            }

            Rectangle {
                visible: DBridge.progress.rows.length > 0
                width: parent.width; radius: Ui.Theme.radiusMd
                color: "#FFFFFF"; border.width: 1; border.color: Ui.Theme.border
                height: pgCol.height + 20
                Column {
                    id: pgCol
                    x: 14; y: 10; width: parent.width - 28; spacing: 10

                    Text {
                        visible: DBridge.progress.totalLeft > 0
                        text: DBridge.progress.coursesLeft + " 门课共 "
                              + DBridge.progress.totalLeft + " 个任务点未完成"
                        color: Ui.Theme.warn; font.pixelSize: 11; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        visible: DBridge.progress.rows.length > 0
                                 && DBridge.progress.totalLeft === 0
                        text: "本学期课程任务点全部完成 ✓"
                        color: Ui.Theme.ok; font.pixelSize: 11
                        font.family: Ui.Theme.fontFamily
                    }

                    Repeater {
                        model: DBridge.progress.rows
                        delegate: Column {
                            width: pgCol.width; spacing: 4
                            opacity: modelData.done === null ? 0.55 : 1
                            // 定位器（Row/Column）里不能用 anchors，行结构用 Item 摆
                            Item {
                                width: parent.width; height: 16
                                Text {
                                    x: 0; width: parent.width - 100
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.course
                                    color: Ui.Theme.fg; font.pixelSize: 11
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.done === null ? "无数据"
                                          : modelData.left > 0
                                            ? "差 " + modelData.left + " 个"
                                            : "完成 ✓"
                                    color: modelData.done === null ? Ui.Theme.faint
                                           : modelData.left > 0 ? Ui.Theme.warn
                                           : Ui.Theme.ok
                                    font.pixelSize: 10; font.weight: Font.Medium
                                    font.family: Ui.Theme.fontFamily
                                }
                            }
                            // 细进度条（未完成多的课程一眼可见）
                            Rectangle {
                                visible: modelData.done !== null
                                width: parent.width; height: 4; radius: 2
                                color: Ui.Theme.secondary
                                Rectangle {
                                    width: parent.width * (modelData.pct / 100)
                                    height: parent.height; radius: 2
                                    color: modelData.left > 0 ? Ui.Theme.primary
                                           : Ui.Theme.ok
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                visible: DBridge.progress.rows.length === 0
                width: parent.width; height: 56; radius: Ui.Theme.radiusMd
                color: "#FFFFFF"; border.width: 1; border.color: Ui.Theme.border
                Text {
                    anchors.centerIn: parent
                    text: "任务点数据还没拉取（每天自动刷一次，或点右上 ⟳）"
                    color: Ui.Theme.faint; font.pixelSize: 10
                    font.family: Ui.Theme.fontFamily
                }
            }
        }
    }
}
