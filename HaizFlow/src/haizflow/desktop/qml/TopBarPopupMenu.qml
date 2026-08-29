import QtQuick
import QtQuick.Controls.Basic
import "."

Menu {
    id: root

    property real menuContentWidth: 0

    width: Math.min(menuContentWidth + padding * 2, 210)
    modal: false
    padding: Theme.space4
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside

    background: Rectangle {
        radius: Theme.radiusSmall
        color: Theme.surface
        border.width: 0
    }
}
