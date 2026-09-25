import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property string directory: ""
    property bool managed: false
    property bool selectionEnabled: true
    signal chooseRequested()

    spacing: Theme.space4

    Text {
        text: qsTr("Lưu vào")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        textFormat: Text.PlainText
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: root.directory.length > 0 ? root.directory : qsTr("Chưa chọn thư mục")
            color: root.directory.length > 0 ? Theme.text : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            elide: Text.ElideMiddle
            textFormat: Text.PlainText
        }

        StudioButton {
            visible: !root.managed
            text: qsTr("Chọn thư mục")
            enabled: root.selectionEnabled
            onClicked: root.chooseRequested()
        }
    }
}
