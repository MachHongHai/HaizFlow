pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string fileName
    required property string caption
    required property string hashtags
    required property string postText
    required property string publishStatus
    required property string publishError
    required property string thumbnailSource
    required property int uploadProgress
    required property string zernioPostId
    required property string platformPostUrl

    signal editRequested()

    readonly property bool working: publishStatus === "uploading" || publishStatus === "publishing"
    readonly property bool published: publishStatus === "published" || publishStatus === "posted"
    readonly property bool canPublish: !working && publishStatus !== "missing"
        && publishStatus !== "scheduled" && !AppController.tiktokPublishBusy
        && AppController.zernioPublishConsentConfirmed
    readonly property string statusLabel: publishStatus === "ready" ? I18n.t("Ready")
        : publishStatus === "uploading" ? I18n.t("Uploading")
        : publishStatus === "publishing" ? I18n.t("Publishing")
        : publishStatus === "published" || publishStatus === "posted" ? I18n.t("Published")
        : publishStatus === "scheduled" ? I18n.t("Scheduled")
        : publishStatus === "draft" ? I18n.t("Draft")
        : publishStatus === "failed" || publishStatus === "partial" ? I18n.t("Failed")
        : publishStatus === "missing" ? I18n.t("Missing file")
        : publishStatus
    readonly property color statusColor: published ? Theme.success
        : publishStatus === "failed" || publishStatus === "partial" || publishStatus === "missing" ? Theme.danger
        : working ? Theme.warning
        : publishStatus === "scheduled" || publishStatus === "draft" ? Theme.violet
        : Theme.textMuted

    width: 220
    height: 272
    radius: Theme.radius
    color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surface
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.focus : hoverHandler.hovered ? Theme.outlineStrong : Theme.outline
    focusPolicy: Qt.TabFocus
    Accessible.name: fileName

    HoverHandler {
        id: hoverHandler
        cursorShape: Qt.PointingHandCursor
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 124
            radius: Theme.radius
            color: Theme.video
            clip: true

            Image {
                id: thumbnail
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: 440
                sourceSize.height: 248
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }

            ThumbnailFallback {
                anchors.fill: parent
                visible: root.thumbnailSource.length === 0 || thumbnail.status === Image.Error
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: root.working ? 4 : 0
                color: Theme.surfaceStrong

                Rectangle {
                    width: parent.width * Math.max(0, Math.min(100, root.uploadProgress)) / 100
                    height: parent.height
                    color: Theme.warning
                    Behavior on width { NumberAnimation { duration: Theme.motionStandard } }
                }
            }

            Rectangle {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Theme.space8
                implicitWidth: statusText.implicitWidth + Theme.space12
                implicitHeight: 24
                radius: Theme.radiusSmall
                color: Theme.scrim

                Text {
                    id: statusText
                    anchors.centerIn: parent
                    text: root.statusLabel
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
            Layout.margins: Theme.space12
            spacing: Theme.space4

            Text {
                Layout.fillWidth: true
                text: root.fileName
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
            }

            Text {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                text: root.publishError.length > 0 ? root.publishError : root.postText
                color: root.publishError.length > 0 ? Theme.danger : Theme.textMuted
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                elide: Text.ElideRight
                maximumLineCount: 2
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                AppButton {
                    Layout.fillWidth: true
                    compact: true
                    text: root.published && root.platformPostUrl.length > 0
                        ? I18n.t("Open post")
                        : root.publishStatus === "failed" || root.publishStatus === "partial"
                            ? I18n.t("Retry")
                            : I18n.t("Publish")
                    iconGlyph: root.published && root.platformPostUrl.length > 0 ? "\uE8A7" : "\uE768"
                    tone: root.published ? "secondary" : "primary"
                    enabled: root.published ? root.platformPostUrl.length > 0 : root.canPublish
                    onClicked: {
                        if (root.published)
                            AppController.openTikTokPublishedPost(root.index)
                        else
                            AppController.publishTikTokItem(root.index)
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
                        width: 210
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
                            text: I18n.t("Edit caption")
                            iconGlyph: "\uE70F"
                            enabled: !root.working
                            onTriggered: root.editRequested()
                        }

                        AppMenuItem {
                            text: I18n.t("Copy caption")
                            iconGlyph: "\uE8C8"
                            onTriggered: AppController.copyTikTokPublishCaption(root.index)
                        }

                        AppMenuItem {
                            text: I18n.t("Open published post")
                            iconGlyph: "\uE8A7"
                            collapsed: root.platformPostUrl.length === 0
                            onTriggered: AppController.openTikTokPublishedPost(root.index)
                        }

                        AppMenuItem {
                            text: I18n.t("Remove")
                            iconGlyph: "\uE74D"
                            tone: "danger"
                            enabled: !root.working
                            onTriggered: AppController.removeTikTokPublishItem(root.index)
                        }
                    }
                }
            }
        }
    }

    Behavior on color { ColorAnimation { duration: Theme.motionFast } }
    Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }
}
