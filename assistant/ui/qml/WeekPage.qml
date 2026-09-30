import QtQuick
import "." as Ui

// 课表页：微信小程序课表范式（参考图）
// 节次时间轨（当前节胶囊高亮）+ 星期/日期双行表头 + 满铺淡彩课程块
// （连堂合并一块、无边框、空格纯白无网格线）
Item {
    id: page
    property int weekOffset: 0     // 本地导航状态；数据由 app 按 offset 重算塞进 Bridge.grid

    onVisibleChanged: if (visible) enter.restart()

    ParallelAnimation {
        id: enter
        NumberAnimation { target: page; property: "opacity"; from: 0; to: 1; duration: 160 }
        NumberAnimation {
            target: page; property: "x"; from: 10; to: 0; duration: 220
            easing.type: Easing.Bezier; easing.bezierCurve: Ui.Theme.ccEnter
        }
    }

    // 几何常量：7 列恒显 + 左侧时间轨
    readonly property int railW: 34
    readonly property real colW: (width - 24 - railW) / 7
    readonly property int rowH: 38

    // ---- 周次导航（浮在顶部） ----
    Rectangle {
        y: 0; width: parent.width; height: 40; color: Ui.Theme.card
        Row {
            anchors.left: parent.left; anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 26; height: 26; radius: 13
                color: !enabled ? "transparent"
                       : prevHover.hovered ? Ui.Theme.secondary : "transparent"
                enabled: (Bridge.grid.week || 1) > 1
                opacity: enabled ? 1 : 0.35
                HoverHandler { id: prevHover }
                Text {
                    anchors.centerIn: parent; text: "‹"
                    color: Ui.Theme.muted; font.pixelSize: 15
                    font.family: Ui.Theme.fontFamily
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: { page.weekOffset--; Bridge.requestWeek(page.weekOffset) }
                }
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "第 " + (Bridge.grid.week || 1) + " 教学周"
                      + (Bridge.grid.rangeLabel ? " · " + Bridge.grid.rangeLabel : "")
                color: Ui.Theme.fg; font.pixelSize: 12
                font.weight: Font.DemiBold
                font.family: Ui.Theme.fontFamily
            }

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 26; height: 26; radius: 13
                color: !enabled ? "transparent"
                       : nextHover.hovered ? Ui.Theme.secondary : "transparent"
                enabled: !Bridge.grid.maxWeek
                         || (Bridge.grid.week || 1) < Bridge.grid.maxWeek
                opacity: enabled ? 1 : 0.35
                HoverHandler { id: nextHover }
                Text {
                    anchors.centerIn: parent; text: "›"
                    color: Ui.Theme.muted; font.pixelSize: 15
                    font.family: Ui.Theme.fontFamily
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: { page.weekOffset++; Bridge.requestWeek(page.weekOffset) }
                }
            }

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                visible: page.weekOffset !== 0
                width: backTxt.width + 16; height: 22; radius: 11
                color: Ui.Theme.primarySoft
                Text {
                    id: backTxt
                    anchors.centerIn: parent; text: "回本周"
                    color: Ui.Theme.primary; font.pixelSize: 10
                    font.family: Ui.Theme.fontFamily
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: { page.weekOffset = 0; Bridge.requestWeek(0) }
                }
            }
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            text: Bridge.grid.maxWeek ? "/ 共 " + Bridge.grid.maxWeek + " 周" : ""
            color: Ui.Theme.faint; font.pixelSize: 10
            font.family: Ui.Theme.fontFamily
        }
        Rectangle { y: 39; width: parent.width; height: 1; color: Ui.Theme.borderSoft }
    }

    // ---- 网格主体（表头随内容滚动） ----
    Flickable {
        anchors.fill: parent
        anchors.topMargin: 40
        contentWidth: width
        contentHeight: headRow.height + gridBody.height + 24
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            x: 12; width: parent.width - 24

            // 表头：角标 + 星期/日期双行（今天列文字变主题色）
            Row {
                id: headRow
                Item { width: page.railW; height: 34 }
                Repeater {
                    model: (Bridge.grid.dayLabels || []).length
                    delegate: Item {
                        width: page.colW; height: 34
                        readonly property int cidx: index
                        readonly property bool today:
                            ((Bridge.grid.isTodayCol || [])[index] === true)
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 3
                            text: (Bridge.grid.dayLabels || [])[index] || ""
                            color: today ? Ui.Theme.primary : Ui.Theme.fg
                            font.pixelSize: 12
                            font.weight: today ? Font.DemiBold : Font.Medium
                            font.family: Ui.Theme.fontFamily
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 19
                            text: (Bridge.grid.dayDates || [])[index] || ""
                            color: today ? Ui.Theme.primary : Ui.Theme.faint
                            font.pixelSize: 9
                            font.family: Ui.Theme.fontFamily
                        }
                    }
                }
            }

            // 主体：时间轨 + 课程块画布
            Item {
                id: gridBody
                width: parent.width
                height: (Bridge.grid.nodeLabels || []).length * page.rowH + 16

                // 时间轨：节号+起始时间；当前节套胶囊高亮（参考图玫红胶囊→主色蓝）
                Repeater {
                    model: (Bridge.grid.nodeLabels || []).length
                    delegate: Item {
                        width: page.railW; height: page.rowH
                        y: index * page.rowH
                        readonly property bool isNow:
                            index === (Bridge.grid.currentNode === undefined
                                       ? -1 : Bridge.grid.currentNode)
                        Rectangle {
                            anchors.fill: parent; anchors.margins: 2
                            radius: 9
                            color: parent.isNow ? Ui.Theme.primarySoft : "transparent"
                        }
                        Text {
                            anchors.centerIn: parent
                            text: ((Bridge.grid.nodeLabels || [])[index] || "")
                                  + "\n" + ((Bridge.grid.nodeTimes || [])[index] || "")
                            horizontalAlignment: Text.AlignHCenter
                            color: parent.isNow ? Ui.Theme.primary : Ui.Theme.muted
                            font.pixelSize: parent.isNow ? 10 : 9
                            font.weight: parent.isNow ? Font.DemiBold : Font.Medium
                            lineHeight: 1.15
                            font.family: Ui.Theme.fontFamily
                        }
                    }
                }

                // 课程块：满铺淡彩、无边框、连堂合并一块、文字居中换行
                Repeater {
                    model: Bridge.grid.blocks || []
                    delegate: Rectangle {
                        x: page.railW + modelData.col * page.colW + 1.5
                        y: (modelData.node - 1) * page.rowH + 1.5
                        width: page.colW - 3
                        height: modelData.len * page.rowH - 3
                        radius: 5
                        color: modelData.bg
                        Column {
                            anchors.centerIn: parent
                            width: parent.width - 4
                            spacing: 1
                            Text {
                                width: parent.width
                                text: modelData.name
                                color: modelData.fg
                                font.pixelSize: 9
                                font.weight: Font.Medium
                                font.family: Ui.Theme.fontFamily
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WrapAnywhere
                            }
                            Text {
                                // 地点不逐字折行（"北主楼60/4"没法读）：
                                // 单行 + 按宽度自动缩字号
                                width: parent.width
                                visible: modelData.location !== ""
                                text: modelData.location
                                color: modelData.fg
                                opacity: 0.8
                                font.pixelSize: 8
                                minimumPixelSize: 6
                                fontSizeMode: Text.HorizontalFit
                                font.family: Ui.Theme.fontFamily
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }
                    }
                }

                // 空态
                Text {
                    visible: (Bridge.grid.blocks || []).length === 0
                    anchors.centerIn: parent
                    text: Bridge.grid.empty ? "课表还没同步好" : "这一周没有课"
                    color: Ui.Theme.faint; font.pixelSize: 12
                    font.family: Ui.Theme.fontFamily
                }
            }
        }
    }
}
