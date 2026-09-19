pragma ComponentBehavior: Bound

import QtQuick
import "."

Item {
    id: root

    property rect videoRect: Qt.rect(0, 0, 0, 0)
    property string subtitleText: ""
    property var sprite: ({})
    property real karaokeProgress: 0
    property int fontSize: 60
    property int positionXPercent: 50
    property int positionYPercent: 88
    property int boxWidthPercent: 72
    property int outlineWidth: 5
    property int layoutWidthPixels: 0
    property int layoutHeightPixels: 0
    property int referenceWidthPixels: 0
    property int referenceHeightPixels: 0
    property bool interactive: false
    property bool editing: false
    property bool livePreviewVisible: true
    signal activated()
    signal editingDismissed()
    signal layoutPreviewChanged(int fontSize, int positionX, int positionY)
    signal layoutCommitted(int fontSize, int positionX, int positionY)

    property int draftFontSize: fontSize
    property real draftPositionX: positionXPercent
    property real draftPositionY: positionYPercent
    readonly property real referenceHeight: referenceHeightPixels > 0
        ? referenceHeightPixels
        : videoCanvas.height > videoCanvas.width ? 1920 : 1080
    readonly property real previewFontSize: Math.max(
        10,
        draftFontSize * videoCanvas.height / Math.max(1, referenceHeight)
    )
    readonly property real referenceWidth: referenceWidthPixels > 0
        ? referenceWidthPixels
        : videoCanvas.height > videoCanvas.width ? 1080 : 1920
    readonly property real previewScale: Math.min(
        videoCanvas.width / Math.max(1, referenceWidth),
        videoCanvas.height / Math.max(1, referenceHeight)
    )
    readonly property real previewLetterSpacing: Math.max(0, previewScale)

    visible: (interactive || livePreviewVisible)
        && String(sprite.normal || "").length > 0
        && videoRect.width > 0
        && videoRect.height > 0

    onFontSizeChanged: if (!moveArea.pressed && !resizeInProgress()) draftFontSize = fontSize
    onPositionXPercentChanged: if (!moveArea.pressed) draftPositionX = positionXPercent
    onPositionYPercentChanged: if (!moveArea.pressed) draftPositionY = positionYPercent

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function resizeInProgress() {
        return topLeftHandle.pressed
            || topRightHandle.pressed
            || bottomLeftHandle.pressed
            || bottomRightHandle.pressed;
    }

    function commit() {
        layoutCommitted(
            Math.round(clamp(draftFontSize, 10, 240)),
            Math.round(clamp(draftPositionX, 0, 100)),
            Math.round(clamp(draftPositionY, 0, 100))
        );
    }

    function publishPreview() {
        layoutPreviewChanged(
            Math.round(clamp(draftFontSize, 10, 240)),
            Math.round(clamp(draftPositionX, 0, 100)),
            Math.round(clamp(draftPositionY, 0, 100))
        );
    }

    function activateEditor() {
        if (!editing)
            activated();

    }

    MouseArea {
        anchors.fill: parent
        enabled: root.editing
        onClicked: root.editingDismissed()
    }

    Item {
        id: videoCanvas
        x: root.videoRect.x
        y: root.videoRect.y
        width: root.videoRect.width
        height: root.videoRect.height

        MouseArea {
            anchors.fill: parent
            enabled: root.editing
            onClicked: root.editingDismissed()
        }

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
            width: Math.max(1, Number(root.sprite.width || 1) * rasterScale)
            height: Math.max(1, Number(root.sprite.height || 1) * rasterScale)
            x: videoCanvas.width * root.draftPositionX / 100
                + (Number(root.sprite.x || 0) - Number(root.sprite.outputWidth || 1)
                   * Number(root.sprite.positionXPercent || 50) / 100) * rasterScale
            y: videoCanvas.height * root.draftPositionY / 100
                + (Number(root.sprite.y || 0) - Number(root.sprite.outputHeight || 1)
                   * Number(root.sprite.positionYPercent || 88) / 100) * rasterScale
            color: "transparent"
            border.width: root.editing && root.livePreviewVisible ? 1 : 0
            border.color: root.editing ? Theme.focus : Theme.outlineStrong
            radius: Theme.radiusTiny
            activeFocusOnTab: root.interactive
            Accessible.role: Accessible.Slider
            Accessible.name: qsTr("Vị trí và cỡ phụ đề")
            Item {
                anchors.fill: parent
                visible: root.livePreviewVisible
                clip: true
                Image {
                    objectName: "subtitleTransformSprite"
                    x: -Number(root.sprite.x || 0) * selection.rasterScale
                    y: -Number(root.sprite.y || 0) * selection.rasterScale
                    width: Number(root.sprite.outputWidth || 1) * selection.rasterScale
                    height: Number(root.sprite.outputHeight || 1) * selection.rasterScale
                    source: root.sprite.normal || ""
                    sourceSize: Qt.size(Number(root.sprite.outputWidth || 1), Number(root.sprite.outputHeight || 1))
                    asynchronous: true
                }
                Item {
                    width: parent.width * root.clamp(Number(root.sprite.progress || 0), 0, 1)
                    height: parent.height
                    clip: true
                    Image {
                        x: -Number(root.sprite.x || 0) * selection.rasterScale
                        y: -Number(root.sprite.y || 0) * selection.rasterScale
                        width: Number(root.sprite.outputWidth || 1) * selection.rasterScale
                        height: Number(root.sprite.outputHeight || 1) * selection.rasterScale
                        source: root.sprite.karaoke || ""
                        sourceSize: Qt.size(Number(root.sprite.outputWidth || 1), Number(root.sprite.outputHeight || 1))
                        asynchronous: true
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
                    offsetX = point.x - (selection.x + selection.width / 2);
                    offsetY = point.y - (selection.y + selection.height / 2);
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
                    text: qsTr("%1 px · X %2% · Y %3%")
                        .arg(Math.round(root.draftFontSize))
                        .arg(Math.round(root.draftPositionX))
                        .arg(Math.round(root.draftPositionY))
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }
            }

            CornerScaleHandle {
                id: topLeftHandle
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: -1
                verticalDirection: -1
                currentValue: root.draftFontSize
                minimumValue: 10
                maximumValue: 240
                objectNamePrefix: "subtitleScaleHandle"
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
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: 1
                verticalDirection: -1
                currentValue: root.draftFontSize
                minimumValue: 10
                maximumValue: 240
                objectNamePrefix: "subtitleScaleHandle"
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
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: -1
                verticalDirection: 1
                currentValue: root.draftFontSize
                minimumValue: 10
                maximumValue: 240
                objectNamePrefix: "subtitleScaleHandle"
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
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: 1
                verticalDirection: 1
                currentValue: root.draftFontSize
                minimumValue: 10
                maximumValue: 240
                objectNamePrefix: "subtitleScaleHandle"
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
