import QtQuick
import "."

Rectangle {
    id: root

    property real value: 0
    property bool indeterminate: false
    property real sweepPhase: 0.5

    implicitHeight: 3
    color: Theme.outline
    clip: true

    Rectangle {
        id: indicator
        height: parent.height
        width: root.indeterminate ? parent.width * 0.28
            : parent.width * Math.max(0, Math.min(1, root.value))
        x: root.indeterminate ? -width + (root.width + width) * root.sweepPhase : 0
        color: Theme.interactive

        NumberAnimation {
            target: root
            property: "sweepPhase"
            from: 0
            to: 1
            duration: 1100
            loops: Animation.Infinite
            running: root.visible && root.indeterminate && Theme.motionEnabled
            easing.type: Easing.Linear
        }
    }
}
