pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
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
        if (AppController.zernioCredentialBusy)
            return qsTr("Đang kiểm tra kết nối")
        if (!AppController.zernioApiKeyConfigured)
            return qsTr("Thêm Zernio API key trong Cài đặt để đăng video.")
        if (!AppController.zernioApiKeyVerified)
            return qsTr("Cần kiểm tra kết nối Zernio")
        if (AppController.zernioOauthSyncPending)
            return qsTr("Đang chờ kết nối")
        if (AppController.zernioAccountSyncing)
            return qsTr("Đang đồng bộ")
        if (AppController.zernioConnectedAccountCount === 0)
            return qsTr("Chưa kết nối nền tảng")
        if (!AppController.zernioCanPostMore)
            return qsTr("Đã đạt giới hạn đăng")
        if (AppController.zernioAccountReady)
            return ""
        return qsTr("Đang tải")
    }

    function openPostOptions() {
        optionsDialog.open()
    }

    padding: 0
    spacing: 0
    border.width: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        PlatformLogo {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            platform: root.hasSelectedPlatform ? root.platform : ""
            visible: root.hasSelectedPlatform
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
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
                visible: text.length > 0
                text: root.connectionStatus()
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        StudioButton {
            variant: "secondary"
            text: !AppController.zernioApiKeyConfigured ? qsTr("Thêm API key")
                : !AppController.zernioApiKeyVerified ? qsTr("Kiểm tra kết nối")
                : root.hasSelectedPlatform ? qsTr("Đổi tài khoản") : qsTr("Chọn tài khoản")
            enabled: !AppController.tiktokPublishBusy && !AppController.zernioCredentialBusy
            onClicked: {
                if (!AppController.zernioApiKeyVerified)
                    root.apiKeyManagementRequested();
                else
                    root.connectionPickerRequested();
            }
        }

        StudioIconButton {
            id: setupMoreButton
            iconName: "more"
            toolTipText: qsTr("Thiết lập đăng bài")
            onClicked: setupMenu.open()

            Menu {
                id: setupMenu
                width: 180
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
                    text: qsTr("API key")
                    enabled: !AppController.tiktokPublishBusy && !AppController.zernioAccountSyncing
                    onTriggered: root.apiKeyManagementRequested()
                }
                AppMenuItem {
                    text: qsTr("Hướng dẫn")
                    onTriggered: root.setupGuideRequested()
                }
            }
        }
    }

    ZernioPostOptionsDialog { id: optionsDialog }
}
