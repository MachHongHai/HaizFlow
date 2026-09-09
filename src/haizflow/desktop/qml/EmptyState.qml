import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property string iconName: "projects"
    property string title: ""
    property string message: ""
    default property alias actions: actionArea.data

    spacing: Theme.space8

    Rectangle {
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: 44
        Layout.preferredHeight: 44
        radius: Theme.radius
        color: Theme.interactiveMuted

        FluentIcon {
            anchors.centerIn: parent
            width: 22
            height: 22
            name: root.iconName
            iconColor: Theme.interactive
            iconSize: 21
        }
    }

    Text {
        Layout.fillWidth: true
        text: root.title
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.section
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
    }

    Text {
        Layout.fillWidth: true
        Layout.maximumWidth: 440
        Layout.alignment: Qt.AlignHCenter
        text: root.message
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.control
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }

    RowLayout {
        id: actionArea
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: Theme.space4
        spacing: Theme.space8
    }
}
