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

    signal segmentSelected(int index)
    signal seekRequested(real seconds)
    signal timingCommitted(int index, real start, real end)

    readonly property real trackLeft: 64
    readonly property real usableWidth: Math.max(1, timelineFlick.width - trackLeft - 8)
    readonly property real fitPixelsPerSecond: usableWidth / Math.max(0.1, duration)
    readonly property real pixelsPerSecond: fitPixelsPerSecond * zoomFactor
    readonly property real trackWidth: Math.max(usableWidth, duration * pixelsPerSecond)
    readonly property real snapDistanceSeconds: Math.min(0.16, 8 / Math.max(1, pixelsPerSecond))
    readonly property real tickStep: pixelsPerSecond >= 240 ? 0.25 : pixelsPerSecond >= 120 ? 0.5 : pixelsPerSecond >= 58 ? 1 : pixelsPerSecond >= 28 ? 2 : 5
    readonly property real minimumSegmentDuration: 0.12

    color: Theme.codeSurface
    radius: Theme.radiusSmall
    border.width: 1
    border.color: Theme.outline
    clip: true

    function clamp(value, lower, upper) {
        return Math.max(lower, Math.min(upper, value));
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
        // A short magnetic threshold is always active. It is intentionally
        // not exposed as a toolbar mode: editors should feel precise without
        // asking users to understand or manage another persistent setting.
        const targets = [0, duration, position];
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

    function zoomAt(viewX, requestedFactor) {
        const oldScale = Math.max(0.001, pixelsPerSecond);
        const anchorX = clamp(viewX, trackLeft, timelineFlick.width);
        const anchorTime = clamp((timelineFlick.contentX + anchorX - trackLeft) / oldScale, 0, duration);
        zoomFactor = clamp(requestedFactor, 1, 24);
        Qt.callLater(function () {
            const nextContentX = trackLeft + anchorTime * root.pixelsPerSecond - anchorX;
            timelineFlick.contentX = root.clamp(nextContentX, 0, Math.max(0, timelineFlick.contentWidth - timelineFlick.width));
        });
    }

    function panByPixels(delta) {
        timelineFlick.contentX = clamp(timelineFlick.contentX + delta, 0, Math.max(0, timelineFlick.contentWidth - timelineFlick.width));
    }

    function ensurePositionVisible() {
        if (zoomFactor <= 1 || timelineFlick.moving || timelineFlick.dragging)
            return;
        const playheadX = trackLeft + position * pixelsPerSecond;
        const leftBoundary = timelineFlick.contentX + trackLeft + 24;
        const rightBoundary = timelineFlick.contentX + timelineFlick.width - 32;
        if (playheadX < leftBoundary)
            timelineFlick.contentX = clamp(playheadX - trackLeft - 24, 0, Math.max(0, timelineFlick.contentWidth - timelineFlick.width));
        else if (playheadX > rightBoundary)
            timelineFlick.contentX = clamp(playheadX - timelineFlick.width + 32, 0, Math.max(0, timelineFlick.contentWidth - timelineFlick.width));
    }

    onPositionChanged: ensurePositionVisible()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space8
        spacing: Theme.space4

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            spacing: Theme.space8

            Text {
                text: I18n.t("Timeline")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
            }

            Text {
                text: root.selectedIndex >= 0 && root.selectedIndex < root.segments.length ? I18n.t("Selected clip") + "  " + root.formatShortTime(Number(root.segments[root.selectedIndex].end || 0) - Number(root.segments[root.selectedIndex].start || 0)) : I18n.t("Drag a clip or its edges to adjust timing")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Text {
                Layout.preferredWidth: 42
                text: Math.round(root.zoomFactor * 100) + "%"
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                horizontalAlignment: Text.AlignRight
            }

            Slider {
                Layout.preferredWidth: 132
                from: 1
                to: 24
                value: root.zoomFactor
                stepSize: 0.1
                onMoved: root.zoomAt(timelineFlick.width / 2, value)
                Accessible.name: I18n.t("Timeline zoom")
            }
        }

        Flickable {
            id: timelineFlick
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: root.trackLeft + root.trackWidth + 8
            contentHeight: height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.HorizontalFlick
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
                    if ((event.modifiers & Qt.ShiftModifier) !== 0 && root.zoomFactor > 1.001) {
                        root.panByPixels(-delta);
                    } else {
                        const steps = angle !== 0 ? delta / 120 : delta / 80;
                        root.zoomAt(event.x, root.zoomFactor * Math.pow(1.2, steps));
                    }
                    event.accepted = true;
                }
            }

            Item {
                id: timelineCanvas
                width: timelineFlick.contentWidth
                height: timelineFlick.height

                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton
                    onClicked: function (mouse) {
                        if (mouse.x < root.trackLeft)
                            return;
                        root.seekRequested(root.clamp((mouse.x - root.trackLeft) / root.pixelsPerSecond, 0, root.duration));
                    }
                }

                Repeater {
                    model: Math.ceil(root.duration / root.tickStep) + 1
                    delegate: Item {
                        id: tick
                        required property int index
                        x: root.trackLeft + index * root.tickStep * root.pixelsPerSecond
                        y: 0
                        width: 1
                        height: 28

                        Rectangle {
                            x: 0
                            y: 17
                            width: 1
                            height: tick.index % 2 === 0 ? 11 : 7
                            color: Theme.textSubtle
                        }

                        Text {
                            x: 5
                            y: 0
                            text: root.formatShortTime(tick.index * root.tickStep)
                            color: Theme.textSubtle
                            font.pixelSize: Theme.label
                        }
                    }
                }

                Text {
                    x: 4
                    y: 50
                    text: I18n.t("Video")
                    color: Theme.textMuted
                    font.pixelSize: Theme.label
                }

                Rectangle {
                    id: videoTrack
                    x: root.trackLeft
                    y: 34
                    width: root.trackWidth
                    height: 48
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
                }

                Text {
                    x: 4
                    y: 124
                    text: I18n.t("Subtitles")
                    color: Theme.textMuted
                    font.pixelSize: Theme.label
                }

                Rectangle {
                    x: root.trackLeft
                    y: 92
                    width: root.trackWidth
                    height: 96
                    color: Theme.surface
                    border.width: 1
                    border.color: Theme.divider
                }

                Repeater {
                    model: root.segments

                    delegate: Rectangle {
                        id: clip
                        required property int index
                        required property var modelData

                        property real previewStart: Number(modelData.start || 0)
                        property real previewEnd: Number(modelData.end || 0)
                        property real gestureStart: previewStart
                        property real gestureEnd: previewEnd
                        property real pointerStartX: 0
                        property bool editingTiming: false

                        x: root.trackLeft + previewStart * root.pixelsPerSecond
                        y: 100
                        width: Math.max(8, (previewEnd - previewStart) * root.pixelsPerSecond)
                        height: 78
                        radius: Theme.radiusTiny
                        color: index === root.selectedIndex ? Theme.interactiveMuted : Theme.blueMuted
                        border.width: index === root.selectedIndex ? 2 : 1
                        border.color: index === root.selectedIndex ? Theme.focus : Theme.blueOutline
                        z: editingTiming || index === root.selectedIndex ? 3 : 2
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: I18n.t("Subtitle clip") + " " + String(index + 1)

                        onModelDataChanged: {
                            if (!editingTiming) {
                                previewStart = Number(modelData.start || 0);
                                previewEnd = Number(modelData.end || 0);
                            }
                        }

                        Keys.onReturnPressed: root.segmentSelected(index)

                        function pointerInCanvas(area, mouse) {
                            return area.mapToItem(timelineCanvas, mouse.x, mouse.y).x;
                        }

                        function beginTiming(area, mouse) {
                            root.segmentSelected(index);
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

                        function commitTiming() {
                            editingTiming = false;
                            root.editingClip = false;
                            const oldStart = Number(modelData.start || 0);
                            const oldEnd = Number(modelData.end || 0);
                            if (Math.abs(previewStart - oldStart) > 0.0005 || Math.abs(previewEnd - oldEnd) > 0.0005)
                                root.timingCommitted(index, previewStart, previewEnd);
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
                                anchors.topMargin: 7
                                anchors.bottomMargin: clip.index === root.selectedIndex && clip.width >= 78 ? 23 : 7
                                text: String(clip.modelData.text || "")
                                color: Theme.text
                                font.pixelSize: Theme.caption
                                wrapMode: Text.Wrap
                                elide: Text.ElideRight
                                maximumLineCount: 3
                                visible: clip.width >= 34
                            }

                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 4
                                text: root.formatShortTime(clip.previewEnd - clip.previewStart)
                                color: Theme.textMuted
                                font.pixelSize: Theme.label
                                visible: clip.index === root.selectedIndex && clip.width >= 78
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
                                const lower = root.previousEnd(clip.index);
                                const upper = Math.max(lower, root.nextStart(clip.index) - duration);
                                let nextStart = root.clamp(clip.gestureStart + delta, lower, upper);
                                const startSnapped = root.snapTime(nextStart, clip.index, true, false);
                                const endSnapped = root.snapTime(nextStart + duration, clip.index, false, true);
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
                            color: clip.index === root.selectedIndex || leftResize.containsMouse ? Theme.interactive : Theme.blueOutline

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
                                    const lower = root.previousEnd(clip.index);
                                    const upper = clip.gestureEnd - root.minimumSegmentDuration;
                                    const proposed = root.clamp(clip.gestureStart + delta, lower, upper);
                                    clip.previewStart = root.clamp(root.snapTime(proposed, clip.index, true, false), lower, upper);
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
                            color: clip.index === root.selectedIndex || rightResize.containsMouse ? Theme.interactive : Theme.blueOutline

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
                                    const upper = root.nextStart(clip.index);
                                    const proposed = root.clamp(clip.gestureEnd + delta, lower, upper);
                                    clip.previewEnd = root.clamp(root.snapTime(proposed, clip.index, false, true), lower, upper);
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
                    height: 174
                    color: Theme.danger
                    z: 5

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
                        width: 18
                        height: parent.height + 8
                        cursorShape: Qt.SizeHorCursor
                        preventStealing: true
                        onPressed: root.editingClip = true
                        onPositionChanged: function (mouse) {
                            if (!pressed)
                                return;
                            const point = mapToItem(timelineCanvas, mouse.x, mouse.y);
                            root.seekRequested(root.clamp((point.x - root.trackLeft) / root.pixelsPerSecond, 0, root.duration));
                        }
                        onReleased: root.editingClip = false
                        onCanceled: root.editingClip = false
                    }
                }
            }

            ScrollBar.horizontal: ScrollBar {
                policy: root.zoomFactor > 1.001 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
            }
        }
    }
}
