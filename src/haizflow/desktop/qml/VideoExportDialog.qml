pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property var controller: AppController
    property var configuration: ({})
    property string destination: ""
    property bool destinationExists: false
    property bool processBeforeExport: false
    property bool batchMode: false
    readonly property bool targetExportActive: (root.controller.videoExportJobs || []).some(job =>
        job.videoId === (root.configuration.videoId || "") &&
        (["pending", "rendering", "exporting"].indexOf(job.status) >= 0
         || root.controller.videoExportBusy && ["paused", "awaiting_review"].indexOf(job.status) >= 0))
    title: batchMode ? qsTr("Xử lý và xuất hàng loạt") : processBeforeExport ? qsTr("Xử lý và xuất video") : qsTr("Xuất video")
    subtitle: ""
    preferredWidth: batchMode ? 680 : 600
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
        batchScope.searchText = "";
        quality.currentIndex = Math.max(0, (configuration.presets || []).findIndex(item => item.value === configuration.preset));
        open();
    }
    function matchesBatchRequest(request) {
        return request && root.batchMode && root.visible
            && request.projectKey === root.configuration.projectKey
            && request.destination === root.destination && request.preset === quality.currentValue
            && request.process === root.processBeforeExport
            && request.videoIds.length === batchScope.targetIds.length
            && request.videoIds.every((id, index) => id === batchScope.targetIds[index]);
    }
    function startBatchRequest(request, conflicts) {
        if (root.matchesBatchRequest(request) && root.controller.processBatchTo(request.projectKey,
                request.videoIds, request.preset, request.destination, Object.keys(conflicts).length > 0,
                request.process, conflicts)) {
            root.close();
        }
    }
    DialogScrollBody {
        maximumBodyHeight: root.availableBodyHeight
        spacing: Theme.space12

        BatchVideoScope {
            id: batchScope
            visible: root.batchMode
            Layout.fillWidth: true
            videos: root.configuration.videos || []
        }
        AppDialog {
            id: replaceBatchFiles
            objectName: "replaceBatchExportFiles"
            property var request: null
            property var conflicts: ({})
            onClosed: { request = null; conflicts = ({}); }
            title: qsTr("Thay thế tệp đã có?")
            Text {
                Layout.fillWidth: true
                text: qsTr("Có %1 tệp trùng tên trong số video đã chọn. Bạn muốn thay thế khi xuất?")
                    .arg(Object.keys(replaceBatchFiles.conflicts).length)
                color: Theme.text
                font.pixelSize: TypeScale.control
                wrapMode: Text.Wrap
            }
            footerActions: [
                StudioButton { text: qsTr("Hủy"); onClicked: replaceBatchFiles.close() },
                StudioButton {
                    objectName: "confirmBatchOverwrite"
                    text: qsTr("Thay thế")
                    variant: "primary"
                    onClicked: {
                        const request = replaceBatchFiles.request;
                        const conflicts = replaceBatchFiles.conflicts;
                        replaceBatchFiles.close();
                        root.startBatchRequest(request, conflicts);
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
                    objectName: "chooseExportDestination"
                    text: qsTr("Chọn…")
                    iconName: "folder"
                    onClicked: {
                        if (root.batchMode) {
                            const projectKey = root.configuration.projectKey;
                            const folder = root.controller.chooseBatchExportFolder();
                            if (folder.length === 0 || projectKey !== root.configuration.projectKey)
                                return;
                            root.destination = folder;
                            return;
                        }
                        const path = root.controller.chooseVideoExportDestination(root.configuration.videoId);
                        if (path.length > 0) {
                            root.destination = path;
                            root.destinationExists = root.controller.exportDestinationExists(path);
                        }
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
                if (context.batch) {
                    if (!root.matchesBatchRequest(context))
                        return;
                    const conflicts = root.controller.batchExportConflicts(context.projectKey,
                        context.videoIds, context.destination);
                    if (Object.keys(conflicts).length > 0) {
                        replaceBatchFiles.request = context;
                        replaceBatchFiles.conflicts = conflicts;
                        replaceBatchFiles.open();
                    } else {
                        root.startBatchRequest(context, conflicts);
                    }
                    return;
                }
                const started = context.process
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
