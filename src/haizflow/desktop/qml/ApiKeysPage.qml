pragma ComponentBehavior: Bound
// qmllint disable missing-property

import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root
    property bool keyVisible: false
    property bool focusRequested: false
    onVisibleChanged: {
        if (visible && focusRequested) {
            focusRequested = false
            Qt.callLater(function() { keyInput.forceActiveFocus(); })
        }
    }

    Connections {
        target: AppController
        function onGeminiSetupRequested() {
            root.focusRequested = true;
            if (root.visible) {
                root.focusRequested = false;
                Qt.callLater(function() { keyInput.forceActiveFocus(); });
            }
        }
    }

    SettingsPageShell {
        anchors.fill: parent
        title: qsTr("API Key")
        showHeader: false
        contentMaximumWidth: 920

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space16
            Layout.bottomMargin: Theme.space12
            spacing: Theme.space12
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Gemini API Key")
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.section
                    font.weight: Font.DemiBold
                }
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Lưu nhiều key trên máy và chọn key dùng để dịch trong các dự án.")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    wrapMode: Text.WordWrap
                }
            }
            StudioButton {
                text: qsTr("Hướng dẫn")
                variant: "secondary"
                onClicked: guideLoader.invoke("open", [])
            }
        }

        Text {
            Layout.fillWidth: true
            visible: AppController.geminiApiKeys.length === 0
            text: qsTr("Chưa có key. Thêm một key từ Google AI Studio để bắt đầu.")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            wrapMode: Text.WordWrap
        }

        Repeater {
            model: AppController.geminiApiKeys
            delegate: Rectangle {
                id: keyRow
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 64
                color: modelData.active ? Theme.interactiveMuted : Theme.surface
                radius: Theme.radiusSmall
                border.width: 1
                border.color: modelData.active ? Theme.interactiveOutline : Theme.outline
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space16
                    anchors.rightMargin: Theme.space12
                    spacing: Theme.space12
                    Text {
                        Layout.fillWidth: true
                        text: keyRow.modelData.label
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.control
                        elide: Text.ElideRight
                    }
                    Text {
                        visible: keyRow.modelData.active
                        text: qsTr("Đang dùng")
                        color: Theme.success
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.label
                    }
                    StudioButton {
                        visible: !keyRow.modelData.active
                        text: qsTr("Sử dụng")
                        variant: "secondary"
                        onClicked: AppController.selectGeminiApiKey(keyRow.modelData.id)
                    }
                    StudioButton {
                        text: qsTr("Xóa")
                        variant: "danger"
                        onClicked: removeLoader.invoke("confirm", [keyRow.modelData.id, keyRow.modelData.label])
                    }
                }
            }
        }

        SettingsSectionHeader {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space24
            title: qsTr("Thêm key")
        }
        Text {
            Layout.fillWidth: true
            text: qsTr("Tên key")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
        }
        AppTextField {
            id: nameInput
            Layout.fillWidth: true
            placeholderText: qsTr("Tên để phân biệt, ví dụ: Cá nhân")
            accessibleName: qsTr("Tên API key")
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space8
            text: qsTr("API key")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
        }
        AppTextField {
            id: keyInput
            Layout.fillWidth: true
            placeholderText: qsTr("Dán Gemini API key")
            accessibleName: qsTr("Gemini API key")
            echoMode: root.keyVisible ? TextInput.Normal : TextInput.Password
            inputMethodHints: Qt.ImhHiddenText | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space8
            spacing: Theme.space8
            StudioButton {
                text: root.keyVisible ? qsTr("Ẩn") : qsTr("Hiện")
                variant: "secondary"
                enabled: keyInput.text.length > 0
                onClicked: root.keyVisible = !root.keyVisible
            }
            Item { Layout.fillWidth: true }
            StudioButton {
                text: qsTr("Lưu và sử dụng")
                variant: "primary"
                enabled: nameInput.text.trim().length > 0 && keyInput.text.trim().length > 0
                onClicked: {
                    if (AppController.addGeminiApiKey(nameInput.text, keyInput.text)) {
                        nameInput.clear();
                        keyInput.clear();
                        root.keyVisible = false;
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space20
            text: qsTr("Key được lưu trong Windows Credential Manager, không nằm trong tệp dự án. HaizFlow chỉ gửi câu thoại theo lô, không gửi video hoặc âm thanh. Gemini 3.1 Flash-Lite là lựa chọn chi phí thấp; giá và quota do Google quản lý.")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            wrapMode: Text.WordWrap
        }
    }

    LazyDialogLoader {
        id: guideLoader
        parent: root
        sourceComponent: Component {
            GeminiApiGuideDialog { onClosed: guideLoader.release() }
        }
    }
    LazyDialogLoader {
        id: removeLoader
        parent: root
        sourceComponent: Component {
            AppDialog {
                id: dialog
                property string keyId: ""
                function confirm(id, label) {
                    keyId = id;
                    subtitle = label;
                    open();
                }
                title: qsTr("Xóa API key?")
                preferredWidth: 440
                onClosed: removeLoader.release()
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Key này sẽ bị xóa khỏi Windows Credential Manager. Các key khác vẫn được giữ nguyên.")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    wrapMode: Text.WordWrap
                }
                footerActions: [
                    StudioButton { text: qsTr("Hủy"); variant: "secondary"; onClicked: dialog.close() },
                    StudioButton {
                        text: qsTr("Xóa key")
                        variant: "danger"
                        onClicked: {
                            AppController.removeGeminiApiKey(dialog.keyId);
                            dialog.close();
                        }
                    }
                ]
            }
        }
    }
}
