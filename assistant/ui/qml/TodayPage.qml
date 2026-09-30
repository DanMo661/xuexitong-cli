import QtQuick
import "." as Ui

// 今天页：日期头 + 今日概览 + 课程手风琴（点行展开详情）+ 最近截止
Item {
    id: page
    signal jumpToHw()
    property string expandedKey: ""  // 手风琴：记课名+时段（换天/重建后行号会悬空）

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

            // ---- 日期头 ----
            Item {
                width: parent.width; height: 26
                Text {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    text: Bridge.dateLabel
                    color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.DemiBold
                    font.family: Ui.Theme.fontFamily
                }
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    visible: Bridge.weekLabel !== ""
                    width: weekTxt.width + 16; height: 20; radius: 10
                    color: Ui.Theme.secondary
                    Text {
                        id: weekTxt
                        anchors.centerIn: parent
                        text: Bridge.weekLabel
                        color: Ui.Theme.muted; font.pixelSize: 10
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }

            // ---- 今日概览条 ----
            Rectangle {
                visible: Bridge.dayTotal > 0 || Bridge.progressLeft > 0
                width: parent.width; height: 30; radius: Ui.Theme.radiusSm
                color: Ui.Theme.cardAlt
                Text {
                    anchors.centerIn: parent
                    text: Bridge.dayTotal > 0
                          ? "今天 " + Bridge.dayTotal + " 次课 · 已结束 "
                            + Bridge.dayDone + " · 还剩 "
                            + (Bridge.dayTotal - Bridge.dayDone)
                            + (Bridge.progressLeft > 0
                               ? " · 任务点缺 " + Bridge.progressLeft : "")
                          : "任务点还差 " + Bridge.progressLeft + " 个没刷完"
                    color: Ui.Theme.muted; font.pixelSize: 11
                    font.family: Ui.Theme.fontFamily
                }
            }

            // ---- 课程手风琴 ----
            Repeater {
                model: Bridge.lessons
                delegate: Item {
                    id: lessonItem
                    width: col.width
                    readonly property string lkey: modelData.name + "|" + modelData.timeLabel
                    height: 52 + (page.expandedKey === lkey ? 30 : 0)
                    clip: true
                    Behavior on height {
                        NumberAnimation {
                            duration: 200; easing.type: Easing.Bezier
                            easing.bezierCurve: Ui.Theme.popBack
                        }
                    }
                    // 入场 stagger（首次展开面板）
                    opacity: 0
                    Component.onCompleted: stagger.start()
                    SequentialAnimation {
                        id: stagger
                        PauseAnimation { duration: index * 35 }
                        ParallelAnimation {
                            NumberAnimation { target: lessonItem; property: "opacity"; to: 1; duration: 180 }
                            NumberAnimation {
                                target: lessonCard; property: "y"; from: 6; to: 0
                                duration: 240; easing.type: Easing.Bezier
                                easing.bezierCurve: Ui.Theme.popBack
                            }
                        }
                    }

                    Rectangle {
                        id: lessonCard
                        width: parent.width; height: 52
                        radius: Ui.Theme.radiusMd
                        readonly property bool isCur: modelData.state === "current"
                        readonly property bool isPar: modelData.state === "parallel"
                        readonly property bool isDone: modelData.state === "done"
                        // cc-switch 卡片体系：白底 1px 描边；选中态整套换装（蓝底+蓝边）
                        border.width: lessonCard.isCur || lessonCard.isPar ? 1.5 : 1
                        border.color: lessonCard.isCur ? Ui.Theme.primary
                                     : lessonCard.isPar ? Ui.Theme.primaryBorder
                                     : Ui.Theme.border
                        color: lessonCard.isCur ? Ui.Theme.primarySoft
                               : lessonCard.isPar ? Ui.Theme.primarySoft : "#FFFFFF"
                        Behavior on color { ColorAnimation { duration: 150 } }
                        HoverHandler { id: rowHover }
                        // hover 高亮独立层：透明度动画，避免 color 插值灰影
                        Rectangle {
                            anchors.fill: parent; radius: parent.radius
                            color: "#FAFAFB"
                            visible: !lessonCard.isCur && !lessonCard.isPar
                            opacity: rowHover.hovered ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: 110 } }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.expandedKey =
                                (page.expandedKey === lessonItem.lkey ? "" : lessonItem.lkey)
                        }

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 9; anchors.rightMargin: 8
                            spacing: 10

                            // 课程色块（cc-switch 的品牌 logo tile 等效物）
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 36; height: 36; radius: 10
                                color: lessonCard.isDone ? Ui.Theme.secondary
                                       : modelData.cbg || Ui.Theme.secondary
                                border.width: 1
                                border.color: Ui.Theme.border
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.name.length > 0 ? modelData.name[0] : "?"
                                    color: lessonCard.isDone ? Ui.Theme.faint
                                           : modelData.cfg || Ui.Theme.muted
                                    font.pixelSize: 15; font.bold: true
                                    font.family: Ui.Theme.fontFamily
                                }
                            }

                            // 名称 + 时间地点（cc-switch 的名称+链接两行制）
                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2
                                width: parent.width - 36 - chip.width - chev.width - 40
                                Text {
                                    width: parent.width
                                    text: modelData.name
                                    color: lessonCard.isDone ? Ui.Theme.muted : Ui.Theme.fg
                                    font.pixelSize: 13
                                    font.weight: lessonCard.isCur ? Font.DemiBold : Font.Medium
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: modelData.timeLabel + " · " + modelData.location
                                    color: lessonCard.isCur ? Ui.Theme.primary : Ui.Theme.muted
                                    font.pixelSize: 10
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                            }

                            // 状态 chip
                            Rectangle {
                                id: chip
                                anchors.verticalCenter: parent.verticalCenter
                                width: chipTxt.width + 14; height: 20; radius: 10
                                color: lessonCard.isCur || lessonCard.isPar ? Ui.Theme.primarySoft
                                       : Ui.Theme.secondary
                                Text {
                                    id: chipTxt
                                    anchors.centerIn: parent
                                    text: lessonCard.isCur ? "进行中"
                                          : lessonCard.isPar ? "同时段"
                                          : lessonCard.isDone ? "已结束" : "未开始"
                                    color: lessonCard.isCur || lessonCard.isPar ? Ui.Theme.primary
                                           : lessonCard.isDone ? Ui.Theme.faint : Ui.Theme.muted
                                    font.pixelSize: 10
                                    font.family: Ui.Theme.fontFamily
                                }
                            }

                            // 展开箭头
                            Text {
                                id: chev
                                anchors.verticalCenter: parent.verticalCenter
                                text: "›"
                                color: Ui.Theme.faint; font.pixelSize: 14
                                font.family: Ui.Theme.fontFamily
                                rotation: page.expandedKey === lessonItem.lkey ? 90 : 0
                                Behavior on rotation { NumberAnimation { duration: 200; easing.type: Easing.Bezier; easing.bezierCurve: Ui.Theme.popBack } }
                            }
                        }
                    }

                    // 展开详情（老师/节次/周次）
                    Item {
                        x: 55; y: 54; width: parent.width - 70; height: 26
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: [modelData.teacher, modelData.nodeLabel,
                                   modelData.weeks ? modelData.weeks + "周" : ""]
                                  .filter(s => s !== "").join("  ·  ")
                            color: Ui.Theme.muted; font.pixelSize: 10
                            font.family: Ui.Theme.fontFamily
                            elide: Text.ElideRight; width: parent.width
                        }
                    }
                }
            }

            // 空态
            Rectangle {
                visible: Bridge.lessons.length === 0
                width: parent.width; height: 64; radius: Ui.Theme.radiusMd
                color: "#FFFFFF"
                border.width: 1; border.color: Ui.Theme.border
                Column {
                    anchors.centerIn: parent; spacing: 4
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: Bridge.synced ? "今天没有课" : "课表还没同步好"
                        color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: Bridge.synced ? "看看作业和截止 →" : "等一轮检查就好"
                        color: Ui.Theme.primary; font.pixelSize: 11
                        font.family: Ui.Theme.fontFamily
                    }
                }
                MouseArea { anchors.fill: parent; onClicked: page.jumpToHw() }
            }

            // ---- 最近截止横幅 ----
            Rectangle {
                // ddlRows 已按"待办在前"排序；首条是过期/未知就不出横幅
                readonly property var first: {
                    for (let i = 0; i < Bridge.ddlRows.length; i++) {
                        const u = Bridge.ddlRows[i].urgency
                        if (u !== "expired" && u !== "unknown")
                            return Bridge.ddlRows[i]
                    }
                    return null
                }
                visible: first !== null
                width: parent.width; height: 48; radius: Ui.Theme.radiusMd
                color: "#FFFFFF"
                border.width: 1; border.color: Ui.Theme.border
                Rectangle {
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    width: 3; height: 22; radius: 1.5
                    color: parent.first
                           ? (parent.first.urgency === "high" ? Ui.Theme.danger
                              : parent.first.urgency === "mid" ? Ui.Theme.warn
                              : parent.first.urgency === "expired" ? Ui.Theme.faint
                              : Ui.Theme.primary) : Ui.Theme.primary
                }
                Column {
                    x: 22; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                    Text {
                        text: parent.parent.first ? parent.parent.first.course : ""
                        color: Ui.Theme.faint; font.pixelSize: 10
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        width: 200
                        text: parent.parent.first ? parent.parent.first.title : ""
                        color: Ui.Theme.fg; font.pixelSize: 11; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                        elide: Text.ElideRight
                    }
                }
                Text {
                    anchors.right: parent.right; anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: parent.first ? parent.first.remainText : ""
                    color: parent.first && parent.first.urgency === "high" ? Ui.Theme.danger
                           : parent.first && parent.first.urgency === "mid" ? Ui.Theme.warn
                           : Ui.Theme.muted
                    font.pixelSize: 11; font.weight: Font.Medium
                    font.family: Ui.Theme.fontFamily
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.jumpToHw() }
            }

            // ---- 考试横幅（有待考/进行中才出现）----
            Rectangle {
                visible: Bridge.examSummary !== ""
                width: parent.width; height: 48; radius: Ui.Theme.radiusMd
                color: "#FFFFFF"
                border.width: 1; border.color: Ui.Theme.border
                Rectangle {
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    width: 3; height: 22; radius: 1.5
                    color: Ui.Theme.warn
                }
                // 考试图标块（与课程色块同规格，暖色区分"不是课"）
                Rectangle {
                    x: 22; anchors.verticalCenter: parent.verticalCenter
                    width: 30; height: 30; radius: 9
                    color: Ui.Theme.warnSoft
                    border.width: 1; border.color: Ui.Theme.border
                    Text {
                        anchors.centerIn: parent; text: "考"
                        color: Ui.Theme.warn; font.pixelSize: 13; font.bold: true
                        font.family: Ui.Theme.fontFamily
                    }
                }
                Column {
                    x: 60; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                    width: parent.width - 60 - examChip.width - 30
                    Text {
                        width: parent.width
                        text: Bridge.examSummary
                        color: Ui.Theme.fg; font.pixelSize: 11; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                        elide: Text.ElideRight
                    }
                    Text {
                        text: "点击查看全部考试安排"
                        color: Ui.Theme.faint; font.pixelSize: 9
                        font.family: Ui.Theme.fontFamily
                    }
                }
                Rectangle {
                    id: examChip
                    anchors.right: parent.right; anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    width: examChipTxt.width + 14; height: 20; radius: 10
                    color: Ui.Theme.warnSoft
                    Text {
                        id: examChipTxt
                        anchors.centerIn: parent
                        text: Bridge.examCount + " 场"
                        color: Ui.Theme.warn; font.pixelSize: 10; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: Bridge.action("open_detail_exam")
                }
            }
        }
    }
}
