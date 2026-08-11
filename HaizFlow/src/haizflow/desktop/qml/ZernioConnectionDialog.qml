pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    property int pendingDisconnectIndex: -1
    property string pendingDisconnectName: ""

    modal: true
    focus: true
    parent: Overlay.overlay
    width: Math.min(680, parent ? parent.width - 48 : 680)
    height: Math.min(500, parent ? parent.height - 48 : 500)
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    padding: Theme.space24
    title: I18n.t("Choose publishing platform")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    function openForSelection() {
        connectionCombo.currentIndex = AppController.zernioSelectedAccountIndex
        open()
        if (AppController.zernioApiKeyVerified
                && !AppController.tiktokPublishBusy
                && !AppController.zernioAccountSyncing)
            AppController.refreshZernioConnections()
    }

    Connections {
        target: AppController

        function onTiktokPublishChanged() {
            if (!root.visible)
                return
            const selected = AppController.zernioSelectedAccountIndex
            if (selected >= 0)
                connectionCombo.currentIndex = selected
            else if (connectionCombo.count <= 0)
                connectionCombo.currentIndex = -1
            else if (connectionCombo.currentIndex >= connectionCombo.count)
                connectionCombo.currentIndex = connectionCombo.count - 1
        }
    }

    Dialog {
        id: disconnectConfirmation

        modal: true
        focus: true
        parent: Overlay.overlay
        width: Math.min(480, parent ? parent.width - 48 : 480)
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        padding: Theme.space24
        title: I18n.t("Disconnect platform")
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.outlineStrong
        }

        contentItem: ColumnLayout {
            spacing: Theme.space20

            Text {
                Layout.fillWidth: true
                text: I18n.t("Disconnect this account from Zernio?")
                    + (root.pendingDisconnectName.length > 0
                        ? "\n" + root.pendingDisconnectName : "")
                color: Theme.text
                font.pixelSize: Theme.body
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: I18n.t("You can reconnect it later from Zernio.")
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
                    text: I18n.t("Cancel")
                    onClicked: disconnectConfirmation.close()
                }
                AppButton {
                    compact: true
                    tone: "danger"
                    text: I18n.t("Disconnect")
                    onClicked: {
                        AppController.disconnectZernioConnection(root.pendingDisconnectIndex)
                        disconnectConfirmation.close()
                    }
                }
            }
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: Theme.space16

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space4

            Text {
                text: I18n.t("Available platforms")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true
                text: I18n.t("Select where this project will publish")
                color: Theme.textMuted
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
            AppComboBox {
                id: connectionCombo
                Layout.fillWidth: true
                model: AppController.zernioConnections
                logoRole: "platform"
                logoModel: AppController.zernioConnectionPlatforms
                enabled: count > 0 && !AppController.tiktokPublishBusy
                displayText: currentIndex >= 0 && currentIndex < count
                    ? textAt(currentIndex) : I18n.t("No connected account")
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.outline
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            Text {
                text: I18n.t("Connect another platform")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true
                text: I18n.t("Authorize the account in your browser")
                color: Theme.textMuted
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: accountLimitText.implicitHeight + Theme.space16
                visible: AppController.zernioConnectedAccountCount >= 2
                radius: Theme.radiusSmall
                color: Theme.warmSurface
                border.width: 1
                border.color: Theme.amberMuted

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space8
                    spacing: Theme.space8

                    AppIcon {
                        Layout.preferredWidth: Theme.icon
                        Layout.preferredHeight: Theme.icon
                        glyph: "\uE7BA"
                        iconColor: Theme.warning
                        iconSize: Theme.icon
                    }
                    Text {
                        id: accountLimitText

                        Layout.fillWidth: true
                        text: I18n.t("Zernio includes 2 connected accounts for free. A third account requires Zernio billing.")
                        color: Theme.text
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                    }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: Theme.space8
                rowSpacing: Theme.space8

                Repeater {
                    model: [
                        { "key": "tiktok", "label": "TikTok" },
                        { "key": "youtube", "label": "YouTube Shorts" },
                        { "key": "facebook", "label": "Facebook Reels" },
                        { "key": "instagram", "label": "Instagram Reels" }
                    ]

                    delegate: AppButton {
                        required property var modelData
                        Layout.fillWidth: true
                        tone: "secondary"
                        text: I18n.t(modelData.label)
                        enabled: AppController.zernioApiKeyVerified
                            && !AppController.tiktokPublishBusy
                            && !AppController.zernioAccountSyncing
                        onClicked: {
                            AppController.connectZernioPlatform(modelData.key)
                            root.close()
                        }
                    }
                }
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            AppButton {
                compact: true
                tone: "ghost"
                text: AppController.zernioAccountSyncing ? I18n.t("Updating") : I18n.t("Refresh")
                enabled: AppController.zernioApiKeyVerified
                    && !AppController.tiktokPublishBusy
                    && !AppController.zernioAccountSyncing
                onClicked: AppController.refreshZernioConnections()
            }
            AppButton {
                compact: true
                tone: "danger"
                text: I18n.t("Disconnect")
                enabled: connectionCombo.currentIndex >= 0
                    && !AppController.tiktokPublishBusy
                    && !AppController.zernioAccountSyncing
                onClicked: {
                    root.pendingDisconnectIndex = connectionCombo.currentIndex
                    root.pendingDisconnectName = connectionCombo.textAt(connectionCombo.currentIndex)
                    disconnectConfirmation.open()
                }
            }
            Item { Layout.fillWidth: true }
            AppButton {
                compact: true
                tone: "ghost"
                text: I18n.t("Cancel")
                onClicked: root.close()
            }
            AppButton {
                compact: true
                tone: "primary"
                text: I18n.t("Use platform")
                enabled: connectionCombo.currentIndex >= 0
                    && !AppController.tiktokPublishBusy
                    && !AppController.zernioAccountSyncing
                onClicked: {
                    if (AppController.selectZernioConnection(connectionCombo.currentIndex))
                        root.close()
                }
            }
        }
    }
}
