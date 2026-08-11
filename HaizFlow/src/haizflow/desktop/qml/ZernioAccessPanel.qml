pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    signal setupGuideRequested()
    signal apiKeyManagementRequested()

    readonly property bool freeAccountsInUse: AppController.zernioConnectedAccountCount >= 2

    implicitHeight: 56
    radius: Theme.radius
    color: root.freeAccountsInUse ? Theme.warmSurface : Theme.blueSurface
    border.width: 1
    border.color: root.freeAccountsInUse ? Theme.amberMuted : Theme.blueOutline

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.space8
        spacing: Theme.space8

        Rectangle {
            Layout.preferredWidth: 32
            Layout.preferredHeight: 32
            radius: Theme.radiusSmall
            color: root.freeAccountsInUse ? Theme.warningMuted : Theme.blueMuted

            AppIcon {
                anchors.centerIn: parent
                glyph: root.freeAccountsInUse ? "\uE7BA" : "\uE946"
                iconColor: root.freeAccountsInUse ? Theme.warning : Theme.blue
                iconSize: Theme.icon
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            Text {
                Layout.fillWidth: true
                text: I18n.t("Zernio access")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                text: root.freeAccountsInUse
                    ? I18n.t("2 accounts are free; additional accounts require Zernio billing")
                    : I18n.t("Guide and API key management")
                color: root.freeAccountsInUse ? Theme.warning : Theme.textMuted
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        AppButton {
            compact: true
            tone: "violet"
            text: I18n.t("Zernio guide and setup")
            iconGlyph: "\uE946"
            onClicked: root.setupGuideRequested()
        }

        AppButton {
            compact: true
            tone: "secondary"
            text: I18n.t("Manage API key")
            iconGlyph: "\uE8D7"
            enabled: !AppController.tiktokPublishBusy && !AppController.zernioAccountSyncing
            onClicked: root.apiKeyManagementRequested()
        }
    }
}
