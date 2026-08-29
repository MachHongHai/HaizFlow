pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    signal openVideoDetail
    signal requestBatchSettings
    signal requestUrlImport
    signal requestDownloadProjectImport

    property bool dropActive: false
    readonly property bool compactHeight: height < 740

    opacity: visible ? 1 : 0
    transform: Translate {
        y: root.visible ? 0 : 8
        Behavior on y {
            NumberAnimation {
                duration: Theme.motionStandard
                easing.type: Easing.OutCubic
            }
        }
    }
    Behavior on opacity {
        NumberAnimation {
            duration: Theme.motionStandard
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space20
        spacing: root.compactHeight ? Theme.space12 : Theme.space16

        PageHeader {
            Layout.fillWidth: true
            Layout.minimumHeight: root.compactHeight ? 52 : 58
            Layout.preferredHeight: root.compactHeight ? 52 : 58
            title: AppController.projectName || qsTr("Dự án hàng loạt")
            subtitle: qsTr("%1 %2").arg(AppController.batchCount).arg(qsTr("video"))

            ProjectHeaderActions {
                projectFolderEnabled: AppController.hasOpenProject
                deleteEnabled: AppController.hasOpenProject
                onProjectFolderRequested: AppController.openProjectFolder()
                onDeleteRequested: AppController.deleteCurrentBatch()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 52
            Layout.preferredHeight: 52
            Layout.maximumHeight: 52
            spacing: Theme.space12

            Rectangle {
                id: importCard

                Layout.preferredWidth: Math.min(640, Math.max(500, root.width * 0.48))
                Layout.minimumWidth: 500
                Layout.maximumWidth: 640
                Layout.fillHeight: true
                radius: Theme.radiusSmall
                color: root.dropActive ? Theme.interactiveMuted : Theme.interactiveMuted
                border.width: root.dropActive ? 2 : 1
                border.color: root.dropActive ? Theme.focus : Theme.interactiveOutline

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space12
                    anchors.rightMargin: Theme.space12
                    spacing: Theme.space8

                    Rectangle {
                        Layout.preferredWidth: 24
                        Layout.preferredHeight: 24
                        radius: Theme.radiusSmall
                        color: Theme.interactiveMuted

                        AppIcon {
                            anchors.centerIn: parent
                            width: 14
                            height: 14
                            glyph: "\uE898"
                            iconColor: Theme.interactive
                            iconSize: Theme.iconSmall
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: AppController.mediaImportBusy ? qsTr("Adding %1 / %2…").arg(AppController.mediaImportCompleted).arg(AppController.mediaImportTotal) : root.dropActive ? qsTr("Thả để thêm video") : qsTr("Thêm vào hàng đợi")
                        color: Theme.text
                        font.pixelSize: Theme.caption
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }

                    MediaSourceImportButton {
                        Layout.preferredWidth: 132
                        tone: "primary"
                        onFileRequested: AppController.browseBatchVideos()
                        onLinkRequested: root.requestUrlImport()
                        onDownloadProjectRequested: root.requestDownloadProjectImport()
                    }
                }

                DropArea {
                    anchors.fill: parent
                    keys: ["text/uri-list"]
                    onEntered: function (drag) {
                        if (drag.hasUrls) {
                            root.dropActive = true;
                            drag.accept();
                        }
                    }
                    onExited: root.dropActive = false
                    onDropped: function (drop) {
                        root.dropActive = false;
                        if (!drop.urls || drop.urls.length === 0)
                            return;
                        const paths = [];
                        for (let index = 0; index < drop.urls.length; ++index)
                            paths.push(String(drop.urls[index]));
                        AppController.importBatchVideos(paths);
                    }
                }
            }

            Item {
                Layout.fillWidth: true
            }

            AppButton {
                text: qsTr("Cài đặt hàng loạt")
                iconGlyph: "\uE713"
                tone: "secondary"
                enabled: AppController.batchCount > 0 && !AppController.isBatchRunning
                onClicked: root.requestBatchSettings()
            }

            AppButton {
                visible: !AppController.isBatchRunning
                text: AppController.batchPausedCount > 0 ? qsTr("Tiếp tục xử lý") : qsTr("Bắt đầu xử lý")
                iconGlyph: "\uE768"
                tone: "primary"
                enabled: AppController.batchPendingCount > 0 || AppController.batchPausedCount > 0
                onClicked: {
                    if (AppController.batchPausedCount > 0)
                        AppController.resumeBatch();
                    else
                        AppController.startBatch();
                }
            }

            AppButton {
                visible: AppController.isBatchRunning
                text: AppController.isBatchPausing ? qsTr("Đang tạm dừng") : qsTr("Tạm dừng xử lý")
                iconGlyph: "\uE71A"
                tone: "danger"
                enabled: !AppController.isBatchPausing
                onClicked: AppController.stopBatch()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                text: qsTr("Hàng đợi xử lý")
                color: Theme.text
                font.pixelSize: Theme.h2
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Rectangle {
                visible: AppController.isBatchRunning
                Layout.preferredWidth: queueStateLabel.implicitWidth + Theme.space20
                Layout.preferredHeight: 28
                radius: Theme.radiusSmall
                color: Theme.warningMuted

                Text {
                    id: queueStateLabel
                    anchors.centerIn: parent
                    text: AppController.isBatchPausing ? qsTr("Đang tạm dừng") : qsTr("Đang xử lý")
                    color: Theme.warning
                    font.pixelSize: Theme.label
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }

            Text {
                visible: AppController.batchCount > 0
                text: qsTr("%1 %2").arg(AppController.batchCount).arg(qsTr("mục"))
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: queueList.cellHeight + Theme.space12
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.outline

            GridView {
                id: queueList

                // Keep batch cards at the same compact scale as project cards.
                readonly property int columnCount: Math.max(1, Math.floor((width + Theme.space16) / (200 + Theme.space16)))
                readonly property real cellContentWidth: Math.floor(width / columnCount)
                readonly property real cardWidth: Math.min(220, Math.max(1, cellContentWidth - Theme.space16))
                readonly property real cardHeight: Math.round(cardWidth * 0.56 + 64)

                anchors.fill: parent
                anchors.margins: AppController.batchCount > 0 ? Theme.space12 : 0
                clip: true
                model: AppController.batchVideoModel
                reuseItems: true
                cellWidth: cellContentWidth
                cellHeight: cardHeight + Theme.space16

                delegate: BatchVideoCard {
                    width: queueList.cardWidth
                    height: queueList.cardHeight
                    onActivated: {
                        AppController.selectBatchVideo(index);
                        root.openVideoDetail();
                    }
                }

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
            }

            Column {
                anchors.centerIn: parent
                width: Math.min(420, parent.width - 40)
                spacing: Theme.space8
                visible: AppController.batchCount === 0

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 44
                    height: 44
                    radius: Theme.radius
                    color: Theme.interactiveMuted

                    AppIcon {
                        anchors.centerIn: parent
                        width: 26
                        height: 26
                        glyph: "\uE8FD"
                        iconColor: Theme.interactive
                        iconSize: Theme.iconLarge
                    }
                }

                Text {
                    width: parent.width
                    text: qsTr("Hàng đợi đang trống")
                    color: Theme.text
                    font.pixelSize: Theme.h3
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    textFormat: Text.PlainText
                }

                Text {
                    width: parent.width
                    text: qsTr("Thêm video ở phía trên để bắt đầu xử lý")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    horizontalAlignment: Text.AlignHCenter
                    textFormat: Text.PlainText
                }
            }
        }

        Rectangle {
            id: batchProgressPanel

            Layout.fillWidth: true
            Layout.minimumHeight: 52
            Layout.preferredHeight: 52
            Layout.maximumHeight: 52
            radius: Theme.radiusSmall
            color: Theme.interactiveMuted
            border.width: 1
            border.color: Theme.interactiveOutline

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space12
                anchors.rightMargin: Theme.space12
                spacing: Theme.space12

                Rectangle {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    radius: Theme.radiusSmall
                    color: Theme.interactiveMuted

                    AppIcon {
                        anchors.centerIn: parent
                        width: 16
                        height: 16
                        glyph: "\uE9D2"
                        iconColor: Theme.interactive
                        iconSize: Theme.icon
                    }
                }

                InfoRow {
                    Layout.preferredWidth: 78
                    label: qsTr("Video")
                    value: String(AppController.batchCount)
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 28
                    color: Theme.interactiveOutline
                }

                InfoRow {
                    Layout.preferredWidth: 112
                    label: qsTr("Hoàn tất")
                    value: qsTr("%1 / %2").arg(AppController.batchCompletedCount).arg(AppController.batchCount)
                }

                ColumnLayout {
                    visible: root.width >= 1180
                    Layout.preferredWidth: visible ? 150 : 0
                    spacing: 3

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Ngôn ngữ đích")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: AppController.batchTargetLanguageLabel
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            Layout.fillWidth: true
                            text: AppController.isBatchRunning ? qsTr("Đang xử lý hàng đợi") : qsTr("Tiến độ tổng")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                        }

                        Text {
                            text: qsTr("%1%").arg(AppController.batchProgress)
                            color: AppController.batchProgress >= 100 ? Theme.success : Theme.interactive
                            font.pixelSize: Theme.h3
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                        }
                    }

                    AppProgressBar {
                        Layout.fillWidth: true
                        value: AppController.batchProgress
                    }
                }
            }
        }
    }
}
