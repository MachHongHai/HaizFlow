import QtQuick
import "."

Rectangle {
    id: root

    property string status: "pending"
    property string label: status

    readonly property color statusColor: TaskPresentation.foreground(status)
    readonly property color statusBackground: TaskPresentation.background(status)

    implicitWidth: content.implicitWidth + 20
    implicitHeight: 26
    radius: Theme.radiusSmall
    color: statusBackground
    border.width: 0

    Row {
        id: content
        anchors.centerIn: parent
        spacing: 7

        Rectangle {
            width: 6
            height: 6
            radius: 3
            anchors.verticalCenter: parent.verticalCenter
            color: root.statusColor
        }

        Text {
            text: root.label
            color: root.statusColor
            font.pixelSize: Theme.label
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }
    }
}
