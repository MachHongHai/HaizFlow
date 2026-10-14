pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    required property int stepNumber
    required property string title
    required property string description
    default property alias actions: actionRow.data
    spacing: Theme.space8
    Text {
        Layout.fillWidth: true
        text: root.stepNumber + ". " + root.title
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.control
        font.weight: Font.DemiBold
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }
    Text {
        Layout.fillWidth: true
        text: root.description
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }
    RowLayout {
        id: actionRow
        spacing: Theme.space8
        visible: children.length > 0
    }
}
