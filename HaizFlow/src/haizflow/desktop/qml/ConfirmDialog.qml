import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property string message: ""
    property string confirmText: qsTr("Xác nhận")
    property string confirmTone: "primary"
    signal confirmed()

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
        AppButton {
            text: qsTr("Hủy")
            onClicked: root.reject()
        },
        AppButton {
            text: root.confirmText
            tone: root.confirmTone
            onClicked: {
                root.confirmed()
                root.accept()
            }
        }
    ]
}
