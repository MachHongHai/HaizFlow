pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property int pendingDisconnectIndex: -1
    property string pendingDisconnectName: ""

    title: qsTr("Nền tảng đăng")
    subtitle: qsTr("Chọn tài khoản hoặc kết nối nền tảng mới")
    preferredWidth: 620
    preferredHeight: 480
    maximumWidth: 660
    maximumHeight: 620

    function openForSelection() {
        connectionCombo.currentIndex = AppController.zernioSelectedAccountIndex
        open()
        // Cached accounts appear immediately; reconciliation stays in the background.
        Qt.callLater(AppController.reconcileZernioConnections)
    }

    Connections {
        target: AppController

        function onZernioAccountsChanged() {
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

    ConfirmDialog {
        id: disconnectConfirmation
        title: qsTr("Ngắt kết nối")
        message: root.pendingDisconnectName.length > 0
            ? qsTr("Ngắt kết nối tài khoản %1? Bạn có thể kết nối lại sau.").arg(root.pendingDisconnectName)
            : qsTr("Ngắt kết nối tài khoản này? Bạn có thể kết nối lại sau.")
        confirmText: qsTr("Ngắt kết nối")
        confirmTone: "danger"
        onConfirmed: AppController.disconnectZernioConnection(root.pendingDisconnectIndex)
    }

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Tài khoản đang dùng")
    }

    StudioComboBox {
        id: connectionCombo
        Layout.fillWidth: true
        model: AppController.zernioConnections
        logoRole: "platform"
        logoModel: AppController.zernioConnectionPlatforms
        enabled: count > 0 && !AppController.tiktokPublishBusy
        displayText: currentIndex >= 0 && currentIndex < count
            ? textAt(currentIndex) : qsTr("Chưa có tài khoản kết nối")
        Accessible.name: qsTr("Tài khoản đăng")
    }

    InlineBanner {
        Layout.fillWidth: true
        visible: AppController.zernioConnectedAccountCount >= 2
        tone: "warning"
        title: qsTr("Đã dùng 2 kết nối miễn phí")
        message: qsTr("Kết nối thứ ba cần gói trả phí của Zernio.")
    }

    FormSection {
        Layout.fillWidth: true
        title: qsTr("Kết nối nền tảng")

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

                delegate: StudioButton {
                    required property var modelData
                    Layout.fillWidth: true
                    variant: "secondary"
                    text: modelData.label
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

    footerActions: [
        StudioButton {
            text: AppController.zernioAccountSyncing ? qsTr("Đang đồng bộ") : qsTr("Làm mới")
            iconName: "refresh"
            variant: "ghost"
            enabled: AppController.zernioApiKeyVerified
                && !AppController.tiktokPublishBusy
                && !AppController.zernioAccountSyncing
            onClicked: AppController.refreshZernioConnections()
        },
        StudioButton {
            text: qsTr("Ngắt kết nối")
            variant: "danger"
            enabled: connectionCombo.currentIndex >= 0
                && !AppController.tiktokPublishBusy
                && !AppController.zernioAccountSyncing
            onClicked: {
                root.pendingDisconnectIndex = connectionCombo.currentIndex
                root.pendingDisconnectName = connectionCombo.textAt(connectionCombo.currentIndex)
                disconnectConfirmation.open()
            }
        },
        StudioButton {
            text: qsTr("Hủy")
            variant: "secondary"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Sử dụng")
            variant: "primary"
            enabled: connectionCombo.currentIndex >= 0
                && !AppController.tiktokPublishBusy
                && !AppController.zernioAccountSyncing
            onClicked: {
                if (AppController.selectZernioConnection(connectionCombo.currentIndex))
                    root.close()
            }
        }
    ]
}
