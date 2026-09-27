import QtQuick
import QtQuick.Layouts
import "."

AppSurface {
    id: root

    required property var downloader
    readonly property bool waitingForBytes: downloader.busy && downloader.progress <= 0
    readonly property bool finalizing: downloader.busy && downloader.progress >= 99
    readonly property bool cancelled: /cancelled|canceled|đã hủy/i.test(downloader.status)
    readonly property bool failed: !downloader.busy && downloader.state === "error" && !root.cancelled
    visible: downloader.queueStatus.length > 0 || downloader.status.length > 0
    padding: Theme.space12
    spacing: Theme.space8

    SectionHeader {
        Layout.fillWidth: true
        title: qsTr("Hàng đợi tải xuống")
    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.downloader.queueCount > 0

        Text {
            Layout.fillWidth: true
            text: root.downloader.busy
                ? qsTr("Đang tải · %1 tác vụ tiếp theo").arg(root.downloader.queueCount)
                : qsTr("%1 tác vụ đang chờ").arg(root.downloader.queueCount)
            color: Theme.textMuted
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        StudioButton {
            visible: root.downloader.queueCount > 0
            text: qsTr("Xóa hàng đợi")
            variant: "secondary"
            onClicked: root.downloader.clearQueuedDownloads()
        }
    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.downloader.status.length > 0

        Text {
            Layout.fillWidth: true
            text: root.downloader.busy
                ? root.finalizing ? qsTr("Đang hoàn thiện tệp")
                    : root.waitingForBytes ? qsTr("Đang chuẩn bị tải")
                    : qsTr("Đang tải · %1%").arg(root.downloader.progress)
                : root.failed ? qsTr("Không tải được · Xem chi tiết lỗi")
                : root.cancelled ? qsTr("Đã hủy tải xuống")
                : I18n.downloadStatus(root.downloader.status)
            color: root.failed ? Theme.danger
                : root.downloader.busy ? Theme.textMuted : Theme.text
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        StudioButton {
            visible: root.downloader.busy
            text: qsTr("Hủy tải")
            variant: "danger"
            onClicked: root.downloader.cancel()
        }
        StudioIconButton {
            visible: root.failed
            iconName: "info"
            toolTipText: qsTr("Xem chi tiết lỗi")
            onClicked: AppController.showAppAlert(qsTr("Lỗi tải xuống"), root.downloader.status, "warning")
        }
    }

    AppProgressBar {
        Layout.fillWidth: true
        visible: root.downloader.busy && !root.downloader.channelBusy
        value: root.downloader.progress
        indeterminate: root.waitingForBytes || root.finalizing
        active: root.downloader.busy
    }
}
