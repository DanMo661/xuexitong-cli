import QtQuick
import "." as Ui

// 通知页：通知中心列表（全部/未读过滤），点条目展开全文并记本地已读
Item {
    id: page
    property int filter: 0   // 0 全部 1 未读
    property string expandedKey: ""   // 展开全文的那条

    // 过滤在 JS 层做（数据量 ≤40 行，不值得上 C++ 模型）
    readonly property var shown: filter === 1
        ? DBridge.notices.filter(function(n) { return n.unread })
        : DBridge.notices

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

            // ---- 头：标题 + 过滤胶囊 ----
            Item {
                width: parent.width; height: 28
                Text {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    text: "通知中心"
                    color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.DemiBold
                    font.family: Ui.Theme.fontFamily
                }
                // mini 分段（全部/未读）
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: 108; height: 24; radius: 12
                    color: Ui.Theme.secondary
                    Rectangle {
                        y: 2; height: 20; radius: 10; width: 52
                        x: 2 + page.filter * 52
                        color: "#FFFFFF"
                        border.width: 1; border.color: Ui.Theme.borderSoft
                        Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.Bezier; easing.bezierCurve: Ui.Theme.ccEnter } }
                    }
                    Row {
                        anchors.fill: parent
                        Repeater {
                            model: ["全部", "未读"]
                            delegate: Item {
                                width: 52; height: 24
                                Text {
                                    anchors.centerIn: parent; text: modelData
                                    color: page.filter === index ? Ui.Theme.fg : Ui.Theme.muted
                                    font.pixelSize: 10
                                    font.weight: page.filter === index ? Font.DemiBold : Font.Normal
                                    font.family: Ui.Theme.fontFamily
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
                    radius: Ui.Theme.radiusMd
                    color: "#FFFFFF"
                    border.width: 1
                    border.color: ncCard.expanded ? Ui.Theme.primaryBorder : Ui.Theme.border
                    Behavior on height {
                        NumberAnimation {
                            duration: 180; easing.type: Easing.Bezier
                            easing.bezierCurve: Ui.Theme.popBack
                        }
                    }
                    // 未读红点
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
                                color: Ui.Theme.fg; font.pixelSize: 12
                                font.weight: modelData.unread ? Font.DemiBold : Font.Medium
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: ncCard.expanded ? "▴" : "▾"
                                color: Ui.Theme.faint; font.pixelSize: 10
                                font.family: Ui.Theme.fontFamily
                                visible: modelData.content !== ""
                            }
                        }
                        Text {
                            width: parent.width
                            text: modelData.sender + " · " + modelData.time
                            color: Ui.Theme.faint; font.pixelSize: 10
                            font.family: Ui.Theme.fontFamily
                            elide: Text.ElideRight
                        }
                        Text {
                            visible: !ncCard.expanded && modelData.content !== ""
                            width: parent.width
                            text: modelData.content.replace(/\n/g, " ")
                            color: Ui.Theme.muted; font.pixelSize: 10
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
                        color: Ui.Theme.fg; font.pixelSize: 11
                        font.family: Ui.Theme.fontFamily
                        wrapMode: Text.Wrap
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

            Rectangle {
                visible: page.shown.length === 0
                width: parent.width; height: 72; radius: Ui.Theme.radiusMd
                color: "#FFFFFF"; border.width: 1; border.color: Ui.Theme.border
                Column {
                    anchors.centerIn: parent; spacing: 4
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: page.filter === 1 ? "没有未读通知" : "还没有通知"
                        color: Ui.Theme.fg; font.pixelSize: 13; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "老师/学校发的通知会出现在这里"
                        color: Ui.Theme.faint; font.pixelSize: 10
                        font.family: Ui.Theme.fontFamily
                    }
                }
            }
        }
    }
}
