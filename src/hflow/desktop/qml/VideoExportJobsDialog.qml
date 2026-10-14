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

    Text {
        Layout.fillWidth: true
        visible: root.controller.videoExportJobs.length > 1
        text: qsTr("%1 thành công · %2 lỗi · %3 đã hủy")
            .arg(root.controller.videoExportJobs.filter(item => item.status === "done").length)
            .arg(root.controller.videoExportJobs.filter(item => item.status === "failed").length)
            .arg(root.controller.videoExportJobs.filter(item => item.status === "cancelled").length)
        color: Theme.text
        font.pixelSize: TypeScale.control
        wrapMode: Text.WordWrap
    }

    ScrollView {
        id: jobsView
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(420, jobsColumn.implicitHeight)
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            id: jobsColumn
            width: jobsView.availableWidth
            spacing: Theme.space16
            Repeater {
                model: root.controller.videoExportJobs
                delegate: ColumnLayout {
                    id: exportJob
                    required property var modelData
                    readonly property bool measured: modelData.status === "exporting"
                        || Boolean(modelData.progressMeasured)
                    readonly property int progressPercent: Math.max(0, Math.min(100,
                        Number(modelData.progress || 0)))
                    Layout.fillWidth: true
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
                        text: exportJob.modelData.status === "rendering"
                            ? ((exportJob.modelData.process ? qsTr("Đang xử lý và dựng video") : qsTr("Đang dựng video"))
                                + (exportJob.measured ? " · " + exportJob.progressPercent + "%" : ""))
                            : exportJob.modelData.status === "exporting" ? qsTr("Đang lưu · %1%").arg(exportJob.modelData.progress)
                            : exportJob.modelData.status === "done" ? qsTr("Đã xuất thành công")
                            : exportJob.modelData.status === "pending" ? qsTr("Đang chờ") : exportJob.modelData.error
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: exportJob.modelData.status === "failed" ? Theme.danger : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                    }
                    AppProgressBar {
                        objectName: "exportJobProgress"
                        Layout.fillWidth: true
                        visible: exportJob.modelData.status === "exporting" || exportJob.modelData.status === "rendering"
                        value: exportJob.progressPercent
                        indeterminate: !exportJob.measured
                        active: visible
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
        }
    }
    footerActions: [
        StudioButton {
            visible: root.controller.videoExportBusy || root.controller.videoExportJobs.some(item => item.status === "paused" || item.status === "awaiting_review")
            text: qsTr("Hủy xuất")
            variant: "ghost"
            onClicked: root.controller.cancelVideoExport()
        },
        StudioButton {
            visible: !root.controller.videoExportBusy && root.controller.videoExportJobs.some(item => item.status === "failed" || item.status === "cancelled")
            text: qsTr("Thử lại tệp lỗi")
            variant: "secondary"
            onClicked: root.controller.retryVideoExports()
        },
        StudioButton { text: qsTr("Đóng"); variant: "primary"; onClicked: root.close() }
    ]
}
