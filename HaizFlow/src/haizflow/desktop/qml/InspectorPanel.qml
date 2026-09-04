import QtQuick
import QtQuick.Layouts
import "."

AppSurface {
    id: root

    property string title: ""
    property string subtitle: ""
    default property alias inspectorContent: inspectorBody.data

    tone: "default"
    padding: Theme.space12
    spacing: Theme.space12

    SectionHeader {
        Layout.fillWidth: true
        title: root.title
        subtitle: root.subtitle
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: Theme.divider
    }

    ColumnLayout {
        id: inspectorBody
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: Theme.space12
    }
}
