import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string title: ""
    property string subtitle: ""
    default property alias actions: actionArea.data

    spacing: Theme.space12

    ColumnLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: 2

        Text {
            Layout.fillWidth: true
            text: root.title
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.section
            font.weight: Font.DemiBold
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }

        Text {
            Layout.fillWidth: true
            visible: root.subtitle.length > 0
            text: root.subtitle
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }
    }

    RowLayout {
        id: actionArea
        spacing: Theme.space8
    }
}
