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
    focusPolicy: Qt.StrongFocus
    selectByMouse: true
    inputMethodHints: Qt.ImhNoPredictiveText
    Accessible.name: accessibleName.length > 0 ? accessibleName : placeholderText

    property string accessibleName: ""
    readonly property bool keyboardFocus: activeFocus && (focusReason === Qt.TabFocusReason
        || focusReason === Qt.BacktabFocusReason || focusReason === Qt.ShortcutFocusReason)

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.enabled ? Theme.input : Theme.surfaceMuted
        border.width: root.keyboardFocus ? 2 : 1
        border.color: root.keyboardFocus ? Theme.controlFocus
            : root.activeFocus || root.hovered ? Theme.outlineStrong : Theme.outline
    }
}
