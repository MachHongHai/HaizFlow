import QtQuick
import QtQuick.Controls.Basic
import "."

TextField {
    id: root

    implicitHeight: UiMetrics.controlHeight
    leftPadding: 12
    rightPadding: 12
    color: Theme.text
    selectionColor: Theme.interactive
    selectedTextColor: Theme.textOnAccent
    placeholderTextColor: Theme.textSubtle
    font.family: Theme.fontFamily
    font.pixelSize: TypeScale.control
    focusPolicy: Qt.TabFocus
    Accessible.name: accessibleName.length > 0 ? accessibleName : placeholderText

    property string accessibleName: ""

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.enabled ? Theme.input : Theme.surfaceMuted
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? Theme.focus
            : root.hovered ? Theme.outlineStrong : Theme.outline
    }
}
