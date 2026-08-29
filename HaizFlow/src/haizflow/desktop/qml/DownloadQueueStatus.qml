import QtQuick
import QtQuick.Layouts
import "."

AppSurface {
    id: root

    required property var downloader
    visible: downloader.queueStatus.length > 0 || downloader.status.length > 0
    padding: Theme.space12
    spacing: Theme.space8

    SectionHeader {
        Layout.fillWidth: true
        title: qsTr("Hàng đợi tải xuống")
    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.downloader.queueStatus.length > 0

        Text {
            Layout.fillWidth: true
            text: root.downloader.queueStatus
            color: Theme.textMuted
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        AppButton {
            visible: root.downloader.queueCount > 0
            text: qsTr("Xóa hàng đợi")
            compact: true
            tone: "secondary"
            onClicked: root.downloader.clearQueuedDownloads()
        }
    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.downloader.status.length > 0

        Text {
            Layout.fillWidth: true
            text: root.downloader.status
            color: root.downloader.busy ? Theme.textMuted : Theme.text
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        AppButton {
            visible: root.downloader.busy
            text: qsTr("Hủy tải")
            compact: true
            tone: "danger"
            onClicked: root.downloader.cancel()
        }
    }

    AppProgressBar {
        Layout.fillWidth: true
        visible: root.downloader.busy && !root.downloader.channelBusy
        value: root.downloader.progress
    }
}
