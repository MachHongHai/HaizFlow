pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property var segments: []
    property int selectedIndex: -1
    property real duration: 1
    property real position: 0
    property url thumbnailSource: ""
    property real zoomFactor: 1
    property bool editingClip: false
    property bool managedScrubbing: false
    property bool snappingEnabled: true
    property var editorTracks: []
    property var editorClips: []
    property bool sourceTrimEnabled: true
    property var selectedClipIds: []
    property var collapsedTrackIds: ({})
    property var visibleSegments: []
    property var visibleTicks: []
    property real visibleStartSeconds: 0
    property real visibleEndSeconds: 1
    property real pendingZoomAnchorTime: 0
    property real pendingZoomAnchorX: 0

    signal segmentSelected(int index)
    signal segmentFocused(int index)
    signal seekRequested(real seconds)
    signal scrubStarted(real seconds)
    signal scrubMoved(real seconds)
    signal scrubFinished(real seconds)
    signal interactionDismissed()
    signal timingCommitted(int index, real start, real end)
    signal timingCommitResolution(int index, bool accepted)
    signal clipSelected(string clipId, bool additive)
    signal trackSelected(string trackId)
    signal trackStateRequested(string trackId, string propertyName, bool value)
    signal clipMoveCommitted(string clipId, int startMs, string trackId)
    signal clipTrimCommitted(string clipId, string edge, int timeMs)

    readonly property real trackLeft: 140
    readonly property real usableWidth: Math.max(1, timelineFlick.width - trackLeft - 8)
    readonly property real fitPixelsPerSecond: usableWidth / Math.max(0.1, duration)
    readonly property real pixelsPerSecond: fitPixelsPerSecond * zoomFactor
    readonly property real trackWidth: Math.max(usableWidth, duration * pixelsPerSecond)
    readonly property real snapDistanceSeconds: Math.min(0.16, 8 / Math.max(1, pixelsPerSecond))
    readonly property real tickStep: pixelsPerSecond >= 240 ? 0.25 : pixelsPerSecond >= 120 ? 0.5 : pixelsPerSecond >= 58 ? 1 : pixelsPerSecond >= 28 ? 2 : 5
    readonly property real minimumSegmentDuration: 0.12
    readonly property var extraTracks: editorTracks.filter(function(track) {
        const trackId = String(track.track_id || "");
        if (trackId === "source-video" || trackId === "subtitles")
            return false;
        if (trackId === "overlays")
            return editorClips.some(function(clip) {
                return String(clip.clip_id || "") === "watermark-1";
            });
        return true;
    })
    readonly property real trackCanvasHeight: trackY(extraTracks.length) + 8

    color: Theme.codeSurface
    radius: 0
    border.width: 0
    clip: true

    function clamp(value, lower, upper) {
        return Math.max(lower, Math.min(upper, value));
    }

    function isTrackCollapsed(trackId) {
        return Boolean(collapsedTrackIds[String(trackId || "")]);
    }

    function toggleTrackCollapsed(trackId) {
        const next = Object.assign({}, collapsedTrackIds);
        next[trackId] = !Boolean(next[trackId]);
        collapsedTrackIds = next;
    }

    function trackY(index) {
        let top = 128;
        for (let trackIndex = 0; trackIndex < index; ++trackIndex) {
            const track = extraTracks[trackIndex];
            if (String(track.track_id || "") === "voice")
                continue;
            top += isTrackCollapsed(track.track_id) ? 28 : 36;
        }
        return top;
    }

    function trackById(trackId) {
        for (let index = 0; index < editorTracks.length; ++index) {
            if (String(editorTracks[index].track_id || "") === trackId)
                return editorTracks[index];
        }
        return ({ "track_id": trackId, "name": trackId,
            "kind": "overlay", "visible": true, "locked": false,
            "muted": false, "solo": false });
    }

    function formatShortTime(secondsValue) {
        const totalMs = Math.max(0, Math.round(Number(secondsValue || 0) * 1000));
        const minutes = Math.floor(totalMs / 60000);
        const seconds = Math.floor((totalMs % 60000) / 1000);
        const tenths = Math.floor((totalMs % 1000) / 100);
        return minutes > 0 ? String(minutes) + ":" + String(seconds).padStart(2, "0") + "." + String(tenths) : String(seconds) + "." + String(tenths) + "s";
    }

    function previousEnd(index) {
        return index > 0 ? Number(segments[index - 1].end || 0) : 0;
    }

    function nextStart(index) {
        return index + 1 < segments.length ? Number(segments[index + 1].start || duration) : duration;
    }

    function snapTime(value, index, includePrevious, includeNext) {
        if (!snappingEnabled)
            return value;
        // A short magnetic threshold is always active. It is intentionally
        // not exposed as a toolbar mode: editors should feel precise without
        // asking users to understand or manage another persistent setting.
        const targets = snapTargets("");
        if (includePrevious && index > 0)
            targets.push(previousEnd(index));
        if (includeNext && index + 1 < segments.length)
            targets.push(nextStart(index));
        let result = value;
        let bestDistance = snapDistanceSeconds;
        for (let targetIndex = 0; targetIndex < targets.length; ++targetIndex) {
            const distance = Math.abs(value - targets[targetIndex]);
            if (distance <= bestDistance) {
                result = targets[targetIndex];
                bestDistance = distance;
            }
        }
        return result;
    }

    function snapTargets() {
        const targets = [0, duration, position];
        for (let index = 0; index < segments.length; ++index) {
            targets.push(Number(segments[index].start || 0));
            targets.push(Number(segments[index].end || 0));
        }
        for (let index = 0; index < editorClips.length; ++index) {
            const clip = editorClips[index];
            const start = Number(clip.start_ms || 0) / 1000;
            targets.push(start);
            targets.push(start + Number(clip.duration_ms || 0) / 1000);
        }
        return targets;
    }

    function snapAnyTime(value) {
        if (!snappingEnabled)
            return value;
        const targets = snapTargets();
        let result = value;
        let bestDistance = snapDistanceSeconds;
        for (let index = 0; index < targets.length; ++index) {
            const distance = Math.abs(value - targets[index]);
            if (distance <= bestDistance) {
                result = targets[index];
                bestDistance = distance;
            }
        }
        return result;
    }

    function zoomAt(viewX, requestedFactor) {
        const oldScale = Math.max(0.001, pixelsPerSecond);
        const anchorX = clamp(viewX, trackLeft, timelineFlick.width);
        const anchorTime = clamp((timelineFlick.contentX + anchorX - trackLeft) / oldScale, 0, duration);
        pendingZoomAnchorX = anchorX;
        pendingZoomAnchorTime = anchorTime;
        zoomFactor = clamp(requestedFactor, 1, 24);
        zoomPositionTimer.restart();
    }

    function panByPixels(delta) {
        timelineFlick.contentX = clamp(timelineFlick.contentX + delta, 0, Math.max(0, timelineFlick.contentWidth - timelineFlick.width));
    }

    function ensurePositionVisible() {
        if (editingClip || zoomFactor <= 1 || timelineFlick.moving || timelineFlick.dragging)
            return;
        const playheadX = trackLeft + position * pixelsPerSecond;
        const leftBoundary = timelineFlick.contentX + trackLeft + 24;
        const rightBoundary = timelineFlick.contentX + timelineFlick.width - 32;
        if (playheadX < leftBoundary)
            timelineFlick.contentX = clamp(playheadX - trackLeft - 24, 0, Math.max(0, timelineFlick.contentWidth - timelineFlick.width));
        else if (playheadX > rightBoundary)
            timelineFlick.contentX = clamp(playheadX - timelineFlick.width + 32, 0, Math.max(0, timelineFlick.contentWidth - timelineFlick.width));
    }

    function resolveTimingCommit(sourceIndex, accepted) {
        timingCommitResolution(sourceIndex, accepted);
        editingClip = false;
    }

    function refreshVisibleSegments() {
        if (editingClip)
            return;
        const left = Math.max(0, (timelineFlick.contentX - trackLeft)
            / Math.max(1, pixelsPerSecond) - 2);
        const right = (timelineFlick.contentX + timelineFlick.width - trackLeft)
            / Math.max(1, pixelsPerSecond) + 2;
        visibleStartSeconds = left;
        visibleEndSeconds = right;
        const next = [];
        for (let index = 0; index < segments.length; ++index) {
            const segment = segments[index];
            if (Number(segment.end || 0) < left || Number(segment.start || 0) > right)
                continue;
            next.push(Object.assign({ "sourceIndex": index }, segment));
        }
        visibleSegments = next;
        const firstTick = Math.max(0, Math.floor(left / tickStep));
        const lastTick = Math.min(Math.ceil(duration / tickStep),
            Math.ceil(right / tickStep));
        const ticks = [];
        for (let index = firstTick; index <= lastTick; ++index)
            ticks.push(index);
        visibleTicks = ticks;
    }

    onPositionChanged: ensurePositionVisible()
    onSegmentsChanged: {
        editingClip = false;
        visibleRefreshTimer.restart();
    }
    onZoomFactorChanged: visibleRefreshTimer.restart()
    onWidthChanged: visibleRefreshTimer.restart()
    onDurationChanged: visibleRefreshTimer.restart()
    onEditingClipChanged: if (!editingClip) visibleRefreshTimer.restart()
    Component.onCompleted: visibleRefreshTimer.restart()

    Timer {
        id: visibleRefreshTimer
        interval: 35
        onTriggered: root.refreshVisibleSegments()
    }

    Timer {
        id: zoomPositionTimer
        interval: 0
        repeat: false
        onTriggered: {
            const nextContentX = root.trackLeft
                + root.pendingZoomAnchorTime * root.pixelsPerSecond
                - root.pendingZoomAnchorX;
            timelineFlick.contentX = root.clamp(
                nextContentX,
                0,
                Math.max(0, timelineFlick.contentWidth - timelineFlick.width)
            );
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 0
        spacing: Theme.space4

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            Layout.leftMargin: Theme.space8
            Layout.rightMargin: Theme.space8
            spacing: Theme.space8

            Text {
                text: qsTr("Dòng thời gian")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
            }

            Text {
                text: root.selectedIndex >= 0 && root.selectedIndex < root.segments.length
                    ? qsTr("Đoạn đã chọn · %1").arg(root.formatShortTime(
                        Number(root.segments[root.selectedIndex].end || 0)
                        - Number(root.segments[root.selectedIndex].start || 0))) : ""
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

        }

        Flickable {
            id: timelineFlick
            onContentXChanged: visibleRefreshTimer.restart()
            onWidthChanged: visibleRefreshTimer.restart()
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: root.trackLeft + root.trackWidth + 8
            contentHeight: Math.max(height, root.trackCanvasHeight)
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.AutoFlickDirection
            interactive: !root.editingClip

            // Pointer handlers participate in Qt Quick's grab negotiation, so
            // wheel zoom remains available above delegates without placing a
            // high-z MouseArea over the draggable clips.  That overlay was the
            // reason clips stopped moving/resizing after toolbar zoom.
            WheelHandler {
                id: timelineWheelHandler
                target: null
                blocking: true
                onWheel: function (event) {
                    const angle = event.angleDelta.y !== 0 ? event.angleDelta.y : event.angleDelta.x;
                    const pixel = event.pixelDelta.y !== 0 ? event.pixelDelta.y : event.pixelDelta.x;
                    const delta = angle !== 0 ? angle : pixel;
                    if (delta === 0)
                        return;
                    if ((event.modifiers & Qt.ControlModifier) !== 0) {
                        const steps = angle !== 0 ? delta / 120 : delta / 80;
                        root.zoomAt(event.x, root.zoomFactor * Math.pow(1.2, steps));
                    } else if ((event.modifiers & Qt.ShiftModifier) !== 0 && root.zoomFactor > 1.001) {
                        root.panByPixels(-delta);
                    } else {
                        timelineFlick.contentY = root.clamp(
                            timelineFlick.contentY - delta,
                            0,
                            Math.max(0, timelineFlick.contentHeight - timelineFlick.height)
                        );
                    }
                    event.accepted = true;
                }
            }

            Item {
                id: timelineCanvas
                width: timelineFlick.contentWidth
                height: Math.max(timelineFlick.height, root.trackCanvasHeight)

                Rectangle {
                    x: timelineFlick.contentX
                    y: timelineFlick.contentY
                    width: timelineFlick.width
                    height: 28
                    z: 10
                    color: Theme.surface
                }

                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton
                    onClicked: function (mouse) {
                        if (mouse.x < root.trackLeft)
                            return;
                        root.interactionDismissed();
                        root.seekRequested(root.clamp((mouse.x - root.trackLeft) / root.pixelsPerSecond, 0, root.duration));
                    }
                }

                Repeater {
                    model: root.visibleTicks
                    delegate: Item {
                        id: tick
                        required property int modelData
                        x: root.trackLeft + modelData * root.tickStep * root.pixelsPerSecond
                        y: timelineFlick.contentY
                        width: 1
                        height: 26
                        z: 11

                        Rectangle {
                            x: 0
                            y: 17
                            width: 1
                            height: tick.modelData % 2 === 0 ? 11 : 7
                            color: Theme.textSubtle
                        }

                        Text {
                            x: 5
                            y: 0
                            text: root.formatShortTime(tick.modelData * root.tickStep)
                            color: Theme.textSubtle
                            font.pixelSize: Theme.label
                        }
                    }
                }

                TrackHeader {
                    id: sourceTrackHeader
                    x: timelineFlick.contentX
                    y: 30
                    width: root.trackLeft - 4
                    height: 40
                    z: 8
                    readonly property var track: root.trackById("source-video")
                    title: String(track.name || qsTr("Video nguồn"))
                    kind: "source_video"
                    legacyReadOnly: !root.sourceTrimEnabled
                    trackVisible: Boolean(track.visible)
                    locked: Boolean(track.locked)
                    selected: String(AppController.manualEditorDocumentModel.selectedTrackId || "") === "source-video"
                    onSelectedRequested: root.trackSelected("source-video")
                    onVisibilityToggled: root.trackStateRequested("source-video", "visible", !trackVisible)
                    onLockToggled: root.trackStateRequested("source-video", "locked", !locked)
                }

                Repeater {
                    model: root.extraTracks

                    delegate: Item {
                        id: layerTrack
                        required property int index
                        required property var modelData
                        readonly property string trackId: String(modelData.track_id || "")
                        readonly property bool combinedVoice: trackId === "voice"
                        readonly property bool canEditClips: trackId !== "overlays"
                            && !Boolean(modelData.locked)
                        readonly property var clips: root.editorClips.filter(function(clip) {
                            const start = Number(clip.start_ms || 0) / 1000;
                            const end = start + Number(clip.duration_ms || 0) / 1000;
                            return String(clip.track_id || "") === layerTrack.trackId
                                && (layerTrack.trackId !== "overlays"
                                    || String(clip.clip_id || "") === "watermark-1")
                                && end >= root.visibleStartSeconds
                                && start <= root.visibleEndSeconds;
                        })
                        x: 0
                        y: combinedVoice ? 104 : root.trackY(index)
                        width: root.trackLeft + root.trackWidth
                        height: combinedVoice ? 16 : root.isTrackCollapsed(trackId) ? 24 : 32
                        z: combinedVoice ? 6 : 0

                        TrackHeader {
                            visible: !layerTrack.combinedVoice
                            x: timelineFlick.contentX
                            width: root.trackLeft - 4
                            height: parent.height
                            z: 8
                            title: layerTrack.trackId === "overlays"
                                ? qsTr("Watermark")
                                : String(layerTrack.modelData.name || "")
                            legacyReadOnly: layerTrack.trackId === "overlays"
                            kind: String(layerTrack.modelData.kind || "")
                            trackVisible: Boolean(layerTrack.modelData.visible)
                            locked: Boolean(layerTrack.modelData.locked)
                            muted: Boolean(layerTrack.modelData.muted)
                            solo: Boolean(layerTrack.modelData.solo)
                            collapsed: root.isTrackCollapsed(layerTrack.trackId)
                            selected: String(AppController.manualEditorDocumentModel.selectedTrackId || "")
                                === layerTrack.trackId
                            onSelectedRequested: root.trackSelected(layerTrack.trackId)
                            onVisibilityToggled: root.trackStateRequested(
                                layerTrack.trackId, "visible", !trackVisible)
                            onLockToggled: root.trackStateRequested(
                                layerTrack.trackId, "locked", !locked)
                            onMuteToggled: root.trackStateRequested(
                                layerTrack.trackId, "muted", !muted)
                            onSoloToggled: root.trackStateRequested(
                                layerTrack.trackId, "solo", !solo)
                            onCollapsedToggled: root.toggleTrackCollapsed(layerTrack.trackId)
                        }

                        Rectangle {
                            x: root.trackLeft
                            width: root.trackWidth
                            height: parent.height
                            color: layerTrack.combinedVoice ? "transparent" : Theme.input
                            border.width: layerTrack.combinedVoice ? 0 : 1
                            border.color: Theme.divider
                        }

                        Repeater {
                            visible: layerTrack.combinedVoice || !root.isTrackCollapsed(layerTrack.trackId)
                            model: layerTrack.clips
                            delegate: Rectangle {
                                id: editorClip
                                required property int index
                                required property var modelData
                                readonly property string clipId: String(modelData.clip_id || "")
                                readonly property bool selected: root.selectedClipIds.indexOf(clipId) >= 0
                                property int previewStartMs: Number(modelData.start_ms || 0)
                                property int previewDurationMs: Number(modelData.duration_ms || 0)
                                property int gestureStartMs: previewStartMs
                                property int gestureDurationMs: previewDurationMs
                                property real gesturePointerX: 0
                                property bool manipulating: false
                                x: root.trackLeft + previewStartMs / 1000 * root.pixelsPerSecond
                                y: layerTrack.combinedVoice ? 0 : 3
                                width: Math.max(8, previewDurationMs / 1000 * root.pixelsPerSecond)
                                height: layerTrack.combinedVoice ? 16 : layerTrack.height - 6
                                radius: Theme.radiusTiny
                                color: String(modelData.kind || "") === "voice"
                                    ? Theme.successMuted
                                    : String(modelData.kind || "") === "audio"
                                        ? Theme.interactiveMuted : Theme.warningMuted
                                border.width: selected ? 2 : 1
                                border.color: selected ? Theme.focus
                                    : String(modelData.kind || "") === "voice"
                                        ? Theme.success : Theme.interactiveOutline
                                opacity: Boolean(modelData.enabled) && Boolean(layerTrack.modelData.visible) ? 1 : 0.45

                                onModelDataChanged: {
                                    if (!manipulating) {
                                        previewStartMs = Number(modelData.start_ms || 0)
                                        previewDurationMs = Number(modelData.duration_ms || 0)
                                    }
                                }

                                Text {
                                    z: 1
                                    visible: !layerTrack.combinedVoice
                                    anchors.fill: parent
                                    anchors.leftMargin: Theme.space8
                                    anchors.rightMargin: Theme.space8
                                    text: String(editorClip.modelData.name || "")
                                    color: Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: TypeScale.metadata
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }

                                Row {
                                    id: waveformRow
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.leftMargin: 3
                                    anchors.rightMargin: 3
                                    height: parent.height - 8
                                    spacing: 1
                                    visible: (editorClip.modelData.waveform || []).length > 0
                                    opacity: layerTrack.combinedVoice ? 0.8 : 0.42

                                    Repeater {
                                        model: editorClip.modelData.waveform || []
                                        delegate: Rectangle {
                                            required property real modelData
                                            width: Math.max(1, (waveformRow.width
                                                - Math.max(0, (editorClip.modelData.waveform || []).length - 1)
                                                * waveformRow.spacing)
                                                / Math.max(1, (editorClip.modelData.waveform || []).length))
                                            height: Math.max(2, waveformRow.height * Number(modelData || 0.08))
                                            y: (waveformRow.height - height) / 2
                                            radius: width > 2 ? 1 : 0
                                            color: layerTrack.combinedVoice ? Theme.success : Theme.text
                                        }
                                    }
                                }

                                MouseArea {
                                    id: editorMoveArea
                                    anchors.fill: parent
                                    anchors.leftMargin: 8
                                    anchors.rightMargin: 8
                                    acceptedButtons: Qt.LeftButton
                                    cursorShape: !layerTrack.canEditClips
                                        ? Qt.ForbiddenCursor : Qt.SizeAllCursor
                                    preventStealing: true
                                    onPressed: function(mouse) {
                                        root.clipSelected(editorClip.clipId,
                                            (mouse.modifiers & Qt.ControlModifier) !== 0);
                                        if (!layerTrack.canEditClips)
                                            return;
                                        editorClip.gestureStartMs = Number(editorClip.modelData.start_ms || 0);
                                        editorClip.gestureDurationMs = Number(editorClip.modelData.duration_ms || 0);
                                        editorClip.gesturePointerX = mapToItem(timelineCanvas, mouse.x, mouse.y).x;
                                        editorClip.manipulating = true;
                                        root.editingClip = true;
                                    }
                                    onPositionChanged: function(mouse) {
                                        if (!pressed || !layerTrack.canEditClips)
                                            return;
                                        const point = mapToItem(timelineCanvas, mouse.x, mouse.y);
                                        const deltaMs = Math.round((point.x - editorClip.gesturePointerX)
                                            / root.pixelsPerSecond * 1000);
                                        editorClip.previewStartMs = Math.max(0, Math.min(
                                            Math.round(root.duration * 1000) - editorClip.gestureDurationMs,
                                            editorClip.gestureStartMs + deltaMs));
                                    }
                                    onReleased: {
                                        if (layerTrack.canEditClips) {
                                            root.clipMoveCommitted(editorClip.clipId,
                                                editorClip.previewStartMs,
                                                layerTrack.trackId);
                                            editorClip.manipulating = false;
                                            root.editingClip = false;
                                        }
                                    }
                                    onCanceled: {
                                        editorClip.previewStartMs = Number(editorClip.modelData.start_ms || 0);
                                        editorClip.previewDurationMs = Number(editorClip.modelData.duration_ms || 0);
                                        editorClip.manipulating = false;
                                        root.editingClip = false;
                                    }
                                }

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 8
                                    height: parent.height
                                    color: layerTrack.canEditClips
                                        && (editorClip.selected || leftClipHandle.containsMouse)
                                        ? Theme.interactive : "transparent"
                                    MouseArea {
                                        id: leftClipHandle
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: !layerTrack.canEditClips
                                            ? Qt.ForbiddenCursor : Qt.SizeHorCursor
                                        preventStealing: true
                                        onPressed: function(mouse) {
                                            if (!layerTrack.canEditClips) return;
                                            editorClip.gestureStartMs = Number(editorClip.modelData.start_ms || 0);
                                            editorClip.gestureDurationMs = Number(editorClip.modelData.duration_ms || 0);
                                            editorClip.gesturePointerX = mapToItem(timelineCanvas, mouse.x, mouse.y).x;
                                            editorClip.manipulating = true;
                                            root.editingClip = true;
                                        }
                                        onPositionChanged: function(mouse) {
                                            if (!pressed || !layerTrack.canEditClips) return;
                                            const point = mapToItem(timelineCanvas, mouse.x, mouse.y);
                                            const deltaMs = Math.round((point.x - editorClip.gesturePointerX)
                                                / root.pixelsPerSecond * 1000);
                                            const nextStart = Math.max(0, Math.min(
                                                editorClip.gestureStartMs + editorClip.gestureDurationMs - 80,
                                                editorClip.gestureStartMs + deltaMs));
                                            editorClip.previewStartMs = nextStart;
                                            editorClip.previewDurationMs = editorClip.gestureDurationMs
                                                - (nextStart - editorClip.gestureStartMs);
                                        }
                                        onReleased: {
                                            if (layerTrack.canEditClips)
                                                root.clipTrimCommitted(editorClip.clipId, "left", editorClip.previewStartMs);
                                            editorClip.manipulating = false;
                                            root.editingClip = false;
                                        }
                                    }
                                }

                                Rectangle {
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 8
                                    height: parent.height
                                    color: layerTrack.canEditClips
                                        && (editorClip.selected || rightClipHandle.containsMouse)
                                        ? Theme.interactive : "transparent"
                                    MouseArea {
                                        id: rightClipHandle
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: !layerTrack.canEditClips
                                            ? Qt.ForbiddenCursor : Qt.SizeHorCursor
                                        preventStealing: true
                                        onPressed: function(mouse) {
                                            if (!layerTrack.canEditClips) return;
                                            editorClip.gestureStartMs = Number(editorClip.modelData.start_ms || 0);
                                            editorClip.gestureDurationMs = Number(editorClip.modelData.duration_ms || 0);
                                            editorClip.gesturePointerX = mapToItem(timelineCanvas, mouse.x, mouse.y).x;
                                            editorClip.manipulating = true;
                                            root.editingClip = true;
                                        }
                                        onPositionChanged: function(mouse) {
                                            if (!pressed || !layerTrack.canEditClips) return;
                                            const point = mapToItem(timelineCanvas, mouse.x, mouse.y);
                                            const deltaMs = Math.round((point.x - editorClip.gesturePointerX)
                                                / root.pixelsPerSecond * 1000);
                                            editorClip.previewDurationMs = Math.max(80,
                                                editorClip.gestureDurationMs + deltaMs);
                                        }
                                        onReleased: {
                                            if (layerTrack.canEditClips)
                                                root.clipTrimCommitted(editorClip.clipId, "right",
                                                    editorClip.previewStartMs + editorClip.previewDurationMs);
                                            editorClip.manipulating = false;
                                            root.editingClip = false;
                                        }
                                    }
                                }

                            }
                        }
                    }
                }

                Rectangle {
                    id: videoTrack
                    x: root.trackLeft
                    y: 30
                    width: root.trackWidth
                    height: 40
                    color: Theme.video
                    border.width: 1
                    border.color: Theme.divider
                    clip: true

                    Row {
                        anchors.fill: parent

                        Repeater {
                            model: Math.max(1, Math.min(80, Math.ceil(videoTrack.width / 150)))

                            delegate: Image {
                                id: thumbnailTile
                                required property int index
                                readonly property int tileCount: Math.max(1, Math.min(80, Math.ceil(videoTrack.width / 150)))
                                width: videoTrack.width / tileCount
                                height: videoTrack.height
                                source: root.thumbnailSource
                                sourceSize.width: 240
                                sourceSize.height: 96
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                opacity: status === Image.Ready ? 0.72 : 0
                            }
                        }
                    }

                    Repeater {
                        model: root.editorClips.filter(function(clip) {
                            return String(clip.track_id || "") === "source-video";
                        })
                        delegate: Rectangle {
                            id: sourceClip
                            required property var modelData
                            readonly property string clipId: String(modelData.clip_id || "")
                            property int previewStartMs: Number(modelData.start_ms || 0)
                            property int previewDurationMs: Number(modelData.duration_ms || 0)
                            property int gestureStartMs: previewStartMs
                            property int gestureDurationMs: previewDurationMs
                            property real gesturePointerX: 0
                            property bool trimming: false
                            x: previewStartMs / 1000 * root.pixelsPerSecond
                            width: Math.max(8, previewDurationMs / 1000 * root.pixelsPerSecond)
                            height: videoTrack.height
                            color: "transparent"
                            border.width: root.selectedClipIds.indexOf(clipId) >= 0 ? 2 : 1
                            border.color: root.selectedClipIds.indexOf(clipId) >= 0
                                ? Theme.focus : Theme.divider

                            onModelDataChanged: {
                                if (!trimming) {
                                    previewStartMs = Number(modelData.start_ms || 0)
                                    previewDurationMs = Number(modelData.duration_ms || 0)
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                cursorShape: sourceTrackHeader.locked ? Qt.ForbiddenCursor : Qt.PointingHandCursor
                                onClicked: function(mouse) {
                                    root.clipSelected(sourceClip.clipId,
                                        (mouse.modifiers & Qt.ControlModifier) !== 0);
                                    root.seekRequested(Number(sourceClip.modelData.start_ms || 0) / 1000);
                                }
                            }

                            Rectangle {
                                anchors.left: parent.left
                                visible: root.sourceTrimEnabled
                                width: 8
                                height: parent.height
                                color: root.selectedClipIds.indexOf(sourceClip.clipId) >= 0
                                    || sourceLeftHandle.containsMouse ? Theme.interactive : "transparent"
                                MouseArea {
                                    id: sourceLeftHandle
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: sourceTrackHeader.locked ? Qt.ForbiddenCursor : Qt.SizeHorCursor
                                    preventStealing: true
                                    onPressed: function(mouse) {
                                        if (sourceTrackHeader.locked) return;
                                        sourceClip.gestureStartMs = Number(sourceClip.modelData.start_ms || 0);
                                        sourceClip.gestureDurationMs = Number(sourceClip.modelData.duration_ms || 0);
                                        sourceClip.gesturePointerX = mapToItem(timelineCanvas, mouse.x, mouse.y).x;
                                        sourceClip.trimming = true;
                                        root.editingClip = true;
                                    }
                                    onPositionChanged: function(mouse) {
                                        if (!pressed || sourceTrackHeader.locked) return;
                                        const point = mapToItem(timelineCanvas, mouse.x, mouse.y);
                                        const deltaMs = Math.round((point.x - sourceClip.gesturePointerX)
                                            / root.pixelsPerSecond * 1000);
                                        const nextStart = Math.max(sourceClip.gestureStartMs,
                                            Math.min(sourceClip.gestureStartMs
                                                + sourceClip.gestureDurationMs - 80,
                                                sourceClip.gestureStartMs + deltaMs));
                                        sourceClip.previewStartMs = nextStart;
                                        sourceClip.previewDurationMs = sourceClip.gestureDurationMs
                                            - (nextStart - sourceClip.gestureStartMs);
                                    }
                                    onReleased: {
                                        if (!sourceTrackHeader.locked)
                                            root.clipTrimCommitted(sourceClip.clipId, "left", sourceClip.previewStartMs);
                                        sourceClip.trimming = false;
                                        root.editingClip = false;
                                    }
                                }
                            }

                            Rectangle {
                                anchors.right: parent.right
                                visible: root.sourceTrimEnabled
                                width: 8
                                height: parent.height
                                color: root.selectedClipIds.indexOf(sourceClip.clipId) >= 0
                                    || sourceRightHandle.containsMouse ? Theme.interactive : "transparent"
                                MouseArea {
                                    id: sourceRightHandle
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: sourceTrackHeader.locked ? Qt.ForbiddenCursor : Qt.SizeHorCursor
                                    preventStealing: true
                                    onPressed: function(mouse) {
                                        if (sourceTrackHeader.locked) return;
                                        sourceClip.gestureStartMs = Number(sourceClip.modelData.start_ms || 0);
                                        sourceClip.gestureDurationMs = Number(sourceClip.modelData.duration_ms || 0);
                                        sourceClip.gesturePointerX = mapToItem(timelineCanvas, mouse.x, mouse.y).x;
                                        sourceClip.trimming = true;
                                        root.editingClip = true;
                                    }
                                    onPositionChanged: function(mouse) {
                                        if (!pressed || sourceTrackHeader.locked) return;
                                        const point = mapToItem(timelineCanvas, mouse.x, mouse.y);
                                        const deltaMs = Math.round((point.x - sourceClip.gesturePointerX)
                                            / root.pixelsPerSecond * 1000);
                                        sourceClip.previewDurationMs = Math.max(80,
                                            sourceClip.gestureDurationMs + deltaMs);
                                    }
                                    onReleased: {
                                        if (!sourceTrackHeader.locked)
                                            root.clipTrimCommitted(sourceClip.clipId, "right",
                                                sourceClip.previewStartMs + sourceClip.previewDurationMs);
                                        sourceClip.trimming = false;
                                        root.editingClip = false;
                                    }
                                }
                            }
                        }
                    }
                }

                TrackHeader {
                    id: subtitleTrackHeader
                    x: timelineFlick.contentX
                    y: 74
                    width: root.trackLeft - 4
                    height: 50
                    z: 8
                    readonly property var track: root.trackById("subtitles")
                    title: qsTr("Phụ đề · Giọng đọc")
                    kind: "subtitle"
                    secondaryAudioTrack: true
                    secondaryMuted: Boolean(root.trackById("voice").muted)
                    trackVisible: Boolean(track.visible)
                    locked: Boolean(track.locked)
                    selected: ["subtitles", "voice"].indexOf(
                        String(AppController.manualEditorDocumentModel.selectedTrackId || "")) >= 0
                    onSelectedRequested: root.trackSelected("subtitles")
                    onVisibilityToggled: root.trackStateRequested("subtitles", "visible", !trackVisible)
                    onLockToggled: root.trackStateRequested("subtitles", "locked", !locked)
                    onSecondaryMuteToggled: root.trackStateRequested("voice", "muted", !secondaryMuted)
                }

                Rectangle {
                    x: root.trackLeft
                    y: 74
                    width: root.trackWidth
                    height: 50
                    color: Theme.surface
                    border.width: 1
                    border.color: Theme.divider
                }

                Repeater {
                    id: clipRepeater
                    model: root.visibleSegments

                    delegate: Rectangle {
                        id: clip
                        objectName: "subtitleTimelineClip-" + sourceIndex
                        required property var modelData
                        readonly property int sourceIndex: Number(modelData.sourceIndex)

                        property real previewStart: Number(modelData.start || 0)
                        property real previewEnd: Number(modelData.end || 0)
                        property real gestureStart: previewStart
                        property real gestureEnd: previewEnd
                        property real pointerStartX: 0
                        property bool editingTiming: false

                        x: root.trackLeft + previewStart * root.pixelsPerSecond
                        y: 78
                        width: Math.max(8, (previewEnd - previewStart) * root.pixelsPerSecond)
                        height: 24
                        visible: previewEnd >= Math.max(
                            0,
                            (timelineFlick.contentX - root.trackLeft)
                                / Math.max(1, root.pixelsPerSecond) - 2
                        ) && previewStart <= Math.min(
                            root.duration,
                            (timelineFlick.contentX + timelineFlick.width - root.trackLeft)
                                / Math.max(1, root.pixelsPerSecond) + 2
                        )
                        radius: Theme.radiusTiny
                        color: Theme.interactiveMuted
                        border.width: sourceIndex === root.selectedIndex ? 2 : 1
                        border.color: sourceIndex === root.selectedIndex ? Theme.focus : Theme.interactiveOutline
                        z: editingTiming || sourceIndex === root.selectedIndex ? 3 : 2
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: qsTr("Đoạn phụ đề") + " " + String(sourceIndex + 1)

                        onModelDataChanged: {
                            if (!editingTiming) {
                                previewStart = Number(modelData.start || 0);
                                previewEnd = Number(modelData.end || 0);
                            }
                        }

                        Keys.onReturnPressed: root.segmentSelected(sourceIndex)

                        function pointerInCanvas(area, mouse) {
                            return area.mapToItem(timelineCanvas, mouse.x, mouse.y).x;
                        }

                        function beginTiming(area, mouse) {
                            // Press selects the clip. Editing timing and editing
                            // text are separate actions; neither opens a dialog.
                            root.segmentFocused(sourceIndex);
                            gestureStart = Number(modelData.start || 0);
                            gestureEnd = Number(modelData.end || 0);
                            previewStart = gestureStart;
                            previewEnd = gestureEnd;
                            pointerStartX = pointerInCanvas(area, mouse);
                            editingTiming = true;
                            root.editingClip = true;
                        }

                        function cancelTiming() {
                            previewStart = Number(modelData.start || 0);
                            previewEnd = Number(modelData.end || 0);
                            editingTiming = false;
                            root.editingClip = false;
                        }

                        function resolveCommit(accepted) {
                            if (!accepted) {
                                previewStart = Number(modelData.start || 0);
                                previewEnd = Number(modelData.end || 0);
                            }
                            editingTiming = false;
                            root.editingClip = false;
                        }

                        function commitTiming() {
                            editingTiming = false;
                            root.editingClip = false;
                            const oldStart = Number(modelData.start || 0);
                            const oldEnd = Number(modelData.end || 0);
                            const timingChanged = Math.abs(previewStart - oldStart) > 0.0005
                                || Math.abs(previewEnd - oldEnd) > 0.0005;
                            if (timingChanged)
                                root.timingCommitted(sourceIndex, previewStart, previewEnd);
                            else
                                root.segmentSelected(sourceIndex);
                        }

                        Connections {
                            target: root

                            function onTimingCommitResolution(resolvedIndex, accepted) {
                                if (resolvedIndex === clip.sourceIndex)
                                    clip.resolveCommit(accepted);
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 3
                            radius: Theme.radiusTiny
                            color: "transparent"

                            Text {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                anchors.topMargin: 3
                                anchors.bottomMargin: 3
                                text: String(clip.modelData.text || "")
                                color: Theme.text
                                font.pixelSize: Theme.caption
                                wrapMode: Text.NoWrap
                                elide: Text.ElideRight
                                maximumLineCount: 1
                                visible: clip.width >= 34
                            }
                        }

                        MouseArea {
                            id: moveArea
                            anchors.fill: parent
                            anchors.leftMargin: 9
                            anchors.rightMargin: 9
                            acceptedButtons: Qt.LeftButton
                            cursorShape: Qt.SizeAllCursor
                            preventStealing: true

                            onPressed: function (mouse) {
                                clip.beginTiming(moveArea, mouse);
                            }
                            onPositionChanged: function (mouse) {
                                if (!pressed)
                                    return;
                                const delta = (clip.pointerInCanvas(moveArea, mouse) - clip.pointerStartX) / root.pixelsPerSecond;
                                const duration = clip.gestureEnd - clip.gestureStart;
                                const lower = root.previousEnd(clip.sourceIndex);
                                const upper = Math.max(lower, root.nextStart(clip.sourceIndex) - duration);
                                let nextStart = root.clamp(clip.gestureStart + delta, lower, upper);
                                const startSnapped = root.snapTime(nextStart, clip.sourceIndex, true, false);
                                const endSnapped = root.snapTime(nextStart + duration, clip.sourceIndex, false, true);
                                if (Math.abs(startSnapped - nextStart) <= root.snapDistanceSeconds)
                                    nextStart = startSnapped;
                                else if (Math.abs(endSnapped - (nextStart + duration)) <= root.snapDistanceSeconds)
                                    nextStart = endSnapped - duration;
                                clip.previewStart = root.clamp(nextStart, lower, upper);
                                clip.previewEnd = clip.previewStart + duration;
                            }
                            onReleased: clip.commitTiming()
                            onCanceled: clip.cancelTiming()
                            onDoubleClicked: root.seekRequested(clip.previewStart)
                        }

                        Rectangle {
                            id: leftHandle
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            width: 9
                            radius: Theme.radiusTiny
                            color: clip.sourceIndex === root.selectedIndex || leftResize.containsMouse ? Theme.interactive : Theme.interactiveOutline

                            MouseArea {
                                id: leftResize
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.SizeHorCursor
                                preventStealing: true
                                onPressed: function (mouse) {
                                    clip.beginTiming(leftResize, mouse);
                                }
                                onPositionChanged: function (mouse) {
                                    if (!pressed)
                                        return;
                                    const delta = (clip.pointerInCanvas(leftResize, mouse) - clip.pointerStartX) / root.pixelsPerSecond;
                                    const lower = root.previousEnd(clip.sourceIndex);
                                    const upper = clip.gestureEnd - root.minimumSegmentDuration;
                                    const proposed = root.clamp(clip.gestureStart + delta, lower, upper);
                                    clip.previewStart = root.clamp(root.snapTime(proposed, clip.sourceIndex, true, false), lower, upper);
                                }
                                onReleased: clip.commitTiming()
                                onCanceled: clip.cancelTiming()
                            }
                        }

                        Rectangle {
                            id: rightHandle
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            width: 9
                            radius: Theme.radiusTiny
                            color: clip.sourceIndex === root.selectedIndex || rightResize.containsMouse ? Theme.interactive : Theme.interactiveOutline

                            MouseArea {
                                id: rightResize
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.SizeHorCursor
                                preventStealing: true
                                onPressed: function (mouse) {
                                    clip.beginTiming(rightResize, mouse);
                                }
                                onPositionChanged: function (mouse) {
                                    if (!pressed)
                                        return;
                                    const delta = (clip.pointerInCanvas(rightResize, mouse) - clip.pointerStartX) / root.pixelsPerSecond;
                                    const lower = clip.gestureStart + root.minimumSegmentDuration;
                                    const upper = root.nextStart(clip.sourceIndex);
                                    const proposed = root.clamp(clip.gestureEnd + delta, lower, upper);
                                    clip.previewEnd = root.clamp(root.snapTime(proposed, clip.sourceIndex, false, true), lower, upper);
                                }
                                onReleased: clip.commitTiming()
                                onCanceled: clip.cancelTiming()
                            }
                        }
                    }
                }

                Rectangle {
                    id: playhead
                    x: root.trackLeft + root.position * root.pixelsPerSecond
                    y: 20
                    width: 2
                    height: root.trackCanvasHeight - 20
                    color: Theme.danger
                    z: 7

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 0
                        width: 10
                        height: 10
                        radius: 5
                        color: Theme.danger
                    }

                    MouseArea {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: -4
                        width: 24
                        height: parent.height + 8
                        cursorShape: Qt.SizeHorCursor
                        preventStealing: true
                        property real lastTarget: 0
                        onPressed: function(mouse) {
                            root.editingClip = true;
                            const point = mapToItem(timelineCanvas, mouse.x, mouse.y);
                            lastTarget = root.clamp((point.x - root.trackLeft) / root.pixelsPerSecond, 0, root.duration);
                            root.scrubStarted(lastTarget);
                            if (!root.managedScrubbing) root.seekRequested(lastTarget);
                        }
                        onPositionChanged: function (mouse) {
                            if (!pressed)
                                return;
                            const point = mapToItem(timelineCanvas, mouse.x, mouse.y);
                            lastTarget = root.clamp((point.x - root.trackLeft) / root.pixelsPerSecond, 0, root.duration);
                            root.scrubMoved(lastTarget);
                            if (!root.managedScrubbing) root.seekRequested(lastTarget);
                        }
                        onReleased: { root.editingClip = false; root.scrubFinished(lastTarget); }
                        onCanceled: { root.editingClip = false; root.scrubFinished(lastTarget); }
                    }
                }
            }

            ScrollBar.horizontal: ScrollBar {
                policy: root.zoomFactor > 1.001 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
            }
            ScrollBar.vertical: ScrollBar {
                policy: timelineFlick.contentHeight > timelineFlick.height
                    ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
            }
        }
    }
}
