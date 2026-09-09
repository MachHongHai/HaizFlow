import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    default property alias actions: actionArea.data
    property string statusText: ""

    implicitHeight: Theme.commandBarHeight
    color: Theme.surfaceElevated
    border.width: 1
    border.color: Theme.outline
    radius: Theme.radiusSmall

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space16
        anchors.rightMargin: Theme.space12
        spacing: Theme.space12
        Text {
            Layout.fillWidth: true
            text: root.statusText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }
        RowLayout { id: actionArea; spacing: Theme.space8 }
    }
}
