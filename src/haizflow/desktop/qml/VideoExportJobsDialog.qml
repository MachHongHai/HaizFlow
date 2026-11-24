pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property var controller: AppController
    property string reviewVideoId: ""
    title: qsTr("Xuất video")
    preferredWidth: 640
    maximumHeight: 650
    property var videoIds: []
    readonly property var scopedJobs: (controller.videoExportJobs || []).filter(job => videoIds.length === 0 || videoIds.includes(job.videoId))
    readonly property var jobSummary: ({count: scopedJobs.length,
        done: scopedJobs.filter(job => job.status === "done").length,
        failed: scopedJobs.filter(job => job.status === "failed").length,
        cancelled: scopedJobs.filter(job => job.status === "cancelled").length,
        unfinished: scopedJobs.filter(job => !["done", "failed", "cancelled"].includes(job.status)).length,
        waiting: scopedJobs.some(job => ["paused", "awaiting_review"].includes(job.status))})
    readonly property bool scopeBusy: scopedJobs.some(job => ["preparing", "pending", "rendering", "exporting"].includes(job.status))

    function openForVideos(ids) {
        if (!(controller.videoExportJobs || []).some(job => ids.includes(job.videoId)))
            return;
        reviewVideoId = "";
        videoIds = ids.slice();
        controller.setVideoExportDialogScope(videoIds);
        open();
    }

    Text {
        Layout.fillWidth: true
        visible: root.jobSummary.count > 1
        text: qsTr("%1 thành công · %2 lỗi · %3 đã hủy · %4 chưa xong")
            .arg(root.jobSummary.done).arg(root.jobSummary.failed).arg(root.jobSummary.cancelled).arg(root.jobSummary.unfinished)
        color: Theme.text
        font.pixelSize: TypeScale.control
        wrapMode: Text.WordWrap
    }

    ListView {
        id: jobsView
        Layout.fillWidth: true
        Layout.minimumHeight: 0
        Layout.preferredHeight: Math.min(420, contentHeight)
        clip: true
        reuseItems: true
        spacing: Theme.space16
        model: root.controller.videoExportDialogModel || root.scopedJobs
        ScrollBar.vertical: ScrollBar {}
        delegate: ColumnLayout {
            id: exportJob
            required property var model
            readonly property var modelData: model.job || model.modelData
            readonly property string taskState: TaskPresentation.exportState(modelData.status, modelData.queued)
            readonly property bool measured: taskState === "exporting"
                || (taskState === "rendering" && Boolean(modelData.progressMeasured))
            readonly property int progressPercent: Math.max(0, Math.min(100, Number(modelData.progress || 0)))
            width: jobsView.width - Theme.space16
            spacing: Theme.space8
            Text {
                Layout.fillWidth: true
                text: exportJob.modelData.name
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
            }
            Text {
                objectName: "exportJobStatus"
                Layout.fillWidth: true
                text: exportJob.taskState === "done" ? qsTr("Đã xuất thành công") : exportJob.measured
                    ? qsTr("%1 · %2%").arg(TaskPresentation.label(exportJob.taskState)).arg(exportJob.progressPercent)
                    : TaskPresentation.label(exportJob.taskState)
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: TaskPresentation.foreground(exportJob.taskState)
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
            }
            AppProgressBar {
                objectName: "exportJobProgress"
                Layout.fillWidth: true
                visible: ["exporting", "rendering"].includes(exportJob.taskState)
                    || (exportJob.taskState === "preparing" && !exportJob.modelData.queued)
                value: exportJob.progressPercent
                indeterminate: !exportJob.measured
                active: visible
            }
            UserErrorNotice {
                Layout.fillWidth: true
                title: qsTr("Xuất video chưa hoàn tất")
                details: exportJob.modelData.status === "failed" ? String(exportJob.modelData.error || qsTr("Không thể xuất video.")) : ""
            }
            Text {
                Layout.fillWidth: true
                text: exportJob.modelData.path
                textFormat: Text.PlainText
                color: Theme.textSubtle
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                wrapMode: Text.WrapAnywhere
            }
            StudioButton {
                visible: exportJob.modelData.status === "done"
                text: qsTr("Mở thư mục")
                variant: "secondary"
                onClicked: root.controller.openExportDestinationFolder(exportJob.modelData.path)
            }
            StudioButton {
                objectName: "exportJobNextAction"
                visible: ["paused", "awaiting_review", "failed", "cancelled"].includes(exportJob.taskState)
                enabled: !["failed", "cancelled"].includes(exportJob.taskState) || !root.controller.videoExportBusy
                text: exportJob.taskState === "paused" ? qsTr("Tiếp tục")
                    : exportJob.taskState === "awaiting_review" ? qsTr("Duyệt phụ đề") : qsTr("Thử lại")
                onClicked: {
                    const id = exportJob.modelData.videoId;
                    const state = exportJob.taskState;
                    if (["failed", "cancelled"].includes(state)) {
                        root.controller.retryVideoExportsFor([id]);
                    } else if (root.controller.continueVideoExportJob(id, state) && state === "awaiting_review") {
                        root.reviewVideoId = id;
                        root.close();
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                visible: root.controller.videoExportBusy && ["failed", "cancelled"].includes(exportJob.taskState)
                text: qsTr("Chờ lượt xuất hiện tại kết thúc để thử lại.")
                wrapMode: Text.WordWrap
                color: Theme.textMuted
                font.pixelSize: TypeScale.metadata
            }
        }
    }
    footerActions: [
        StudioButton {
            visible: root.scopeBusy || root.jobSummary.waiting
            text: qsTr("Hủy xuất")
            variant: "ghost"
            onClicked: root.controller.cancelVideoExportsFor(root.videoIds)
        },
        StudioButton {
            visible: !root.controller.videoExportBusy && root.jobSummary.failed + root.jobSummary.cancelled > 1
            text: qsTr("Thử lại các tệp lỗi hoặc đã hủy")
            variant: "secondary"
            onClicked: root.controller.retryVideoExportsFor(root.videoIds)
        },
        StudioButton {
            text: qsTr("Đóng")
            variant: "primary"
            onClicked: root.close()
        }
    ]
}
