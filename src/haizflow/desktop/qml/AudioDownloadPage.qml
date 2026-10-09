import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    required property var downloader
    property string sourceMode: String(downloader.workspaceState.audioMode || "link")
    readonly property bool fromLink: root.sourceMode === "link"

    Connections {
        target: root.downloader
        function onWorkspaceChanged() {
            root.sourceMode = String(root.downloader.workspaceState.audioMode || "link");
            audioLink.text = String(root.downloader.workspaceState.audioUrl || "");
        }
    }

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
                        Layout.preferredWidth: 248
                        currentValue: root.sourceMode
                        options: [{ "label": qsTr("Liên kết"), "value": "link" }, { "label": qsTr("Tệp"), "value": "file" }]
                        onActivated: function(value) {
                            root.sourceMode = value
                            root.downloader.saveWorkspaceState({audioMode: value})
                        }
                    }

                    AppTextField {
                        id: audioLink
                        Layout.fillWidth: true
                        visible: root.fromLink
                        placeholderText: qsTr("Dán liên kết video")
                        selectByMouse: true
                        accessibleName: qsTr("Liên kết video")
                        text: String(root.downloader.workspaceState.audioUrl || "")
                        onTextEdited: {
                            root.downloader.clearDownloadFeedback();
                            root.downloader.saveWorkspaceState({audioUrl: text});
                        }
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
                        StudioButton { text: qsTr("Chọn tệp"); onClicked: root.downloader.chooseAudioSource() }
                    }

                    DownloadDestinationRow {
                        Layout.fillWidth: true
                        directory: root.downloader.audioOutputDirectory
                        managed: root.downloader.outputManaged
                        onChooseRequested: root.downloader.chooseAudioOutputDirectory()
                    }

                    DouyinSessionAction {
                        id: douyinAction
                        Layout.fillWidth: true
                        url: root.fromLink ? audioLink.text : ""
                        visible: root.fromLink && requiresSession
                        operationBusy: root.downloader.hasWork || root.downloader.videoPreviewBusy
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        StudioButton {
                            text: root.fromLink ? qsTr("Tải âm thanh") : qsTr("Tách âm thanh")
                            variant: "primary"
                            enabled: root.downloader.audioOutputDirectory.length > 0
                                && (root.fromLink ? audioLink.text.trim().length > 0 : root.downloader.audioSource.length > 0)
                                && douyinAction.permitsRequest
                            onClicked: root.fromLink ? root.downloader.downloadAudio(audioLink.text.trim()) : root.downloader.extractAudio()
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
