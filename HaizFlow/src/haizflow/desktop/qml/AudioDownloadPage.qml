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

        ScrollView {
            id: audioScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: audioScroll.availableWidth
                spacing: Theme.space16

                AppSurface {
                    Layout.fillWidth: true
                    padding: Theme.space16

                    SectionHeader {
                        Layout.fillWidth: true
                        title: qsTr("Nguồn âm thanh")
                    }

                    SegmentedControl {
                        id: audioSource
                        Layout.fillWidth: true
                        currentValue: root.sourceMode
                        options: [{ "label": qsTr("Liên kết"), "value": "link" }, { "label": qsTr("Tệp"), "value": "file" }]
                        onActivated: function(value) {
                            root.sourceMode = value
                        }
                    }

                    AppTextField {
                        id: audioLink
                        Layout.fillWidth: true
                        visible: root.fromLink
                        placeholderText: qsTr("Dán liên kết video")
                        selectByMouse: true
                        accessibleName: qsTr("Liên kết video")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: !root.fromLink
                        Text {
                            Layout.fillWidth: true
                            text: root.downloader.audioSource.length > 0 ? root.downloader.audioSource : qsTr("Chưa chọn tệp")
                            color: root.downloader.audioSource.length > 0 ? Theme.text : Theme.textMuted
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                        }
                        AppButton { text: qsTr("Chọn tệp"); compact: true; onClicked: root.downloader.chooseAudioSource() }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: root.downloader.audioOutputDirectory.length > 0 ? root.downloader.audioOutputDirectory : qsTr("Chưa chọn thư mục")
                            color: root.downloader.audioOutputDirectory.length > 0 ? Theme.text : Theme.textMuted
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                        }
                        AppButton {
                            visible: !root.downloader.outputManaged
                            text: qsTr("Chọn thư mục")
                            compact: true
                            onClicked: root.downloader.chooseAudioOutputDirectory()
                        }
                    }

                    AppButton {
                        Layout.fillWidth: true
                        text: root.fromLink ? qsTr("Tải âm thanh") : qsTr("Tách âm thanh")
                        tone: "primary"
                        enabled: root.downloader.audioOutputDirectory.length > 0
                            && (root.fromLink ? audioLink.text.trim().length > 0 : root.downloader.audioSource.length > 0)
                        onClicked: root.fromLink ? root.downloader.downloadAudio(audioLink.text.trim()) : root.downloader.extractAudio()
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
