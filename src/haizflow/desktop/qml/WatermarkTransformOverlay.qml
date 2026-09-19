pragma ComponentBehavior: Bound

import QtQuick
import "."

Item {
    id: root

    property rect videoRect: Qt.rect(0, 0, 0, 0)
    property string watermarkText: ""
    property int scalePercent: 100
    property real timeSeconds: 0
    property int referenceWidthPixels: 0
    property int referenceHeightPixels: 0
    property bool interactive: false
    property bool editing: false
    property bool livePreviewVisible: true
    property int draftScalePercent: scalePercent

    signal activated()
    signal editingDismissed()
    signal scalePreviewChanged(int scalePercent)
    signal scaleCommitted(int beforeScalePercent, int afterScalePercent)

    readonly property real referenceWidth: referenceWidthPixels > 0
        ? referenceWidthPixels : (videoCanvas.height > videoCanvas.width ? 1080 : 1920)
    readonly property real referenceHeight: referenceHeightPixels > 0
        ? referenceHeightPixels : (videoCanvas.height > videoCanvas.width ? 1920 : 1080)
    readonly property real previewScale: Math.min(
        videoCanvas.width / Math.max(1, referenceWidth),
        videoCanvas.height / Math.max(1, referenceHeight)
    )
    readonly property real baseFontSize: Math.max(
        15,
        Math.min(38, Math.round(Math.min(referenceWidth, referenceHeight) * 0.029))
    )
    readonly property real previewFontSize: Math.max(
        8,
        Math.min(114, Math.round(baseFontSize * draftScalePercent / 100))
    ) * previewScale

    visible: livePreviewVisible
        && watermarkText.trim().length > 0
        && videoRect.width > 0
        && videoRect.height > 0

    onScalePercentChanged: if (!resizeInProgress()) draftScalePercent = scalePercent

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function resizeInProgress() {
        return topLeftHandle.pressed
            || topRightHandle.pressed
            || bottomLeftHandle.pressed
            || bottomRightHandle.pressed;
    }

    function publishPreview(value) {
        draftScalePercent = clamp(Math.round(value), 25, 300);
        scalePreviewChanged(draftScalePercent);
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
            id: watermarkLabel
            objectName: "watermarkTransformText"
            text: root.watermarkText.trim()
            color: "#75FFFFFF"
            style: Text.Outline
            styleColor: "#7A000000"
            font.family: "Arial"
            font.bold: true
            font.italic: true
            font.pixelSize: root.previewFontSize
            textFormat: Text.PlainText
            renderType: Text.NativeRendering
            x: (videoCanvas.width - width) * (
                0.08 + 0.84 * (0.5 + 0.5 * Math.sin(2 * Math.PI * root.timeSeconds / 31))
            )
            y: (videoCanvas.height - height) * (
                0.10 + 0.80 * (0.5 + 0.5 * Math.sin(2 * Math.PI * root.timeSeconds / 43 + 1.2))
            )

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
            x: watermarkLabel.x - 3
            y: watermarkLabel.y - 3
            width: watermarkLabel.width + 6
            height: watermarkLabel.height + 6
            color: "transparent"
            border.width: root.editing ? 1 : 0
            border.color: Theme.focus
            radius: Theme.radiusTiny
            visible: root.editing
            activeFocusOnTab: root.interactive
            Accessible.role: Accessible.Slider
            Accessible.name: qsTr("Kích thước watermark")

            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Escape) {
                    root.editingDismissed();
                    event.accepted = true;
                    return;
                }
                const step = event.modifiers & Qt.ShiftModifier ? 10 : 2;
                const before = root.draftScalePercent;
                if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal)
                    root.publishPreview(before + step);
                else if (event.key === Qt.Key_Minus)
                    root.publishPreview(before - step);
                else
                    return;
                root.scaleCommitted(before, root.draftScalePercent);
                event.accepted = true;
            }

            Rectangle {
                z: 3
                x: Math.max(0, selection.width - width)
                y: selection.y > height + Theme.space4
                    ? -height - Theme.space4 : selection.height + Theme.space4
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
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: -1
                verticalDirection: -1
                currentValue: root.draftScalePercent
                minimumValue: 25
                maximumValue: 300
                objectNamePrefix: "watermarkScaleHandle"
                onValuePreviewed: function(value) { root.publishPreview(value); }
                onValueCommitted: function(beforeValue, value) {
                    root.publishPreview(value);
                    root.scaleCommitted(Math.round(beforeValue), root.draftScalePercent);
                }
            }
            CornerScaleHandle {
                id: topRightHandle
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: 1
                verticalDirection: -1
                currentValue: root.draftScalePercent
                minimumValue: 25
                maximumValue: 300
                objectNamePrefix: "watermarkScaleHandle"
                onValuePreviewed: function(value) { root.publishPreview(value); }
                onValueCommitted: function(beforeValue, value) {
                    root.publishPreview(value);
                    root.scaleCommitted(Math.round(beforeValue), root.draftScalePercent);
                }
            }
            CornerScaleHandle {
                id: bottomLeftHandle
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: -1
                verticalDirection: 1
                currentValue: root.draftScalePercent
                minimumValue: 25
                maximumValue: 300
                objectNamePrefix: "watermarkScaleHandle"
                onValuePreviewed: function(value) { root.publishPreview(value); }
                onValueCommitted: function(beforeValue, value) {
                    root.publishPreview(value);
                    root.scaleCommitted(Math.round(beforeValue), root.draftScalePercent);
                }
            }
            CornerScaleHandle {
                id: bottomRightHandle
                selectionItem: selection
                coordinateItem: root
                horizontalDirection: 1
                verticalDirection: 1
                currentValue: root.draftScalePercent
                minimumValue: 25
                maximumValue: 300
                objectNamePrefix: "watermarkScaleHandle"
                onValuePreviewed: function(value) { root.publishPreview(value); }
                onValueCommitted: function(beforeValue, value) {
                    root.publishPreview(value);
                    root.scaleCommitted(Math.round(beforeValue), root.draftScalePercent);
                }
            }
        }
    }
}
