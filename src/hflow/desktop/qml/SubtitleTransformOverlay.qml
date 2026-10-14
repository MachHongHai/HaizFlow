pragma ComponentBehavior: Bound

import QtQuick
import "."

Item {
    id: root

    property rect videoRect: Qt.rect(0, 0, 0, 0)
    property string subtitleText: ""
    property string sampleText: ""
    property string sampleFontFamily: Theme.fontFamily
    property real sampleFontScale: 1
    property color sampleTextColor: "white"
    property color sampleOutlineColor: "black"
    property bool sampleBold: false
    property bool sampleItalic: false
    property var sprite: ({})
    property real karaokeProgress: 0
    property int fontSize: 60
    property int positionXPercent: 50
    property int positionYPercent: 88
    property int boxWidthPercent: 72
    property int boxHeightPercent: 12
    property int outlineWidth: 5
    property int layoutWidthPixels: 0
    property int layoutHeightPixels: 0
    property int referenceWidthPixels: 0
    property int referenceHeightPixels: 0
    property bool interactive: false
    property bool editing: false
    property bool backgroundDismissEnabled: true
    property bool livePreviewVisible: true
    signal activated()
    signal editingDismissed()
    signal layoutPreviewChanged(int fontSize, int positionX, int positionY, int boxWidth, int boxHeight)
    signal layoutCommitted(int fontSize, int positionX, int positionY, int boxWidth, int boxHeight)

    property int draftFontSize: fontSize
    property real draftPositionX: positionXPercent
    property real draftPositionY: positionYPercent
    property real draftBoxWidth: boxWidthPercent
    property real draftBoxHeight: boxHeightPercent
    property bool boxResizeActive: false
    property rect boxResizeRect
    property rect boxResizeStartRect
    property real boxResizeStartWidth: 72
    property real boxResizeStartHeight: 12
    property real boxResizeStartX: 50
    property real boxResizeStartY: 88
    readonly property real referenceHeight: referenceHeightPixels > 0
        ? referenceHeightPixels
        : videoCanvas.height > videoCanvas.width ? 1920 : 1080
    readonly property real previewFontSize: Math.max(
        10,
        draftFontSize * sampleFontScale * videoCanvas.height / Math.max(1, referenceHeight)
    )
    readonly property real referenceWidth: referenceWidthPixels > 0
        ? referenceWidthPixels
        : videoCanvas.height > videoCanvas.width ? 1080 : 1920
    readonly property real previewScale: Math.min(
        videoCanvas.width / Math.max(1, referenceWidth),
        videoCanvas.height / Math.max(1, referenceHeight)
    )
    readonly property real previewLetterSpacing: Math.max(0, previewScale)

    readonly property bool sampleMode: String(sampleText).length > 0
        && String(sprite.normal || "").length === 0
    visible: (interactive || livePreviewVisible)
        && (String(sprite.normal || "").length > 0 || sampleMode)
        && videoRect.width > 0
        && videoRect.height > 0

    onFontSizeChanged: if (!moveArea.pressed && !resizeInProgress()) draftFontSize = fontSize
    onPositionXPercentChanged: if (!moveArea.pressed && !resizeInProgress()) draftPositionX = positionXPercent
    onPositionYPercentChanged: if (!moveArea.pressed && !resizeInProgress()) draftPositionY = positionYPercent
    onBoxWidthPercentChanged: if (!resizeInProgress()) draftBoxWidth = boxWidthPercent
    onBoxHeightPercentChanged: if (!resizeInProgress()) draftBoxHeight = boxHeightPercent

    function beginBoxResize() {
        activateEditor();
        boxResizeStartRect = Qt.rect(selection.x, selection.y, selection.width, selection.height);
        boxResizeRect = boxResizeStartRect;
        boxResizeStartWidth = draftBoxWidth;
        boxResizeStartHeight = draftBoxHeight;
        boxResizeStartX = draftPositionX;
        boxResizeStartY = draftPositionY;
        boxResizeActive = true;
    }

    function previewBox(rectangle) {
        // The handles surround visible glyphs, not the (usually much larger)
        // phrase-capacity region. Use the new visible width as word capacity;
        // legacy 100% capacity must not lock a smaller on-screen frame.
        boxResizeRect = rectangle;
        if (Math.abs(rectangle.width - boxResizeStartRect.width) > 0.01)
            draftBoxWidth = clamp(rectangle.width / videoCanvas.width * 100, 20, 100);
        draftBoxHeight = clamp(boxResizeStartHeight * rectangle.height / Math.max(1, boxResizeStartRect.height), 1, 100);
        draftPositionX = boxResizeStartX + (rectangle.x + rectangle.width / 2
            - boxResizeStartRect.x - boxResizeStartRect.width / 2) / videoCanvas.width * 100;
        draftPositionY = boxResizeStartY + (rectangle.y + rectangle.height / 2
            - boxResizeStartRect.y - boxResizeStartRect.height / 2) / videoCanvas.height * 100;
        publishPreview();
    }

    function cancelBoxResize() {
        draftBoxWidth = boxResizeStartWidth;
        draftBoxHeight = boxResizeStartHeight;
        draftPositionX = boxResizeStartX;
        draftPositionY = boxResizeStartY;
        boxResizeActive = false;
        publishPreview();
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function resizeInProgress() {
        if (boxResizeActive) return true;
        for (let i = 0; i < edgeHandles.count; ++i) {
            const handle = edgeHandles.itemAt(i) as SubtitleBoxHandle;
            if (handle && handle.pressed) return true;
        }
        return topLeftHandle.pressed
            || topRightHandle.pressed
            || bottomLeftHandle.pressed
            || bottomRightHandle.pressed;
    }

    function commit() {
        previewDebounce.stop();
        emitPreview();
        layoutCommitted(
            Math.round(clamp(draftFontSize, 10, 240)),
            Math.round(clamp(draftPositionX, 0, 100)),
            Math.round(clamp(draftPositionY, 0, 100)),
            Math.round(clamp(draftBoxWidth, 20, 100)),
            Math.round(clamp(draftBoxHeight, 1, 100))
        );
    }

    function publishPreview() {
        if (!previewDebounce.running) previewDebounce.start();
    }

    function emitPreview() {
        layoutPreviewChanged(
            Math.round(clamp(draftFontSize, 10, 240)),
            Math.round(clamp(draftPositionX, 0, 100)),
            Math.round(clamp(draftPositionY, 0, 100)),
            Math.round(clamp(draftBoxWidth, 20, 100)),
            Math.round(clamp(draftBoxHeight, 1, 100))
        );
    }

    Timer {
        id: previewDebounce
        interval: 120
        repeat: false
        onTriggered: root.emitPreview()
    }

    function activateEditor() {
        if (!editing)
            activated();

    }

    TapHandler {
        enabled: root.editing && root.backgroundDismissEnabled
        gesturePolicy: TapHandler.DragThreshold
        onTapped: function(eventPoint) {
            const point = selection.mapFromItem(root, eventPoint.position.x, eventPoint.position.y);
            if (point.x < -18 || point.y < -18 || point.x > selection.width + 18 || point.y > selection.height + 18)
                root.editingDismissed();
        }
    }

    Item {
        id: videoCanvas
        x: root.videoRect.x
        y: root.videoRect.y
        width: root.videoRect.width
        height: root.videoRect.height

        Rectangle {
            visible: moveArea.pressed && Math.abs(root.draftPositionX - 50) < 0.01
            x: Math.round(videoCanvas.width / 2)
            width: 1
            height: videoCanvas.height
            color: Theme.focus
        }

        Rectangle {
            visible: moveArea.pressed && Math.abs(root.draftPositionY - 50) < 0.01
            y: Math.round(videoCanvas.height / 2)
            width: videoCanvas.width
            height: 1
            color: Theme.focus
        }

        Rectangle {
            id: selection
            objectName: "subtitleTransformSelection"
            readonly property real rasterScale: root.previewScale * root.draftFontSize / Math.max(1, Number(root.sprite.fontSize || root.fontSize))
            readonly property real rasterX: videoCanvas.width * root.draftPositionX / 100
                + (Number(root.sprite.x || 0) - Number(root.sprite.outputWidth || 1)
                * Number(root.sprite.positionXPercent || 50) / 100) * rasterScale
            readonly property real rasterY: videoCanvas.height * root.draftPositionY / 100
                + (Number(root.sprite.y || 0) - Number(root.sprite.outputHeight || 1)
                * Number(root.sprite.positionYPercent || 88) / 100) * rasterScale
            readonly property real fontScaleExtent: root.sampleMode
                ? Math.max(sampleLabel.contentWidth, sampleLabel.contentHeight)
                : Math.max(Number(root.sprite.width || 1), Number(root.sprite.height || 1)) * rasterScale
            readonly property real glyphPadding: root.editing ? 3 : 0
            width: root.boxResizeActive ? root.boxResizeRect.width
                : root.sampleMode ? sampleLabel.contentWidth + glyphPadding * 2
                : Math.max(1, Number(root.sprite.width || 1) * rasterScale) + glyphPadding * 2
            height: root.boxResizeActive ? root.boxResizeRect.height
                : root.sampleMode ? sampleLabel.contentHeight + glyphPadding * 2
                : Math.max(1, Number(root.sprite.height || 1) * rasterScale) + glyphPadding * 2
            x: root.boxResizeActive ? root.boxResizeRect.x : root.sampleMode
                ? videoCanvas.width * root.draftPositionX / 100 - width / 2
                : rasterX - glyphPadding
            y: root.boxResizeActive ? root.boxResizeRect.y : root.sampleMode
                ? videoCanvas.height * root.draftPositionY / 100 - height / 2
                : rasterY - glyphPadding
            color: "transparent"
            border.width: root.editing && root.livePreviewVisible ? 1 : 0
            border.color: root.editing ? Theme.focus : Theme.outlineStrong
            radius: Theme.radiusTiny
            activeFocusOnTab: root.interactive
            Accessible.role: Accessible.Slider
            Accessible.name: qsTr("Vị trí và cỡ phụ đề")
            Text {
                id: sampleLabel
                anchors.centerIn: parent
                visible: root.sampleMode
                text: root.sampleText
                color: root.sampleTextColor
                style: Text.Outline
                styleColor: root.sampleOutlineColor
                font.family: root.sampleFontFamily
                font.pixelSize: root.previewFontSize
                font.bold: root.sampleBold
                font.italic: root.sampleItalic
                width: Math.max(1, videoCanvas.width * root.draftBoxWidth / 100)
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                textFormat: Text.PlainText
            }
            Item {
                anchors.fill: parent
                visible: root.livePreviewVisible
                Image {
                    objectName: "subtitleTransformSprite"
                    x: selection.rasterX - selection.x - Number(root.sprite.x || 0) * selection.rasterScale
                    y: selection.rasterY - selection.y - Number(root.sprite.y || 0) * selection.rasterScale
                    width: Number(root.sprite.outputWidth || 1) * selection.rasterScale
                    height: Number(root.sprite.outputHeight || 1) * selection.rasterScale
                    source: root.sprite.normal || ""
                    visible: !root.sampleMode
                    sourceSize: Qt.size(Number(root.sprite.outputWidth || 1), Number(root.sprite.outputHeight || 1))
                    asynchronous: true
                }
                Repeater {
                    // An integer model preserves image delegates during playback.
                    // Only mask widths change; no raster work runs on a video tick.
                    model: Math.max(1, Number(root.sprite.lineCount || 1))
                    delegate: Item {
                        id: karaokeLine
                        required property int index
                        z: 1
                        readonly property var line: (root.sprite.karaokeLines || [])[index] || root.sprite
                        objectName: "subtitleKaraokeLine" + index
                        x: selection.rasterX - selection.x
                            + (Number(line.x || 0) - Number(root.sprite.x || 0)) * selection.rasterScale
                        y: selection.rasterY - selection.y
                            + (Number(line.y || 0) - Number(root.sprite.y || 0)) * selection.rasterScale
                        width: Number(line.width || 0) * selection.rasterScale
                            * root.clamp(Number(line.progress || 0), 0, 1)
                        height: Number(line.height || 0) * selection.rasterScale
                        clip: true
                        Image {
                            x: -Number(karaokeLine.line.x || 0) * selection.rasterScale
                            y: -Number(karaokeLine.line.y || 0) * selection.rasterScale
                            width: Number(root.sprite.outputWidth || 1) * selection.rasterScale
                            height: Number(root.sprite.outputHeight || 1) * selection.rasterScale
                            source: root.sprite.karaoke || ""
                            sourceSize: Qt.size(Number(root.sprite.outputWidth || 1), Number(root.sprite.outputHeight || 1))
                            asynchronous: true
                        }
                    }
                }
            }

            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Escape) {
                    root.editingDismissed();
                    event.accepted = true;
                    return;
                }
                if (!root.editing)
                    return;
                const step = event.modifiers & Qt.ShiftModifier ? 5 : 1;
                if (event.key === Qt.Key_Left)
                    root.draftPositionX = root.clamp(root.draftPositionX - step, 0, 100);
                else if (event.key === Qt.Key_Right)
                    root.draftPositionX = root.clamp(root.draftPositionX + step, 0, 100);
                else if (event.key === Qt.Key_Up)
                    root.draftPositionY = root.clamp(root.draftPositionY - step, 0, 100);
                else if (event.key === Qt.Key_Down)
                    root.draftPositionY = root.clamp(root.draftPositionY + step, 0, 100);
                else if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal)
                    root.draftFontSize = root.clamp(root.draftFontSize + step, 10, 240);
                else if (event.key === Qt.Key_Minus)
                    root.draftFontSize = root.clamp(root.draftFontSize - step, 10, 240);
                else
                    return;
                event.accepted = true;
                root.publishPreview();
                root.commit();
            }

            MouseArea {
                id: moveArea
                enabled: root.interactive
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: root.editing ? Qt.SizeAllCursor : Qt.PointingHandCursor
                property real offsetX: 0
                property real offsetY: 0
                property bool moved: false

                onPressed: function(mouse) {
                    root.activateEditor();
                    const point = mapToItem(videoCanvas, mouse.x, mouse.y);
                    offsetX = point.x - videoCanvas.width * root.draftPositionX / 100;
                    offsetY = point.y - videoCanvas.height * root.draftPositionY / 100;
                    moved = false;
                }
                onPositionChanged: function(mouse) {
                    if (!pressed || !root.editing)
                        return;
                    const point = mapToItem(videoCanvas, mouse.x, mouse.y);
                    let nextX = root.clamp((point.x - offsetX) / videoCanvas.width * 100, 0, 100);
                    let nextY = root.clamp((point.y - offsetY) / videoCanvas.height * 100, 0, 100);
                    if (Math.abs(nextX - 50) <= 0.7)
                        nextX = 50;
                    if (Math.abs(nextY - 50) <= 0.7)
                        nextY = 50;
                    root.draftPositionX = nextX;
                    root.draftPositionY = nextY;
                    root.publishPreview();
                    moved = true;
                }
                onReleased: if (moved) root.commit()
            }

            Rectangle {
                visible: root.editing
                z: 3
                x: root.clamp(
                    selection.width - width,
                    -selection.x,
                    videoCanvas.width - selection.x - width
                )
                y: selection.y > height + Theme.space4
                    ? -height - Theme.space4
                    : selection.height + Theme.space4
                width: measurementText.implicitWidth + Theme.space12
                height: 24
                radius: Theme.radiusTiny
                color: Theme.surfaceElevated
                border.width: 1
                border.color: Theme.outlineStrong

                Text {
                    id: measurementText
                    anchors.centerIn: parent
                    text: qsTr("%1 px · %2% × %3%")
                        .arg(Math.round(root.draftFontSize))
                        .arg(Math.round(root.draftBoxWidth))
                        .arg(Math.round(root.draftBoxHeight))
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }
            }

            Repeater {
                id: edgeHandles
                model: [{h: -1, v: 0}, {h: 1, v: 0}, {h: 0, v: -1}, {h: 0, v: 1}]
                delegate: SubtitleBoxHandle {
                    required property var modelData
                    selectionItem: selection
                    canvasItem: videoCanvas
                    horizontalDirection: modelData.h
                    verticalDirection: modelData.v
                    minimumWidthPixels: Math.min(root.boxResizeStartRect.width, videoCanvas.width * 0.2)
                    maximumWidthPixels: videoCanvas.width
                    minimumHeightPixels: Math.max(4, root.boxResizeStartRect.height / Math.max(1, root.boxResizeStartHeight))
                    maximumHeightPixels: root.boxResizeStartRect.height * 100 / Math.max(1, root.boxResizeStartHeight)
                    visible: root.editing
                    onResizeStarted: root.beginBoxResize()
                    onRectanglePreviewed: function(rectangle) { root.previewBox(rectangle); }
                    onRectangleCommitted: function(rectangle) {
                        root.previewBox(rectangle);
                        root.commit();
                        root.boxResizeActive = false;
                    }
                    onResizeCanceled: root.cancelBoxResize()
                }
            }
            CornerScaleHandle {
                id: topLeftHandle
                z: 6
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: -1
                verticalDirection: -1
                currentValue: root.draftFontSize
                minimumValue: 10
                maximumValue: 240
                objectNamePrefix: "subtitleScaleHandle"
                scaleReferenceExtent: selection.fontScaleExtent
                visible: root.editing
                onResizeStarted: root.activateEditor()
                onValuePreviewed: function(value) {
                    root.draftFontSize = value;
                    root.publishPreview();
                }
                onValueCommitted: function(_beforeValue, value) {
                    root.draftFontSize = value;
                    root.commit();
                }
            }
            CornerScaleHandle {
                id: topRightHandle
                z: 6
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: 1
                verticalDirection: -1
                currentValue: root.draftFontSize
                minimumValue: 10
                maximumValue: 240
                objectNamePrefix: "subtitleScaleHandle"
                scaleReferenceExtent: selection.fontScaleExtent
                visible: root.editing
                onResizeStarted: root.activateEditor()
                onValuePreviewed: function(value) {
                    root.draftFontSize = value;
                    root.publishPreview();
                }
                onValueCommitted: function(_beforeValue, value) {
                    root.draftFontSize = value;
                    root.commit();
                }
            }
            CornerScaleHandle {
                id: bottomLeftHandle
                z: 6
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: -1
                verticalDirection: 1
                currentValue: root.draftFontSize
                minimumValue: 10
                maximumValue: 240
                objectNamePrefix: "subtitleScaleHandle"
                scaleReferenceExtent: selection.fontScaleExtent
                visible: root.editing
                onResizeStarted: root.activateEditor()
                onValuePreviewed: function(value) {
                    root.draftFontSize = value;
                    root.publishPreview();
                }
                onValueCommitted: function(_beforeValue, value) {
                    root.draftFontSize = value;
                    root.commit();
                }
            }
            CornerScaleHandle {
                id: bottomRightHandle
                z: 6
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: 1
                verticalDirection: 1
                currentValue: root.draftFontSize
                minimumValue: 10
                maximumValue: 240
                objectNamePrefix: "subtitleScaleHandle"
                scaleReferenceExtent: selection.fontScaleExtent
                visible: root.editing
                onResizeStarted: root.activateEditor()
                onValuePreviewed: function(value) {
                    root.draftFontSize = value;
                    root.publishPreview();
                }
                onValueCommitted: function(_beforeValue, value) {
                    root.draftFontSize = value;
                    root.commit();
                }
            }
        }
    }

}
