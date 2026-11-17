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
    readonly property bool narrow: width < 680
    property var settingOverrides: []
    property var results: ({})
    property string removalVideoId: ""
    property string removalProjectKey: ""
    property bool removingVideo: false
    readonly property bool preparingBatch: (AppController.videoExportJobs || []).some(job =>
        job.status === "preparing" && (AppController.videoExportScope || []).includes(job.videoId))
    readonly property string queueState: AppController.isBatchPausing ? qsTr("Đang tạm dừng")
        : AppController.isBatchRunning ? qsTr("Đang xử lý")
        : AppController.batchPausedCount > 0 ? qsTr("Đã tạm dừng")
        : AppController.batchCount > 0 && (results.succeeded || 0) === AppController.batchCount
            ? qsTr("Đã hoàn tất") : qsTr("Sẵn sàng xử lý")

    function refreshOverrides() {
        settingOverrides = AppController.batchSettingOverrides();
        results = AppController.batchResults();
    }
    Component.onCompleted: refreshOverrides()
    Connections {
        target: AppController
        function onBatchChanged() {
            root.refreshOverrides();
            if (root.removingVideo && !AppController.batchVideoRemovalPending(root.removalVideoId)) {
                root.removingVideo = false;
                removeVideoDialog.close();
            }
        }
        function onBatchResultsChanged() { root.results = AppController.batchResults(); }
    }

    function importDrop(drop) {
        root.dropActive = false;
        if (!drop.urls || drop.urls.length === 0)
            return;
        const paths = [];
        for (let index = 0; index < drop.urls.length; ++index)
            paths.push(String(drop.urls[index]));
        AppController.importBatchVideos(paths);
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UiMetrics.pageMargin
        spacing: root.compactHeight ? Theme.space12 : Theme.space20

        PageHeader {
            Layout.fillWidth: true
            title: AppController.projectName || qsTr("Dự án hàng loạt")
            subtitle: qsTr("Dự án hàng loạt · %1").arg(AppController.batchTargetLanguageLabel)
            ProjectHeaderActions {
                projectFolderEnabled: AppController.hasOpenProject
                deleteEnabled: AppController.hasOpenProject
                onProjectFolderRequested: AppController.openProjectFolder()
                onDeleteRequested: AppController.deleteCurrentBatch()
            }
        }

        GridLayout {
            id: queueToolbar
            objectName: "batchQueueToolbar"
            Layout.fillWidth: true
            columns: root.narrow ? 1 : 2
            columnSpacing: Theme.space16
            rowSpacing: Theme.space12
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                Text {
                    text: qsTr("Hàng đợi xử lý")
                    color: Theme.text
                    font.pixelSize: TypeScale.section
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
                Rectangle {
                    implicitWidth: countLabel.implicitWidth + Theme.space16
                    implicitHeight: 24
                    radius: Theme.radiusSmall
                    color: Theme.surfaceMuted
                    Text {
                        id: countLabel
                        anchors.centerIn: parent
                        text: String(AppController.batchCount)
                        color: Theme.textMuted
                        font.pixelSize: TypeScale.metadata
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                }
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    visible: AppController.mediaImportBusy
                    text: qsTr("Đang thêm %1 / %2…").arg(AppController.mediaImportCompleted).arg(AppController.mediaImportTotal)
                    color: Theme.textMuted
                    font.pixelSize: TypeScale.label
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
                Item {
                    Layout.fillWidth: true
                    visible: !AppController.mediaImportBusy
                }
            }
            RowLayout {
                Layout.alignment: root.narrow ? Qt.AlignLeft : Qt.AlignRight
                spacing: Theme.space8
                MediaSourceImportButton {
                    objectName: "batchImportButton"
                    text: qsTr("Thêm video")
                    variant: AppController.batchCount === 0 ? "primary" : "secondary"
                    enabled: !AppController.mediaImportBusy
                    onFileRequested: AppController.browseBatchVideos()
                    onLinkRequested: root.requestUrlImport()
                    onDownloadProjectRequested: root.requestDownloadProjectImport()
                }
                StudioButton {
                    objectName: "batchSettingsButton"
                    text: qsTr("Cài đặt hàng loạt")
                    iconGlyph: "\uE713"
                    variant: "secondary"
                    enabled: !AppController.isBatchRunning && !root.preparingBatch
                    onClicked: root.requestBatchSettings()
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.settingOverrides.length > 0
            spacing: Theme.space8
            AppIcon {
                Layout.preferredWidth: Theme.icon
                Layout.preferredHeight: Theme.icon
                glyph: IconCatalog.glyph("info")
                iconColor: Theme.warning
                Accessible.ignored: true
            }
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: qsTr("%1 video dùng cài đặt riêng").arg(root.settingOverrides.length)
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                font.pixelSize: TypeScale.label
                color: Theme.textMuted
            }
            StudioButton {
                text: qsTr("Xem chi tiết")
                variant: "ghost"
                onClicked: overrideDetailsLoader.invoke("open", [])
            }
        }

        Rectangle {
            id: queuePanel
            objectName: "batchQueuePanel"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 160
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.divider
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
                onDropped: function (drop) { root.importDrop(drop); }
            }
            GridView {
                id: queueList
                objectName: "batchQueueList"
                // Virtualized gallery: fill each row without oversized cards or dead columns.
                readonly property int columnCount: Math.max(1, Math.floor(width / (232 + Theme.space16)))
                readonly property real cellContentWidth: Math.floor(width / columnCount)
                readonly property real cardWidth: Math.max(1, cellContentWidth - Theme.space16)
                readonly property real cardHeight: Math.round(cardWidth * 0.56 + 120)
                anchors.fill: parent
                anchors.margins: Theme.space16
                anchors.rightMargin: 0
                clip: true
                model: AppController.batchVideoModel
                reuseItems: true
                cellWidth: cellContentWidth
                cellHeight: cardHeight + Theme.space16
                delegate: BatchVideoCard {
                    required property string videoId
                    customSettings: root.settingOverrides.some(item => item.videoId === videoId)
                    removalEnabled: !AppController.isBatchRunning && !AppController.videoExportBusy
                    onRemovalRequested: {
                        root.removalVideoId = videoId;
                        root.removalProjectKey = AppController.projectKey;
                        removeVideoDialog.open();
                    }
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
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(420, parent.width - Theme.space32)
                spacing: Theme.space12
                visible: AppController.batchCount === 0
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    implicitWidth: 56
                    implicitHeight: 56
                    radius: Theme.radius
                    color: Theme.surfaceMuted
                    AppIcon {
                        anchors.centerIn: parent
                        width: 24
                        height: 24
                        iconSize: 24
                        glyph: IconCatalog.glyph("batch")
                        iconColor: Theme.textMuted
                        Accessible.ignored: true
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Thêm video để bắt đầu")
                    color: Theme.text
                    font.pixelSize: TypeScale.section
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    textFormat: Text.PlainText
                }
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Kéo thả video vào đây hoặc chọn Thêm video ở phía trên.")
                    color: Theme.textMuted
                    font.pixelSize: TypeScale.label
                    horizontalAlignment: Text.AlignHCenter
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }
            }
            Rectangle {
                anchors.fill: parent
                visible: root.dropActive
                radius: Theme.radius
                color: Theme.surfaceElevated
                border.width: 2
                border.color: Theme.interactive
                Text {
                    anchors.centerIn: parent
                    text: qsTr("Thả để thêm video")
                    color: Theme.text
                    font.pixelSize: TypeScale.section
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }
        }

        RowLayout {
            id: batchCommandBar
            objectName: "batchCommandBar"
            visible: AppController.batchCount > 0
            Layout.fillWidth: true
            Layout.minimumHeight: 44
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: root.queueState
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
            Text {
                visible: !root.narrow
                text: (root.results.failed || 0) > 0
                    ? qsTr("%1 / %2 hoàn tất · %3 lỗi").arg(root.results.succeeded || 0).arg(AppController.batchCount).arg(root.results.failed)
                    : qsTr("%1 / %2 hoàn tất").arg(root.results.succeeded || 0).arg(AppController.batchCount)
                color: (root.results.failed || 0) > 0 ? Theme.warning : Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }
            StudioButton {
                objectName: "batchResultDetailsButton"
                text: qsTr("Chi tiết")
                variant: "ghost"
                onClicked: resultDetailsLoader.invoke("open", [])
            }
            RowLayout {
                objectName: "batchRunActions"
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                spacing: Theme.space8
                DeferredActionButton {
                    objectName: "batchResumeButton"
                    visible: !AppController.isBatchRunning && AppController.batchPausedCount > 0
                    readyText: qsTr("Tiếp tục")
                    variant: "secondary"
                    actionEnabled: !AppController.videoExportBusy && !AppController.mediaImportBusy
                    actionContext: ({projectKey: AppController.projectKey})
                    onExecute: context => {
                        if (context && context.projectKey === AppController.projectKey
                                && !AppController.isBatchRunning && AppController.batchPausedCount > 0)
                            AppController.resumeBatch();
                    }
                }
                DeferredActionButton {
                    objectName: "batchProcessButton"
                    visible: !AppController.isBatchRunning
                    readyText: AppController.batchPausedCount > 0 || (root.results.succeeded || 0) > 0
                        || (root.results.failed || 0) > 0 ? qsTr("Xử lý lại") : qsTr("Xử lý")
                    iconGlyph: "\uE768"
                    variant: "primary"
                    Layout.minimumWidth: 112
                    actionEnabled: AppController.batchCount > 0 && !AppController.videoExportBusy && !AppController.mediaImportBusy
                    actionContext: ({projectKey: AppController.projectKey})
                    onExecute: context => {
                        if (context && context.projectKey === AppController.projectKey && !AppController.isBatchRunning)
                            AppController.requestBatchProcessing();
                    }
                }
                StudioButton {
                    objectName: "batchPauseButton"
                    visible: AppController.isBatchRunning
                    text: AppController.isBatchPausing ? qsTr("Đang tạm dừng") : qsTr("Tạm dừng xử lý")
                    iconGlyph: "\uE71A"
                    variant: "secondary"
                    enabled: !AppController.isBatchPausing
                    onClicked: AppController.stopBatch()
                }
            }
        }
    }

    LazyDialogLoader {
        id: overrideDetailsLoader
        sourceComponent: Component {
            BatchDetailsDialog {
                overrides: true
                rows: root.settingOverrides
                onClosed: overrideDetailsLoader.release()
            }
        }
    }
    AppDialog {
        id: removeVideoDialog
        title: qsTr("Xóa video khỏi dự án?")
        dismissible: !root.removingVideo
        Text {
            Layout.fillWidth: true
            text: qsTr("Video và kết quả trong dự án sẽ bị xóa. Tệp nguồn bên ngoài và video đã xuất được giữ lại.")
            wrapMode: Text.Wrap
            font.pixelSize: TypeScale.control
            color: Theme.text
        }
        footerActions: [
            StudioButton { text: qsTr("Hủy"); enabled: !root.removingVideo; onClicked: removeVideoDialog.close() },
            DeferredActionButton {
                readyText: root.removingVideo ? qsTr("Đang xóa…") : qsTr("Xóa video")
                variant: "danger"
                actionEnabled: !root.removingVideo
                actionContext: ({projectKey: root.removalProjectKey, videoId: root.removalVideoId})
                onExecute: context => {
                    if (AppController.removeBatchVideo(context.projectKey, context.videoId))
                        root.removingVideo = true;
                }
            }
        ]
    }
    LazyDialogLoader {
        id: resultDetailsLoader
        sourceComponent: Component {
            BatchDetailsDialog {
                rows: root.results.rows || []
                onClosed: resultDetailsLoader.release()
            }
        }
    }
}
