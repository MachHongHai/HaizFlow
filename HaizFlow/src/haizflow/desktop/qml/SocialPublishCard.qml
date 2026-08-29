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
    required property bool platformPostUrlVerified
    required property string targetPlatform

    signal editRequested
    signal publishRequested

    readonly property bool hasRemotePost: zernioPostId.length > 0
    readonly property bool remoteInFlight: hasRemotePost && !published && publishStatus !== "failed" && publishStatus !== "partial" && publishStatus !== "cancelled" && publishStatus !== "deleted" && publishStatus !== "draft" && publishStatus !== "scheduled"
    readonly property bool working: publishStatus === "uploading" || publishStatus === "publishing" || publishStatus === "pending" || publishStatus === "processing" || publishStatus === "queued" || remoteInFlight
    readonly property bool published: publishStatus === "published" || publishStatus === "posted"
    readonly property bool awaitingPublicUrl: published && hasRemotePost && (!platformPostUrlVerified || platformPostUrl.length === 0)
    readonly property bool canPublish: !working && publishStatus !== "missing" && publishStatus !== "scheduled" && (!hasRemotePost || publishStatus === "failed" || publishStatus === "partial" || publishStatus === "draft") && !AppController.tiktokPublishBusy && !AppController.zernioAccountSyncing && AppController.zernioApiKeyVerified && AppController.zernioAccountReady
    readonly property string statusLabel: publishStatus === "ready" ? qsTr("Sẵn sàng") : publishStatus === "uploading" ? qsTr("Đang tải lên") : publishStatus === "publishing" ? qsTr("Đang đăng") : publishStatus === "pending" || publishStatus === "processing" || publishStatus === "queued" ? qsTr("Đang đăng") : publishStatus === "published" || publishStatus === "posted" ? awaitingPublicUrl ? qsTr("Đang hoàn thiện video") : qsTr("Đã đăng") : publishStatus === "scheduled" ? qsTr("Đã lên lịch") : publishStatus === "draft" ? qsTr("Bản nháp") : publishStatus === "failed" || publishStatus === "partial" ? qsTr("Lỗi") : publishStatus === "missing" ? qsTr("Thiếu tệp") : publishStatus
    readonly property color statusColor: awaitingPublicUrl ? Theme.warning : published ? Theme.success : publishStatus === "failed" || publishStatus === "partial" || publishStatus === "missing" ? Theme.danger : working ? Theme.warning : publishStatus === "scheduled" || publishStatus === "draft" ? Theme.interactive : Theme.textMuted

    width: 220
    height: 272
    radius: Theme.radius
    color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surface
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.focus : hoverHandler.hovered ? Theme.outlineStrong : Theme.outline
    focusPolicy: Qt.TabFocus
    Accessible.name: fileName

    function resetReusableState() {
        actionMenu.close();
        moreButton.focus = false;
        root.focus = false;
    }

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
                }
            }

            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: Theme.space8
                implicitWidth: platformRow.implicitWidth + Theme.space12
                implicitHeight: 24
                radius: Theme.radiusSmall
                color: Theme.scrim
                visible: root.targetPlatform.length > 0

                RowLayout {
                    id: platformRow
                    anchors.centerIn: parent
                    spacing: Theme.space4

                    PlatformLogo {
                        Layout.preferredWidth: 16
                        Layout.preferredHeight: 16
                        platform: root.targetPlatform
                    }
                    Text {
                        text: root.targetPlatform === "youtube" ? "YouTube" : root.targetPlatform === "facebook" ? "Facebook" : root.targetPlatform === "instagram" ? "Instagram" : "TikTok"
                        color: Theme.text
                        font.pixelSize: Theme.label
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
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

            Item {
                Layout.fillHeight: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                AppButton {
                    Layout.fillWidth: true
                    compact: true
                    text: root.published ? root.platformPostUrlVerified && root.platformPostUrl.length > 0 ? qsTr("Mở bài đăng") : qsTr("Đang hoàn thiện video") : root.working || root.publishStatus === "scheduled" ? root.statusLabel : root.publishStatus === "failed" || root.publishStatus === "partial" ? qsTr("Thử lại") : qsTr("Đăng")
                    iconGlyph: root.published ? root.platformPostUrlVerified && root.platformPostUrl.length > 0 ? "\uE8A7" : "" : "\uE768"
                    tone: root.published ? "secondary" : "primary"
                    enabled: root.published ? root.platformPostUrlVerified && root.platformPostUrl.length > 0 && !AppController.tiktokPublishBusy : root.canPublish
                    onClicked: {
                        if (root.published && root.platformPostUrlVerified && root.platformPostUrl.length > 0)
                            AppController.openTikTokPublishedPost(root.index);
                        else
                            root.publishRequested();
                    }
                }

                IconButton {
                    id: moreButton
                    property bool menuWasOpenOnPress: false

                    visible: !root.published
                    controlSize: 34
                    glyph: "\uE712"
                    Accessible.name: qsTr("Thao tác khác")
                    onPressed: menuWasOpenOnPress = actionMenu.visible
                    onClicked: {
                        if (menuWasOpenOnPress || actionMenu.visible)
                            actionMenu.close();
                        else
                            actionMenu.open();
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
                            text: qsTr("Chỉnh nội dung")
                            iconGlyph: "\uE70F"
                            collapsed: root.published || root.publishStatus === "scheduled"
                            enabled: !root.working
                            onTriggered: root.editRequested()
                        }

                        AppMenuItem {
                            text: qsTr("Sao chép mô tả")
                            iconGlyph: "\uE8C8"
                            onTriggered: AppController.copyTikTokPublishCaption(root.index)
                        }

                        AppMenuItem {
                            text: qsTr("Xóa")
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
}
