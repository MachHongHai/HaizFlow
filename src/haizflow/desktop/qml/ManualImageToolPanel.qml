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
    readonly property string clipId: "ocr-source-region"
    readonly property string appliedTreatment: !controller.removeOriginalSubtitles
        ? "keep" : controller.originalSubtitleRemovalMode
    readonly property string draftTreatment: String(inspector.ocrModeDrafts[clipId] || appliedTreatment)

    function applyTreatment() {
        // Committing a region emits model notifications synchronously. Capture
        // the complete draft before those bindings can refresh.
        const region = inspector.ocrRegionDraft || selectedLayer.region;
        const treatment = draftTreatment;
        return imagePane.controller.setManualSubtitleTreatment(treatment, region || ({}));
    }
    AppComboBox {
        objectName: "ocrTreatmentSelector"
        Layout.fillWidth: true
        enabled: imagePane.inspector.editable && !imagePane.inspector.taskQueued
        textRole: "label"
        valueRole: "value"
        model: [
            { "label": qsTr("Giữ nguyên"), "value": "keep" },
            { "label": qsTr("Che · Làm mờ"), "value": "blur" },
            { "label": qsTr("Che · Vá nền"), "value": "patch" }
        ]
        currentIndex: imagePane.draftTreatment === "keep" ? 0
            : imagePane.draftTreatment === "blur" ? 1 : 2
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
            visible: Number((imagePane.controller.reviewPreviewMedia.detectedOcrRegion || {}).width_percent || 0) > 0
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
