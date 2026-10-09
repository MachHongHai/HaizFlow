pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    property var inspector
    property var controller: AppController
    id: imagePane
    spacing: Theme.space8
    readonly property var selectedLayer: inspector.selectedOcrLayer || ({})
    readonly property string clipId: String(selectedLayer.clip_id || "ocr-source-region")
    readonly property bool primary: Boolean(selectedLayer.primary) || clipId === "ocr-source-region"
    readonly property string appliedTreatment: primary
        ? (!controller.removeOriginalSubtitles ? "keep" : controller.originalSubtitleRemovalMode)
        : String(selectedLayer.mode || "blur")
    readonly property string draftTreatment: String(inspector.ocrModeDrafts[clipId] || appliedTreatment)

    function applyTreatment() {
        // Committing a region emits model notifications synchronously. Capture
        // the complete draft before those bindings can refresh.
        const region = inspector.ocrRegionDraft || selectedLayer.region;
        const treatment = draftTreatment;
        return primary ? imagePane.controller.setManualSubtitleTreatment(treatment, region || ({}))
            : imagePane.controller.updateOcrLayer(clipId, region || ({}), treatment);
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8
        OcrLayerList {
            Layout.fillWidth: true
            layers: imagePane.inspector.ocrLayers
            selectedId: imagePane.clipId
            editable: imagePane.inspector.editable && !imagePane.inspector.taskQueued
            onLayerSelected: function(id) { imagePane.inspector.ocrLayerSelected(id); }
        }
        StudioButton {
            objectName: "addOcrLayerButton"
            text: qsTr("Thêm lớp")
            iconName: "add"
            variant: "secondary"
            enabled: imagePane.inspector.editable && !imagePane.inspector.taskQueued
            onClicked: {
                const id = imagePane.controller.addOcrLayer();
                if (id.length > 0)
                    imagePane.inspector.ocrLayerSelected(id);
            }
        }
    }
    AppComboBox {
        objectName: "ocrTreatmentSelector"
        Layout.fillWidth: true
        enabled: imagePane.inspector.editable && !imagePane.inspector.taskQueued
        textRole: "label"
        valueRole: "value"
        model: imagePane.primary ? [
            { "label": qsTr("Giữ nguyên"), "value": "keep" },
            { "label": qsTr("Che · Làm mờ"), "value": "blur" },
            { "label": qsTr("Che · Vá nền"), "value": "patch" }
        ] : [
            { "label": qsTr("Làm mờ"), "value": "blur" },
            { "label": qsTr("Vá nền"), "value": "patch" }
        ]
        currentIndex: imagePane.primary ? (imagePane.draftTreatment === "keep" ? 0
            : imagePane.draftTreatment === "blur" ? 1 : 2)
            : imagePane.draftTreatment === "blur" ? 0 : 1
        onActivated: function(index) {
            const selected = model[index]
            if (selected)
                imagePane.inspector.ocrModeDraftRequested(imagePane.clipId, String(selected.value || "blur"));
        }
    }
    Text {
        Layout.fillWidth: true
        visible: Number((imagePane.selectedLayer.region || {}).width_percent || 0) > 0
        text: qsTr("Bấm vào vùng che trên preview để chỉnh. Chọn Áp dụng để lưu thay đổi.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
    }
    Flow {
        Layout.fillWidth: true
        spacing: Theme.space8
        StudioButton {
            visible: imagePane.primary && Number((imagePane.controller.reviewPreviewMedia.detectedOcrRegion || {}).width_percent || 0) > 0
            text: qsTr("Khôi phục vùng nhận diện")
            variant: "secondary"
            enabled: imagePane.inspector.editable && !imagePane.inspector.taskQueued
            onClicked: imagePane.inspector.restoreDetectedOcrRegion()
        }
        StudioButton {
            visible: imagePane.inspector.ocrRegionDraft !== null || imagePane.draftTreatment !== imagePane.appliedTreatment
            text: qsTr("Bỏ thay đổi")
            variant: "secondary"
            enabled: imagePane.inspector.editable && !imagePane.inspector.taskQueued
            onClicked: imagePane.inspector.ocrRegionDiscardRequested()
        }
    }
}
