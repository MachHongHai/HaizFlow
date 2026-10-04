pragma ComponentBehavior: Bound
// qmllint disable missing-property
import QtQuick
import QtQuick.Layouts
import "."

SettingsGroup {
    id: root
    property bool zernio: false
    property bool replacing: false
    property bool locked: false
    property bool keyVisible: false
    signal accepted()
    signal cancelled()
    title: replacing ? qsTr("Thay API key") : qsTr("Thêm API key")
    function clear() { nameInput.clear(); keyInput.clear(); keyVisible = false; }
    onVisibleChanged: { if (!visible) clear(); }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space8
        SettingLabel { Layout.fillWidth: true; text: qsTr("Tên key") }
        AppTextField {
            id: nameInput
            objectName: "apiKeyNameInput"
            Layout.fillWidth: true
            placeholderText: qsTr("Ví dụ: Cá nhân")
            accessibleName: qsTr("Tên API key")
            maximumLength: 64
            enabled: !root.locked
        }
        SettingLabel { Layout.fillWidth: true; Layout.topMargin: Theme.space4; text: qsTr("API key") }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            AppTextField {
                id: keyInput
                objectName: "apiKeySecretInput"
                Layout.fillWidth: true
                enabled: !root.locked
                placeholderText: root.zernio ? qsTr("Dán Zernio API key") : qsTr("Dán Gemini API key")
                accessibleName: root.zernio ? qsTr("Zernio API key") : qsTr("Gemini API key")
                echoMode: root.keyVisible ? TextInput.Normal : TextInput.Password
                inputMethodHints: Qt.ImhHiddenText | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
            }
            StudioButton {
                text: root.keyVisible ? qsTr("Ẩn") : qsTr("Hiện")
                toolTipText: root.keyVisible ? qsTr("Ẩn API key") : qsTr("Hiện API key")
                enabled: keyInput.text.length > 0
                onClicked: root.keyVisible = !root.keyVisible
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space8
            spacing: Theme.space8
            StudioButton {
                objectName: "saveApiKeyButton"
                text: root.zernio ? qsTr("Kiểm tra và lưu") : qsTr("Lưu và sử dụng")
                variant: "primary"
                enabled: !root.locked && keyInput.text.trim().length > 0
                    && nameInput.text.trim().length > 0
                onClicked: {
                    const saved = root.zernio ? AppController.addZernioApiKey(nameInput.text, keyInput.text)
                        : AppController.addGeminiApiKey(nameInput.text, keyInput.text);
                    if (saved) { root.clear(); root.accepted(); }
                }
            }
            StudioButton {
                text: qsTr("Hủy")
                enabled: !root.locked
                onClicked: { root.clear(); root.cancelled(); }
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space4
            text: qsTr("Lưu trên máy bằng Windows Credential Manager.")
            color: Theme.textSubtle
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.WordWrap
        }
    }
}
