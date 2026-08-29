import QtQuick
import QtQuick.Controls.Basic
import "."

Switch {
    id: root

    spacing: Theme.space8
    font.family: Theme.fontFamily
    font.pixelSize: TypeScale.control
    focusPolicy: Qt.TabFocus
    Accessible.name: text

    indicator: Rectangle {
        implicitWidth: 38
        implicitHeight: 20
        radius: 10
        color: root.checked ? Theme.interactive : Theme.surfaceStrong
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? Theme.focus
            : root.checked ? Theme.interactiveOutline : Theme.outlineStrong

        Rectangle {
            x: root.checked ? parent.width - width - 3 : 3
            anchors.verticalCenter: parent.verticalCenter
            width: 14
            height: 14
            radius: 7
            color: root.checked ? Theme.textOnAccent : Theme.textMuted
        }
    }

    contentItem: Text {
        leftPadding: root.indicator.width + root.spacing
        text: root.text
        color: root.enabled ? Theme.text : Theme.textDisabled
        font: root.font
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
    }
}
