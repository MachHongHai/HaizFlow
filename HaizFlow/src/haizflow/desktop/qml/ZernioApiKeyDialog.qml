pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property bool keyVisible: false

    preferredWidth: 540
    maximumWidth: 580
    title: qsTr("Quản lý API key")

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

    InlineBanner {
        Layout.fillWidth: true
        tone: AppController.zernioApiKeyVerified ? "success"
            : AppController.zernioApiKeyConfigured ? "warning" : "info"
        title: AppController.zernioApiKeyVerified
            ? qsTr("API key đã được xác thực")
            : AppController.zernioApiKeyConfigured
                ? qsTr("API key đã lưu; cần xác thực")
                : qsTr("Chưa lưu API key")
        message: qsTr("Lưu trong Windows Credential Manager")

        StudioButton {
            visible: AppController.zernioApiKeyConfigured
            enabled: !AppController.tiktokPublishBusy
                && !AppController.zernioAccountSyncing
            text: qsTr("Xóa")
            variant: "danger"
            onClicked: {
                if (AppController.clearZernioApiKey()) {
                    apiKeyInput.clear()
                    root.keyVisible = false
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            text: qsTr("Tạo key đọc-ghi trên Zernio rồi dán đầy đủ vào bên dưới. Zernio chỉ hiển thị key một lần.")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }

        StudioButton {
            text: qsTr("Mở trang API key")
            variant: "ghost"
            onClicked: AppController.openZernioApiKeys()
        }
    }

    SettingLabel {
        Layout.fillWidth: true
        text: AppController.zernioApiKeyConfigured
            ? qsTr("API key thay thế") : qsTr("API key")
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        StudioField {
            id: apiKeyInput
            Layout.fillWidth: true
            echoMode: root.keyVisible ? TextInput.Normal : TextInput.Password
            passwordMaskDelay: 0
            inputMethodHints: Qt.ImhHiddenText | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
            placeholderText: AppController.zernioApiKeyConfigured
                ? qsTr("Dán key thay thế") : "sk_..."
            accessibleName: qsTr("API key")
            selectByMouse: true
        }

        StudioIconButton {
            iconName: root.keyVisible ? "hide" : "show"
            toolTipText: root.keyVisible ? qsTr("Ẩn") : qsTr("Hiện")
            enabled: apiKeyInput.text.length > 0
            onClicked: root.keyVisible = !root.keyVisible
        }
    }

    InlineBanner {
        Layout.fillWidth: true
        tone: "warning"
        message: qsTr("Không chia sẻ API key này.")
    }

    footerActions: [
        StudioButton {
            text: qsTr("Đóng")
            variant: "ghost"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Lưu và xác thực")
            variant: "primary"
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
    ]
}
