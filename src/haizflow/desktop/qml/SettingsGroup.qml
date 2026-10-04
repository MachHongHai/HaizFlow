pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    property string title: ""
    default property alias content: rows.data
    implicitHeight: rows.implicitHeight + Theme.space32
    color: Theme.surface
    radius: Theme.radius
    border.color: Theme.divider
    ColumnLayout {
        id: rows
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.space16
        spacing: Theme.space20
        Text {
            Layout.fillWidth: true
            text: root.title
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.section
            font.weight: Font.DemiBold
        }
    }
}
