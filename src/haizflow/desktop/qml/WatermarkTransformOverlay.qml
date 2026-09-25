pragma ComponentBehavior: Bound

import QtQuick
import QtMultimedia
import "."

Item {
    id: root

    property rect videoRect: Qt.rect(0, 0, 0, 0)
    property string watermarkKind: "text"
    property string watermarkText: ""
    property url watermarkImageSource: ""
    property url watermarkVideoSource: ""
    property string fontFamily: "Arial"
    property color textColor: "#FFFFFF"
    property bool fontBold: true
    property bool fontItalic: true
    property int opacityPercent: 46
    property int outlinePercent: 100
    property int scalePercent: 100
    property real timeSeconds: 0
    property int referenceWidthPixels: 0
    property int referenceHeightPixels: 0
    property bool interactive: false
    property bool editing: false
    property bool livePreviewVisible: true
    property bool playing: false
    property int draftScalePercent: scalePercent

    signal activated()
    signal editingDismissed()
    signal scalePreviewChanged(int scalePercent)
    signal scaleCommitted(int beforeScalePercent, int afterScalePercent)

    readonly property bool imageMode: watermarkKind === "image"
    readonly property bool videoMode: watermarkKind === "video"
    readonly property bool mediaMode: imageMode || videoMode
    readonly property bool hasContent: imageMode ? String(watermarkImageSource).length > 0
        : videoMode ? String(watermarkVideoSource).length > 0 : watermarkText.trim().length > 0
    readonly property real referenceWidth: referenceWidthPixels > 0
        ? referenceWidthPixels : (videoCanvas.height > videoCanvas.width ? 1080 : 1920)
    readonly property real referenceHeight: referenceHeightPixels > 0
        ? referenceHeightPixels : (videoCanvas.height > videoCanvas.width ? 1920 : 1080)
    readonly property real previewScale: Math.min(
        videoCanvas.width / Math.max(1, referenceWidth),
        videoCanvas.height / Math.max(1, referenceHeight)
    )
    readonly property real baseFontSize: Math.max(
        15, Math.min(38, Math.round(Math.min(referenceWidth, referenceHeight) * 0.029))
    )
    readonly property real previewFontSize: Math.max(
        8, Math.min(114, Math.round(baseFontSize * draftScalePercent / 100))
    ) * previewScale
    readonly property real imageWidth: Math.max(24, Math.min(
        videoCanvas.width * 0.72,
        videoCanvas.width * 0.16 * draftScalePercent / 100
    ))
    readonly property real imageAspect: videoMode && watermarkVideoOutput.sourceRect.height > 0
        ? watermarkVideoOutput.sourceRect.width / watermarkVideoOutput.sourceRect.height
        : watermarkImage.status === Image.Ready
            && watermarkImage.sourceSize.width > 0 && watermarkImage.sourceSize.height > 0
        ? watermarkImage.sourceSize.width / watermarkImage.sourceSize.height : (videoMode ? 16 / 9 : 1)
    readonly property real previewOutline: Math.max(0, Math.min(8,
        previewFontSize * 0.065 * outlinePercent / 100))

    visible: livePreviewVisible && hasContent && videoRect.width > 0 && videoRect.height > 0
    onScalePercentChanged: if (!resizeInProgress()) draftScalePercent = scalePercent
    onVisibleChanged: syncVideoPlayback()
    onPlayingChanged: syncVideoPlayback()
    onTimeSecondsChanged: {
        if (videoMode && watermarkVideoPlayer.duration > 0 && !playing) {
            const expected = Math.round((timeSeconds * 1000) % watermarkVideoPlayer.duration);
            if (Math.abs(watermarkVideoPlayer.position - expected) > 120)
                watermarkVideoPlayer.setPosition(expected);
        }
    }

    function syncVideoPlayback() {
        if (!videoMode || !visible) {
            watermarkVideoPlayer.pause();
            return;
        }
        if (watermarkVideoPlayer.duration > 0) {
            const expected = Math.round((timeSeconds * 1000) % watermarkVideoPlayer.duration);
            if (Math.abs(watermarkVideoPlayer.position - expected) > 250)
                watermarkVideoPlayer.setPosition(expected);
        }
        if (playing)
            watermarkVideoPlayer.play();
        else
            watermarkVideoPlayer.pause();
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }
    function resizeInProgress() {
        return topLeftHandle.pressed || topRightHandle.pressed
            || bottomLeftHandle.pressed || bottomRightHandle.pressed;
    }
    function publishPreview(value) {
        draftScalePercent = clamp(Math.round(value), 25, 300);
        scalePreviewChanged(draftScalePercent);
    }
    function outlineX(index) { return [-1, 0, 1, -1, 1, -1, 0, 1][index] * previewOutline; }
    function outlineY(index) { return [-1, -1, -1, 0, 0, 1, 1, 1][index] * previewOutline; }

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

        Item {
            id: mark
            objectName: "watermarkTransformMark"
            width: root.mediaMode ? root.imageWidth : watermarkLabel.implicitWidth + root.previewOutline * 2
            height: root.mediaMode ? root.imageWidth / Math.max(0.05, root.imageAspect)
                : watermarkLabel.implicitHeight + root.previewOutline * 2
            x: (videoCanvas.width - width) * (
                0.08 + 0.84 * (0.5 + 0.5 * Math.sin(2 * Math.PI * root.timeSeconds / 31)))
            y: (videoCanvas.height - height) * (
                0.10 + 0.80 * (0.5 + 0.5 * Math.sin(2 * Math.PI * root.timeSeconds / 43 + 1.2)))

            Repeater {
                model: root.mediaMode || root.previewOutline <= 0 ? 0 : 8
                delegate: Text {
                    required property int index
                    x: root.previewOutline + root.outlineX(index)
                    y: root.previewOutline + root.outlineY(index)
                    text: root.watermarkText.trim()
                    color: "black"
                    opacity: Math.min(1, root.opacityPercent / 100 + 0.02)
                    font: watermarkLabel.font
                    textFormat: Text.PlainText
                    renderType: Text.NativeRendering
                }
            }

            Text {
                id: watermarkLabel
                objectName: "watermarkTransformText"
                visible: !root.mediaMode
                x: root.previewOutline
                y: root.previewOutline
                text: root.watermarkText.trim()
                color: root.textColor
                opacity: root.opacityPercent / 100
                font.family: root.fontFamily
                font.bold: root.fontBold
                font.italic: root.fontItalic
                font.pixelSize: root.previewFontSize
                textFormat: Text.PlainText
                renderType: Text.NativeRendering
            }

            Rectangle {
                visible: root.mediaMode
                anchors.fill: parent
                color: "transparent"
                radius: Theme.radiusTiny

                Image {
                    id: watermarkImage
                    anchors.fill: parent
                    anchors.margins: 0
                    visible: root.imageMode
                    source: root.imageMode ? root.watermarkImageSource : ""
                    sourceSize.width: 1024
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    mipmap: true
                    opacity: root.opacityPercent / 100
                }

                VideoOutput {
                    id: watermarkVideoOutput
                    anchors.fill: parent
                    anchors.margins: 0
                    visible: root.videoMode
                    fillMode: VideoOutput.PreserveAspectFit
                    opacity: root.opacityPercent / 100
                    endOfStreamPolicy: VideoOutput.KeepLastFrame
                }

                MediaPlayer {
                    id: watermarkVideoPlayer
                    source: root.visible && root.videoMode ? root.watermarkVideoSource : ""
                    videoOutput: watermarkVideoOutput
                    loops: MediaPlayer.Infinite
                    onMediaStatusChanged: {
                        if (mediaStatus === MediaPlayer.LoadedMedia)
                            root.syncVideoPlayback();
                    }
                }
            }

            MouseArea {
                anchors.fill: parent
                anchors.margins: -8
                enabled: root.interactive
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.activated()
            }
        }

        Rectangle {
            id: selection
            objectName: "watermarkTransformSelection"
            x: mark.x - 3
            y: mark.y - 3
            width: mark.width + 6
            height: mark.height + 6
            color: "transparent"
            border.width: root.editing ? 1 : 0
            border.color: Theme.focus
            radius: Theme.radiusTiny
            visible: root.editing && !root.mediaMode
            activeFocusOnTab: root.interactive
            Accessible.role: Accessible.Slider
            Accessible.name: qsTr("Kích thước watermark")

            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Escape) {
                    root.editingDismissed(); event.accepted = true; return;
                }
                const step = event.modifiers & Qt.ShiftModifier ? 10 : 2;
                const before = root.draftScalePercent;
                if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal)
                    root.publishPreview(before + step);
                else if (event.key === Qt.Key_Minus)
                    root.publishPreview(before - step);
                else return;
                root.scaleCommitted(before, root.draftScalePercent);
                event.accepted = true;
            }

            Rectangle {
                z: 3
                x: Math.max(0, selection.width - width)
                y: selection.y > height + Theme.space4 ? -height - Theme.space4 : selection.height + Theme.space4
                width: scaleText.implicitWidth + Theme.space12
                height: 24
                radius: Theme.radiusTiny
                color: Theme.surfaceElevated
                border.width: 1
                border.color: Theme.outlineStrong
                Text {
                    id: scaleText
                    anchors.centerIn: parent
                    text: qsTr("%1%").arg(root.draftScalePercent)
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }
            }

            CornerScaleHandle {
                id: topLeftHandle
                selectionItem: selection; coordinateItem: root
                horizontalDirection: -1; verticalDirection: -1
                currentValue: root.draftScalePercent; minimumValue: 25; maximumValue: 300
                objectNamePrefix: "watermarkScaleHandle"
                onValuePreviewed: function(value) { root.publishPreview(value); }
                onValueCommitted: function(beforeValue, value) {
                    root.publishPreview(value); root.scaleCommitted(Math.round(beforeValue), root.draftScalePercent);
                }
            }
            CornerScaleHandle {
                id: topRightHandle
                selectionItem: selection; coordinateItem: root
                horizontalDirection: 1; verticalDirection: -1
                currentValue: root.draftScalePercent; minimumValue: 25; maximumValue: 300
                objectNamePrefix: "watermarkScaleHandle"
                onValuePreviewed: function(value) { root.publishPreview(value); }
                onValueCommitted: function(beforeValue, value) {
                    root.publishPreview(value); root.scaleCommitted(Math.round(beforeValue), root.draftScalePercent);
                }
            }
            CornerScaleHandle {
                id: bottomLeftHandle
                selectionItem: selection; coordinateItem: root
                horizontalDirection: -1; verticalDirection: 1
                currentValue: root.draftScalePercent; minimumValue: 25; maximumValue: 300
                objectNamePrefix: "watermarkScaleHandle"
                onValuePreviewed: function(value) { root.publishPreview(value); }
                onValueCommitted: function(beforeValue, value) {
                    root.publishPreview(value); root.scaleCommitted(Math.round(beforeValue), root.draftScalePercent);
                }
            }
            CornerScaleHandle {
                id: bottomRightHandle
                selectionItem: selection; coordinateItem: root
                horizontalDirection: 1; verticalDirection: 1
                currentValue: root.draftScalePercent; minimumValue: 25; maximumValue: 300
                objectNamePrefix: "watermarkScaleHandle"
                onValuePreviewed: function(value) { root.publishPreview(value); }
                onValueCommitted: function(beforeValue, value) {
                    root.publishPreview(value); root.scaleCommitted(Math.round(beforeValue), root.draftScalePercent);
                }
            }
        }
    }
}
