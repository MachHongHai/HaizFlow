import QtQuick
import QtQuick.Controls.Basic
import "."

Slider {
    id: root

    implicitHeight: 30
    activeFocusOnTab: true
    property bool animateValueChanges: true

    background: Rectangle {
        x: root.leftPadding
        y: root.topPadding + root.availableHeight / 2 - height / 2
        width: root.availableWidth
        height: 4
        radius: 2
        color: Theme.surfaceStrong

        Rectangle {
            width: root.visualPosition * parent.width
            height: parent.height
            radius: 2
            color: root.enabled ? Theme.interactive : Theme.textDisabled
        }
    }

    handle: Rectangle {
        x: root.leftPadding + root.visualPosition * (root.availableWidth - width)
        y: root.topPadding + root.availableHeight / 2 - height / 2
        implicitWidth: root.pressed || root.hovered ? 18 : 16
        implicitHeight: implicitWidth
        radius: width / 2
        color: root.enabled ? Theme.text : Theme.textDisabled
        border.width: root.activeFocus ? 3 : 2
        border.color: root.activeFocus ? Theme.focus : Theme.interactive
    }
}
