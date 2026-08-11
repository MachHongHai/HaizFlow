pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    signal connectionPickerRequested()

    readonly property bool setupComplete: AppController.zernioApiKeyVerified
        && AppController.zernioAccountReady
    readonly property bool hasSelectedPlatform: AppController.zernioApiKeyVerified
        && AppController.zernioSelectedAccountIndex >= 0
    readonly property string platform: AppController.zernioSelectedPlatform

    function privacyLabel(value) {
        if (value === "PUBLIC_TO_EVERYONE" || value === "public")
            return I18n.t("Public")
        if (value === "MUTUAL_FOLLOW_FRIENDS")
            return I18n.t("Friends")
        if (value === "FOLLOWER_OF_CREATOR")
            return I18n.t("Followers")
        if (value === "SELF_ONLY" || value === "private")
            return I18n.t("Private")
        if (value === "unlisted")
            return I18n.t("Unlisted")
        return value
    }

    function connectionStatus() {
        if (!AppController.zernioApiKeyConfigured)
            return I18n.t("Setup required")
        if (!AppController.zernioApiKeyVerified)
            return I18n.t("API key needs verification")
        if (AppController.zernioOauthSyncPending)
            return I18n.t("Waiting for the new account")
        if (AppController.zernioAccountSyncing)
            return I18n.t("Updating platforms")
        if (AppController.zernioConnectedAccountCount === 0)
            return I18n.t("No publishing platform")
        if (!AppController.zernioCanPostMore)
            return I18n.t("Posting limit reached")
        if (AppController.zernioAccountReady)
            return I18n.t("Ready")
        return I18n.t("Loading")
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

    function openPostOptions() {
        optionsDialog.open()
    }

    implicitHeight: 56
    radius: Theme.radius
    color: Theme.violetSurface
    border.width: 1
    border.color: root.hasSelectedPlatform ? Theme.interactiveOutline : Theme.violetOutline

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.space8
        spacing: Theme.space12

        Rectangle {
            Layout.preferredWidth: 32
            Layout.preferredHeight: 32
            radius: Theme.radiusSmall
            color: root.hasSelectedPlatform ? Theme.successMuted : Theme.violetMuted

            PlatformLogo {
                anchors.centerIn: parent
                width: 20
                height: 20
                platform: root.setupComplete ? root.platform : ""
                visible: root.hasSelectedPlatform
            }
            AppIcon {
                anchors.centerIn: parent
                glyph: "\uE72E"
                iconColor: Theme.violet
                iconSize: Theme.icon
                visible: !root.hasSelectedPlatform
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            Text {
                Layout.fillWidth: true
                text: root.hasSelectedPlatform && AppController.zernioSelectedAccountName.length > 0
                    ? AppController.zernioSelectedAccountName
                    : I18n.t("Social publishing")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                text: root.connectionStatus()
                color: root.setupComplete ? Theme.success
                    : AppController.zernioApiKeyConfigured ? Theme.warning : Theme.textMuted
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        AppButton {
            compact: true
            tone: "secondary"
            text: I18n.t("Platform")
            enabled: AppController.zernioApiKeyVerified && !AppController.tiktokPublishBusy
            onClicked: root.connectionPickerRequested()
        }

    }

    Dialog {
        id: optionsDialog
        modal: true
        focus: true
        parent: Overlay.overlay
        width: Math.min(600, parent ? parent.width - 48 : 600)
        height: optionsContent.implicitHeight + 112
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        padding: Theme.space24
        title: I18n.t("Post options")
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.outlineStrong
        }

        contentItem: ColumnLayout {
            id: optionsContent
            spacing: Theme.space16

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                PlatformLogo {
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                    platform: root.platform
                }
                Text {
                    Layout.fillWidth: true
                    text: AppController.zernioSelectedPlatformLabel
                    color: Theme.text
                    font.pixelSize: Theme.h3
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4
                Text {
                    text: I18n.t("Visibility")
                    color: Theme.textMuted
                    font.pixelSize: Theme.label
                    textFormat: Text.PlainText
                }
                AppComboBox {
                    id: privacyCombo
                    Layout.fillWidth: true
                    model: AppController.zernioPrivacyLevels
                    enabled: count > 1 && !AppController.tiktokPublishBusy
                    displayText: currentIndex >= 0
                        ? root.privacyLabel(String(model[currentIndex]))
                        : I18n.t("Loading")
                    delegate: ItemDelegate {
                        id: privacyDelegate
                        required property int index
                        width: privacyCombo.popup.width - 12
                        height: 40
                        contentItem: Text {
                            text: root.privacyLabel(String(privacyCombo.model[privacyDelegate.index]))
                            color: Theme.text
                            font.pixelSize: Theme.body
                            verticalAlignment: Text.AlignVCenter
                            textFormat: Text.PlainText
                        }
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: privacyDelegate.highlighted ? Theme.interactiveMuted : "transparent"
                        }
                    }
                    onActivated: function(index) { root.savePublishSettings() }
                    Binding {
                        target: privacyCombo
                        property: "currentIndex"
                        value: AppController.zernioPrivacyLevels.indexOf(AppController.zernioPrivacyLevel)
                    }
                }
            }

            Flow {
                Layout.fillWidth: true
                spacing: Theme.space12

                AppCheckBox {
                    id: publishNowCheck
                    text: I18n.t("Publish now")
                    enabled: !AppController.tiktokPublishBusy
                    onClicked: root.savePublishSettings()
                    Binding { target: publishNowCheck; property: "checked"; value: AppController.zernioPublishNow }
                }
                AppCheckBox {
                    id: commentsCheck
                    visible: root.platform === "tiktok"
                    text: I18n.t("Comments")
                    enabled: AppController.zernioCommentAvailable && !AppController.tiktokPublishBusy
                    onClicked: root.savePublishSettings()
                    Binding { target: commentsCheck; property: "checked"; value: AppController.zernioAllowComment }
                }
                AppCheckBox {
                    id: duetCheck
                    visible: root.platform === "tiktok"
                    text: I18n.t("Duet")
                    enabled: AppController.zernioDuetAvailable && !AppController.tiktokPublishBusy
                    onClicked: root.savePublishSettings()
                    Binding { target: duetCheck; property: "checked"; value: AppController.zernioAllowDuet }
                }
                AppCheckBox {
                    id: stitchCheck
                    visible: root.platform === "tiktok"
                    text: I18n.t("Stitch")
                    enabled: AppController.zernioStitchAvailable && !AppController.tiktokPublishBusy
                    onClicked: root.savePublishSettings()
                    Binding { target: stitchCheck; property: "checked"; value: AppController.zernioAllowStitch }
                }
                AppCheckBox {
                    id: shareToFeedCheck
                    visible: root.platform === "instagram"
                    text: I18n.t("Share to profile feed")
                    enabled: !AppController.tiktokPublishBusy
                    onClicked: root.savePublishSettings()
                    Binding { target: shareToFeedCheck; property: "checked"; value: AppController.zernioShareToFeed }
                }
                AppCheckBox {
                    id: aiGeneratedCheck
                    visible: root.platform === "tiktok" || root.platform === "instagram"
                    text: I18n.t("AI-generated label")
                    enabled: !AppController.tiktokPublishBusy
                    onClicked: root.savePublishSettings()
                    Binding { target: aiGeneratedCheck; property: "checked"; value: AppController.zernioAiGenerated }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                visible: root.platform === "facebook" || root.platform === "instagram"
                spacing: Theme.space4
                Text {
                    text: I18n.t("First comment")
                    color: Theme.textMuted
                    font.pixelSize: Theme.label
                    textFormat: Text.PlainText
                }
                TextField {
                    id: firstCommentInput
                    Layout.fillWidth: true
                    implicitHeight: 42
                    color: Theme.text
                    placeholderText: I18n.t("Optional first comment")
                    font.pixelSize: Theme.body
                    selectByMouse: true
                    enabled: !AppController.tiktokPublishBusy
                    onEditingFinished: root.savePublishSettings()
                    background: Rectangle {
                        radius: Theme.radiusSmall
                        color: Theme.input
                        border.width: firstCommentInput.activeFocus ? 2 : 1
                        border.color: firstCommentInput.activeFocus ? Theme.focus : Theme.outline
                    }
                    Binding {
                        target: firstCommentInput
                        property: "text"
                        value: AppController.zernioFirstComment
                        when: !firstCommentInput.activeFocus
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton {
                    compact: true
                    tone: "primary"
                    text: I18n.t("Done")
                    onClicked: optionsDialog.close()
                }
            }
        }
    }
}
