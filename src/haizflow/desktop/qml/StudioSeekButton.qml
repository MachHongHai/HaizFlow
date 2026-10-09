import QtQuick
import QtQuick.Shapes
import "."

IconButton {
    id: root

    required property int offsetSeconds
    readonly property color seekColor: !enabled ? Theme.textDisabled
        : hovered || visualFocus ? Theme.text : Theme.textMuted

    controlSize: 40
    padding: 6
    showToolTip: false
    toolTipText: offsetSeconds < 0 ? qsTr("Tua lùi %1 giây").arg(-offsetSeconds)
        : qsTr("Tua tới %1 giây").arg(offsetSeconds)

    contentItem: Item {
        Accessible.ignored: true

        Shape {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            width: 24
            height: 12
            transform: Scale {
                origin.x: 12
                xScale: root.offsetSeconds < 0 ? -1 : 1
            }
            ShapePath {
                strokeColor: root.seekColor
                strokeWidth: 1.6
                capStyle: ShapePath.RoundCap
                joinStyle: ShapePath.RoundJoin
                fillColor: "transparent"
                PathSvg { path: "M 3 10 C 3 2 17 2 20 10 M 20 4 L 20 10 L 14 10" }
            }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            text: Math.abs(root.offsetSeconds)
            color: root.seekColor
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
            Accessible.ignored: true
        }
    }
}
