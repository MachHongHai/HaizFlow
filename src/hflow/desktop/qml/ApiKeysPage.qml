pragma ComponentBehavior: Bound
// qmllint disable missing-property
import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root
    property string provider: "gemini"
    property bool editingKey: false
    readonly property bool zernio: provider === "zernio"
    readonly property var apiKeys: zernio ? AppController.zernioApiKeys : AppController.geminiApiKeys
    readonly property bool configured: apiKeys.length > 0
    readonly property bool credentialLocked: zernio && (AppController.zernioCredentialBusy
        || AppController.tiktokPublishBusy || AppController.zernioAccountSyncing)
    readonly property string checkResult: String(AppController.zernioCredentialResult || "")
    readonly property bool checkFinished: zernio && !AppController.zernioCredentialBusy
        && checkResult.length > 0
    onProviderChanged: { entryForm.clear(); editingKey = false; }
    onVisibleChanged: { if (!visible) { entryForm.clear(); editingKey = false; } }
    function zernioMessage() {
        if (AppController.zernioCredentialBusy) return qsTr("Đang kiểm tra kết nối…");
        switch (AppController.zernioCredentialResult) {
        case "verified": return qsTr("Kiểm tra thành công");
        case "format-error": return qsTr("Kiểm tra thất bại · Key chưa đầy đủ.");
        case "invalid": return qsTr("Kiểm tra thất bại · Key không hợp lệ hoặc đã bị thu hồi.");
        case "permissions": return qsTr("Kiểm tra thất bại · Key thiếu quyền đọc và ghi.");
        case "rate-limit": return qsTr("Kiểm tra thất bại · Zernio đang giới hạn yêu cầu.");
        case "unavailable": return qsTr("Kiểm tra thất bại · Chưa kết nối được Zernio.");
        case "storage-error": return qsTr("Lưu thất bại · Không thể lưu key trên máy.");
        default: return root.configured && !AppController.zernioApiKeyConfigured ? qsTr("Chọn key để kết nối tài khoản đăng bài.")
            : root.configured ? qsTr("Đã lưu key · Chưa kiểm tra kết nối")
            : qsTr("Chưa có key. Thêm key để kết nối tài khoản đăng bài.");
        }
    }
    Connections {
        target: AppController
        function onApiKeySettingsRequested(provider) { root.provider = provider; }
        function onApiKeyGuideRequested(provider) {
            root.provider = provider;
            Qt.callLater(function() {
                if (provider === "zernio") zernioGuideLoader.invoke("open", []);
                else geminiGuideLoader.invoke("open", []);
            });
        }
        function onGeminiSetupRequested() { root.provider = "gemini"; }
    }
    SettingsPageShell {
        anchors.fill: parent
        showHeader: false
        pageInset: 0
        horizontalInset: 0
        alignLeft: false
        contentMaximumWidth: 760
        contentSpacing: Theme.space20

        NavigationTabs {
            objectName: "apiKeyProviderSelector"
            options: [{ label: "Gemini", value: "gemini" }, { label: "Zernio", value: "zernio" }]
            currentValue: root.provider
            onActivated: function(value) { root.provider = value; }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space16
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: root.zernio ? qsTr("Zernio API key") : qsTr("Gemini API key")
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.title
                    font.weight: Font.DemiBold
                }
                Text {
                    Layout.fillWidth: true
                    text: root.zernio ? qsTr("Kết nối đăng bài. Chọn tài khoản trong dự án.")
                        : qsTr("Dịch bằng Gemini. Chọn model trong dự án.")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.body
                    wrapMode: Text.WordWrap
                }
            }
            StudioButton {
                objectName: "apiKeyGuideButton"
                text: qsTr("Hướng dẫn")
                onClicked: {
                    if (root.zernio) zernioGuideLoader.invoke("open", []);
                    else geminiGuideLoader.invoke("open", []);
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: !root.configured || root.zernio && root.editingKey && root.checkFinished
                && root.checkResult !== "verified"
            spacing: Theme.space8
            Text {
                objectName: "credentialStatus"
                Layout.fillWidth: true
                text: root.zernio ? root.zernioMessage() : qsTr("Chưa có key. Bạn vẫn có thể dùng model dịch cục bộ.")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.body
                wrapMode: Text.WordWrap
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space12
            visible: root.configured
            Repeater {
                model: root.apiKeys
                delegate: ApiKeyListRow {
                    required property var modelData
                    Layout.fillWidth: true
                    credential: modelData
                    zernio: root.zernio
                    locked: root.credentialLocked
                    onRemoveRequested: function(id, label) { removeLoader.invoke("confirm", [id, label, root.zernio]); }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: root.configured && !root.editingKey
            spacing: Theme.space8
            StudioButton {
                objectName: "editApiKeyButton"
                text: qsTr("Thêm key")
                enabled: !root.credentialLocked
                onClicked: root.editingKey = true
            }
            StudioButton {
                objectName: "checkAllZernioKeysButton"
                visible: root.zernio
                text: AppController.zernioCredentialBusy ? qsTr("Đang kiểm tra…") : qsTr("Kiểm tra kết nối")
                enabled: !root.credentialLocked
                onClicked: AppController.verifyZernioApiKey()
            }
        }
        ApiKeyEntryForm {
            id: entryForm
            objectName: "apiKeyEntryForm"
            Layout.fillWidth: true
            visible: root.editingKey || !root.configured
            zernio: root.zernio
            locked: root.credentialLocked
            onAccepted: root.editingKey = false
            onCancelled: root.editingKey = false
        }
        Item { Layout.preferredHeight: Theme.space16 }
    }
    LazyDialogLoader {
        id: geminiGuideLoader
        sourceComponent: Component { GeminiApiGuideDialog { onClosed: geminiGuideLoader.release() } }
    }
    LazyDialogLoader {
        id: zernioGuideLoader
        sourceComponent: Component {
            ZernioGuideDialog {
                onClosed: zernioGuideLoader.release()
            }
        }
    }
    LazyDialogLoader {
        id: removeLoader
        sourceComponent: Component {
            AppDialog {
                id: dialog
                property string keyId: ""
                property bool zernio: false
                function confirm(id, label, isZernio) { keyId = id; zernio = isZernio; subtitle = label; open(); }
                title: qsTr("Xóa API key?")
                preferredWidth: 440
                onClosed: removeLoader.release()
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Chỉ xóa key trên máy này. Dự án và tài khoản trên dịch vụ vẫn được giữ nguyên.")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    wrapMode: Text.WordWrap
                }
                footerActions: [
                    StudioButton { text: qsTr("Hủy"); onClicked: dialog.close() },
                    StudioButton {
                        text: qsTr("Xóa key")
                        variant: "danger"
                        onClicked: {
                            const removed = dialog.zernio ? AppController.removeZernioApiKey(dialog.keyId)
                                : AppController.removeGeminiApiKey(dialog.keyId);
                            if (removed) dialog.close();
                        }
                    }
                ]
            }
        }
    }
}
