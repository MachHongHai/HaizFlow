pragma ComponentBehavior: Bound
import QtQuick
import "."

Item {
    id: root
    property rect videoRect: Qt.rect(0, 0, width, height)
    property rect sourceFramePercent: Qt.rect(0, 0, 100, 100)
    property var layers: []
    property string selectedLayerId: "ocr-source-region"
    property var regionDrafts: ({})
    property real positionSeconds: 0
    property bool interactive: false
    property bool editing: false
    signal layerSelected(string clipId)
    signal regionEdited(string clipId, var region)

    Repeater {
        model: root.layers
        delegate: OcrRegionOverlay {
            required property var modelData
            required property int index
            readonly property string clipId: String(modelData.clip_id || "")
            readonly property bool selected: root.selectedLayerId === clipId
            readonly property bool activeAtPosition: root.positionSeconds * 1000 >= Number(modelData.start_ms || 0)
                && root.positionSeconds * 1000 < Number(modelData.start_ms || 0) + Number(modelData.duration_ms || 0)
            anchors.fill: root
            z: selected && root.editing ? root.layers.length + 1 : root.layers.length - index
            videoRect: root.videoRect
            sourceFramePercent: root.sourceFramePercent
            region: root.regionDrafts[clipId] || modelData.region || ({})
            interactive: root.interactive && (Boolean(modelData.enabled) && activeAtPosition
                || root.editing && selected)
            editing: root.editing && selected
            showOutline: root.editing
            regionLabel: I18n.progressDetail(String(modelData.name || ""))
            onEditingStarted: root.layerSelected(clipId)
            onRegionEdited: function(region) { root.regionEdited(clipId, region); }
        }
    }
}
