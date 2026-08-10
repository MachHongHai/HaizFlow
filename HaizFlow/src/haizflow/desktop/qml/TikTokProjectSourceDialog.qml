pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    modal: true
    focus: true
    parent: Overlay.overlay
    width: Math.min(760, parent ? parent.width - 48 : 760)
    height: Math.min(620, parent ? parent.height - 48 : 620)
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    padding: 0
    header: null
    footer: null
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    function openForSelection() {
        AppController.refreshTikTokProjectSources()
        open()
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 68
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Add from projects")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Choose a single-project video or an entire batch project")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
            }

            IconButton {
                glyph: "\uE711"
                toolTipText: I18n.t("Close")
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ListView {
            id: sourceList

            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.space16
            model: AppController.tiktokProjectSourceModel
            spacing: Theme.space8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            delegate: Rectangle {
                id: sourceDelegate

                required property int index
                required property string videoId
                required property string projectName
                required property string projectType
                required property string fileName
                required property string thumbnailSource
                required property string videoSize
                required property int sourceVideoCount
                required property bool sourceSelected

                width: ListView.view.width
                height: 78
                radius: Theme.radiusSmall
                color: sourceDelegate.sourceSelected ? Theme.interactiveMuted : Theme.surfaceMuted
                border.width: 1
                border.color: sourceDelegate.sourceSelected ? Theme.focus : Theme.outline

                ListView.onPooled: {
                    visible = false
                    focus = false
                }
                ListView.onReused: {
                    visible = true
                    focus = false
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space8
                    spacing: Theme.space12

                    Rectangle {
                        Layout.preferredWidth: 92
                        Layout.fillHeight: true
                        radius: Theme.radiusSmall
                        color: Theme.video
                        clip: true

                        Image {
                            id: sourceThumbnail
                            anchors.fill: parent
                            source: sourceDelegate.thumbnailSource
                            sourceSize.width: 184
                            sourceSize.height: 124
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            visible: status === Image.Ready
                        }

                        ThumbnailFallback {
                            anchors.fill: parent
                            visible: sourceDelegate.thumbnailSource.length === 0
                                || sourceThumbnail.status === Image.Error
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space4

                        Text {
                            Layout.fillWidth: true
                            text: sourceDelegate.projectName
                            color: Theme.text
                            font.pixelSize: Theme.body
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: sourceDelegate.projectType === "batch"
                                ? qsTr("%1 %2").arg(sourceDelegate.sourceVideoCount).arg(I18n.t("videos ready"))
                                : sourceDelegate.fileName
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                            elide: Text.ElideMiddle
                        }
                    }

                    Text {
                        text: sourceDelegate.projectType === "batch"
                            ? qsTr("%1 %2").arg(sourceDelegate.sourceVideoCount).arg(I18n.t("videos"))
                            : sourceDelegate.videoSize.length > 0 ? sourceDelegate.videoSize : I18n.t("Unknown size")
                        color: Theme.textSubtle
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }

                    Text {
                        text: sourceDelegate.projectType === "batch" ? I18n.t("Batch") : I18n.t("Single")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }

                    AppCheckBox {
                        checked: sourceDelegate.sourceSelected
                        onToggled: AppController.setTikTokProjectSourceSelected(
                            sourceDelegate.index,
                            checked
                        )
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: sourceList.count === 0
                width: Math.min(420, sourceList.width - Theme.space32)
                text: I18n.t("No rendered videos are available yet")
                color: Theme.textMuted
                font.pixelSize: Theme.body
                textFormat: Text.PlainText
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 68
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space24
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: qsTr("%1 %2")
                    .arg(AppController.tiktokProjectSourceSelectedCount)
                    .arg(I18n.t("selected"))
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }

            AppButton {
                text: I18n.t("Cancel")
                tone: "ghost"
                onClicked: root.close()
            }

            AppButton {
                text: I18n.t("Add selected videos")
                tone: "primary"
                enabled: AppController.tiktokProjectSourceSelectedCount > 0
                    && !AppController.tiktokPublishBusy
                onClicked: {
                    if (AppController.addSelectedTikTokProjectVideos())
                        root.close()
                }
            }
        }
    }
}

