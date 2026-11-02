pragma ComponentBehavior: Bound
// qmllint disable missing-property
import QtQuick
import QtQuick.Layouts
import "."

SettingsGroup {
    id: root
    property string provider: "openai"
    property bool keyVisible: false
    signal accepted()
    signal cancelled()
    title: qsTr("Thêm API key")
    function clear() {
        nameInput.clear(); keyInput.clear(); endpointInput.clear();
        keyVisible = false;
    }
    onProviderChanged: clear()
    onVisibleChanged: { if (!visible) clear(); }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space8
        SettingLabel { Layout.fillWidth: true; text: qsTr("Tên kết nối") }
        AppTextField {
            id: nameInput
            objectName: "translationApiNameInput"
            Layout.fillWidth: true
            maximumLength: 64
            placeholderText: qsTr("Tên để phân biệt API key")
            accessibleName: qsTr("Tên kết nối dịch")
        }
        SettingLabel { Layout.fillWidth: true; text: qsTr("API key") }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            AppTextField {
                id: keyInput
                objectName: "translationApiSecretInput"
                Layout.fillWidth: true
                placeholderText: qsTr("Dán API key của nhà cung cấp")
                accessibleName: qsTr("API key dịch")
                echoMode: root.keyVisible ? TextInput.Normal : TextInput.Password
                inputMethodHints: Qt.ImhHiddenText | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                maximumLength: 4096
            }
            StudioButton {
                text: root.keyVisible ? qsTr("Ẩn") : qsTr("Hiện")
                enabled: keyInput.text.length > 0
                onClicked: root.keyVisible = !root.keyVisible
            }
        }
        SettingLabel { Layout.fillWidth: true; visible: root.provider === "custom"; text: "Base URL" }
        AppTextField {
            id: endpointInput
            objectName: "translationApiEndpointInput"
            Layout.fillWidth: true
            visible: root.provider === "custom"
            placeholderText: "https://api.example.com/v1"
            accessibleName: qsTr("Base URL của API dịch")
            maximumLength: 500
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space8
            spacing: Theme.space8
            StudioButton {
                objectName: "saveTranslationApiButton"
                text: qsTr("Lưu key")
                variant: "primary"
                enabled: nameInput.text.trim().length > 0 && keyInput.text.trim().length > 0
                    && (root.provider !== "custom" || endpointInput.text.trim().length > 0)
                onClicked: {
                    if (AppController.translationApi.addCredential(root.provider, nameInput.text,
                            keyInput.text, endpointInput.text)) {
                        root.clear(); root.accepted();
                    }
                }
            }
            StudioButton { text: qsTr("Hủy"); onClicked: { root.clear(); root.cancelled(); } }
        }
    }
}
