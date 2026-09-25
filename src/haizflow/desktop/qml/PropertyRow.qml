import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string label: ""
    property string description: ""
    property alias contentItem: contentSlot.data

    spacing: Theme.space12
    Layout.fillWidth: true
    Layout.minimumHeight: Math.max(40, labels.implicitHeight)

    ColumnLayout {
        id: labels
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignVCenter
        spacing: 2

        Text {
            Layout.fillWidth: true
            text: root.label
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
        }

        Text {
            Layout.fillWidth: true
            visible: root.description.length > 0
            text: root.description
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
        }
    }

    RowLayout {
        id: contentSlot
        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
        spacing: Theme.space4
    }
}
