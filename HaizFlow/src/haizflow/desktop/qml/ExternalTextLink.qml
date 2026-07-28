import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: root

    property url destination

    implicitWidth: linkLabel.implicitWidth
    implicitHeight: linkLabel.implicitHeight
    padding: 0
    activeFocusOnTab: true
    Accessible.name: text

    contentItem: Text {
        id: linkLabel

        text: root.text
        color: root.hovered || root.activeFocus ? Theme.interactiveHover : Theme.interactive
        font.pixelSize: Theme.caption
        font.underline: root.hovered || root.activeFocus
        textFormat: Text.PlainText
    }

    background: Item {}

    onClicked: AppController.openExternalUrl(root.destination.toString())
}
