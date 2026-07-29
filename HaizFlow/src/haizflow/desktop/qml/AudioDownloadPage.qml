import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    required property var downloader
    property string sourceMode: "link"
    readonly property bool fromLink: root.sourceMode === "link"

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space16

        PageHeader {
            Layout.fillWidth: true
            title: I18n.t("Download or extract audio")
            subtitle: I18n.t("Save audio from a link or extract the audio track from a local media file")
        }

        ScrollView {
            id: audioScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: audioScroll.availableWidth
                spacing: Theme.space16

                Panel {
                    Layout.fillWidth: true
                    title: I18n.t("Audio source")
                    subtitle: I18n.t("Choose a source, then select the destination folder")

                    SegmentedControl {
                        id: audioSource
                        Layout.fillWidth: true
                        currentValue: root.sourceMode
                        options: [{ "label": I18n.t("From link"), "value": "link" }, { "label": I18n.t("From file"), "value": "file" }]
                        onActivated: function(value) {
                            root.sourceMode = value
                        }
                    }

                    TextField {
                        id: audioLink
                        Layout.fillWidth: true
                        visible: root.fromLink
                        implicitHeight: 44
                        placeholderText: I18n.t("Paste a video link")
                        selectByMouse: true
                        activeFocusOnTab: true
                        Accessible.name: I18n.t("Video link")
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: Theme.input
                            border.width: audioLink.activeFocus ? 2 : 1
                            border.color: audioLink.activeFocus ? Theme.focus : Theme.outline
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: !root.fromLink
                        Text {
                            Layout.fillWidth: true
                            text: root.downloader.audioSource.length > 0 ? root.downloader.audioSource : I18n.t("No media file selected")
                            color: root.downloader.audioSource.length > 0 ? Theme.text : Theme.textMuted
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                        }
                        AppButton { text: I18n.t("Choose file"); onClicked: root.downloader.chooseAudioSource() }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: root.downloader.audioOutputDirectory.length > 0 ? root.downloader.audioOutputDirectory : I18n.t("No audio folder selected")
                            color: root.downloader.audioOutputDirectory.length > 0 ? Theme.text : Theme.textMuted
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                        }
                        AppButton {
                            visible: !root.downloader.outputManaged
                            text: I18n.t("Choose folder")
                            onClicked: root.downloader.chooseAudioOutputDirectory()
                        }
                    }

                    AppButton {
                        Layout.fillWidth: true
                        text: root.fromLink ? I18n.t("Download audio") : I18n.t("Extract audio")
                        tone: "primary"
                        enabled: root.downloader.audioOutputDirectory.length > 0
                            && (root.fromLink ? audioLink.text.trim().length > 0 : root.downloader.audioSource.length > 0)
                        onClicked: root.fromLink ? root.downloader.downloadAudio(audioLink.text.trim()) : root.downloader.extractAudio()
                    }
                }

                DownloadQueueStatus { Layout.fillWidth: true; downloader: root.downloader }
                Item { Layout.fillHeight: true }
            }
        }
    }
}
