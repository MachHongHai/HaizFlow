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

    signal editRequested()
    signal publishRequested()

    readonly property bool hasRemotePost: zernioPostId.length > 0
    readonly property bool published: publishStatus === "published" || publishStatus === "posted"
    readonly property bool remoteInFlight: hasRemotePost && !published
        && !["failed", "partial", "cancelled", "deleted", "draft", "scheduled"].includes(publishStatus)
    readonly property bool working: ["uploading", "publishing", "pending", "processing", "queued"].includes(publishStatus) || remoteInFlight
    readonly property bool awaitingUrl: published && hasRemotePost
        && (!platformPostUrlVerified || platformPostUrl.length === 0)
    readonly property bool canPublish: !working && publishStatus !== "missing"
        && publishStatus !== "scheduled"
        && (!hasRemotePost || ["failed", "partial", "draft"].includes(publishStatus))
        && !AppController.tiktokPublishBusy && !AppController.zernioAccountSyncing
        && AppController.zernioApiKeyVerified && AppController.zernioAccountReady
    readonly property string statusLabel: published ? (awaitingUrl ? qsTr("Đang hoàn tất") : qsTr("Đã đăng"))
        : working ? qsTr("Đang đăng")
        : publishStatus === "failed" || publishStatus === "partial" ? qsTr("Lỗi")
        : publishStatus === "scheduled" ? qsTr("Đã hẹn giờ")
        : publishStatus === "missing" ? qsTr("Thiếu tệp") : qsTr("Sẵn sàng")

    implicitHeight: 68
    color: hoverHandler.hovered ? Theme.surfaceMuted : "transparent"

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space12
        anchors.rightMargin: Theme.space8
        spacing: Theme.space12

        MediaThumbnail {
            Layout.preferredWidth: 76
            Layout.preferredHeight: 48
            source: root.thumbnailSource
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                Layout.fillWidth: true
                text: root.fileName
                color: Theme.text
                font.pixelSize: TypeScale.control
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
            }
            Text {
                Layout.fillWidth: true
                text: root.publishError.length > 0 ? root.publishError : root.postText
                color: root.publishError.length > 0 ? Theme.danger : Theme.textMuted
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        RowLayout {
            Layout.preferredWidth: 112
            spacing: Theme.space4
            PlatformLogo {
                Layout.preferredWidth: 17
                Layout.preferredHeight: 17
                platform: root.targetPlatform
            }
            Text {
                Layout.fillWidth: true
                text: root.targetPlatform === "youtube" ? "YouTube"
                    : root.targetPlatform === "facebook" ? "Facebook"
                    : root.targetPlatform === "instagram" ? "Instagram" : "TikTok"
                color: Theme.textMuted
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        StatusBadge {
            Layout.preferredWidth: 104
            status: root.published ? "done"
                : root.publishStatus === "failed" || root.publishStatus === "partial" ? "failed"
                : root.working ? "processing" : "ready"
            label: root.statusLabel
        }

        Text {
            Layout.preferredWidth: 42
            visible: root.working
            text: qsTr("%1%").arg(root.uploadProgress)
            color: Theme.interactive
            font.pixelSize: TypeScale.metadata
            horizontalAlignment: Text.AlignRight
            textFormat: Text.PlainText
        }

        StudioButton {
            text: root.published ? (root.awaitingUrl ? qsTr("Đang hoàn tất") : qsTr("Mở bài đăng"))
                : root.publishStatus === "failed" || root.publishStatus === "partial" ? qsTr("Đăng lại") : qsTr("Đăng")
            variant: root.published ? "secondary" : "primary"
            enabled: root.published
                ? root.platformPostUrlVerified && root.platformPostUrl.length > 0 && !AppController.tiktokPublishBusy
                : root.canPublish
            onClicked: {
                if (root.published)
                    AppController.openTikTokPublishedPost(root.index)
                else
                    root.publishRequested()
            }
        }

        StudioIconButton {
            id: moreButton
            visible: !root.published
            iconName: "more"
            toolTipText: qsTr("Tùy chọn")
            onClicked: actionMenu.popup(this, width, 0)
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.divider
    }

    Menu {
        id: actionMenu
        width: 200
        AppMenuItem {
            text: qsTr("Chỉnh nội dung")
            iconGlyph: IconCatalog.glyph("edit")
            collapsed: root.published || root.publishStatus === "scheduled"
            enabled: !root.working
            onTriggered: root.editRequested()
        }
        AppMenuItem {
            text: qsTr("Sao chép caption")
            iconGlyph: "\uE8C8"
            onTriggered: AppController.copyTikTokPublishCaption(root.index)
        }
        AppMenuItem {
            text: qsTr("Xóa khỏi hàng đợi")
            iconGlyph: "\uE74D"
            tone: "danger"
            enabled: !root.working
            onTriggered: AppController.removeTikTokPublishItem(root.index)
        }
    }

    HoverHandler { id: hoverHandler; cursorShape: Qt.PointingHandCursor }
}
