import QtQuick
import QtMultimedia
import "."

Rectangle {
    id: root

    property real position: 0
    property real duration: 0
    property bool playing: false
    property alias videoOutput: fullscreenVideoOutput

    signal playbackToggled()
    signal scrubStarted(real position)
    signal scrubbed(real position)
    signal scrubFinished(real position)
    signal closeRequested()

    color: Theme.video

    VideoOutput {
        id: fullscreenVideoOutput
        anchors.fill: parent
        anchors.margins: Theme.space12
        fillMode: VideoOutput.PreserveAspectFit
    }

    PreviewTransport {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        position: root.position
        duration: root.duration
        playing: root.playing
        fullscreen: true
        onPlaybackToggled: root.playbackToggled()
        onScrubStarted: function(value) { root.scrubStarted(value) }
        onScrubbed: function(value) { root.scrubbed(value) }
        onScrubFinished: function(value) { root.scrubFinished(value) }
        onFullscreenRequested: root.closeRequested()
    }
}
