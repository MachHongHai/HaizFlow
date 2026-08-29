import QtQuick
import "."

Rectangle {
    id: root

    property real value: 0
    property bool indeterminate: false

    implicitHeight: 3
    color: Theme.outline
    clip: true

    Rectangle {
        id: indicator
        height: parent.height
        width: root.indeterminate ? parent.width * 0.28
            : parent.width * Math.max(0, Math.min(1, root.value))
        x: root.indeterminate ? -width : 0
        color: Theme.interactive

        XAnimator {
            target: indicator
            from: -indicator.width
            to: root.width
            duration: 1100
            loops: Animation.Infinite
            running: root.visible && root.indeterminate
        }
    }
}
