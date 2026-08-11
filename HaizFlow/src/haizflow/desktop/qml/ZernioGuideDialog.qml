pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    signal configureApiKeyRequested()
    signal chooseConnectionRequested()

    modal: true
    focus: true
    parent: Overlay.overlay
    width: Math.min(680, parent ? parent.width - 48 : 680)
    height: Math.min(500, parent ? parent.height - 48 : 500)
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    padding: Theme.space24
    title: I18n.t("Set up social publishing")
    closePolicy: Popup.CloseOnEscape

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: Theme.space12

        Text {
            Layout.fillWidth: true
            text: I18n.t("Zernio connects HaizFlow to TikTok, YouTube, Facebook and Instagram. Complete these steps once; HaizFlow remembers the connection for later projects.")
            color: Theme.textMuted
            font.pixelSize: Theme.body
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }

        ZernioSetupStep {
            Layout.fillWidth: true
            stepNumber: 1
            title: I18n.t("Sign in to Zernio")
            description: I18n.t("Create an account if needed, then sign in to the Zernio dashboard.")
            statusText: I18n.t("Browser")
            statusTone: "muted"

            AppButton {
                compact: true
                tone: "secondary"
                text: I18n.t("Open Zernio")
                onClicked: AppController.openZernioSignIn()
            }
        }

        ZernioSetupStep {
            Layout.fillWidth: true
            stepNumber: 2
            title: I18n.t("Add an API key")
            description: I18n.t("Create a read-write key and save it securely in HaizFlow.")
            statusText: !AppController.zernioApiKeyConfigured
                ? I18n.t("Required")
                : AppController.zernioApiKeyVerified ? I18n.t("Verified") : I18n.t("Needs verification")
            statusTone: !AppController.zernioApiKeyConfigured
                ? "warning" : AppController.zernioApiKeyVerified ? "success" : "warning"

            AppButton {
                compact: true
                tone: AppController.zernioApiKeyVerified ? "secondary" : "primary"
                text: I18n.t("Manage API key")
                onClicked: root.configureApiKeyRequested()
            }
        }

        ZernioSetupStep {
            Layout.fillWidth: true
            stepNumber: 3
            title: I18n.t("Connect social accounts")
            description: AppController.zernioConnectedAccountCount > 0
                ? I18n.t("Your connected accounts are available in HaizFlow.")
                : I18n.t("Choose a platform and authorize it in the browser.")
            statusText: AppController.zernioConnectedAccountCount > 0
                ? I18n.t("%1 connected").arg(AppController.zernioConnectedAccountCount)
                : I18n.t("Not connected")
            statusTone: AppController.zernioConnectedAccountCount > 0 ? "success" : "muted"

            AppButton {
                compact: true
                tone: AppController.zernioConnectedAccountCount > 0 ? "secondary" : "primary"
                text: I18n.t("Manage connections")
                enabled: AppController.zernioApiKeyVerified && !AppController.tiktokPublishBusy
                onClicked: root.chooseConnectionRequested()
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            AppButton {
                compact: true
                tone: "ghost"
                text: I18n.t("Zernio documentation")
                onClicked: AppController.openZernioPostingDocs()
            }
            Item { Layout.fillWidth: true }
            AppButton {
                compact: true
                tone: "primary"
                text: I18n.t("Done")
                onClicked: root.close()
            }
        }
    }
}
