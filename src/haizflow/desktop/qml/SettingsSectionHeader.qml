import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property string title: ""
    property string description: ""

    spacing: Theme.space4

    Text {
        Layout.fillWidth: true
        text: root.title
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.section
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

    Rectangle {
        Layout.fillWidth: true
        Layout.topMargin: Theme.space8
        Layout.preferredHeight: 1
        color: Theme.divider
    }
}
