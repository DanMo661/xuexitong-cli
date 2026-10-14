import QtQuick
import "." as Ui

// 课表页：微信小程序课表范式（参考图）
// 节次时间轨（起止双时刻+当前节胶囊）+ 星期/日期双行表头 + 满铺淡彩课程块。
// 整学期恒 11 节次轨（晚间没课也留行），行高自适应高度 → 单页放得下，
// 永不出现纵向滚动；按住鼠标左/右拖动 = 翻上/下一周。
Item {
    id: page
    property int weekOffset: 0     // 本地导航状态；数据由 app 按 offset 重算塞进 Bridge.grid
    property real dragOffset: 0    // 翻周拖动的跟手位移（阻尼后）

    // app 侧会钳制/零点重置 offset，网格每次更新后用 week-curWeek 反推，
    // 本地计数器才不会和真实显示周脱节（脱节后翻周方向会跳错）
    Connections {
        target: Bridge
        function onGridChanged() {
            weekOffset = (Bridge.grid.week || 0) - (Bridge.grid.curWeek || 0)
        }
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

    // 几何常量：7 列恒显 + 左侧时间轨
    readonly property int railW: 38
    readonly property real colW: (width - 24 - railW) / 7
    readonly property int nodeCount: (Bridge.grid.nodeLabels || []).length
    // 行高吃满剩余高度：网格高度整学期恒定（节次轨固定到晚上），不滚动
    readonly property real gridTop: 40 + 30       // 导航行 + 星期表头
    readonly property real rowH: nodeCount > 0
                                  ? Math.max(20, (height - gridTop - 8) / nodeCount)
                                  : 30

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
                text: (Bridge.grid.week || 0) > 0
                      ? "第 " + Bridge.grid.week + " 教学周"
                        + (Bridge.grid.rangeLabel ? " · " + Bridge.grid.rangeLabel : "")
                      : "学期未同步"
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
                // 假期（curWeek>maxWeek）/未开学时"回本周"无意义且会
                // 误亮振荡，只在学期内且看的不是当前周时出现
                visible: (Bridge.grid.curWeek || 0) >= 1
                         && (Bridge.grid.week || 0) >= 1
                         && Bridge.grid.week !== Bridge.grid.curWeek
                         && (!Bridge.grid.maxWeek
                             || Bridge.grid.curWeek <= Bridge.grid.maxWeek)
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

    // ---- 表头：角标 + 星期/日期双行（今天列文字变主题色），随拖动一起平移 ----
    Row {
        id: headRow
        x: 12 + page.dragOffset; y: 40
        width: parent.width - 24
        Item { width: page.railW; height: 30 }
        Repeater {
            model: (Bridge.grid.dayLabels || []).length
            delegate: Item {
                width: page.colW; height: 30
                readonly property bool today:
                    ((Bridge.grid.isTodayCol || [])[index] === true)
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 2
                    text: (Bridge.grid.dayLabels || [])[index] || ""
                    color: today ? Ui.Theme.primary : Ui.Theme.fg
                    font.pixelSize: 12
                    font.weight: today ? Font.DemiBold : Font.Medium
                    font.family: Ui.Theme.fontFamily
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 17
                    text: (Bridge.grid.dayDates || [])[index] || ""
                    color: today ? Ui.Theme.primary : Ui.Theme.faint
                    font.pixelSize: 9
                    font.family: Ui.Theme.fontFamily
                }
            }
        }
    }

    // ---- 网格主体：时间轨 + 课程块画布（单页，无滚动） ----
    Item {
        id: gridBody
        x: 12; y: 70
        width: parent.width - 24
        height: parent.height - 78
        clip: true

        Item {
            id: sheet
            x: page.dragOffset
            width: parent.width
            height: page.nodeCount * page.rowH

            // 时间轨：每节上沿=开始、下沿=结束（真课表的排法）；
            // 当前节整行胶囊高亮
            Repeater {
                model: page.nodeCount
                delegate: Item {
                    width: page.railW; height: page.rowH
                    y: index * page.rowH
                    readonly property bool isNow:
                        index === (Bridge.grid.currentNode === undefined
                                   ? -1 : Bridge.grid.currentNode)
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 1
                        radius: 7
                        color: parent.isNow ? Ui.Theme.primarySoft : "transparent"
                    }
                    Text {
                        anchors.top: parent.top; anchors.topMargin: 0
                        anchors.right: parent.right; anchors.rightMargin: 2
                        text: (Bridge.grid.nodeTimes || [])[index] || ""
                        color: parent.isNow ? Ui.Theme.primary : Ui.Theme.muted
                        font.pixelSize: 8
                        font.weight: parent.isNow ? Font.DemiBold : Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 0
                        anchors.right: parent.right; anchors.rightMargin: 2
                        text: (Bridge.grid.nodeTimesEnd || [])[index] || ""
                        color: parent.isNow ? Ui.Theme.primary : Ui.Theme.faint
                        font.pixelSize: 8
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }

            // 课程块：满铺淡彩、无边框、连堂合并一块；课名按块高折行+
            // 行数上限（超出省略号），教室单行缩字——文字一律不出块
            Repeater {
                model: Bridge.grid.blocks || []
                delegate: Rectangle {
                    id: blk
                    x: page.railW + modelData.col * page.colW + 1.5
                    y: (modelData.node - 1) * page.rowH + 1.5
                    width: page.colW - 3
                    height: modelData.len * page.rowH - 3
                    radius: 5
                    color: modelData.bg
                    clip: true   // 文字极端情况下宁可裁切也不许溢出色块
                    // 课名超 12 字缩一号；行数上限按块高算，多出的省略号
                    readonly property int namePx:
                        modelData.name.length >= 12 ? 9 : 10
                    readonly property int nameLines: Math.max(1, Math.floor(
                        (height - (modelData.location !== "" ? 15 : 6) - 6)
                        / (namePx + 4)))
                    Column {
                        anchors.centerIn: parent
                        width: parent.width - 8
                        spacing: 1
                        Text {
                            width: parent.width
                            text: modelData.name
                            color: modelData.fg
                            font.pixelSize: blk.namePx
                            font.weight: Font.Medium
                            font.family: Ui.Theme.fontFamily
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            maximumLineCount: blk.nameLines
                            elide: Text.ElideRight
                            lineHeight: 1.05
                        }
                        Text {
                            // 地点单行+省略号：HorizontalFit 缩到 6px 仍可能
                            // 溢出（"马兰芳教学楼102" 7 个全角字），不可靠
                            width: parent.width
                            visible: modelData.location !== ""
                            text: modelData.location
                            color: modelData.fg
                            opacity: 0.75
                            font.pixelSize: 8
                            elide: Text.ElideRight
                            font.family: Ui.Theme.fontFamily
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                }
            }

            // 当前时间红线（仅本周视图）：横贯网格 + 右端圆点。
            // 节内按进度走，课间/午休贴在下节课上沿（网格线上）
            Item {
                visible: Bridge.grid.nowLine !== undefined
                         && Bridge.grid.nowLine >= 0
                y: Bridge.grid.nowLine * page.rowH - 1
                x: page.railW
                width: parent.width - page.railW
                height: 2
                Rectangle {
                    anchors.fill: parent; radius: 1
                    color: Ui.Theme.danger; opacity: 0.85
                }
                Rectangle {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: 6; height: 6; radius: 3
                    color: Ui.Theme.danger
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

        // 拖动翻周：按住左/右拖，超阈值松手 = 上/下一周（跟手位移有阻尼）
        MouseArea {
            id: swipeArea
            anchors.fill: parent
            property real pressX: 0
            property bool dragging: false
            onPressed: mouse => {
                pressX = mouse.x
                dragging = true
                snapBack.stop()
            }
            onPositionChanged: mouse => {
                if (dragging)
                    page.dragOffset = (mouse.x - pressX) * 0.35
            }
            onReleased: {
                dragging = false
                const dx = mouse.x - pressX
                const canPrev = (Bridge.grid.week || 1) > 1
                const canNext = !Bridge.grid.maxWeek
                                || (Bridge.grid.week || 1) < Bridge.grid.maxWeek
                if (dx <= -55 && canNext) {
                    page.weekOffset++
                    Bridge.requestWeek(page.weekOffset)
                    page.dragOffset = Math.max(dx * 0.35, -110)
                } else if (dx >= 55 && canPrev) {
                    page.weekOffset--
                    Bridge.requestWeek(page.weekOffset)
                    page.dragOffset = Math.min(dx * 0.35, 110)
                }
                snapBack.restart()
            }
            onCanceled: { dragging = false; snapBack.restart() }
            NumberAnimation {
                id: snapBack
                target: page; property: "dragOffset"; to: 0
                duration: 180
                easing.type: Easing.Bezier; easing.bezierCurve: Ui.Theme.ccEnter
            }
        }
    }
}
