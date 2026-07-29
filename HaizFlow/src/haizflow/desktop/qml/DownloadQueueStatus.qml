import QtQuick
import QtQuick.Layouts
import "."

Panel {
    id: root

    required property var downloader
    visible: downloader.queueStatus.length > 0 || downloader.status.length > 0
    title: I18n.t("Download queue")

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
            text: I18n.t("Clear queue")
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
            text: I18n.t("Cancel download")
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
