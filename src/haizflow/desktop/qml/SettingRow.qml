import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root
    property string label: ""
    property string description: ""
    default property alias control: controlArea.data
    spacing: Theme.space24

    ColumnLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: 2
        Text {
            Layout.fillWidth: true
            text: root.label
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: root.description.length > 0
            text: root.description
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
    }
    RowLayout {
        id: controlArea
        Layout.alignment: Qt.AlignVCenter
        spacing: Theme.space8
    }
}
