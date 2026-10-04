pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

// Compatibility entry point for older cached QML. Credentials have one settings page.
AppDialog {
    id: root
    title: qsTr("Zernio API key")
    preferredWidth: 440
    function openForConfiguration() {
        AppController.requestApiKeySettings("zernio");
    }
    Text {
        Layout.fillWidth: true
        text: qsTr("Quản lý key trong Cài đặt → API Key → Zernio.")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        wrapMode: Text.WordWrap
    }
    footerActions: [
        StudioButton {
            text: qsTr("Mở Cài đặt")
            onClicked: {
                root.close();
                AppController.requestApiKeySettings("zernio");
            }
        }
    ]
}
