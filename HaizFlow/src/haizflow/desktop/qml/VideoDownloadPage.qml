import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    required property var downloader

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
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        AppButton {
                            text: qsTr("Kiểm tra")
                            tone: "secondary"
                            enabled: videoLink.text.trim().length > 0 && !root.downloader.videoPreviewBusy
                            onClicked: root.downloader.inspectVideo(videoLink.text.trim())
                        }
                        AppButton {
                            visible: root.downloader.videoPreviewBusy
                            text: qsTr("Hủy")
                            tone: "danger"
                            onClicked: root.downloader.cancelVideoPreview()
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: root.downloader.videoPreviewStatus.length > 0
                            text: root.downloader.videoPreviewStatus
                            color: root.downloader.videoPreviewReady ? Theme.success : Theme.textMuted
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 112
                        visible: root.downloader.videoPreviewReady
                        radius: Theme.radiusSmall
                        color: Theme.surfaceElevated
                        border.width: 1
                        border.color: Theme.outline

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.space12
                            spacing: Theme.space12

                            Rectangle {
                                Layout.preferredWidth: 132
                                Layout.preferredHeight: 76
                                radius: Theme.radiusTiny
                                color: Theme.surfaceStrong
                                clip: true

                                Image {
                                    id: previewThumbnail
                                    anchors.fill: parent
                                    source: root.downloader.videoPreviewThumbnail
                                    sourceSize.width: 264
                                    sourceSize.height: 152
                                    asynchronous: true
                                    fillMode: Image.PreserveAspectCrop
                                    visible: status === Image.Ready
                                }
                                ThumbnailFallback {
                                    anchors.fill: parent
                                    visible: root.downloader.videoPreviewThumbnail.length === 0 || previewThumbnail.status === Image.Error
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Theme.space4
                                Text {
                                    Layout.fillWidth: true
                                    text: root.downloader.videoPreviewTitle
                                    color: Theme.text
                                    font.pixelSize: Theme.body
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: [root.downloader.videoPreviewPlatform, root.downloader.videoPreviewUploader, root.downloader.videoPreviewDuration].filter(function(value) { return value.length > 0 }).join(" | ")
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.caption
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: root.downloader.videoOutputDirectory.length > 0 ? root.downloader.videoOutputDirectory : qsTr("Chưa chọn thư mục")
                            color: root.downloader.videoOutputDirectory.length > 0 ? Theme.text : Theme.textMuted
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                        }
                        AppButton {
                            visible: !root.downloader.outputManaged
                            text: qsTr("Chọn thư mục")
                            compact: true
                            onClicked: root.downloader.chooseVideoOutputDirectory()
                        }
                    }

                    AppButton {
                        Layout.fillWidth: true
                        text: qsTr("Tải video")
                        tone: "primary"
                        enabled: root.downloader.videoPreviewReady && root.downloader.videoOutputDirectory.length > 0
                        onClicked: root.downloader.downloadVideo(root.downloader.videoPreviewUrl)
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
