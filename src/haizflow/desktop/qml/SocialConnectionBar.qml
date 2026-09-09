pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppSurface {
    id: root

    signal setupGuideRequested()
    signal apiKeyManagementRequested()
    signal connectionPickerRequested()

    readonly property bool setupComplete: AppController.zernioApiKeyVerified
        && AppController.zernioAccountReady
    readonly property bool hasSelectedPlatform: AppController.zernioApiKeyVerified
        && AppController.zernioSelectedAccountIndex >= 0
    readonly property string platform: AppController.zernioSelectedPlatform

    function connectionStatus() {
        if (!AppController.zernioApiKeyConfigured)
            return qsTr("Chưa có API key")
        if (!AppController.zernioApiKeyVerified)
            return qsTr("API key không hợp lệ")
        if (AppController.zernioOauthSyncPending)
            return qsTr("Đang chờ kết nối")
        if (AppController.zernioAccountSyncing)
            return qsTr("Đang đồng bộ")
        if (AppController.zernioConnectedAccountCount === 0)
            return qsTr("Chưa kết nối nền tảng")
        if (!AppController.zernioCanPostMore)
            return qsTr("Đã đạt giới hạn đăng")
        if (AppController.zernioAccountReady)
            return qsTr("Sẵn sàng")
        return qsTr("Đang tải")
    }

    function openPostOptions() {
        optionsDialog.open()
    }

    padding: Theme.space8
    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        PlatformLogo {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            platform: root.hasSelectedPlatform ? root.platform : ""
            visible: root.hasSelectedPlatform
        }

        FluentIcon {
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
            visible: !root.hasSelectedPlatform
            name: "publish"
            iconColor: Theme.textMuted
            iconSize: 17
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0

            Text {
                Layout.fillWidth: true
                text: root.hasSelectedPlatform && AppController.zernioSelectedAccountName.length > 0
                    ? AppController.zernioSelectedAccountName : qsTr("Kết nối đăng bài")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: root.connectionStatus()
                color: root.setupComplete ? Theme.success
                    : AppController.zernioApiKeyConfigured ? Theme.warning : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        StudioButton {
            variant: "ghost"
            text: qsTr("Hướng dẫn")
            onClicked: root.setupGuideRequested()
        }

        StudioButton {
            variant: "ghost"
            text: qsTr("API key")
            enabled: !AppController.tiktokPublishBusy && !AppController.zernioAccountSyncing
            onClicked: root.apiKeyManagementRequested()
        }

        StudioButton {
            variant: "secondary"
            text: root.hasSelectedPlatform ? qsTr("Đổi nền tảng") : qsTr("Chọn nền tảng")
            enabled: AppController.zernioApiKeyVerified && !AppController.tiktokPublishBusy
            onClicked: root.connectionPickerRequested()
        }
    }

    ZernioPostOptionsDialog { id: optionsDialog }
}
