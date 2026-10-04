import QtQuick
import QtQuick.Controls.Basic
import "."

ProgressBar {
    id: root

    property bool active: false
    implicitHeight: 6
    from: 0
    to: 100

    background: Rectangle {
        implicitHeight: 6
        radius: 3
        color: Theme.surfaceStrong
    }

    contentItem: Item {
        implicitHeight: 6
        clip: true

        Rectangle {
            visible: !root.indeterminate
            width: parent.width
            height: parent.height
            radius: 3
            color: root.value >= root.to ? Theme.success : Theme.interactive
            transform: Scale {
                origin.x: 0
                origin.y: 0
                xScale: root.visualPosition
                Behavior on xScale {
                    enabled: Theme.motionEnabled && root.visible && !root.indeterminate
                    NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
                }
            }
        }

        Rectangle {
            id: busyFill
            visible: root.indeterminate
            width: Math.max(24, parent.width * 0.28)
            height: parent.height
            radius: 3
            color: Theme.interactive
            x: (parent.width - width) / 2
            XAnimator {
                target: busyFill
                running: root.indeterminate && root.visible && Theme.motionEnabled
                loops: Animation.Infinite
                from: -Math.max(24, root.width * 0.28)
                to: root.width
                duration: 1400
                easing.type: Easing.Linear
            }
        }
    }
}
