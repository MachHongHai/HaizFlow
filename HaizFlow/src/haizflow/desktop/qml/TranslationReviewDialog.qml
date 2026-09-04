pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtMultimedia
import "."

FloatingToolDialog {
    id: root
    objectName: "translationReviewDialog"
    // Keep the project/video selection stable while an auto-saved draft is open.
    // The editor is still movable and maximizable, but navigation behind it is blocked.
    modal: true
    closePolicy: root.videoFullscreen ? Popup.NoAutoClose : Popup.CloseOnEscape
    openMaximized: true
    expandedWidth: 1480
    expandedHeight: 900
    toolTitle: root.postProcessingEdit ? qsTr("Sửa phụ đề") : qsTr("Duyệt phụ đề")
    toolSubtitle: qsTr("%1 đoạn · %2").arg(segments.length).arg(AppController.selectedFileName)

    property var segments: []
    property var undoStack: []
    property var redoStack: []
    property string openedSnapshot: "[]"
    property bool approvalInProgress: false
    property bool previewStarted: false
    property bool previewReady: false
    property bool previewQueued: false
    property int selectedIndex: -1
    property var previewMedia: ({})
    property real timelinePosition: 0
    property real sourceDuration: 0
    property string loadedPreviewSource: ""
    property string loadedPreviewAudioSource: ""
    property real pendingPreviewPosition: 0
    property real pendingScrubPosition: 0
    property double positionGuardUntil: 0
    property bool playbackRequested: false
    property bool previewFramePriming: false
    property bool previewScrubbing: false
    property bool previewStatusVisible: false
    property bool videoFullscreen: false
    property string pendingApprovalPayload: ""
    readonly property var selectedSegment: selectedIndex >= 0 && selectedIndex < segments.length ? segments[selectedIndex] : null
    readonly property real contentDuration: {
        let result = Math.max(1, sourceDuration);
        for (let i = 0; i < segments.length; ++i)
            result = Math.max(result, Number(segments[i].end || 0));
        return result;
    }
    readonly property real playheadSeconds: timelinePosition
    readonly property bool usingRenderedPreview: loadedPreviewSource.length > 0
    readonly property bool usingPublishedOutput: !usingRenderedPreview && String(previewMedia.renderedVideoSource || "").length > 0
    readonly property string renderedPreviewMixSource: String(AppController.editorPreviewAudioSource || "")
    readonly property string previewMixSource: usingRenderedPreview
                                                ? renderedPreviewMixSource
                                                : String(previewMedia.finalMixSource || "")
    readonly property bool usesExternalAudio: usingRenderedPreview
                                                ? renderedPreviewMixSource.length > 0
                                                : (!usingPublishedOutput && previewMedia.useVideoAudio === false)
    readonly property bool usingPreparedMix: previewMixSource.length > 0
    readonly property string previewStage: String(AppController.editorPreviewStage || "")
    readonly property bool previewUpdateBusy: AppController.editorPreviewBusy
        && previewStage !== "ready" && previewStage !== "error"
    readonly property real previewUpdateProgress: Math.max(
        0,
        Math.min(1, Number(AppController.editorPreviewProgress || 0))
    )
    property bool postProcessingEdit: false
    readonly property bool manualEditing: AppController.projectType === "manual"

    function cloneSegments(value) {
        return JSON.parse(JSON.stringify(value || []));
    }

    function segmentAt(secondsValue) {
        const position = Number(secondsValue || 0);
        for (let index = 0; index < segments.length; ++index) {
            if (position >= Number(segments[index].start || 0) && position < Number(segments[index].end || 0))
                return segments[index];
        }
        return null;
    }

    function setExternalAudioPosition(positionMs, force) {
        const players = [finalMixPlayer, voicePlayer, backgroundPlayer, musicPlayer];
        for (let index = 0; index < players.length; ++index) {
            const player = players[index];
            const requested = player === musicPlayer && Number(player.duration || 0) > 0 ? positionMs % Number(player.duration) : positionMs;
            if (player.source && (force || Math.abs(Number(player.position || 0) - requested) > 140))
                player.setPosition(requested);
        }
    }

    function syncPreviewAudio(force) {
        setExternalAudioPosition(root.playheadSeconds * 1000, force);
        const playing = videoPlayer.playbackState === MediaPlayer.PlayingState && !previewFramePriming;
        const players = [finalMixPlayer, voicePlayer, backgroundPlayer, musicPlayer];
        for (let index = 0; index < players.length; ++index) {
            const player = players[index];
            if (!player.source)
                continue;
            const activeLayer = root.usingPreparedMix ? player === finalMixPlayer : player !== finalMixPlayer;
            if (root.usesExternalAudio && activeLayer && playing && player.playbackState !== MediaPlayer.PlayingState)
                player.play();
            else if ((!root.usesExternalAudio || !activeLayer || !playing)
                     && player.playbackState === MediaPlayer.PlayingState)
                player.pause();
        }
    }

    function stopPreviewAudio() {
        finalMixPlayer.stop();
        voicePlayer.stop();
        backgroundPlayer.stop();
        musicPlayer.stop();
    }

    function reloadPreviewAudio() {
        // TTS regeneration replaces voice_final.wav in place. A QML binding
        // whose URL string did not change leaves QMediaPlayer on the old file,
        // so explicitly detach and reattach every audio layer.
        const requestedPosition = playheadSeconds;
        const shouldResume = playbackRequested;
        stopPreviewAudio();
        previewMedia = ({});
        Qt.callLater(function () {
            if (!root.visible || root.approvalInProgress)
                return;
            root.previewMedia = AppController.reviewPreviewMedia || ({});
            root.setExternalAudioPosition(requestedPosition * 1000, true);
            if (shouldResume)
                root.syncPreviewAudio(true);
        });
    }

    function togglePreviewPlayback() {
        if (playbackRequested) {
            playbackRequested = false;
            videoPlayer.pause();
            syncPreviewAudio(true);
            return;
        }
        playbackRequested = true;
        previewPrimeTimer.stop();
        previewFramePriming = false;
        videoPlayer.playbackRate = 1.0;
        videoPlayer.play();
    }

    function acceptPreviewFrame(fullscreenFrame) {
        if (fullscreenFrame !== videoFullscreen)
            return;
        previewReady = true;
        if (previewFramePriming) {
            previewPrimeTimer.stop();
            videoPlayer.pause();
            videoPlayer.playbackRate = 1.0;
            timelinePosition = usingRenderedPreview
                ? Number(AppController.editorPreviewStart || 0) + Number(videoPlayer.position || 0) / 1000
                : Number(videoPlayer.position || 0) / 1000;
            previewFramePriming = false;
            syncPreviewAudio(true);
        }
    }

    function refreshVideoSink() {
        if (!visible || !videoPlayer.source)
            return;
        previewReady = false;
        previewPrimeTimer.stop();
        if (playbackRequested) {
            videoPlayer.playbackRate = 1.0;
            if (videoPlayer.playbackState !== MediaPlayer.PlayingState)
                videoPlayer.play();
            return;
        }
        previewFramePriming = true;
        videoPlayer.playbackRate = 0.25;
        videoPlayer.play();
        previewPrimeTimer.restart();
    }

    function releasePreviewMedia() {
        previewStatusDelayTimer.stop();
        previewScrubTimer.stop();
        previewPrimeTimer.stop();
        previewRenderTimer.stop();
        previewReady = false;
        previewQueued = false;
        previewFramePriming = false;
        playbackRequested = false;
        previewScrubbing = false;
        previewStatusVisible = false;
        videoPlayer.playbackRate = 1.0;
        videoPlayer.stop();
        stopPreviewAudio();
        videoPlayer.source = "";
        previewMedia = ({});
        loadedPreviewSource = "";
        loadedPreviewAudioSource = "";
    }

    function beginApproval() {
        commitPendingText();
        pendingApprovalPayload = JSON.stringify(segments);
        approvalInProgress = true;
        draftSaveTimer.stop();
        previewRenderTimer.stop();
        releasePreviewMedia();
        AppController.releaseEditorPreview();
        approvalTimer.restart();
    }

    function markChanged() {
        if (visible && !approvalInProgress) {
            draftSaveTimer.restart();
            // Keep the current preview usable while the replacement is built.
            // The new proxy is swapped in at the current playhead only after
            // FFmpeg has atomically published a complete media file.
            previewQueued = true;
            previewRenderTimer.restart();
        }
    }

    function requestRenderedPreview() {
        if (!visible || approvalInProgress)
            return;
        previewMedia = AppController.reviewPreviewMedia || ({});
        pendingPreviewPosition = playheadSeconds;
        previewQueued = false;
        AppController.requestEditorPreview(JSON.stringify(segments), pendingPreviewPosition);
    }

    function updatePreviewStatus() {
        if (previewUpdateBusy) {
            if (!previewStatusVisible && !previewStatusDelayTimer.running)
                previewStatusDelayTimer.start();
        } else {
            previewStatusDelayTimer.stop();
            previewStatusVisible = false;
        }
    }

    function applyRenderedPreview() {
        if (approvalInProgress)
            return;
        const nextSource = String(AppController.editorPreviewSource || "");
        const nextAudioSource = String(AppController.editorPreviewAudioSource || "");
        const audioChanged = nextAudioSource.length > 0 && nextAudioSource !== loadedPreviewAudioSource;
        if (audioChanged) {
            const requestedPosition = playheadSeconds;
            const shouldResume = videoPlayer.playbackState === MediaPlayer.PlayingState;
            finalMixPlayer.stop();
            loadedPreviewAudioSource = nextAudioSource;
            Qt.callLater(function () {
                if (!root.visible || root.approvalInProgress)
                    return;
                root.setExternalAudioPosition(requestedPosition * 1000, true);
                if (shouldResume)
                    root.syncPreviewAudio(true);
            });
        }
        if (!nextSource || nextSource === loadedPreviewSource)
            return;
        // A full-timeline render may finish after the user has scrubbed. Keep
        // the current playhead instead of jumping back to the request point.
        const requestedPosition = playheadSeconds;
        const shouldResume = playbackRequested;
        loadedPreviewSource = nextSource;
        previewReady = false;
        previewFramePriming = false;
        previewPrimeTimer.stop();
        playbackRequested = shouldResume;
        videoPlayer.stop();
        videoPlayer.source = nextSource;
        pendingPreviewPosition = requestedPosition;
        sourceDuration = Math.max(sourceDuration, Number(AppController.editorPreviewDuration || 0));
    }

    function formatTime(secondsValue) {
        const totalMs = Math.max(0, Math.round((Number(secondsValue) || 0) * 1000));
        const minutes = Math.floor(totalMs / 60000);
        const seconds = Math.floor((totalMs % 60000) / 1000);
        const millis = totalMs % 1000;
        return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0") + "." + String(millis).padStart(3, "0");
    }

    function previewStatusText() {
        const stage = previewStage;
        return stage === "preparing" ? qsTr("Đang chuẩn bị bản xem trước") : qsTr("Đang cập nhật bản xem trước");
    }

    function remember() {
        const history = undoStack.slice();
        history.push(cloneSegments(segments));
        if (history.length > 40)
            history.shift();
        undoStack = history;
        redoStack = [];
    }

    function replaceSegment(index, replacement) {
        if (index < 0 || index >= segments.length)
            return;
        const next = cloneSegments(segments);
        replacement.start = Math.max(0, Number(replacement.start || 0));
        replacement.end = Math.max(replacement.start + 0.05, Number(replacement.end || 0));
        next[index] = replacement;
        next.sort(function (a, b) {
            return Number(a.start || 0) - Number(b.start || 0);
        });
        segments = next;
        selectedIndex = next.indexOf(replacement);
        loadSelectedText();
        markChanged();
    }

    function editSelected(field, value) {
        if (!selectedSegment)
            return;
        remember();
        const updated = cloneSegments(selectedSegment);
        updated[field] = value;
        replaceSegment(selectedIndex, updated);
    }

    function commitSegmentTiming(index, newStart, newEnd) {
        if (index < 0 || index >= segments.length)
            return;
        const start = Math.max(0, Number(newStart || 0));
        const end = Math.max(start + 0.12, Number(newEnd || 0));
        const current = segments[index];
        if (Math.abs(start - Number(current.start || 0)) < 0.0005 && Math.abs(end - Number(current.end || 0)) < 0.0005)
            return;
        remember();
        const next = cloneSegments(segments);
        next[index].start = Math.round(start * 1000) / 1000;
        next[index].end = Math.round(end * 1000) / 1000;
        segments = next;
        selectedIndex = index;
        loadSelectedText();
        markChanged();
    }

    function nudgeSelected(delta) {
        if (!selectedSegment)
            return;
        const duration = Number(selectedSegment.end || 0) - Number(selectedSegment.start || 0);
        const lower = selectedIndex > 0 ? Number(segments[selectedIndex - 1].end || 0) : 0;
        const upper = selectedIndex + 1 < segments.length ? Number(segments[selectedIndex + 1].start || contentDuration) - duration : contentDuration - duration;
        const start = Math.max(lower, Math.min(Math.max(lower, upper), Number(selectedSegment.start || 0) + Number(delta || 0)));
        commitSegmentTiming(selectedIndex, start, start + duration);
        seekTo(start);
    }

    function undo() {
        if (undoStack.length === 0)
            return;
        const history = undoStack.slice();
        const future = redoStack.slice();
        future.push(cloneSegments(segments));
        segments = history.pop();
        undoStack = history;
        redoStack = future;
        selectedIndex = Math.min(selectedIndex, segments.length - 1);
        loadSelectedText();
        markChanged();
    }

    function redo() {
        if (redoStack.length === 0)
            return;
        const future = redoStack.slice();
        const history = undoStack.slice();
        history.push(cloneSegments(segments));
        segments = future.pop();
        undoStack = history;
        redoStack = future;
        selectedIndex = Math.min(selectedIndex, segments.length - 1);
        loadSelectedText();
        markChanged();
    }

    function commitPendingText() {
        editorWorkspace.commitPendingText();
    }

    function loadSelectedText() {
        editorWorkspace.setEditorText(selectedSegment ? String(selectedSegment.text || "") : "");
    }

    function selectSegment(index) {
        if (index < 0 || index >= segments.length)
            return;
        if (index !== selectedIndex) {
            commitPendingText();
            selectedIndex = index;
            loadSelectedText();
        }
        seekTo(Math.max(0, Number(segments[index].start || 0)));
    }

    function selectAdjacent(delta) {
        if (segments.length === 0)
            return;
        const nextIndex = Math.max(0, Math.min(segments.length - 1, selectedIndex + delta));
        selectSegment(nextIndex);
    }

    function saveDraftOnClose() {
        commitPendingText();
        if (approvalInProgress || segments.length === 0)
            return;
        const currentSnapshot = JSON.stringify(segments);
        if (currentSnapshot !== openedSnapshot) {
            if (root.manualEditing)
                AppController.approveTranslationReview(currentSnapshot);
            else
                AppController.saveTranslationReviewDraft(currentSnapshot);
            openedSnapshot = currentSnapshot;
        }
    }

    function seekTo(secondsValue) {
        const seconds = Math.max(0, Math.min(contentDuration, Number(secondsValue || 0)));
        timelinePosition = seconds;
        pendingPreviewPosition = seconds;
        positionGuardUntil = Date.now() + 220;
        // Both the source and the rendered proxy now span the full timeline.
        // Seeking never invalidates the visual cache and never changes source.
        videoPlayer.setPosition(seconds * 1000);
        setExternalAudioPosition(seconds * 1000, true);
        const segment = segmentAt(seconds);
        if (!segment)
            return;
        const index = segments.indexOf(segment);
        if (index >= 0 && index !== selectedIndex) {
            commitPendingText();
            selectedIndex = index;
            loadSelectedText();
        }
    }

    function beginPreviewScrub(secondsValue) {
        previewScrubbing = true;
        scrubPreview(secondsValue);
        previewScrubTimer.start();
    }

    function scrubPreview(secondsValue) {
        const seconds = Math.max(0, Math.min(contentDuration, Number(secondsValue || 0)));
        pendingScrubPosition = seconds;
        pendingPreviewPosition = seconds;
        timelinePosition = seconds;
    }

    function endPreviewScrub(secondsValue) {
        previewScrubTimer.stop();
        previewScrubbing = false;
        seekTo(secondsValue);
    }

    onOpened: {
        postProcessingEdit = AppController.selectedStatus === "done"
            || AppController.selectedStatus === "manual_ready";
        segments = cloneSegments(AppController.reviewSegments);
        undoStack = [];
        redoStack = [];
        approvalInProgress = false;
        openedSnapshot = JSON.stringify(segments);
        selectedIndex = segments.length > 0 ? 0 : -1;
        loadSelectedText();
        previewStarted = false;
        previewReady = false;
        previewQueued = false;
        previewMedia = AppController.reviewPreviewMedia || ({});
        timelinePosition = 0;
        sourceDuration = 0;
        loadedPreviewSource = "";
        loadedPreviewAudioSource = "";
        pendingPreviewPosition = 0;
        pendingScrubPosition = 0;
        positionGuardUntil = 0;
        playbackRequested = false;
        previewScrubbing = false;
        previewStatusVisible = false;
        videoFullscreen = false;
        pendingApprovalPayload = "";
        const publishedSource = String(previewMedia.renderedVideoSource || "");
        videoPlayer.source = publishedSource.length > 0 ? publishedSource : AppController.selectedInputSource;
        videoPlayer.setPosition(0);
        setExternalAudioPosition(0, true);
        // Do not add the edit debounce to initial opening. Cached previews are
        // published immediately; uncached work starts in the background while
        // the source/output frame remains visible.
        Qt.callLater(root.requestRenderedPreview);
    }
    onClosed: {
        saveDraftOnClose();
        releasePreviewMedia();
        videoFullscreen = false;
        AppController.releaseEditorPreview();
    }
    onVideoFullscreenChanged: Qt.callLater(root.refreshVideoSink)

    SubtitleEditorWorkspace {
        id: editorWorkspace
        anchors.fill: parent
        anchors.margins: Theme.space12
        segments: root.segments
        selectedSegment: root.selectedSegment
        selectedIndex: root.selectedIndex
        duration: root.contentDuration
        position: root.playheadSeconds
        thumbnailSource: AppController.videoThumbnailSource
        previewReady: root.previewReady
        statusVisible: root.previewStatusVisible
        previewBusy: root.previewUpdateBusy
        previewProgress: root.previewUpdateProgress
        previewStatusText: root.previewStatusText()
        playing: root.playbackRequested
            && videoPlayer.playbackState === MediaPlayer.PlayingState
        canUndo: root.undoStack.length > 0
        canRedo: root.redoStack.length > 0
        canCommit: root.segments.length > 0 && !root.approvalInProgress
        primaryText: root.manualEditing ? qsTr("Lưu phụ đề")
            : root.postProcessingEdit ? qsTr("Lưu và tạo lại giọng") : qsTr("Duyệt và tiếp tục")
        onPlaybackToggled: root.togglePreviewPlayback()
        onScrubStarted: function(position) { root.beginPreviewScrub(position) }
        onScrubbed: function(position) { root.scrubPreview(position) }
        onScrubFinished: function(position) { root.endPreviewScrub(position) }
        onFullscreenRequested: root.videoFullscreen = true
        onPreviousRequested: root.selectAdjacent(-1)
        onNextRequested: root.selectAdjacent(1)
        onTextCommitted: function(value) { root.editSelected("text", value) }
        onSegmentSelected: function(index) { root.selectSegment(index) }
        onSeekRequested: function(seconds) { root.seekTo(seconds) }
        onTimingCommitted: function(index, start, end) { root.commitSegmentTiming(index, start, end) }
        onUndoRequested: {
            root.commitPendingText()
            root.undo()
        }
        onRedoRequested: {
            root.commitPendingText()
            root.redo()
        }
        onCommitRequested: root.beginApproval()
    }

    SubtitleEditorFullscreenPreview {
        id: fullscreenPreview
        anchors.fill: parent
        visible: root.videoFullscreen
        z: 100
        thumbnailSource: AppController.videoThumbnailSource
        previewReady: root.previewReady
        position: root.playheadSeconds
        duration: root.contentDuration
        playing: root.playbackRequested
            && videoPlayer.playbackState === MediaPlayer.PlayingState
        onPlaybackToggled: root.togglePreviewPlayback()
        onScrubStarted: function(position) { root.beginPreviewScrub(position) }
        onScrubbed: function(position) { root.scrubPreview(position) }
        onScrubFinished: function(position) { root.endPreviewScrub(position) }
        onCloseRequested: root.videoFullscreen = false
    }

    Connections {
        target: AppController

        function onEditorPreviewChanged() {
            if (root.visible) {
                root.applyRenderedPreview();
                root.updatePreviewStatus();
            }
        }

        function onSelectedVideoChanged() {
            if (root.visible)
                root.reloadPreviewAudio();
        }
    }

    Connections {
        target: editorWorkspace.videoOutput.videoSink
        enabled: !root.videoFullscreen

        function onVideoFrameChanged() {
            if (editorWorkspace.videoOutput.videoSink.videoSize.width > 0
                    && editorWorkspace.videoOutput.videoSink.videoSize.height > 0)
                root.acceptPreviewFrame(false);
        }
    }

    Connections {
        target: fullscreenPreview.videoOutput.videoSink
        enabled: root.videoFullscreen

        function onVideoFrameChanged() {
            if (fullscreenPreview.videoOutput.videoSink.videoSize.width > 0
                    && fullscreenPreview.videoOutput.videoSink.videoSize.height > 0)
                root.acceptPreviewFrame(true);
        }
    }

    MediaPlayer {
        id: videoPlayer
        videoOutput: root.videoFullscreen ? fullscreenPreview.videoOutput : editorWorkspace.videoOutput
        audioOutput: AudioOutput {
            volume: root.previewFramePriming || root.usesExternalAudio
                ? 0 : (root.usingPublishedOutput ? 1 : Number(root.previewMedia.videoVolume || 0.6))
        }
        onDurationChanged: {
            if (!root.usingRenderedPreview)
                root.sourceDuration = Math.max(root.sourceDuration, Number(duration || 0) / 1000);
        }
        onPositionChanged: {
            if (!root.previewFramePriming && !root.previewScrubbing && Date.now() >= root.positionGuardUntil)
                root.timelinePosition = root.usingRenderedPreview ? Number(AppController.editorPreviewStart || 0) + Number(position || 0) / 1000 : Number(position || 0) / 1000;
        }
        onMediaStatusChanged: {
            if (mediaStatus === MediaPlayer.LoadedMedia || mediaStatus === MediaPlayer.BufferedMedia) {
                const offset = root.usingRenderedPreview ? root.pendingPreviewPosition - Number(AppController.editorPreviewStart || 0) : root.pendingPreviewPosition;
                setPosition(Math.max(0, offset * 1000));
                root.timelinePosition = root.pendingPreviewPosition;
                root.setExternalAudioPosition(root.pendingPreviewPosition * 1000, true);
                if (root.playbackRequested) {
                    playbackRate = 1.0;
                    play();
                } else if (!root.previewFramePriming) {
                    // Windows Media Foundation does not always decode a frame
                    // after a paused seek. Prime the decoder silently, then
                    // pause back on the requested frame before revealing it.
                    root.previewFramePriming = true;
                    playbackRate = 0.25;
                    play();
                    previewPrimeTimer.restart();
                }
            }
            else if (mediaStatus === MediaPlayer.LoadingMedia) {
                previewPrimeTimer.stop();
                root.previewFramePriming = false;
                root.previewReady = false;
            } else if (mediaStatus === MediaPlayer.InvalidMedia || mediaStatus === MediaPlayer.EndOfMedia) {
                previewPrimeTimer.stop();
                root.previewFramePriming = false;
                if (mediaStatus === MediaPlayer.EndOfMedia)
                    root.playbackRequested = false;
            }
        }
        onPlaybackStateChanged: {
            if (playbackState === MediaPlayer.PlayingState
                    && root.playbackRequested && !root.previewFramePriming)
                root.previewStarted = true;
            root.syncPreviewAudio(true);
        }
        onErrorOccurred: function() {
            previewPrimeTimer.stop();
            root.previewFramePriming = false;
            root.playbackRequested = false;
        }
    }

    MediaPlayer {
        id: finalMixPlayer
        source: root.previewMixSource
        audioOutput: AudioOutput {
            volume: 1
        }
        onMediaStatusChanged: {
            if (mediaStatus === MediaPlayer.LoadedMedia || mediaStatus === MediaPlayer.BufferedMedia) {
                root.setExternalAudioPosition(root.playheadSeconds * 1000, true);
                root.syncPreviewAudio(true);
            }
        }
    }

    MediaPlayer {
        id: voicePlayer
        source: String(root.previewMedia.voiceSource || "")
        audioOutput: AudioOutput {
            volume: Number(root.previewMedia.ttsVolume || 1)
        }
    }

    MediaPlayer {
        id: backgroundPlayer
        source: String(root.previewMedia.backgroundSource || "")
        audioOutput: AudioOutput {
            volume: Number(root.previewMedia.backgroundVolume || 0.6)
        }
    }

    MediaPlayer {
        id: musicPlayer
        source: String(root.previewMedia.musicSource || "")
        loops: MediaPlayer.Infinite
        audioOutput: AudioOutput {
            volume: Number(root.previewMedia.musicVolume || 0.3)
        }
    }

    Timer {
        id: previewStatusDelayTimer
        interval: 240
        repeat: false
        onTriggered: root.previewStatusVisible = root.visible && root.previewUpdateBusy
    }

    Timer {
        id: previewScrubTimer
        interval: 80
        repeat: true
        onTriggered: {
            const seconds = root.pendingScrubPosition;
            root.positionGuardUntil = Date.now() + 220;
            videoPlayer.setPosition(seconds * 1000);
            root.setExternalAudioPosition(seconds * 1000, true);
        }
    }

    Timer {
        id: previewPrimeTimer
        interval: 800
        repeat: false
        onTriggered: {
            if (!root.previewFramePriming)
                return
            videoPlayer.pause()
            videoPlayer.playbackRate = 1.0
            root.previewFramePriming = false
            // A timeout is cleanup, not proof that a frame exists. Keep the
            // thumbnail over the sink instead of revealing a black surface.
            root.syncPreviewAudio(true)
        }
    }

    Timer {
        interval: 160
        running: root.visible && videoPlayer.playbackState === MediaPlayer.PlayingState
        repeat: true
        onTriggered: root.syncPreviewAudio(false)
    }

    Timer {
        id: draftSaveTimer
        interval: 500
        repeat: false
        onTriggered: root.saveDraftOnClose()
    }

    Timer {
        id: previewRenderTimer
        // Content and timing edits render only after the user pauses. This
        // avoids starting and cancelling FFmpeg for every drag/text event.
        interval: 360
        repeat: false
        onTriggered: root.requestRenderedPreview()
    }

    Timer {
        id: approvalTimer
        // Qt Multimedia releases Windows file handles asynchronously. Give it
        // one event-loop window before the pipeline replaces voice_final.wav.
        interval: 240
        repeat: false
        onTriggered: {
            if (AppController.approveTranslationReview(root.pendingApprovalPayload)) {
                root.close();
                return;
            }
            root.approvalInProgress = false;
            root.previewMedia = AppController.reviewPreviewMedia || ({});
            root.loadedPreviewSource = "";
            videoPlayer.source = AppController.selectedInputSource;
        }
    }

}
