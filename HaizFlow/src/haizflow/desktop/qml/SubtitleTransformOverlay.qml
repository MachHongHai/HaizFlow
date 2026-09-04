pragma ComponentBehavior: Bound

import QtQuick
import "."

Item {
    id: root

    property rect videoRect: Qt.rect(0, 0, 0, 0)
    property string subtitleText: ""
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

    visible: interactive
        && subtitleText.trim().length > 0
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
            Math.round(clamp(draftFontSize, 10, 160)),
            Math.round(clamp(draftPositionX, 0, 100)),
            Math.round(clamp(draftPositionY, 0, 100))
        );
    }

    function publishPreview() {
        layoutPreviewChanged(
            Math.round(clamp(draftFontSize, 10, 160)),
            Math.round(clamp(draftPositionX, 0, 100)),
            Math.round(clamp(draftPositionY, 0, 100))
        );
    }

    function activateEditor() {
        if (!editing)
            activated();
        selection.forceActiveFocus();
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

        Text {
            id: textMeasure
            visible: false
            text: root.subtitleText
            font.family: karaokeFont.status === FontLoader.Ready ? karaokeFont.name : Theme.fontFamily
            font.bold: false
            font.pixelSize: root.previewFontSize
            font.letterSpacing: root.previewLetterSpacing
            textFormat: Text.PlainText
        }

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
            readonly property real maximumTextWidth: Math.max(
                48,
                videoCanvas.width * root.clamp(root.boxWidthPercent, 20, 100) / 100
            )
            readonly property real outlinePadding: Math.max(
                4,
                root.outlineWidth * root.previewScale + 2 * root.previewScale
            )

            readonly property real rendererWidthLimit: root.layoutWidthPixels > 0
                ? root.layoutWidthPixels * root.previewScale
                : maximumTextWidth
            readonly property real rendererHeightLimit: root.layoutHeightPixels > 0
                ? root.layoutHeightPixels * root.previewScale
                : videoCanvas.height * 0.32

            width: root.clamp(
                textMeasure.implicitWidth + outlinePadding * 2,
                48,
                Math.max(48, Math.min(maximumTextWidth, rendererWidthLimit))
            )
            height: root.clamp(
                textMeasure.implicitHeight + outlinePadding * 2,
                26,
                Math.max(26, rendererHeightLimit)
            )
            x: root.clamp(
                videoCanvas.width * root.draftPositionX / 100 - width / 2,
                0,
                Math.max(0, videoCanvas.width - width)
            )
            y: root.clamp(
                videoCanvas.height * root.draftPositionY / 100 - height / 2,
                0,
                Math.max(0, videoCanvas.height - height)
            )
            color: root.editing
                ? Qt.rgba(
                    Theme.interactive.r,
                    Theme.interactive.g,
                    Theme.interactive.b,
                    0.08
                )
                : "transparent"
            border.width: root.editing && root.livePreviewVisible ? 1 : 0
            border.color: root.editing ? Theme.focus : Theme.outlineStrong
            radius: Theme.radiusTiny
            activeFocusOnTab: root.interactive
            Accessible.role: Accessible.Slider
            Accessible.name: qsTr("Vị trí và cỡ phụ đề")
            onActiveFocusChanged: {
                if (!activeFocus
                        && root.editing
                        && !root.resizeInProgress()
                        && !moveArea.pressed)
                    root.editingDismissed();
            }

            Text {
                id: liveSubtitle
                objectName: "subtitleTransformLiveText"
                x: selection.outlinePadding
                y: selection.outlinePadding
                width: Math.max(1, selection.width - selection.outlinePadding * 2)
                height: Math.max(1, selection.height - selection.outlinePadding * 2)
                text: root.subtitleText
                visible: root.livePreviewVisible
                color: "#FFFFFFFF"
                font.family: karaokeFont.status === FontLoader.Ready ? karaokeFont.name : Theme.fontFamily
                font.bold: false
                font.pixelSize: root.previewFontSize
                font.letterSpacing: root.previewLetterSpacing
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.NoWrap
                elide: Text.ElideNone
                style: Text.Outline
                styleColor: "#FF000000"
                textFormat: Text.PlainText
            }

            Item {
                x: selection.outlinePadding
                y: selection.outlinePadding
                width: Math.max(
                    0,
                    (selection.width - selection.outlinePadding * 2)
                        * root.clamp(root.karaokeProgress, 0, 1)
                )
                height: Math.max(1, selection.height - selection.outlinePadding * 2)
                visible: root.livePreviewVisible && width > 0
                clip: true

                Text {
                    width: Math.max(1, selection.width - selection.outlinePadding * 2)
                    height: parent.height
                    text: root.subtitleText
                    color: "#FFEF00"
                    font.family: karaokeFont.status === FontLoader.Ready
                        ? karaokeFont.name : Theme.fontFamily
                    font.bold: false
                    font.pixelSize: root.previewFontSize
                    font.letterSpacing: root.previewLetterSpacing
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.NoWrap
                    elide: Text.ElideNone
                    style: Text.Outline
                    styleColor: "#FF000000"
                    textFormat: Text.PlainText
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
                    root.draftFontSize = root.clamp(root.draftFontSize + step, 10, 160);
                else if (event.key === Qt.Key_Minus)
                    root.draftFontSize = root.clamp(root.draftFontSize - step, 10, 160);
                else
                    return;
                event.accepted = true;
                root.publishPreview();
                root.commit();
            }

            MouseArea {
                id: moveArea
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

            ScaleHandle {
                id: topLeftHandle
                horizontalDirection: -1
                verticalDirection: -1
            }
            ScaleHandle {
                id: topRightHandle
                horizontalDirection: 1
                verticalDirection: -1
            }
            ScaleHandle {
                id: bottomLeftHandle
                horizontalDirection: -1
                verticalDirection: 1
            }
            ScaleHandle {
                id: bottomRightHandle
                horizontalDirection: 1
                verticalDirection: 1
            }
        }
    }

    component ScaleHandle: Rectangle {
        id: handle

        required property int horizontalDirection
        required property int verticalDirection
        readonly property bool pressed: resizeArea.pressed
        property real startDistance: 1
        property int startFontSize: 60

        visible: root.editing
        z: 4
        x: horizontalDirection < 0 ? 0 : selection.width - width
        y: verticalDirection < 0 ? 0 : selection.height - height
        width: 10
        height: 10
        radius: 2
        color: Theme.focus
        border.width: 2
        border.color: Theme.surface

        MouseArea {
            id: resizeArea
            anchors.fill: parent
            anchors.margins: -7
            cursorShape: handle.horizontalDirection === handle.verticalDirection
                ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor

            onPressed: function(mouse) {
                root.activateEditor();
                const point = mapToItem(videoCanvas, mouse.x, mouse.y);
                const centerX = selection.x + selection.width / 2;
                const centerY = selection.y + selection.height / 2;
                handle.startDistance = Math.max(1, Math.hypot(point.x - centerX, point.y - centerY));
                handle.startFontSize = root.draftFontSize;
            }
            onPositionChanged: function(mouse) {
                if (!pressed)
                    return;
                const point = mapToItem(videoCanvas, mouse.x, mouse.y);
                const centerX = selection.x + selection.width / 2;
                const centerY = selection.y + selection.height / 2;
                const distance = Math.max(1, Math.hypot(point.x - centerX, point.y - centerY));
                root.draftFontSize = root.clamp(
                    handle.startFontSize * distance / handle.startDistance,
                    10,
                    160
                );
                root.publishPreview();
            }
            onReleased: root.commit()
        }
    }

    FontLoader {
        id: karaokeFont
        source: "../../assets/fonts/Bangers-Regular.ttf"
    }
}
