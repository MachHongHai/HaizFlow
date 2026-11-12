pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import "."

AppDialog {
    id: root
    property var controller: AppController
    property var configuration: ({})
    property string destination: ""
    property bool destinationExists: false
    property bool processBeforeExport: false
    property bool batchMode: false
    property string pendingFolder: ""
    readonly property bool targetExportActive: (root.controller.videoExportJobs || []).some(job =>
        job.videoId === (root.configuration.videoId || "") &&
        (["pending", "rendering", "exporting"].indexOf(job.status) >= 0
         || root.controller.videoExportBusy && ["paused", "awaiting_review"].indexOf(job.status) >= 0))
    title: batchMode ? qsTr("Xử lý và xuất hàng loạt") : processBeforeExport ? qsTr("Xử lý và xuất video") : qsTr("Xuất video")
    subtitle: ""
    preferredWidth: 600
    bodySpacing: Theme.space12

    function openForSelection(processFirst = false) {
        batchMode = false;
        processBeforeExport = processFirst;
        configuration = controller.manualExportSettings();
        exportRange.currentIndex = 0;
        destination = "";
        destinationExists = false;
        quality.currentIndex = Math.max(0, (configuration.presets || []).findIndex(item => item.value === configuration.preset));
        open();
    }
    function openForProcessing() { openForSelection(true); }
    function openForBatch(processFirst = true) {
        batchMode = true;
        processBeforeExport = processFirst;
        configuration = controller.batchExportSettings();
        destination = "";
        destinationExists = false;
        exportRange.currentIndex = 0;
        batchScope.scope = processFirst ? "unfinished" : "all";
        batchScope.selectedIds = [];
        quality.currentIndex = Math.max(0, (configuration.presets || []).findIndex(item => item.value === configuration.preset));
        open();
    }
    BatchVideoScope {
        id: batchScope
        visible: root.batchMode
        Layout.fillWidth: true
        videos: root.configuration.videos || []
    }
    FolderDialog {
        id: batchFolder
        title: qsTr("Chọn thư mục xuất video")
        onAccepted: {
            root.pendingFolder = root.controller.exportFolderPath(selectedFolder);
            if (root.controller.batchExportDestinationExists(root.pendingFolder))
                replaceBatchFiles.open();
            else {
                root.destination = root.pendingFolder;
                root.destinationExists = false;
            }
        }
    }
    AppDialog {
        id: replaceBatchFiles
        title: qsTr("Thay thế tệp đã có?")
        Text {
            Layout.fillWidth: true
            text: qsTr("Thư mục đã có video trùng tên. Thay thế khi xuất?")
            color: Theme.text
            font.pixelSize: TypeScale.control
            wrapMode: Text.Wrap
        }
        footerActions: [
            StudioButton { text: qsTr("Hủy"); onClicked: replaceBatchFiles.close() },
            StudioButton {
                text: qsTr("Thay thế")
                variant: "primary"
                onClicked: {
                    root.destination = root.pendingFolder;
                    root.destinationExists = true;
                    replaceBatchFiles.close();
                }
            }
        ]
    }
    RowLayout {
        Layout.fillWidth: true
        visible: !root.batchMode
        spacing: Theme.space12
        Text {
            text: qsTr("Tên tệp")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
        }
        Text {
            Layout.fillWidth: true
            text: root.destination.length > 0
                ? root.destination.replace(/\\/g, "/").split("/").pop()
                : root.configuration.filename || ""
            textFormat: Text.PlainText
            elide: Text.ElideMiddle
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: Font.Medium
        }
    }
    FormSection {
        Layout.fillWidth: true
        visible: !root.batchMode && !root.processBeforeExport && (root.configuration.segments || []).length > 0
        title: qsTr("Phạm vi xuất")
        StudioComboBox {
            id: exportRange
            objectName: "exportRange"
            Layout.fillWidth: true
            textRole: "label"
            valueRole: "value"
            model: [{value: "", label: qsTr("Toàn bộ video")}].concat((root.configuration.segments || []).map(function(segment, index) {
                function time(ms) {
                    const seconds = Math.floor(ms / 1000);
                    return String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0")
                        + "." + String(ms % 1000).padStart(3, "0");
                }
                return {value: segment.id, label: qsTr("Đoạn %1 · %2 – %3").arg(index + 1).arg(time(segment.startMs)).arg(time(segment.endMs))};
            }))
        }
    }
    FormSection {
        Layout.fillWidth: true
        title: qsTr("Chất lượng video")
        StudioComboBox {
            id: quality
            objectName: "exportQuality"
            Layout.fillWidth: true
            model: root.configuration.presets || []
            textRole: "label"
            valueRole: "value"
        }
        Text {
            Layout.fillWidth: true
            visible: root.batchMode
            text: qsTr("%1 video").arg(batchScope.targetIds.length)
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: !root.processBeforeExport && !root.configuration.ready
            text: qsTr("Video sẽ được dựng khi xuất.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.WordWrap
        }
    }
    FormSection {
        Layout.fillWidth: true
        title: qsTr("Vị trí lưu")
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            AppTextField {
                Layout.fillWidth: true
                readOnly: true
                text: root.destination
                placeholderText: qsTr("Chưa chọn vị trí lưu")
                accessibleName: qsTr("Đường dẫn xuất video")
            }
            StudioButton {
                text: qsTr("Chọn…")
                iconName: "folder"
                onClicked: {
                    if (root.batchMode) {
                        batchFolder.open();
                        return;
                    }
                    const path = root.controller.chooseVideoExportDestination(root.configuration.videoId);
                    if (path.length > 0) {
                        root.destination = path;
                        root.destinationExists = root.batchMode ? root.controller.batchExportDestinationExists(path)
                            : root.controller.exportDestinationExists(path);
                    }
                }
            }
        }
    }
    footerActions: [
        StudioButton { text: qsTr("Hủy"); variant: "ghost"; onClicked: root.close() },
        DeferredActionButton {
            objectName: "confirmVideoExport"
            readyText: root.processBeforeExport ? qsTr("Xử lý và xuất") : qsTr("Xuất")
            variant: "primary"
            actionEnabled: root.destination.length > 0
                && (!root.batchMode || batchScope.targetIds.length > 0)
                && (root.processBeforeExport && !root.batchMode
                    ? !root.targetExportActive : !root.controller.videoExportBusy)
                && (root.batchMode || (!root.controller.isSelectedVideoProcessing
                    && !root.controller.isSelectedVideoQueued))
            actionContext: ({ batch: root.batchMode, process: root.processBeforeExport,
                projectKey: root.configuration.projectKey || "", videoIds: batchScope.targetIds.slice(),
                videoId: root.configuration.videoId || "", preset: quality.currentValue,
                destination: root.destination, overwrite: root.destinationExists, segmentId: exportRange.currentValue || "" })
            onExecute: context => {
                if (!context || context.videoId !== (root.configuration.videoId || "")
                        || context.projectKey !== (root.configuration.projectKey || ""))
                    return;
                const started = context.batch
                    ? root.controller.processBatchTo(context.projectKey, context.videoIds,
                        context.preset, context.destination, context.overwrite, context.process)
                    : context.process
                    ? root.controller.processVideoTo(context.videoId, context.preset, context.destination, context.overwrite)
                    : context.segmentId
                    ? root.controller.exportVideoSegmentTo(context.videoId, context.preset, context.destination, context.overwrite, context.segmentId)
                    : root.controller.exportVideoTo(context.videoId, context.preset, context.destination, context.overwrite);
                if (started)
                    root.close();
            }
        }
    ]
}
