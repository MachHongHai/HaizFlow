import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property real position: 0
    property real duration: 1
    property bool playing: false
    property bool fullscreen: false
    property bool showFullscreen: true

    signal playbackToggled()
    signal scrubStarted(real position)
    signal scrubbed(real position)
    signal scrubFinished(real position)
    signal fullscreenRequested()

    implicitHeight: 48
    color: Theme.codeSurface

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space12
        anchors.rightMargin: Theme.space12
        spacing: Theme.space8

        IconButton {
            glyph: root.playing ? "\uE769" : "\uE768"
            toolTipText: root.playing ? qsTr("Tạm dừng") : qsTr("Phát")
            Accessible.name: toolTipText
            onClicked: root.playbackToggled()
        }

        TimecodeLabel {
            Layout.preferredWidth: 78
            seconds: root.position
        }

        Slider {
            id: seekSlider
            Layout.fillWidth: true
            from: 0
            to: Math.max(1, root.duration)
            value: root.position
            activeFocusOnTab: true
            Accessible.name: qsTr("Vị trí xem trước")
            onMoved: root.scrubbed(value)
            onPressedChanged: {
                if (pressed)
                    root.scrubStarted(value)
                else
                    root.scrubFinished(value)
            }
        }

        TimecodeLabel {
            Layout.preferredWidth: 78
            seconds: root.duration
            horizontalAlignment: Text.AlignRight
            color: Theme.textMuted
        }

        IconButton {
            visible: root.showFullscreen
            glyph: root.fullscreen ? "\uE73F" : "\uE740"
            toolTipText: root.fullscreen ? qsTr("Thoát toàn màn hình") : qsTr("Xem toàn màn hình")
            Accessible.name: toolTipText
            onClicked: root.fullscreenRequested()
        }
    }
}
