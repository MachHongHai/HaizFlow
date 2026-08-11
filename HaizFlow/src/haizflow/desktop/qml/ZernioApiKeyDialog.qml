pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    property bool keyVisible: false

    modal: true
    focus: true
    parent: Overlay.overlay
    width: Math.min(560, parent ? parent.width - 48 : 560)
    height: Math.min(430, parent ? parent.height - 48 : 430)
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    padding: Theme.space24
    title: I18n.t("Manage API key")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    function openForConfiguration() {
        apiKeyInput.clear()
        keyVisible = false
        open()
        apiKeyInput.forceActiveFocus()
    }

    onClosed: {
        apiKeyInput.clear()
        keyVisible = false
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: Theme.space16

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            radius: Theme.radiusSmall
            color: Theme.surfaceElevated
            border.width: 1
            border.color: AppController.zernioApiKeyConfigured ? Theme.outline : Theme.outlineStrong

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space12
                spacing: Theme.space12

                Rectangle {
                    Layout.preferredWidth: 40
                    Layout.preferredHeight: 40
                    radius: Theme.radiusSmall
                    color: AppController.zernioApiKeyVerified ? Theme.successMuted
                        : AppController.zernioApiKeyConfigured ? Theme.warningMuted : Theme.surfaceMuted

                    AppIcon {
                        anchors.centerIn: parent
                        glyph: AppController.zernioApiKeyVerified ? "\uE73E" : "\uE72E"
                        iconColor: AppController.zernioApiKeyVerified ? Theme.success
                            : AppController.zernioApiKeyConfigured ? Theme.warning : Theme.textMuted
                        iconSize: Theme.icon
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        text: AppController.zernioApiKeyVerified
                            ? I18n.t("API key verified")
                            : AppController.zernioApiKeyConfigured
                                ? I18n.t("API key saved; verification required")
                                : I18n.t("No API key is saved")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Stored in Windows Credential Manager")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                }

                AppButton {
                    compact: true
                    tone: "danger"
                    text: I18n.t("Remove")
                    visible: AppController.zernioApiKeyConfigured
                    enabled: !AppController.tiktokPublishBusy && !AppController.zernioAccountSyncing
                    onClicked: {
                        if (AppController.clearZernioApiKey()) {
                            apiKeyInput.clear()
                            root.keyVisible = false
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                text: I18n.t("Create a read-write key on Zernio, then paste the full value below. Zernio displays it only once.")
                color: Theme.textMuted
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
            AppButton {
                compact: true
                tone: "secondary"
                text: I18n.t("Open API keys")
                onClicked: AppController.openZernioApiKeys()
            }
        }

        Text {
            text: AppController.zernioApiKeyConfigured
                ? I18n.t("Replacement API key") : I18n.t("API key")
            color: Theme.textMuted
            font.pixelSize: Theme.label
            textFormat: Text.PlainText
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            TextField {
                id: apiKeyInput
                Layout.fillWidth: true
                implicitHeight: 44
                echoMode: root.keyVisible ? TextInput.Normal : TextInput.Password
                passwordMaskDelay: 0
                inputMethodHints: Qt.ImhHiddenText | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                placeholderText: AppController.zernioApiKeyConfigured
                    ? I18n.t("Paste a replacement key") : "sk_..."
                color: Theme.text
                selectByMouse: true
                background: Rectangle {
                    radius: Theme.radiusSmall
                    color: Theme.input
                    border.width: apiKeyInput.activeFocus ? 2 : 1
                    border.color: apiKeyInput.activeFocus ? Theme.focus : Theme.outline
                }
            }

            AppButton {
                compact: true
                tone: "secondary"
                text: root.keyVisible ? I18n.t("Hide") : I18n.t("Show")
                enabled: apiKeyInput.text.length > 0
                onClicked: root.keyVisible = !root.keyVisible
            }
        }

        Text {
            Layout.fillWidth: true
            text: I18n.t("Publishing uploads the selected video to Zernio and the chosen social platform. Keep this key private.")
            color: Theme.textMuted
            font.pixelSize: Theme.label
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            Item { Layout.fillWidth: true }
            AppButton {
                compact: true
                tone: "ghost"
                text: I18n.t("Close")
                onClicked: root.close()
            }
            AppButton {
                compact: true
                tone: "primary"
                text: I18n.t("Save and verify")
                enabled: apiKeyInput.text.trim().length > 0
                    && !AppController.tiktokPublishBusy
                    && !AppController.zernioAccountSyncing
                onClicked: {
                    if (AppController.saveZernioApiKey(apiKeyInput.text.trim())) {
                        apiKeyInput.clear()
                        root.keyVisible = false
                    }
                }
            }
        }
    }
}
