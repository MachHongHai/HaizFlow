import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    required property var downloader

    function restoreVideoUrl() {
        const form = root.downloader.workspaceState;
        const value = String(form.videoUrl !== undefined ? form.videoUrl : root.downloader.videoPreviewUrl || "");
        if (videoLink.text !== value)
            videoLink.text = value;
    }

    Component.onCompleted: restoreVideoUrl()

    Connections {
        target: root.downloader
        function onWorkspaceChanged() {
            root.restoreVideoUrl();
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space16

        ScrollView {
            id: videoScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: videoScroll.availableWidth
                spacing: Theme.space16

                AppSurface {
                    Layout.fillWidth: true
                    padding: Theme.space16

                    SectionHeader {
                        Layout.fillWidth: true
                        title: qsTr("Liên kết video")
                    }

                    AppTextField {
                        id: videoLink
                        Layout.fillWidth: true
                        placeholderText: qsTr("Dán liên kết video")
                        selectByMouse: true
                        accessibleName: qsTr("Liên kết video")
                        enabled: !root.downloader.videoPreviewBusy
                        onTextEdited: {
                            const editedUrl = text;
                            root.downloader.saveWorkspaceState({videoUrl: editedUrl});
                            root.downloader.clearVideoPreview();
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        StudioButton {
                            text: qsTr("Kiểm tra")
                            variant: "secondary"
                            enabled: videoLink.text.trim().length > 0 && !root.downloader.videoPreviewBusy
                                && douyinAction.permitsRequest
                            onClicked: root.downloader.inspectVideo(videoLink.text.trim())
                        }
                        StudioButton {
                            visible: root.downloader.videoPreviewBusy
                            text: qsTr("Hủy")
                            variant: "danger"
                            onClicked: root.downloader.cancelVideoPreview()
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: root.downloader.videoPreviewStatus.length > 0
                            text: I18n.runtimeStatus(root.downloader.videoPreviewStatus)
                            color: root.downloader.videoPreviewReady ? Theme.success : Theme.textMuted
                            wrapMode: Text.WordWrap
                            textFormat: Text.PlainText
                        }
                    }

                    DownloadLinkPreview {
                        Layout.fillWidth: true
                        Layout.preferredHeight: implicitHeight
                        visible: root.downloader.videoPreviewReady
                        title: root.downloader.videoPreviewTitle
                        platform: root.downloader.videoPreviewPlatform
                        uploader: root.downloader.videoPreviewUploader
                        duration: root.downloader.videoPreviewDuration
                        thumbnail: root.downloader.videoPreviewThumbnail
                    }

                    DownloadDestinationRow {

                        Layout.fillWidth: true
                        directory: root.downloader.videoOutputDirectory
                        managed: root.downloader.outputManaged
                        onChooseRequested: root.downloader.chooseVideoOutputDirectory()
                    }

                    DouyinSessionAction {
                        id: douyinAction
                        Layout.fillWidth: true
                        url: videoLink.text
                        visible: requiresSession
                        operationBusy: root.downloader.videoPreviewBusy || root.downloader.audioPreviewBusy
                            || root.downloader.hasWork
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        StudioButton {
                            text: qsTr("Tải video")
                            variant: "primary"
                            enabled: root.downloader.videoPreviewReady && root.downloader.videoOutputDirectory.length > 0
                                && douyinAction.permitsRequest
                            onClicked: root.downloader.downloadVideo(root.downloader.videoPreviewUrl)
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
