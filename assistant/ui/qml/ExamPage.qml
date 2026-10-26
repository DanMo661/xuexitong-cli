import QtQuick
import "." as Ui

// 考试页：考试安排卡片（进行中/倒计时/已结束）+ 任务点完成度
// FLstyle：白卡浮灰页无描边；状态 = 左缘竖条/药丸/文字色；刷新 = 图标井
Item {
    id: page
    property int filterUnread: 0   // 占位保持组件签名一致（未用）

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

            // ---- 考试列表头（分组标题 13px 灰）----
            Item {
                width: parent.width; height: 26
                Text {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    text: "考试安排"
                    color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.Medium
                    font.family: Ui.Theme.fontFamily
                }
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: cntTxt.width + 16; height: 20; radius: 10
                    color: Ui.Theme.badge
                    visible: col.liveCount > 0
                    Text {
                        id: cntTxt
                        anchors.centerIn: parent
                        text: col.liveCount + " 场待考"
                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
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
                    radius: Ui.Theme.radiusLg
                    color: "#FFFFFF"
                    readonly property bool isLive: modelData.state !== "done"
                    opacity: modelData.state === "done" ? 0.55 : 1
                    // 左缘色条：进行中红 / 未考按天数黄蓝 / 已结束灰
                    Rectangle {
                        x: 0; width: 3
                        anchors.top: parent.top; anchors.topMargin: 14
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 14
                        radius: 1.5
                        color: modelData.state === "ongoing" ? Ui.Theme.danger
                               : modelData.state === "done" ? Ui.Theme.fg3
                               : modelData.days <= 3 ? Ui.Theme.warn
                               : Ui.Theme.primary
                    }
                    Column {
                        x: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                        width: parent.width - 14 - pill.width - 26
                        Text {
                            width: parent.width
                            text: modelData.name
                            color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsBody
                            font.weight: modelData.state === "ongoing" ? Font.DemiBold : Font.Medium
                            font.family: Ui.Theme.fontFamily
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            // 进行中的考试最有用的信息是几点结束
                            text: modelData.state === "ongoing"
                                  ? "至 " + modelData.endLabel + " 结束"
                                  : modelData.startLabel + " 开考 · "
                                    + modelData.durationMin + " 分钟"
                                    + (modelData.mode && modelData.mode !== "未设置终端"
                                       ? " · " + modelData.mode : "")
                            color: modelData.state === "ongoing" ? Ui.Theme.danger
                                   : Ui.Theme.fg2
                            font.pixelSize: Ui.Theme.fsCap
                            font.family: Ui.Theme.fontFamily
                            elide: Text.ElideRight
                        }
                    }
                    Rectangle {
                        id: pill
                        anchors.right: parent.right; anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        width: pillTxt.width + 14; height: 22; radius: 11
                        // 已结束且有分数 → 绿底数字（考试看板的核心遗留价值）
                        color: modelData.state === "done" && modelData.scoreNum !== ""
                               ? Ui.Theme.okSoft
                               : modelData.state === "ongoing" ? Ui.Theme.dangerSoft
                               : modelData.state === "done" ? Ui.Theme.badge
                               : modelData.days <= 3 ? Ui.Theme.warnSoft
                               : Ui.Theme.primarySoft
                        Text {
                            id: pillTxt
                            anchors.centerIn: parent
                            text: modelData.state === "done"
                                  ? (modelData.scoreNum !== "" ? modelData.scoreNum + " 分" : "已结束")
                                  : modelData.state === "ongoing" ? "进行中"
                                  : modelData.daysLabel
                            color: modelData.state === "done" && modelData.scoreNum !== ""
                                   ? Ui.Theme.ok
                                   : modelData.state === "ongoing" ? Ui.Theme.danger
                                   : modelData.state === "done" ? Ui.Theme.fg2
                                   : modelData.days <= 3 ? Ui.Theme.warn
                                   : Ui.Theme.primary
                            font.pixelSize: Ui.Theme.fsCap; font.weight: Font.Medium
                            font.family: Ui.Theme.fontFamily
                        }
                    }
                }
            }

            // 空态（FLstyle：图标井 + 粗标题 + 副文）
            Rectangle {
                visible: DBridge.exams.length === 0
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
                            kind: 4   // Clock
                            color: Ui.Theme.primary
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "暂无考试安排"
                        color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.DemiBold
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "有新考试会弹提醒"
                        color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
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
                    color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsTitle; font.weight: Font.Medium
                    font.family: Ui.Theme.fontFamily
                }
                // 刷新 = 图标井：中性井底 + 强调色图形
                Rectangle {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: 28; height: 26; radius: 8
                    color: Ui.Theme.well
                    Text {
                        anchors.centerIn: parent; text: "⟳"
                        color: pgHover.hovered || DBridge.refreshing
                               ? Ui.Theme.primary : Ui.Theme.fg2
                        font.pixelSize: Ui.Theme.fsBody; font.family: Ui.Theme.fontFamily
                        RotationAnimation on rotation {
                            running: DBridge.refreshing
                            loops: Animation.Infinite
                            from: 0; to: 360; duration: 900
                            alwaysRunToEnd: true
                        }
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
                width: parent.width; radius: Ui.Theme.radiusLg
                color: "#FFFFFF"
                height: pgCol.height + 20
                Column {
                    id: pgCol
                    x: 14; y: 10; width: parent.width - 28; spacing: 10

                    Text {
                        visible: DBridge.progress.totalLeft > 0
                        text: DBridge.progress.coursesLeft + " 门课共 "
                              + DBridge.progress.totalLeft + " 个任务点未完成"
                        color: Ui.Theme.warn; font.pixelSize: Ui.Theme.fsSub; font.weight: Font.Medium
                        font.family: Ui.Theme.fontFamily
                    }
                    Text {
                        // 有数据且全完成才敢说"全部完成"（全是 error 行时不算）
                        visible: DBridge.progress.hasData === true
                                 && DBridge.progress.totalLeft === 0
                        text: "本学期课程任务点全部完成 ✓"
                        color: Ui.Theme.ok; font.pixelSize: Ui.Theme.fsSub
                        font.family: Ui.Theme.fontFamily
                    }
                    // 数据陈旧度：每天一刷，隔天的缺口数别让人误会
                    Text {
                        visible: DBridge.progress.date !== ""
                                 && DBridge.progress.date
                                     !== Qt.formatDateTime(new Date(), "yyyy-MM-dd")
                        text: "（数据截至 " + DBridge.progress.date.substring(5) + "）"
                        color: Ui.Theme.fg3; font.pixelSize: 9
                        font.family: Ui.Theme.fontFamily
                    }

                    Repeater {
                        model: DBridge.progress.rows
                        delegate: Column {
                            width: pgCol.width; spacing: 4
                            // 注意 == null：Python None 进 QML 是 undefined
                            //（=== null 永假，无数据课会被当"完成"渲染）
                            opacity: modelData.done == null ? 0.55 : 1
                            // 定位器（Row/Column）里不能用 anchors，行结构用 Item 摆
                            Item {
                                width: parent.width; height: 16
                                Text {
                                    x: 0; width: parent.width - 100
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.course
                                    color: Ui.Theme.fg; font.pixelSize: Ui.Theme.fsSub
                                    font.family: Ui.Theme.fontFamily
                                    elide: Text.ElideRight
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.done == null ? "无数据"
                                          : modelData.left > 0
                                            ? "差 " + modelData.left + " 个"
                                            : "完成 ✓"
                                    color: modelData.done == null ? Ui.Theme.fg3
                                           : modelData.left > 0 ? Ui.Theme.warn
                                           : Ui.Theme.ok
                                    font.pixelSize: Ui.Theme.fsCap; font.weight: Font.Medium
                                    font.family: Ui.Theme.fontFamily
                                }
                            }
                            // 细进度条（轨 + 主色/成功填充）
                            Rectangle {
                                visible: modelData.done != null && modelData.left > 0
                                width: parent.width; height: 4; radius: 2
                                color: Ui.Theme.track
                                Rectangle {
                                    width: parent.width * (modelData.pct / 100)
                                    height: parent.height; radius: 2
                                    color: modelData.left > 0 ? Ui.Theme.primary
                                           : Ui.Theme.ok
                                }
                            }
                        }
                    }

                    // 不在课表但有未完成的课（网课/纯线上选修——任务点重灾区）
                    Text {
                        visible: DBridge.progress.otherRows.length > 0
                        text: "不在课表的课（网课等）"
                        color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                        font.family: Ui.Theme.fontFamily
                    }
                    Repeater {
                        model: DBridge.progress.otherRows
                        delegate: Item {
                            width: pgCol.width; height: 16
                            Text {
                                x: 0; width: parent.width - 100
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.course
                                color: Ui.Theme.fg2; font.pixelSize: Ui.Theme.fsCap
                                font.family: Ui.Theme.fontFamily
                                elide: Text.ElideRight
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: "差 " + modelData.left + " 个"
                                color: Ui.Theme.warn; font.pixelSize: Ui.Theme.fsCap
                                font.weight: Font.Medium
                                font.family: Ui.Theme.fontFamily
                            }
                        }
                    }
                }
            }

            Rectangle {
                visible: DBridge.progress.rows.length === 0
                width: parent.width; height: 56; radius: Ui.Theme.radiusLg
                color: "#FFFFFF"
                Text {
                    anchors.centerIn: parent
                    text: "任务点数据还没拉取（每天自动刷一次，或点右上 ⟳）"
                    color: Ui.Theme.fg3; font.pixelSize: Ui.Theme.fsCap
                    font.family: Ui.Theme.fontFamily
                }
            }
        }
    }
}
