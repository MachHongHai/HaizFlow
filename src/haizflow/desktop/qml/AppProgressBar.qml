import QtQuick
import QtQuick.Controls.Basic
import "."

ProgressBar {
    id: root

    property bool active: false
    property bool stalled: false
    implicitHeight: 6
    from: 0
    to: 100
    onValueChanged: {
        stalled = false
        if (active) stallTimer.restart()
    }
    onActiveChanged: {
        stalled = false
        if (active) stallTimer.restart()
        else stallTimer.stop()
    }

    Timer {
        id: stallTimer
        interval: 1800
        onTriggered: root.stalled = root.active
    }

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
            width: root.visualPosition * parent.width
            height: parent.height
            radius: 3
            color: root.value >= root.to ? Theme.success : Theme.interactive
            Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        }

        Rectangle {
            visible: root.indeterminate || root.stalled
            width: Math.max(24, parent.width * 0.28)
            height: parent.height
            radius: 3
            color: Theme.interactive
            opacity: root.indeterminate ? 1 : 0.6
            transform: Translate { id: busyOffset }
            SequentialAnimation {
            running: (root.indeterminate || root.stalled) && root.visible
                loops: Animation.Infinite
                NumberAnimation {
                    target: busyOffset
                    property: "x"
                    from: -Math.max(24, root.width * 0.28)
                    to: root.width
                    duration: 1250
                    easing.type: Easing.InOutCubic
                }
            }
        }
    }
}
