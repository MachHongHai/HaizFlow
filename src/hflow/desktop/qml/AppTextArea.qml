import QtQuick
import QtQuick.Controls.Basic
import "."

TextArea {
    id: root

    property string accessibleName: ""
    readonly property bool keyboardFocus: activeFocus && (focusReason === Qt.TabFocusReason
        || focusReason === Qt.BacktabFocusReason || focusReason === Qt.ShortcutFocusReason)

    leftPadding: 12
    rightPadding: 12
    topPadding: 10
    bottomPadding: 10
    color: Theme.text
    selectionColor: Theme.interactive
    selectedTextColor: Theme.textOnAccent
    placeholderTextColor: Theme.textSubtle
    font.family: Theme.fontFamily
    font.pixelSize: TypeScale.control
    wrapMode: TextEdit.Wrap
    focusPolicy: Qt.StrongFocus
    selectByMouse: true
    textFormat: TextEdit.PlainText
    inputMethodHints: Qt.ImhNoPredictiveText
    Accessible.name: accessibleName.length > 0 ? accessibleName : placeholderText

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.enabled ? Theme.input : Theme.surfaceMuted
        border.width: root.keyboardFocus ? 2 : 1
        border.color: root.keyboardFocus ? Theme.controlFocus
            : root.activeFocus || root.hovered ? Theme.outlineStrong : Theme.outline
    }
}
