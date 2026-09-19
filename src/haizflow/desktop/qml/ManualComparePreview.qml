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
    property url resultBaseSource: ""
    property url thumbnailSource: ""
    property bool previewBusy: false
    property real previewProgress: 0
    property bool inputMuted: true
    property bool resultMuted: false
    property bool synchronizedPlayback: false
    property bool fullscreenResult: true
    property bool inputPriming: false
    property bool resultPriming: false
    property bool inputSourceSwitching: false
    property bool resultSourceSwitching: false
    property url attachedInputSource: ""
    property url attachedResultSource: ""
    property int lastStablePositionMs: 0
    property int pendingResultPositionMs: 0
    property bool resultPlaybackRequested: false
    property bool subtitleInteractive: false
    property bool subtitleEditEnabled: false
    property bool subtitleLivePreviewEnabled: false
    property bool suppressResultAudio: false
    property string subtitleText: ""
    property var subtitleSprite: ({})
    property real subtitleKaraokeProgress: 0
    property int subtitleFontSize: 60
    property int subtitlePositionXPercent: 50
    property int subtitlePositionYPercent: 88
    property int subtitleBoxWidthPercent: 72
    property int subtitleOutline: 5
    property int subtitleLayoutWidth: 0
    property int subtitleLayoutHeight: 0
    property int subtitleReferenceWidth: 0
    property int subtitleReferenceHeight: 0
    property string watermarkText: ""
    property int watermarkScalePercent: 100
    property bool watermarkInteractive: false
    property bool watermarkEditEnabled: false
    signal subtitleActivated()
    signal subtitleEditingDismissed()
    signal subtitleLayoutPreviewChanged(int fontSize, int positionX, int positionY)
    signal subtitleLayoutCommitted(int fontSize, int positionX, int positionY)
    signal watermarkActivated()
    signal watermarkEditingDismissed()
    signal watermarkScalePreviewChanged(int scalePercent)
    signal watermarkScaleCommitted(int beforeScalePercent, int afterScalePercent)
    readonly property url effectiveResultSource: subtitleLivePreviewEnabled ? resultBaseSource : resultSource
    readonly property real positionSeconds: scrubController.scrubPositionMs / 1000
    readonly property real durationSeconds: Math.max(inputPlayer.duration, resultPlayer.duration) / 1000
    readonly property bool bothPlaying: synchronizedPlayback
        && inputPlayer.playbackState === MediaPlayer.PlayingState
        && resultPlayer.playbackState === MediaPlayer.PlayingState

    color: Theme.codeSurface
    radius: Theme.radiusSmall
    border.width: 1
    border.color: Theme.outline

    function seekTo(seconds) {
        beginScrub(seconds);
        endScrub(seconds);
    }

    function beginScrub(seconds) {
        scrubController.begin(seconds * 1000, resultPlaybackRequested
            || (!resultPriming && resultPlayer.playbackState === MediaPlayer.PlayingState));
    }
    function updateScrub(seconds) { scrubController.updatePosition(seconds * 1000); }
    function endScrub(seconds) { scrubController.end(seconds * 1000); }

    function syncAudio() {
        AppController.manualPreviewAudio.synchronize(root.positionSeconds,
            resultPlayer.playbackState === MediaPlayer.PlayingState
                && !root.resultPriming && !root.resultSourceSwitching && !scrubController.scrubbing,
            root.resultMuted);
    }
    onResultMutedChanged: syncAudio()
    onPositionSecondsChanged: syncAudio()

    PreviewScrubController {
        id: scrubController
        onPauseRequested: {
            root.finishFrameRefresh(false);
            root.resultPlaybackRequested = false;
            inputPlayer.pause();
            resultPlayer.pause();
            root.syncAudio();
        }
        onSeekRequested: function(positionMs) {
            AppController.manualPreviewAudio.seek(positionMs / 1000);
            root.pendingResultPositionMs = positionMs;
            root.lastStablePositionMs = positionMs;
            if (!root.inputSourceSwitching && inputPlayer.seekable)
                inputPlayer.position = positionMs;
            if (!root.resultSourceSwitching && resultPlayer.seekable) {
                resultPlayer.position = positionMs;
                // Seeking to the current position need not emit positionChanged.
                scrubController.observe(resultPlayer.position);
            }
        }
        onResumeRequested: {
            if (!root.resultSourceSwitching) {
                root.resultPlaybackRequested = true;
                resultPlayer.play();
                if (root.synchronizedPlayback)
                    inputPlayer.play();
            }
        }
    }

    function restorePosition(seconds) {
        pendingResultPositionMs = Math.max(0, Number(seconds || 0) * 1000);
        lastStablePositionMs = pendingResultPositionMs;
        seekTo(seconds);
    }

    function playOnly(player) {
        // Ignore transport input while the old native decoder is being
        // detached.  Queuing play() in this short window can resurrect the
        // previous Media Foundation audio buffer after the new source loads.
        if ((player === inputPlayer && inputSourceSwitching)
                || (player === resultPlayer && resultSourceSwitching))
            return;
        synchronizedPlayback = false;
        if (player === inputPlayer && inputPriming)
            finishFrameRefresh(true);
        else if (player === resultPlayer && resultPriming)
            finishFrameRefresh(false);
        if (player === inputPlayer) {
            resultPlaybackRequested = false;
            resultPlayer.pause();
        } else {
            inputPlayer.pause();
        }
        const resultRequested = player === resultPlayer && resultPlaybackRequested;
        if (player.playbackState === MediaPlayer.PlayingState || resultRequested) {
            if (player === resultPlayer)
                resultPlaybackRequested = false;
            player.pause();
        } else {
            if (player === resultPlayer)
                resultPlaybackRequested = true;
            player.play();
        }
    }

    function stopOnly(player) {
        synchronizedPlayback = false;
        if (player === inputPlayer)
            finishFrameRefresh(true);
        else
            finishFrameRefresh(false);
        if (player === resultPlayer)
            resultPlaybackRequested = false;
        player.stop();
    }

    function toggleSynchronizedPlayback() {
        if (inputSourceSwitching || resultSourceSwitching)
            return;
        if (bothPlaying) {
            inputPlayer.pause();
            resultPlayer.pause();
            resultPlaybackRequested = false;
            synchronizedPlayback = false;
            return;
        }
        finishFrameRefresh(true);
        finishFrameRefresh(false);
        // Result audio is the comparison clock. Letting both tracks play is
        // perceived as an echo or crackle when their decoders drift slightly.
        inputMuted = true;
        resultMuted = false;
        synchronizedPlayback = true;
        resultPlaybackRequested = true;
        inputPlayer.position = resultPlayer.position;
        inputPlayer.play();
        resultPlayer.play();
    }

    function openFullscreen(showResult) {
        fullscreenResult = showResult;
        fullscreenLayer.open();
    }

    function closeFullscreen() {
        fullscreenLayer.close();
    }

    function activateSubtitleEditor() {
        finishFrameRefresh(false);
        resultPlaybackRequested = false;
        synchronizedPlayback = false;
        inputPlayer.pause();
        resultPlayer.pause();
        subtitleActivated();
    }

    function activateWatermarkEditor() {
        finishFrameRefresh(false);
        resultPlaybackRequested = false;
        synchronizedPlayback = false;
        inputPlayer.pause();
        resultPlayer.pause();
        watermarkActivated();
    }

    function refreshCurrentFrame(player, inputFrame) {
        if ((inputFrame ? String(attachedInputSource) : String(attachedResultSource)).length === 0)
            return;
        // A playing stream paints the newly attached VideoOutput by itself.
        // Starting another priming cycle would mute its AudioOutput until a
        // frame callback arrives, which is not guaranteed while the sink is
        // being moved in or out of the fullscreen popup.
        if (player.playbackState === MediaPlayer.PlayingState
                || (!inputFrame && resultPlaybackRequested)
                || synchronizedPlayback)
            return;
        if (inputFrame)
            inputPriming = true;
        else
            resultPriming = true;
        frameRefreshSafetyTimer.restart();
        player.play();
    }

    function finishFrameRefresh(inputFrame) {
        if (inputFrame) {
            if (!inputPriming)
                return;
            inputPlayer.pause();
            inputPriming = false;
        } else {
            if (!resultPriming)
                return;
            resultPlayer.pause();
            resultPriming = false;
        }
        if (!inputPriming && !resultPriming)
            frameRefreshSafetyTimer.stop();
    }

    function primeInputFrame() {
        if (inputPane.framePresented
                || inputPlayer.playbackState !== MediaPlayer.StoppedState
                || inputSourceSwitching
                || String(attachedInputSource).length === 0)
            return;
        inputPriming = true;
        frameRefreshSafetyTimer.restart();
        inputPlayer.play();
    }

    function primeResultFrame() {
        if (resultPane.framePresented
                || resultPlayer.playbackState !== MediaPlayer.StoppedState
                || resultSourceSwitching
                || String(attachedResultSource).length === 0)
            return;
        resultPriming = true;
        frameRefreshSafetyTimer.restart();
        resultPlayer.play();
    }

    onInputSourceChanged: {
        inputSourceSwitching = true;
        inputPriming = false;
        inputPlayer.stop();
        attachedInputSource = "";
        inputPane.framePresented = false;
        inputSourceSwapTimer.restart();
        if (!resultPriming)
            frameRefreshSafetyTimer.stop();
    }
    onResultSourceChanged: {
        pendingResultPositionMs = scrubController.desiredPositionMs;
        resultPriming = false;
        if (!inputPriming)
            frameRefreshSafetyTimer.stop();
    }
    onEffectiveResultSourceChanged: {
        pendingResultPositionMs = scrubController.desiredPositionMs;
        scrubController.wasPlaying = scrubController.wasPlaying || resultPlaybackRequested
            || (!resultPriming && resultPlayer.playbackState === MediaPlayer.PlayingState);
        scrubController.sourceChanged();
        // A cache swap is a media-clock boundary. Stop every previous clock
        // before attaching the new mux, otherwise Windows Media Foundation
        // can briefly replay buffered audio from both sources.
        resultPlaybackRequested = false;
        resultPriming = false;
        resultSourceSwitching = true;
        inputPlayer.pause();
        resultPlayer.stop();
        attachedResultSource = "";
        resultPane.framePresented = false;
        resultSourceSwapTimer.restart();
        if (!inputPriming)
            frameRefreshSafetyTimer.stop();
    }
    Component.onCompleted: {
        // Source change handlers may run before the component is complete.
        // Always enter through the detach/attach boundary for the initial
        // sources as well, so opening a project cannot inherit a stale clock.
        inputSourceSwitching = true;
        resultSourceSwitching = true;
        inputSourceSwapTimer.restart();
        resultSourceSwapTimer.restart();
    }
    Component.onDestruction: {
        inputSourceSwitching = true;
        resultSourceSwitching = true;
        inputPlayer.stop();
        resultPlayer.stop();
        attachedInputSource = "";
        attachedResultSource = "";
        synchronizedPlayback = false;
        resultPlaybackRequested = false;
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 220
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
                mediaKey: String(root.inputSource)
                onFirstFramePresented: {
                    root.finishFrameRefresh(true);
                }
                onPlayRequested: root.playOnly(inputPlayer)
                onStopRequested: root.stopOnly(inputPlayer)
                onMuteRequested: {
                    root.inputMuted = !root.inputMuted;
                    if (!root.inputMuted)
                        root.resultMuted = true;
                }
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
                mediaKey: String(root.effectiveResultSource)
                awaitingMedia: String(root.effectiveResultSource).length === 0
                busy: root.previewBusy
                progress: root.previewProgress
                onFirstFramePresented: {
                    root.finishFrameRefresh(false);
                }
                onPlayRequested: root.playOnly(resultPlayer)
                onStopRequested: root.stopOnly(resultPlayer)
                onMuteRequested: {
                    root.resultMuted = !root.resultMuted;
                    if (!root.resultMuted)
                        root.inputMuted = true;
                }
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
                    onPressedChanged: pressed ? root.beginScrub(value) : root.endScrub(value)
                    onMoved: root.updateScrub(value)
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
                endOfStreamPolicy: VideoOutput.KeepLastFrame
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: fullscreenTransport.top
                anchors.margins: Theme.space12
                fillMode: VideoOutput.PreserveAspectFit
            }

            SubtitleTransformOverlay {
                objectName: "fullscreenSubtitleTransformOverlay"
                anchors.fill: fullscreenOutput
                z: 4
                videoRect: fullscreenOutput.contentRect
                subtitleText: root.subtitleText
                sprite: root.subtitleSprite
                karaokeProgress: root.subtitleKaraokeProgress
                fontSize: root.subtitleFontSize
                positionXPercent: root.subtitlePositionXPercent
                positionYPercent: root.subtitlePositionYPercent
                boxWidthPercent: root.subtitleBoxWidthPercent
                outlineWidth: root.subtitleOutline
                layoutWidthPixels: root.subtitleLayoutWidth
                layoutHeightPixels: root.subtitleLayoutHeight
                referenceWidthPixels: root.subtitleReferenceWidth
                referenceHeightPixels: root.subtitleReferenceHeight
                interactive: fullscreenLayer.visible
                    && root.fullscreenResult
                    && root.subtitleInteractive
                    && String(root.resultBaseSource).length > 0
                editing: root.subtitleEditEnabled
                livePreviewVisible: root.fullscreenResult && root.subtitleLivePreviewEnabled && !root.resultSourceSwitching
                onActivated: root.activateSubtitleEditor()
                onEditingDismissed: root.subtitleEditingDismissed()
                onLayoutPreviewChanged: function(fontSize, positionX, positionY) {
                    root.subtitleLayoutPreviewChanged(fontSize, positionX, positionY);
                }
                onLayoutCommitted: function(fontSize, positionX, positionY) {
                    root.subtitleLayoutCommitted(fontSize, positionX, positionY);
                }
            }

            WatermarkTransformOverlay {
                objectName: "fullscreenWatermarkTransformOverlay"
                anchors.fill: fullscreenOutput
                z: 5
                videoRect: fullscreenOutput.contentRect
                watermarkText: root.watermarkText
                scalePercent: root.watermarkScalePercent
                timeSeconds: root.positionSeconds
                referenceWidthPixels: root.subtitleReferenceWidth
                referenceHeightPixels: root.subtitleReferenceHeight
                interactive: fullscreenLayer.visible
                    && root.fullscreenResult
                    && root.watermarkInteractive
                    && String(root.resultBaseSource).length > 0
                editing: root.watermarkEditEnabled
                livePreviewVisible: root.fullscreenResult && !root.resultSourceSwitching
                onActivated: root.activateWatermarkEditor()
                onEditingDismissed: root.watermarkEditingDismissed()
                onScalePreviewChanged: function(value) {
                    root.watermarkScalePreviewChanged(value);
                }
                onScaleCommitted: function(beforeValue, afterValue) {
                    root.watermarkScaleCommitted(beforeValue, afterValue);
                }
            }

            Connections {
                target: fullscreenOutput.videoSink
                enabled: fullscreenLayer.visible

                function onVideoFrameChanged() {
                    if (fullscreenOutput.videoSink.videoSize.width <= 0
                            || fullscreenOutput.videoSink.videoSize.height <= 0)
                        return;
                    root.finishFrameRefresh(!root.fullscreenResult);
                }
            }

            Rectangle {
                id: fullscreenTransport
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 52
                color: Theme.surfaceElevated

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space12
                    anchors.rightMargin: Theme.space12
                    spacing: Theme.space8

                    StudioIconButton {
                        iconName: (root.fullscreenResult ? resultPlayer : inputPlayer).playbackState
                            === MediaPlayer.PlayingState ? "pause" : "play"
                        toolTipText: qsTr("Phát hoặc tạm dừng")
                        onClicked: root.fullscreenResult
                            ? root.playOnly(resultPlayer)
                            : root.playOnly(inputPlayer)
                    }
                    StudioIconButton {
                        iconName: "stop"
                        toolTipText: qsTr("Dừng")
                        onClicked: root.fullscreenResult
                            ? root.stopOnly(resultPlayer)
                            : root.stopOnly(inputPlayer)
                    }
                    StudioIconButton {
                        iconName: (root.fullscreenResult ? root.resultMuted : root.inputMuted)
                            ? "muted" : "volume"
                        toolTipText: qsTr("Bật hoặc tắt tiếng")
                        onClicked: {
                            if (root.fullscreenResult)
                                root.resultMuted = !root.resultMuted;
                            else
                                root.inputMuted = !root.inputMuted;
                        }
                    }
                    StudioSlider {
                        Layout.fillWidth: true
                        from: 0
                        to: Math.max(0.1, root.durationSeconds)
                        value: root.positionSeconds
                        onPressedChanged: pressed ? root.beginScrub(value) : root.endScrub(value)
                        onMoved: root.updateScrub(value)
                        Accessible.name: qsTr("Vị trí xem trước")
                    }
                }
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

        onOpened: frameRefreshTimer.restart()
        onClosed: {
            // The inline sink already presented the old frame before the
            // popup opened. Reset its latch so the reattached sink can finish
            // the new priming cycle instead of leaving audio muted.
            if (root.fullscreenResult)
                resultPane.framePresented = false;
            else
                inputPane.framePresented = false;
            frameRefreshTimer.restart();
        }
    }

    Timer {
        id: inputSourceSwapTimer
        interval: 40
        repeat: false
        onTriggered: {
            root.attachedInputSource = root.inputSource;
            if (String(root.attachedInputSource).length === 0)
                root.inputSourceSwitching = false;
        }
    }

    Timer {
        id: resultSourceSwapTimer
        interval: 40
        repeat: false
        onTriggered: {
            root.attachedResultSource = root.effectiveResultSource;
            if (String(root.attachedResultSource).length === 0)
                root.resultSourceSwitching = false;
        }
    }

    Timer {
        id: inputPrimeTimer
        interval: 0
        repeat: false
        onTriggered: root.primeInputFrame()
    }

    Timer {
        id: resultPrimeTimer
        interval: 0
        repeat: false
        onTriggered: root.primeResultFrame()
    }

    Timer {
        id: frameRefreshTimer
        interval: 0
        repeat: false
        onTriggered: root.refreshCurrentFrame(
            root.fullscreenResult ? resultPlayer : inputPlayer,
            !root.fullscreenResult
        )
    }

    Timer {
        id: frameRefreshSafetyTimer
        interval: 750
        repeat: false
        onTriggered: {
            // Some Windows multimedia backends do not emit a sink frame when
            // a paused stream is rebound. Never let that backend quirk keep
            // either AudioOutput muted indefinitely.
            root.finishFrameRefresh(true);
            root.finishFrameRefresh(false);
        }
    }

    Timer {
        interval: 180
        repeat: true
        running: root.visible && (resultPlayer.playbackState === MediaPlayer.PlayingState
            || root.synchronizedPlayback)
        onTriggered: {
            const masterPosition = resultPlayer.position;
            if (!scrubController.scrubbing && !scrubController.pending
                    && root.synchronizedPlayback && Math.abs(inputPlayer.position - masterPosition) > 220)
                inputPlayer.position = masterPosition;
        }
    }

    MediaPlayer {
        id: inputPlayer
        source: root.attachedInputSource
        videoOutput: fullscreenLayer.visible && !root.fullscreenResult
            ? fullscreenOutput : inputPane.videoOutputItem
        audioOutput: AudioOutput {
            muted: root.inputMuted || root.inputPriming || root.inputSourceSwitching
        }

        onMediaStatusChanged: function() {
            if (inputPlayer.mediaStatus === MediaPlayer.InvalidMedia) {
                root.inputSourceSwitching = false;
                root.finishFrameRefresh(true);
                return;
            }
            if (inputPlayer.mediaStatus === MediaPlayer.LoadedMedia
                    || inputPlayer.mediaStatus === MediaPlayer.BufferedMedia) {
                root.inputSourceSwitching = false;
                inputPlayer.position = scrubController.desiredPositionMs;
                inputPrimeTimer.restart();
            }
        }

        onErrorOccurred: function() {
            root.inputSourceSwitching = false;
            root.finishFrameRefresh(true);
        }
    }

    MediaPlayer {
        id: resultPlayer
        source: root.attachedResultSource
        videoOutput: fullscreenLayer.visible && root.fullscreenResult
            ? fullscreenOutput : resultPane.videoOutputItem
        onPlaybackStateChanged: root.syncAudio()

        onMediaStatusChanged: function() {
            if (resultPlayer.mediaStatus === MediaPlayer.EndOfMedia) {
                root.resultPlaybackRequested = false;
                root.synchronizedPlayback = false;
                root.finishFrameRefresh(false);
                return;
            }
            if (resultPlayer.mediaStatus === MediaPlayer.InvalidMedia) {
                root.resultPlaybackRequested = false;
                root.resultSourceSwitching = false;
                root.finishFrameRefresh(false);
                return;
            }
            if (resultPlayer.mediaStatus !== MediaPlayer.LoadedMedia
                    && resultPlayer.mediaStatus !== MediaPlayer.BufferedMedia)
                return;
            if (!root.resultSourceSwitching)
                return;
            root.resultSourceSwitching = false;
            scrubController.sourceReady();
            if (root.resultPlaybackRequested) {
                play();
            } else {
                resultPrimeTimer.restart();
            }
        }

        onErrorOccurred: function() {
            root.resultPlaybackRequested = false;
            root.resultSourceSwitching = false;
            root.finishFrameRefresh(false);
        }

        onPositionChanged: function() {
            if (!root.resultPriming && !root.resultSourceSwitching) {
                scrubController.observe(resultPlayer.position);
                root.lastStablePositionMs = resultPlayer.position;
            }
        }
    }

    component PreviewPane: Rectangle {
        id: pane

        required property string paneTitle
        required property var player
        required property bool muted
        readonly property alias videoOutputItem: paneVideoOutput
        property string mediaKey: ""
        property bool framePresented: false
        property bool busy: false
        property bool awaitingMedia: false
        property real progress: 0
        signal firstFramePresented()
        signal playRequested()
        signal stopRequested()
        signal muteRequested()
        signal fullscreenRequested()

        color: Theme.video
        radius: Theme.radiusSmall
        border.width: 1
        border.color: Theme.divider
        clip: true

        onMediaKeyChanged: framePresented = false

        VideoOutput {
            id: paneVideoOutput
            endOfStreamPolicy: VideoOutput.KeepLastFrame
            anchors.fill: parent
            fillMode: VideoOutput.PreserveAspectFit
        }

        SubtitleTransformOverlay {
            objectName: "inlineSubtitleTransformOverlay"
            anchors.fill: parent
            z: 4
            videoRect: paneVideoOutput.contentRect
            subtitleText: root.subtitleText
            sprite: root.subtitleSprite
            karaokeProgress: root.subtitleKaraokeProgress
            fontSize: root.subtitleFontSize
            positionXPercent: root.subtitlePositionXPercent
            positionYPercent: root.subtitlePositionYPercent
            boxWidthPercent: root.subtitleBoxWidthPercent
            outlineWidth: root.subtitleOutline
            layoutWidthPixels: root.subtitleLayoutWidth
            layoutHeightPixels: root.subtitleLayoutHeight
            referenceWidthPixels: root.subtitleReferenceWidth
            referenceHeightPixels: root.subtitleReferenceHeight
            interactive: pane === resultPane
                && !fullscreenLayer.visible
                && root.subtitleInteractive
                && String(root.resultBaseSource).length > 0
            editing: pane === resultPane && root.subtitleEditEnabled
            livePreviewVisible: pane === resultPane && root.subtitleLivePreviewEnabled && !root.resultSourceSwitching
            onActivated: root.activateSubtitleEditor()
            onEditingDismissed: root.subtitleEditingDismissed()
            onLayoutPreviewChanged: function(fontSize, positionX, positionY) {
                root.subtitleLayoutPreviewChanged(fontSize, positionX, positionY);
            }
            onLayoutCommitted: function(fontSize, positionX, positionY) {
                root.subtitleLayoutCommitted(fontSize, positionX, positionY);
            }
        }

        WatermarkTransformOverlay {
            objectName: "inlineWatermarkTransformOverlay"
            anchors.fill: parent
            z: 5
            videoRect: paneVideoOutput.contentRect
            watermarkText: root.watermarkText
            scalePercent: root.watermarkScalePercent
            timeSeconds: root.positionSeconds
            referenceWidthPixels: root.subtitleReferenceWidth
            referenceHeightPixels: root.subtitleReferenceHeight
            interactive: pane === resultPane
                && !fullscreenLayer.visible
                && root.watermarkInteractive
                && String(root.resultBaseSource).length > 0
            editing: pane === resultPane && root.watermarkEditEnabled
            livePreviewVisible: pane === resultPane && !root.resultSourceSwitching
            onActivated: root.activateWatermarkEditor()
            onEditingDismissed: root.watermarkEditingDismissed()
            onScalePreviewChanged: function(value) {
                root.watermarkScalePreviewChanged(value);
            }
            onScaleCommitted: function(beforeValue, afterValue) {
                root.watermarkScaleCommitted(beforeValue, afterValue);
            }
        }

        Connections {
            target: paneVideoOutput.videoSink

            function onVideoFrameChanged() {
                if (pane.framePresented
                        || paneVideoOutput.videoSink.videoSize.width <= 0
                        || paneVideoOutput.videoSink.videoSize.height <= 0)
                    return;
                pane.framePresented = true;
                pane.firstFramePresented();
            }
        }

        Image {
            anchors.fill: parent
            source: root.thumbnailSource
            sourceSize.width: 960
            sourceSize.height: 540
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            visible: !pane.framePresented && status === Image.Ready
        }

        Rectangle {
            anchors.fill: parent
            visible: pane.awaitingMedia
            color: Theme.scrim
            z: 8

            Text {
                anchors.centerIn: parent
                text: qsTr("Đang chuẩn bị bản xem trước…")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
            }
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
