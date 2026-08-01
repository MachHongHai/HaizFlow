import QtQuick
import QtQuick.Controls.Basic
import "."

ProgressBar {
    id: root

    property string tone: "default"

    implicitHeight: 6
    from: 0
    to: 100

    background: Rectangle {
        implicitHeight: 6
        radius: 3
        color: root.tone === "blue" ? Theme.blueMuted
            : root.tone === "violet" ? Theme.violetMuted
            : Theme.surfaceStrong
    }

    contentItem: Item {
        implicitHeight: 6
        clip: true

        Rectangle {
            width: root.visualPosition * parent.width
            height: parent.height
            radius: 3
            color: root.value >= root.to ? Theme.success
                : root.tone === "blue" ? Theme.blue
                : root.tone === "violet" ? Theme.violet
                : Theme.interactive

            Behavior on width {
                NumberAnimation { duration: Theme.motionStandard; easing.type: Easing.OutCubic }
            }
            Behavior on color {
                ColorAnimation { duration: Theme.motionStandard }
            }
        }
    }
}
