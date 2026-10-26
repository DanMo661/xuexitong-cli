import QtQuick
import QtQuick.Controls.Basic
import "." as Ui

// 今天页：日期头 + 今日概览 + 课程手风琴（点行展开详情）+ 最近截止 + 考试横幅
// FLstyle：白卡浮灰页、无实线边框；状态色只上 chip/左缘竖条/文字，不满染整卡
Item {
    id: page
    signal jumpToHw()
    property string expandedKey: ""  // 手风琴：记课名+时段（换天/重建后行号会悬空）

    onVisibleChanged: if (visible) fade.restart()

    // 根级导航硬切之外的内容入场预算：只做透明度渐变（零位移）
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
        // 课多时一屏放不下：滚动条让"下面还有"看得见
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
            spacing: 8

            // ---- 日期头 ----
            Item {
                width: parent.width; height: 26
                Text {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    text: Bridge.dateLabel
                    color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                    font.family: Ui.Theme.fontFamily
                }
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    visible: Bridge.weekLabel !== ""
                    width: weekTxt.width + 16; height: 20; radius: 10
                    color: Ui.Theme.badge
                    Text {
                        id: weekTxt
                        anchors.centerIn: parent
                        text: Bridge.weekLabel
                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }

            // ---- 今日概览条（轨色信息条；数字用主文字色跳出来）----
            Rectangle {
                visible: Bridge.dayTotal > 0 || Bridge.progressLeft > 0
                width: parent.width; height: 32; radius: Ui.Theme.radiusSm
                color: Ui.Theme.track
                Row {
                    anchors.centerIn: parent
                    spacing: 3
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: Bridge.dayTotal > 0 ? "今天" : "任务点"
                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        visible: Bridge.dayTotal > 0
                        anchors.verticalCenter: parent.verticalCenter
                        text: Bridge.dayTotal
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsSub
                        font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                        font.features: { "tnum": 1 }
                    }
                    Text {
                        visible: Bridge.dayTotal > 0
                        anchors.verticalCenter: parent.verticalCenter
                        text: "次课 · 已结束 " + Bridge.dayDone + " · 还剩 "
                              + (Bridge.dayTotal - Bridge.dayDone)
                              + (Bridge.progressLeft > 0
                                 ? " · 任务点还差 " + Bridge.progressLeft + " 个" : "")
                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        visible: Bridge.dayTotal <= 0
                        anchors.verticalCenter: parent.verticalCenter
                        text: "还差 " + Bridge.progressLeft + " 个没刷完"
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsCap
                        font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
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
                    // 入场 stagger（只做透明度，零位移）
                    opacity: 0
                    Component.onCompleted: stagger.start()
                    SequentialAnimation {
                        id: stagger
                        PauseAnimation { duration: index * 35 }
                        NumberAnimation { target: lessonItem; property: "opacity"; to: 1; duration: 180 }
                    }

                    Rectangle {
                        id: lessonCard
                        width: parent.width; height: 52
                        radius: Ui.Theme.radiusLg
                        readonly property bool isCur: modelData.state === "current"
                        readonly property bool isPar: modelData.state === "parallel"
                        readonly property bool isDone: modelData.state === "done"
                        // FLstyle：白卡无描边；状态 = 左缘 3px 竖条 + 文字/chip，
                        // 不满染整卡（原蓝底+蓝边整卡换装废弃）
                        color: "#FFFFFF"
                        Rectangle {
                            visible: lessonCard.isCur || lessonCard.isPar
                            x: 0; width: 3
                            anchors.top: parent.top; anchors.topMargin: 10
                            anchors.bottom: parent.bottom; anchors.bottomMargin: 10
                            radius: 1.5
                            color: lessonCard.isCur ? Ui.Theme.primary : Ui.Theme.primaryBorder
                        }
                        HoverHandler { id: rowHover }
                        // hover 高亮独立层：透明度动画，避免 color 插值灰影
                        Rectangle {
                            anchors.fill: parent; radius: parent.radius
                            color: Ui.Theme.hoverOverlay
                            visible: !lessonCard.isCur
                            opacity: rowHover.hovered ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: Ui.Theme.durFast } }
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

                            // 课程色块：永远用课程身份色（与课表页一致）——
                            // "已结束就把色块变灰"会让整页傍晚全灰、和课表
                            // 对不上色；结束态交给徽章和标题变淡表达
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 36; height: 36; radius: 10
                                color: modelData.cbg || Ui.Theme.track
                                opacity: 1   // 两窗色值必须一致，已结束不淡化色块
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.name.length > 0 ? modelData.name[0] : "?"
                                    color: modelData.cfg || Ui.Theme.fg2
                                    font.pixelSize: 15; font.bold: true
                                    font.family: Ui.Theme.fontFamily
                                }
                            }

                            // 名称 + 时间地点两行制
                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2
                                width: parent.width - 36 - chip.width - chev.width - 40
                                Text {
                                    width: parent.width
                                    text: modelData.name
                                    color: lessonCard.isDone ? Ui.Theme.fg2 : Ui.Theme.fg
                                    font.pixelSize: Ui.Theme.fsTitle
                                    font.weight: lessonCard.isCur ? Font.DemiBold : Font.Medium
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: modelData.timeLabel + " · " + modelData.location
                                    color: lessonCard.isCur ? Ui.Theme.primary
                                           : lessonCard.isDone ? Ui.Theme.fg3
                                           : Ui.Theme.fg2
                                    font.pixelSize: Ui.Theme.fsCap
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                            }

                            // 状态 chip：进行中/未开始=主色系，已结束=灰——
                            // 单看徽章也要能分清"还要上"和"上完了"
                            Rectangle {
                                id: chip
                                anchors.verticalCenter: parent.verticalCenter
                                width: chipTxt.width + 14; height: 20; radius: 10
                                color: lessonCard.isDone ? Ui.Theme.badge : Ui.Theme.primarySoft
                                Text {
                                    id: chipTxt
                                    anchors.centerIn: parent
                                    text: lessonCard.isCur ? "进行中"
                                          : lessonCard.isPar ? "同时段"
                                          : lessonCard.isDone ? "已结束" : "未开始"
                                    color: lessonCard.isDone ? Ui.Theme.fg2 : Ui.Theme.primary
                                    font.pixelSize: Ui.Theme.fsCap
                                    font.family: Ui.Theme.fontFamily
                                }
                            }

                            // 展开箭头（图标旋转是 FLstyle 允许的回弹对）
                            Text {
                                id: chev
                                anchors.verticalCenter: parent.verticalCenter
                                text: "›"
                                color: Ui.Theme.fg3; font.pixelSize: 14
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
                            color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                            font.family: Ui.Theme.fontFamily
                            elide: Text.ElideRight; width: parent.width
                        }
                    }
                }
            }

            // 空态（FLstyle：空态也是完整设计——图标井 + 粗标题 + 胶囊按钮）
            Rectangle {
                visible: Bridge.lessons.length === 0
                width: parent.width; height: 92; radius: Ui.Theme.radiusLg
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
                            // 图标种类：0=Dot(今天) 4=Clock(等同步)
                            kind: Bridge.synced ? 0 : 4
                            color: Ui.Theme.primary
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: Bridge.synced ? "今天没有课" : "课表还没同步好"
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                    }
                    Rectangle {
                        visible: Bridge.synced
                        width: hwBtnTxt.width + 24; height: 28; radius: 14
                        color: Ui.Theme.track
                        anchors.horizontalCenter: parent.horizontalCenter
                        Text {
                            id: hwBtnTxt
                            anchors.centerIn: parent
                            text: "看看作业和截止"
                            color: Ui.Theme.primary; font.pixelSize: Ui.Theme.fsCap
                            font.weight: Font.Medium
                            font.family: Ui.Theme.fontFamily
                        }
                    }
                    Text {
                        visible: !Bridge.synced
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "等一轮检查就好"
                        color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.jumpToHw() }
            }

            // ---- 最近截止横幅（白卡 + 左缘紧迫度竖条）----
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
                width: parent.width; height: 48; radius: Ui.Theme.radiusLg
                color: "#FFFFFF"
                Rectangle {
                    x: 0; width: 3
                    anchors.top: parent.top; anchors.topMargin: 12
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 12
                    radius: 1.5
                    color: parent.first
                           ? (parent.first.urgency === "high" ? Ui.Theme.danger
                              : parent.first.urgency === "mid" ? Ui.Theme.warn
                              : parent.first.urgency === "expired" ? Ui.Theme.fg3
                              : Ui.Theme.primary) : Ui.Theme.primary
                }
                Column {
                    x: 16; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                    Text {
                        text: parent.parent.first ? parent.parent.first.course : ""
                        color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        width: 200
                        text: parent.parent.first ? parent.parent.first.title : ""
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsSub; font.weight: Font.Medium
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
                           : Ui.Theme.fg2
                    font.pixelSize: Ui.Theme.fsSub; font.weight: Font.Medium
                    font.family: Ui.Theme.fontFamily
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.jumpToHw() }
            }

            // ---- 考试横幅（有待考/进行中才出现）----
            Rectangle {
                visible: Bridge.examSummary !== ""
                width: parent.width; height: 48; radius: Ui.Theme.radiusLg
                color: "#FFFFFF"
                Rectangle {
                    x: 0; width: 3
                    anchors.top: parent.top; anchors.topMargin: 12
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 12
                    radius: 1.5
                    color: Bridge.examOngoing ? Ui.Theme.danger : Ui.Theme.warn
                }
                // 考试图标井（与课程色块同规格；进行中红/平时暖色）
                Rectangle {
                    x: 16; anchors.verticalCenter: parent.verticalCenter
                    width: 30; height: 30; radius: 9
                    color: Bridge.examOngoing ? Ui.Theme.dangerSoft : Ui.Theme.warnSoft
                    Text {
                        anchors.centerIn: parent; text: "考"
                        color: Bridge.examOngoing ? Ui.Theme.danger : Ui.Theme.warn
                        font.pixelSize: Ui.Theme.fsTitle; font.bold: true
                        font.family: Ui.Theme.fontFamily
                    }
                }
                Column {
                    x: 54; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                    width: parent.width - 54 - examChip.width - 26
                    Text {
                        width: parent.width
                        text: Bridge.examSummary
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsSub; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                        elide: Text.ElideRight
                    }
                    Text {
                        // 副行：进行中放课程名，平时引导点击
                        text: Bridge.examSub !== "" ? Bridge.examSub
                              : "点击查看全部考试安排"
                        color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsMicro
                        font.family: Ui.Theme.fontFamily
                        elide: Text.ElideRight; width: parent.width
                    }
                }
                Rectangle {
                    id: examChip
                    anchors.right: parent.right; anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    width: examChipTxt.width + 14; height: 20; radius: 10
                    color: Bridge.examOngoing ? Ui.Theme.dangerSoft : Ui.Theme.warnSoft
                    Text {
                        id: examChipTxt
                        anchors.centerIn: parent
                        text: Bridge.examCount + " 场"
                        color: Bridge.examOngoing ? Ui.Theme.danger : Ui.Theme.warn
                        font.pixelSize: Ui.Theme.fsCap; font.weight: Font.Medium
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

    // 图标种类注释：0=Dot 1=Grid 2=Doc 3=Pulse 4=Clock 5=Bell 6=Sliders 7=Check
}
