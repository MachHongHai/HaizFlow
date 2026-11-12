pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property var controller: AppController
    title: qsTr("Xuất video")
    preferredWidth: 640
    maximumHeight: 650
    property var videoIds: []
    readonly property var scopedJobs: (controller.videoExportJobs || []).filter(job => videoIds.length === 0 || videoIds.includes(job.videoId))
    readonly property var jobSummary: ({count: scopedJobs.length,
        done: scopedJobs.filter(job => job.status === "done").length,
        failed: scopedJobs.filter(job => job.status === "failed").length,
        cancelled: scopedJobs.filter(job => job.status === "cancelled").length,
        waiting: scopedJobs.some(job => ["paused", "awaiting_review"].includes(job.status))})
    readonly property bool scopeBusy: scopedJobs.some(job => ["preparing", "pending", "rendering", "exporting"].includes(job.status))

    function openForVideos(ids) {
        if (!(controller.videoExportJobs || []).some(job => ids.includes(job.videoId)))
            return;
        videoIds = ids.slice();
        controller.setVideoExportDialogScope(videoIds);
        open();
    }

    Text {
        Layout.fillWidth: true
        visible: root.jobSummary.count > 1
        text: qsTr("%1 thành công · %2 lỗi · %3 đã hủy").arg(root.jobSummary.done).arg(root.jobSummary.failed).arg(root.jobSummary.cancelled)
        color: Theme.text
        font.pixelSize: TypeScale.control
        wrapMode: Text.WordWrap
    }

    ListView {
        id: jobsView
        Layout.fillWidth: true
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
            readonly property bool measured: modelData.status === "exporting" || Boolean(modelData.progressMeasured)
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
                Layout.fillWidth: true
                text: exportJob.modelData.status === "preparing" ? qsTr("Đang chuẩn bị") : exportJob.modelData.status === "rendering" ? ((exportJob.modelData.process ? qsTr("Đang xử lý và dựng video") : qsTr("Đang dựng video")) + (exportJob.measured ? " · " + exportJob.progressPercent + "%" : "")) : exportJob.modelData.status === "exporting" ? qsTr("Đang lưu · %1%").arg(exportJob.modelData.progress) : exportJob.modelData.status === "done" ? qsTr("Đã xuất thành công") : exportJob.modelData.status === "pending" ? qsTr("Đang chờ") : exportJob.modelData.status === "cancelled" ? qsTr("Đã hủy xuất") : qsTr("Xuất chưa hoàn tất")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: exportJob.modelData.status === "failed" ? Theme.danger : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
            }
            AppProgressBar {
                objectName: "exportJobProgress"
                Layout.fillWidth: true
                visible: exportJob.modelData.status === "preparing" || exportJob.modelData.status === "exporting" || exportJob.modelData.status === "rendering"
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
            visible: !root.controller.videoExportBusy && (root.jobSummary.failed > 0 || root.jobSummary.cancelled > 0)
            text: qsTr("Thử lại tệp lỗi")
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
