pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    readonly property string platform: AppController.zernioSelectedPlatform

    title: qsTr("Tùy chọn bài đăng")
    subtitle: AppController.zernioSelectedPlatformLabel
    preferredWidth: 540
    preferredHeight: platform === "facebook" || platform === "instagram" ? 440 : 370
    maximumWidth: 580
    maximumHeight: 600

    function privacyLabel(value) {
        if (value === "PUBLIC_TO_EVERYONE" || value === "public")
            return qsTr("Công khai")
        if (value === "MUTUAL_FOLLOW_FRIENDS")
            return qsTr("Bạn bè")
        if (value === "FOLLOWER_OF_CREATOR")
            return qsTr("Người theo dõi")
        if (value === "SELF_ONLY" || value === "private")
            return qsTr("Riêng tư")
        if (value === "unlisted")
            return qsTr("Không công khai")
        return value
    }

    function savePublishSettings() {
        const privacy = privacyCombo.currentIndex >= 0
            ? String(privacyCombo.model[privacyCombo.currentIndex])
            : AppController.zernioPrivacyLevel
        AppController.saveZernioPublishSettings(
            privacy,
            publishNowCheck.checked,
            commentsCheck.checked,
            duetCheck.checked,
            stitchCheck.checked,
            shareToFeedCheck.checked,
            aiGeneratedCheck.checked,
            firstCommentInput.text
        )
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        PlatformLogo {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            platform: root.platform
        }

        SettingLabel {
            Layout.fillWidth: true
            text: qsTr("Quyền riêng tư")
        }
    }

    StudioComboBox {
        id: privacyCombo
        Layout.fillWidth: true
        model: AppController.zernioPrivacyLevels
        enabled: count > 1 && !AppController.tiktokPublishBusy
        displayText: currentIndex >= 0
            ? root.privacyLabel(String(model[currentIndex]))
            : qsTr("Đang tải")
        Accessible.name: qsTr("Quyền riêng tư bài đăng")

        delegate: ItemDelegate {
            id: privacyDelegate
            required property int index
            width: privacyCombo.popup.width - 12
            height: UiMetrics.controlHeight
            contentItem: Text {
                text: root.privacyLabel(String(privacyCombo.model[privacyDelegate.index]))
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                verticalAlignment: Text.AlignVCenter
                textFormat: Text.PlainText
            }
            background: Rectangle {
                radius: Theme.radiusSmall
                color: privacyDelegate.highlighted ? Theme.interactiveMuted : "transparent"
            }
        }

        onActivated: root.savePublishSettings()

        Binding {
            privacyCombo.currentIndex: AppController.zernioPrivacyLevels.indexOf(
                AppController.zernioPrivacyLevel)
        }
    }

    Flow {
        Layout.fillWidth: true
        spacing: Theme.space12

        StudioCheckBox {
            id: publishNowCheck
            text: qsTr("Đăng ngay")
            enabled: !AppController.tiktokPublishBusy
            onClicked: root.savePublishSettings()
            Binding { publishNowCheck.checked: AppController.zernioPublishNow }
        }
        StudioCheckBox {
            id: commentsCheck
            visible: root.platform === "tiktok"
            text: qsTr("Bình luận")
            enabled: AppController.zernioCommentAvailable && !AppController.tiktokPublishBusy
            onClicked: root.savePublishSettings()
            Binding { commentsCheck.checked: AppController.zernioAllowComment }
        }
        StudioCheckBox {
            id: duetCheck
            visible: root.platform === "tiktok"
            text: "Duet"
            enabled: AppController.zernioDuetAvailable && !AppController.tiktokPublishBusy
            onClicked: root.savePublishSettings()
            Binding { duetCheck.checked: AppController.zernioAllowDuet }
        }
        StudioCheckBox {
            id: stitchCheck
            visible: root.platform === "tiktok"
            text: "Stitch"
            enabled: AppController.zernioStitchAvailable && !AppController.tiktokPublishBusy
            onClicked: root.savePublishSettings()
            Binding { stitchCheck.checked: AppController.zernioAllowStitch }
        }
        StudioCheckBox {
            id: shareToFeedCheck
            visible: root.platform === "instagram"
            text: qsTr("Chia sẻ lên trang cá nhân")
            enabled: !AppController.tiktokPublishBusy
            onClicked: root.savePublishSettings()
            Binding { shareToFeedCheck.checked: AppController.zernioShareToFeed }
        }
        StudioCheckBox {
            id: aiGeneratedCheck
            visible: root.platform === "tiktok" || root.platform === "instagram"
            text: qsTr("Nội dung tạo bởi AI")
            enabled: !AppController.tiktokPublishBusy
            onClicked: root.savePublishSettings()
            Binding { aiGeneratedCheck.checked: AppController.zernioAiGenerated }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        visible: root.platform === "facebook" || root.platform === "instagram"
        spacing: Theme.space4

        SettingLabel {
            Layout.fillWidth: true
            text: qsTr("Bình luận đầu tiên")
        }

        StudioField {
            id: firstCommentInput
            Layout.fillWidth: true
            placeholderText: qsTr("Không bắt buộc")
            accessibleName: qsTr("Bình luận đầu tiên")
            selectByMouse: true
            enabled: !AppController.tiktokPublishBusy
            onEditingFinished: root.savePublishSettings()

            Binding {
                firstCommentInput.text: AppController.zernioFirstComment
                when: !firstCommentInput.activeFocus
            }
        }
    }

    footerActions: [
        StudioButton {
            text: qsTr("Đóng")
            variant: "primary"
            onClicked: root.close()
        }
    ]
}
