import QtQuick
import "." as Ui

// 通知页：通知中心列表（全部/未读过滤），点条目展开全文并记本地已读
// FLstyle：白卡浮灰页无描边；过滤 = 分段器（灰轨+选中段实心主色）；
// 展开态用主色文字表达，不画彩色卡边
Item {
    id: page
    property int filter: 0   // 0 全部 1 未读
    property string expandedKey: ""   // 展开全文的那条

    // 过滤在 JS 层做（数据量 ≤40 行，不值得上 C++ 模型）
    readonly property var shown: filter === 1
        ? DBridge.notices.filter(function(n) { return n.unread })
        : DBridge.notices

    onVisibleChanged: if (visible) fade.restart()

    // 内容入场：只做透明度渐变（零位移）
    NumberAnimation {
        id: fade
        target: page; property: "opacity"; from: 0; to: 1; duration: Ui.Theme.durFade
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

            // ---- 头：分组标题 + 过滤分段器 ----
            Item {
                width: parent.width; height: 28
                Text {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    text: "通知中心"
                    color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.Medium
                    font.family: Ui.Theme.fontFamily
                }
                // mini 分段（全部/未读）：灰轨 + 选中段实心主色胶囊，原位迁移
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: 108; height: 24; radius: 12
                    color: Ui.Theme.track
                    Row {
                        anchors.fill: parent
                        Repeater {
                            model: ["全部", "未读"]
                            delegate: Item {
                                width: 54; height: 24
                                readonly property bool sel: page.filter === index
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 50; height: 20; radius: 10
                                    color: sel ? Ui.Theme.primary : "transparent"
                                    Behavior on color { ColorAnimation { duration: Ui.Theme.durSeg } }
                                }
                                Text {
                                    anchors.centerIn: parent; text: modelData
                                    color: sel ? "#FFFFFF" : Ui.Theme.fg2
                                    font.pixelSize: Ui.Theme.fsCap
                                    font.weight: sel ? Font.DemiBold : Font.Normal
                                    font.family: Ui.Theme.fontFamily
                                    Behavior on color { ColorAnimation { duration: Ui.Theme.durSeg } }
                                }
                                MouseArea {
                                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: page.filter = index
                                }
                            }
                        }
                    }
                }
            }

            Repeater {
                model: page.shown
                delegate: Rectangle {
                    id: ncCard
                    width: col.width
                    readonly property bool expanded: page.expandedKey === modelData.key
                    // 展开时高度跟内容走（全文换行），收起固定紧凑高
                    height: expanded ? 20 + titleCol.height + bodyTxt.height + 16
                            : modelData.content !== "" ? 68 : 54
                    radius: Ui.Theme.radiusLg
                    color: "#FFFFFF"
                    Behavior on height {
                        NumberAnimation {
                            duration: 180; easing.type: Easing.Bezier
                            easing.bezierCurve: Ui.Theme.popBack
                        }
                    }
                    // 未读红点（状态允许上小点）
                    Rectangle {
                        visible: modelData.unread
                        x: 10; anchors.verticalCenter: titleCol.verticalCenter
                        width: 8; height: 8; radius: 4
                        color: Ui.Theme.danger
                    }
                    Column {
                        id: titleCol
                        x: 26; y: 8; spacing: 3
                        width: parent.width - 26 - 12
                        Item {
                            width: parent.width; height: 16
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - 14
                                text: modelData.title
                                // 展开 = 选中态：主色文字，不画彩色边
                                color: ncCard.expanded ? Ui.Theme.primary : Ui.Theme.fg
                                font.pixelSize: Ui.Theme.fsBody
                                font.weight: modelData.unread ? Font.DemiBold : Font.Medium
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight
                                Behavior on color { ColorAnimation { duration: Ui.Theme.durFast } }
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: ncCard.expanded ? "▴" : "▾"
                                color: ncCard.expanded ? Ui.Theme.primary : Ui.Theme.fg3
                                font.pixelSize: 10
                                font.family: Ui.Theme.fontFamily
                                visible: modelData.content !== ""
                            }
                        }
                        Text {
                            width: parent.width
                            text: modelData.sender + " · " + modelData.time
                            color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                            font.family: Ui.Theme.fontFamily
                            elide: Text.ElideRight
                        }
                        Text {
                            visible: !ncCard.expanded && modelData.content !== ""
                            width: parent.width
                            text: modelData.content.replace(/\n/g, " ")
                            color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                            font.family: Ui.Theme.fontFamily
                            elide: Text.ElideRight
                        }
                    }
                    // 展开的全文（换行保留）
                    Text {
                        id: bodyTxt
                        visible: ncCard.expanded
                        x: 26; width: parent.width - 38
                        y: titleCol.y + titleCol.height + 4
                        text: modelData.content
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsSub
                        font.family: Ui.Theme.fontFamily
                        wrapMode: Text.WrapAnywhere   // 长 URL 不断行会把整行撑出大空洞
                        lineHeight: 1.25
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            page.expandedKey = ncCard.expanded ? "" : modelData.key
                            if (modelData.unread) DBridge.markNoticeRead(modelData.key)
                        }
                    }
                }
            }

            // 空态（FLstyle：图标井 + 粗标题 + 副文）
            Rectangle {
                visible: page.shown.length === 0
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
                            kind: 5   // Bell
                            color: Ui.Theme.primary
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: page.filter === 1 ? "没有未读通知" : "还没有通知"
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "老师/学校发的通知会出现在这里"
                        color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }
        }
    }
}
