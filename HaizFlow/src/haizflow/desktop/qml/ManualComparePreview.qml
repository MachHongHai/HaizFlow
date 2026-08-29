pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "."

Rectangle {
    id: root

    property url inputSource: ""
    property url resultSource: ""
    property url resultAudioSource: ""
    property url thumbnailSource: ""
    property bool previewBusy: false
    property real previewProgress: 0
    property bool inputMuted: true
    property bool resultMuted: false
    property bool synchronizedPlayback: false
    property bool fullscreenResult: true
    readonly property real positionSeconds: resultPlayer.position / 1000
    readonly property real durationSeconds: Math.max(inputPlayer.duration, resultPlayer.duration) / 1000
    readonly property bool usesExternalAudio: String(resultAudioSource).length > 0
    readonly property bool bothPlaying: synchronizedPlayback
        && inputPlayer.playbackState === MediaPlayer.PlayingState
        && resultPlayer.playbackState === MediaPlayer.PlayingState

    color: Theme.codeSurface
    radius: Theme.radiusSmall
    border.width: 1
    border.color: Theme.outline

    function seekTo(seconds) {
        const milliseconds = Math.max(0, Number(seconds || 0) * 1000);
        inputPlayer.position = milliseconds;
        resultPlayer.position = milliseconds;
        if (usesExternalAudio)
            resultAudio.position = milliseconds;
    }

    function playOnly(player, audioPlayer) {
        synchronizedPlayback = false;
        if (player === inputPlayer) {
            resultPlayer.pause();
            resultAudio.pause();
        } else {
            inputPlayer.pause();
        }
        if (player.playbackState === MediaPlayer.PlayingState) {
            player.pause();
            if (audioPlayer)
                audioPlayer.pause();
        } else {
            player.play();
            if (audioPlayer) {
                audioPlayer.position = player.position;
                audioPlayer.play();
            }
        }
    }

    function stopOnly(player, audioPlayer) {
        synchronizedPlayback = false;
        player.stop();
        if (audioPlayer)
            audioPlayer.stop();
    }

    function toggleSynchronizedPlayback() {
        if (bothPlaying) {
            inputPlayer.pause();
            resultPlayer.pause();
            resultAudio.pause();
            synchronizedPlayback = false;
            return;
        }
        synchronizedPlayback = true;
        inputPlayer.position = resultPlayer.position;
        inputPlayer.play();
        resultPlayer.play();
        if (usesExternalAudio) {
            resultAudio.position = resultPlayer.position;
            resultAudio.play();
        }
    }

    function openFullscreen(showResult) {
        fullscreenResult = showResult;
        fullscreenLayer.open();
    }

    onResultSourceChanged: Qt.callLater(function () {
        root.seekTo(Math.min(root.positionSeconds, root.durationSeconds));
    })

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 320
            Layout.margins: Theme.space8
            spacing: Theme.space8

            PreviewPane {
                id: inputPane
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: root.width * 0.20
                Layout.minimumWidth: 170
                paneTitle: qsTr("Nguồn")
                player: inputPlayer
                muted: root.inputMuted
                thumbnailVisible: inputPlayer.mediaStatus === MediaPlayer.NoMedia
                onPlayRequested: root.playOnly(inputPlayer, null)
                onStopRequested: root.stopOnly(inputPlayer, null)
                onMuteRequested: root.inputMuted = !root.inputMuted
                onFullscreenRequested: root.openFullscreen(false)
            }

            PreviewPane {
                id: resultPane
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: root.width * 0.80
                Layout.minimumWidth: 420
                paneTitle: qsTr("Kết quả")
                player: resultPlayer
                muted: root.resultMuted
                thumbnailVisible: resultPlayer.mediaStatus === MediaPlayer.NoMedia
                busy: root.previewBusy
                progress: root.previewProgress
                onPlayRequested: root.playOnly(resultPlayer, root.usesExternalAudio ? resultAudio : null)
                onStopRequested: root.stopOnly(resultPlayer, root.usesExternalAudio ? resultAudio : null)
                onMuteRequested: root.resultMuted = !root.resultMuted
                onFullscreenRequested: root.openFullscreen(true)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            color: Theme.surfaceElevated

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space12
                anchors.rightMargin: Theme.space12
                spacing: Theme.space8

                StudioButton {
                    text: root.bothPlaying ? qsTr("Tạm dừng cả hai") : qsTr("Phát cả hai")
                    iconName: root.bothPlaying ? "pause" : "play"
                    variant: "secondary"
                    enabled: String(root.inputSource).length > 0 && String(root.resultSource).length > 0
                    onClicked: root.toggleSynchronizedPlayback()
                }

                Text {
                    Layout.preferredWidth: 64
                    text: root.formatTime(root.positionSeconds)
                    color: Theme.text
                    font.pixelSize: Theme.caption
                    font.family: "Cascadia Mono"
                    textFormat: Text.PlainText
                }

                StudioSlider {
                    Layout.fillWidth: true
                    from: 0
                    to: Math.max(0.1, root.durationSeconds)
                    value: root.positionSeconds
                    enabled: root.durationSeconds > 0
                    onMoved: root.seekTo(value)
                    Accessible.name: qsTr("Vị trí xem trước")
                }

                Text {
                    Layout.preferredWidth: 64
                    text: root.formatTime(root.durationSeconds)
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    font.family: "Cascadia Mono"
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                }
            }
        }
    }

    Popup {
        id: fullscreenLayer
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

        contentItem: Item {
            VideoOutput {
                id: fullscreenOutput
                anchors.fill: parent
                anchors.margins: Theme.space12
                fillMode: VideoOutput.PreserveAspectFit
            }

            StudioIconButton {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Theme.space16
                iconName: "close"
                toolTipText: qsTr("Đóng")
                onClicked: fullscreenLayer.close()
            }
        }
    }

    MediaPlayer {
        id: inputPlayer
        source: root.inputSource
        videoOutput: fullscreenLayer.visible && !root.fullscreenResult
            ? fullscreenOutput : inputPane.videoOutputItem
        audioOutput: AudioOutput { muted: root.inputMuted }

        onPositionChanged: {
            if (root.synchronizedPlayback && Math.abs(resultPlayer.position - position) > 140)
                resultPlayer.position = position;
        }
    }

    MediaPlayer {
        id: resultPlayer
        source: root.resultSource
        videoOutput: fullscreenLayer.visible && root.fullscreenResult
            ? fullscreenOutput : resultPane.videoOutputItem
        audioOutput: AudioOutput { muted: root.usesExternalAudio || root.resultMuted }

        onPositionChanged: {
            if (!root.synchronizedPlayback)
                return;
            if (Math.abs(inputPlayer.position - position) > 140)
                inputPlayer.position = position;
            if (root.usesExternalAudio && Math.abs(resultAudio.position - position) > 140)
                resultAudio.position = position;
        }

        onPlaybackStateChanged: {
            if (root.usesExternalAudio
                    && playbackState !== MediaPlayer.PlayingState
                    && resultAudio.playbackState === MediaPlayer.PlayingState)
                resultAudio.pause();
        }
    }

    MediaPlayer {
        id: resultAudio
        source: root.resultAudioSource
        audioOutput: AudioOutput { muted: root.resultMuted }
    }

    component PreviewPane: Rectangle {
        id: pane

        required property string paneTitle
        required property var player
        required property bool muted
        readonly property alias videoOutputItem: paneVideoOutput
        property bool thumbnailVisible: false
        property bool busy: false
        property real progress: 0
        signal playRequested()
        signal stopRequested()
        signal muteRequested()
        signal fullscreenRequested()

        color: Theme.video
        radius: Theme.radiusSmall
        border.width: 1
        border.color: Theme.divider
        clip: true

        VideoOutput {
            id: paneVideoOutput
            anchors.fill: parent
            fillMode: VideoOutput.PreserveAspectFit
        }

        Image {
            anchors.fill: parent
            source: root.thumbnailSource
            sourceSize.width: 960
            sourceSize.height: 540
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            visible: pane.thumbnailVisible && status === Image.Ready
        }

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.margins: Theme.space8
            width: paneLabel.implicitWidth + Theme.space16
            height: 28
            radius: Theme.radiusTiny
            color: Theme.scrim
            z: 3

            Text {
                id: paneLabel
                anchors.centerIn: parent
                text: pane.paneTitle
                color: Theme.text
                font.pixelSize: Theme.caption
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.margins: Theme.space8
            width: paneControls.implicitWidth + Theme.space8
            height: 38
            radius: Theme.radiusSmall
            color: Theme.scrim
            z: 5

            RowLayout {
                id: paneControls
                anchors.centerIn: parent
                spacing: 0

                StudioIconButton {
                    iconName: pane.player.playbackState === MediaPlayer.PlayingState ? "pause" : "play"
                    toolTipText: pane.player.playbackState === MediaPlayer.PlayingState
                        ? qsTr("Tạm dừng") : qsTr("Phát")
                    onClicked: pane.playRequested()
                }
                StudioIconButton {
                    iconName: "stop"
                    toolTipText: qsTr("Dừng")
                    onClicked: pane.stopRequested()
                }
                StudioIconButton {
                    iconName: pane.muted ? "muted" : "volume"
                    toolTipText: pane.muted ? qsTr("Bật tiếng") : qsTr("Tắt tiếng")
                    onClicked: pane.muteRequested()
                }
                StudioIconButton {
                    iconName: "fullscreen"
                    toolTipText: qsTr("Toàn màn hình")
                    onClicked: pane.fullscreenRequested()
                }
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 3
            visible: pane.busy
            color: Theme.outline
            z: 6

            Rectangle {
                width: parent.width * Math.max(0.02, Math.min(1, pane.progress))
                height: parent.height
                color: Theme.focus
            }
        }
    }

    function formatTime(secondsValue) {
        const total = Math.max(0, Math.floor(Number(secondsValue || 0)));
        const minutes = Math.floor(total / 60);
        const seconds = total % 60;
        return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
    }
}
