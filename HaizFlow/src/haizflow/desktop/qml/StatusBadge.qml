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
    readonly property color foreground: status === "done" || status === "success" ? Theme.success
        : status === "failed" || status === "error" ? Theme.danger
        : status === "processing" || status === "paused" ? Theme.warning
        : Theme.textMuted
    readonly property color fill: status === "done" || status === "success" ? Theme.successMuted
        : status === "failed" || status === "error" ? Theme.dangerMuted
        : status === "processing" || status === "paused" ? Theme.warningMuted
        : Theme.surfaceMuted

    implicitWidth: badgeContent.implicitWidth + 16
    implicitHeight: 24
    radius: 12
    color: fill

    RowLayout {
        id: badgeContent
        anchors.centerIn: parent
        spacing: 5

        FluentIcon {
            Layout.preferredWidth: root.iconName.length > 0 ? 12 : 0
            Layout.preferredHeight: 12
            visible: root.iconName.length > 0
            name: root.iconName
            iconColor: root.foreground
            iconSize: 11
        }

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
