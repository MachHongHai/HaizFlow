import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property string tone: "default"
    property int padding: Theme.space16
    property int spacing: Theme.space12
    default property alias content: contentColumn.data

    color: tone === "raised" ? Theme.surfaceElevated
        : tone === "muted" ? Theme.surfaceMuted : Theme.surface
    border.width: 1
    border.color: Theme.outline
    radius: Theme.radius
    implicitHeight: contentColumn.implicitHeight + padding * 2

    ColumnLayout {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: root.padding
        spacing: root.spacing
    }
}
