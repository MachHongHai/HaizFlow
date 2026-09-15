pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtMultimedia
import "."

Item {
    id: root

    property url source
    property url thumbnailSource
    property bool inlineFrameReady: false
    property bool fullscreenFrameReady: false
    property bool fullscreen: false
    property bool scrubbing: false
    property bool resumeAfterScrub: false
    property bool priming: false
    property real primePosition: 0
    readonly property bool hasSource: String(source || "").length > 0
    readonly property bool playing: player.playbackState === MediaPlayer.PlayingState && !priming

    function togglePlayback() {
        primeSafetyTimer.stop();
        priming = false;
        previewAudio.muted = false;
        if (player.playbackState === MediaPlayer.PlayingState) {
            player.pause();
            return;
        }
        if (player.mediaStatus === MediaPlayer.EndOfMedia)
            player.position = 0;
        player.play();
    }

    function beginScrub(positionSeconds) {
        scrubbing = true;
        resumeAfterScrub = player.playbackState === MediaPlayer.PlayingState && !priming;
        player.pause();
        player.position = Math.round(positionSeconds * 1000);
    }

    function updateScrub(positionSeconds) {
        player.position = Math.round(positionSeconds * 1000);
    }

    function finishScrub(positionSeconds) {
        player.position = Math.round(positionSeconds * 1000);
        scrubbing = false;
        if (resumeAfterScrub)
            player.play();
        resumeAfterScrub = false;
    }

    function refreshPausedFrame() {
        if (!hasSource || player.playbackState === MediaPlayer.PlayingState)
            return;
        primePosition = player.position;
        priming = true;
        previewAudio.muted = true;
        player.play();
        primeSafetyTimer.restart();
    }

    function finishPrime() {
        if (!priming)
            return;
        primeSafetyTimer.stop();
        player.pause();
        player.position = primePosition;
        previewAudio.muted = false;
        priming = false;
    }

    function openFullscreen() {
        fullscreen = true;
        fullscreenPopup.open();
        Qt.callLater(refreshPausedFrame);
    }

    function closeFullscreen() {
        fullscreenPopup.close();
    }

    onSourceChanged: {
        inlineFrameReady = false;
        fullscreenFrameReady = false;
        priming = false;
    }

    Component.onDestruction: {
        primeSafetyTimer.stop();
        player.stop();
        player.source = "";
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.video

        VideoOutput {
            id: inlineOutput
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: inlineTransport.top
            fillMode: VideoOutput.PreserveAspectFit
            endOfStreamPolicy: VideoOutput.KeepLastFrame
        }

        Image {
            anchors.fill: inlineOutput
            source: root.thumbnailSource
            sourceSize.width: 960
            sourceSize.height: 540
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            visible: !root.inlineFrameReady && status === Image.Ready
        }

        PreviewTransport {
            id: inlineTransport
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            position: Number(player.position || 0) / 1000
            duration: Math.max(1, Number(player.duration || 0) / 1000)
            playing: root.playing
            onPlaybackToggled: root.togglePlayback()
            onScrubStarted: function(position) { root.beginScrub(position); }
            onScrubbed: function(position) { root.updateScrub(position); }
            onScrubFinished: function(position) { root.finishScrub(position); }
            onFullscreenRequested: root.openFullscreen()
        }
    }

    Popup {
        id: fullscreenPopup
        parent: Overlay.overlay
        x: 0
        y: 0
        width: parent ? parent.width : 0
        height: parent ? parent.height : 0
        padding: 0
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape

        background: Rectangle { color: Theme.video }

        onClosed: {
            root.fullscreen = false;
            Qt.callLater(root.refreshPausedFrame);
        }

        contentItem: Item {
            VideoOutput {
                id: fullscreenOutput
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: fullscreenTransport.top
                fillMode: VideoOutput.PreserveAspectFit
                endOfStreamPolicy: VideoOutput.KeepLastFrame
            }

            Image {
                anchors.fill: fullscreenOutput
                source: root.thumbnailSource
                sourceSize.width: 1920
                sourceSize.height: 1080
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                visible: !root.fullscreenFrameReady && status === Image.Ready
            }

            PreviewTransport {
                id: fullscreenTransport
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                position: Number(player.position || 0) / 1000
                duration: Math.max(1, Number(player.duration || 0) / 1000)
                playing: root.playing
                fullscreen: true
                onPlaybackToggled: root.togglePlayback()
                onScrubStarted: function(position) { root.beginScrub(position); }
                onScrubbed: function(position) { root.updateScrub(position); }
                onScrubFinished: function(position) { root.finishScrub(position); }
                onFullscreenRequested: root.closeFullscreen()
            }
        }
    }

    Connections {
        target: inlineOutput.videoSink
        enabled: !root.fullscreen

        function onVideoFrameChanged() {
            if (inlineOutput.videoSink.videoSize.width <= 0 || inlineOutput.videoSink.videoSize.height <= 0)
                return;
            root.inlineFrameReady = true;
            root.finishPrime();
        }
    }

    Connections {
        target: fullscreenOutput.videoSink
        enabled: root.fullscreen

        function onVideoFrameChanged() {
            if (fullscreenOutput.videoSink.videoSize.width <= 0 || fullscreenOutput.videoSink.videoSize.height <= 0)
                return;
            root.fullscreenFrameReady = true;
            root.finishPrime();
        }
    }

    AudioOutput {
        id: previewAudio
    }

    MediaPlayer {
        id: player
        source: root.source
        videoOutput: root.fullscreen ? fullscreenOutput : inlineOutput
        audioOutput: previewAudio

        onMediaStatusChanged: {
            if (mediaStatus === MediaPlayer.EndOfMedia) {
                player.pause();
                player.position = 0;
            }
        }
        onErrorOccurred: root.finishPrime()
    }

    Timer {
        id: primeSafetyTimer
        interval: 750
        repeat: false
        onTriggered: root.finishPrime()
    }
}
