import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property string status: "ready"
    property string label: status
    property string iconName: status === "done" || status === "success" ? "success"
        : status === "failed" || status === "error" ? "error"
        : status === "processing" ? "info" : ""
    readonly property color foreground: TaskPresentation.foreground(status)
    readonly property color fill: TaskPresentation.background(status)

    implicitWidth: badgeContent.implicitWidth + 16
    implicitHeight: 24
    radius: 12
    color: fill

    RowLayout {
        id: badgeContent
        anchors.centerIn: parent
        spacing: 5

        Text {
            text: root.label
            color: root.foreground
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }
    }
}
