pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    required property var downloader
    property string sourceMode: String(downloader.workspaceState.audioMode || "link")
    readonly property bool fromLink: root.sourceMode === "link"
    function restoreAudioUrl() {
        const value = String(root.downloader.workspaceState.audioUrl || "");
        if (audioLink.text !== value)
            audioLink.text = value;
    }
    Component.onCompleted: restoreAudioUrl()

    Connections {
        target: root.downloader
        function onWorkspaceChanged() {
            root.sourceMode = String(root.downloader.workspaceState.audioMode || "link");
            root.restoreAudioUrl();
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
                        enabled: !root.downloader.audioPreviewBusy
                        onTextEdited: {
                            root.downloader.saveWorkspaceState({audioUrl: text});
                            root.downloader.clearAudioPreview();
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: root.fromLink
                        StudioButton {
                            objectName: "audioInspectButton"
                            text: qsTr("Kiểm tra")
                            variant: "secondary"
                            enabled: audioLink.text.trim().length > 0 && !root.downloader.audioPreviewBusy
                                && douyinAction.permitsRequest
                            onClicked: root.downloader.inspectAudio(audioLink.text.trim())
                        }
                        StudioButton {
                            text: qsTr("Hủy")
                            variant: "danger"
                            visible: root.downloader.audioPreviewBusy
                            onClicked: root.downloader.cancelAudioPreview()
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: root.downloader.audioPreview.status.length > 0
                            text: root.downloader.audioPreviewReady ? qsTr("Sẵn sàng tải âm thanh")
                                : I18n.runtimeStatus(root.downloader.audioPreview.status)
                            color: root.downloader.audioPreviewReady ? Theme.success : Theme.textMuted
                            wrapMode: Text.WordWrap
                            textFormat: Text.PlainText
                        }
                    }

                    DownloadLinkPreview {
                        objectName: "audioLinkPreview"
                        Layout.fillWidth: true
                        Layout.preferredHeight: implicitHeight
                        visible: root.fromLink && root.downloader.audioPreviewReady
                        title: root.downloader.audioPreview.title
                        platform: root.downloader.audioPreview.platform
                        uploader: root.downloader.audioPreview.uploader
                        duration: root.downloader.audioPreview.duration
                        thumbnail: root.downloader.audioPreview.thumbnailSource
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
                            || root.downloader.audioPreviewBusy
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        StudioButton {
                            objectName: "audioDownloadButton"
                            text: root.fromLink ? qsTr("Tải âm thanh") : qsTr("Tách âm thanh")
                            variant: "primary"
                            enabled: root.downloader.audioOutputDirectory.length > 0
                                && (root.fromLink ? root.downloader.audioPreviewReady : root.downloader.audioSource.length > 0)
                                && douyinAction.permitsRequest
                            onClicked: root.fromLink ? root.downloader.downloadAudio(root.downloader.audioPreview.url) : root.downloader.extractAudio()
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
