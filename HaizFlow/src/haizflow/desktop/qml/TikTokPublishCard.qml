import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string fileName
    required property string filePath
    required property string caption
    required property string hashtags
    required property string postText
    required property string publishStatus
    required property string publishError
    required property string thumbnailSource

    signal editRequested()

    readonly property string statusText: publishStatus === "posted" ? I18n.t("Posted")
        : publishStatus === "awaiting_confirmation" ? I18n.t("Awaiting confirmation")
        : publishStatus === "preparing" ? I18n.t("Preparing")
        : publishStatus === "missing" ? I18n.t("File missing")
        : publishStatus === "failed" ? I18n.t("Failed")
        : I18n.t("Ready")
    readonly property color statusColor: publishStatus === "posted" ? Theme.success
        : publishStatus === "awaiting_confirmation" ? Theme.warning
        : publishStatus === "preparing" ? Theme.violet
        : publishStatus === "missing" || publishStatus === "failed" ? Theme.danger
        : Theme.blue

    radius: Theme.radius
    color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surface
    border.width: 1
    border.color: hoverHandler.hovered ? Theme.outlineStrong : Theme.outline

    HoverHandler {
        id: hoverHandler
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(root.width * 0.5625)
            color: Theme.video
            radius: Theme.radius
            clip: true

            Image {
                id: thumbnail
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: Math.round(root.width * 2)
                sourceSize.height: Math.round(root.width * 1.125)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }

            ThumbnailFallback {
                anchors.fill: parent
                visible: root.thumbnailSource.length === 0 || thumbnail.status === Image.Error
            }

            Rectangle {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Theme.space8
                implicitWidth: statusLabel.implicitWidth + Theme.space12
                implicitHeight: 22
                radius: Theme.radiusTiny
                color: Theme.scrim

                Text {
                    id: statusLabel
                    anchors.centerIn: parent
                    text: root.statusText
                    color: root.statusColor
                    font.pixelSize: Theme.label
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: Theme.space12
            Layout.rightMargin: Theme.space12
            Layout.topMargin: Theme.space8
            Layout.bottomMargin: Theme.space8
            spacing: Theme.space4

            Text {
                Layout.fillWidth: true
                text: root.fileName
                color: Theme.text
                font.pixelSize: Theme.caption
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
            }

            Text {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                text: root.postText.length > 0 ? root.postText : I18n.t("No caption or hashtags")
                color: root.postText.length > 0 ? Theme.textMuted : Theme.textSubtle
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                wrapMode: Text.WordWrap
                maximumLineCount: 2
            }

            Text {
                Layout.fillWidth: true
                visible: root.publishError.length > 0
                text: I18n.t(root.publishError)
                color: Theme.danger
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                maximumLineCount: 1
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                AppButton {
                    Layout.fillWidth: true
                    compact: true
                    iconGlyph: root.publishStatus === "posted" ? "\uE72C" : "\uE768"
                    text: root.publishStatus === "awaiting_confirmation"
                        ? I18n.t("Continue")
                        : root.publishStatus === "posted"
                            ? I18n.t("Prepare again")
                            : I18n.t("Prepare")
                    tone: root.publishStatus === "posted" ? "secondary" : "primary"
                    enabled: root.publishStatus !== "missing" && !AppController.tiktokPublishBusy
                    onClicked: {
                        if (root.publishStatus === "awaiting_confirmation")
                            AppController.confirmTikTokPublishAndNext(root.index)
                        else if (root.publishStatus === "posted") {
                            AppController.resetTikTokPublishItem(root.index)
                            AppController.prepareTikTokPublishItem(root.index)
                        } else {
                            AppController.prepareTikTokPublishItem(root.index)
                        }
                    }
                }

                IconButton {
                    id: moreButton

                    property bool menuWasOpenOnPress: false

                    controlSize: 34
                    glyph: "\uE712"
                    Accessible.name: I18n.t("More actions")
                    onPressed: menuWasOpenOnPress = actionMenu.visible
                    onClicked: {
                        if (menuWasOpenOnPress || actionMenu.visible)
                            actionMenu.close()
                        else
                            actionMenu.open()
                    }

                    Menu {
                        id: actionMenu

                        width: 190
                        x: parent.width - width
                        y: parent.height + Theme.space4
                        padding: Theme.space4
                        closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside

                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: Theme.surfaceElevated
                            border.width: 1
                            border.color: Theme.outlineStrong
                        }

                        AppMenuItem {
                            text: I18n.t("Edit")
                            iconGlyph: "\uE70F"
                            onTriggered: root.editRequested()
                        }

                        AppMenuItem {
                            text: I18n.t("Copy caption")
                            iconGlyph: "\uE8C8"
                            onTriggered: AppController.copyTikTokPublishCaption(root.index)
                        }

                        AppMenuItem {
                            text: I18n.t("Remove")
                            iconGlyph: "\uE74D"
                            tone: "danger"
                            onTriggered: AppController.removeTikTokPublishItem(root.index)
                        }
                    }
                }
            }
        }
    }

    Behavior on color {
        ColorAnimation { duration: Theme.motionFast }
    }
    Behavior on border.color {
        ColorAnimation { duration: Theme.motionFast }
    }
}
