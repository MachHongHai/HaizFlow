import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property string message: ""
    property string confirmText: qsTr("Xác nhận")
    property string confirmTone: "primary"
    property bool closeOnConfirm: true
    property bool busy: false
    signal confirmed()

    dismissible: !busy

    preferredWidth: 440
    maximumWidth: 520

    Text {
        Layout.fillWidth: true
        text: root.message
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.control
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }

    footerActions: [
        StudioButton {
            objectName: "confirmationCancelButton"
            text: qsTr("Hủy")
            variant: "ghost"
            enabled: !root.busy
            onClicked: root.reject()
        },
        StudioButton {
            objectName: "confirmationConfirmButton"
            text: root.busy ? qsTr("Đang xóa…") : root.confirmText
            variant: root.confirmTone
            enabled: !root.busy
            onClicked: {
                const shouldClose = root.closeOnConfirm;
                if (!shouldClose)
                    root.busy = true;
                root.confirmed()
                if (shouldClose)
                    root.accept()
            }
        }
    ]
}
