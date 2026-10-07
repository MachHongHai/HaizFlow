pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    property var inspector
    id: imagePane
    spacing: Theme.space8
    readonly property string appliedTreatment: !AppController.removeOriginalSubtitles
        ? "keep" : AppController.originalSubtitleRemovalMode
    readonly property string displayedVideoId: AppController.selectedVideoId
    property string draftTreatment: appliedTreatment
    onAppliedTreatmentChanged: draftTreatment = appliedTreatment
    onDisplayedVideoIdChanged: {
        draftTreatment = appliedTreatment;
    }

    function applyTreatment() {
        if (imagePane.inspector.ocrRegionDraft !== null
                && !AppController.setOriginalSubtitleRegion(imagePane.inspector.ocrRegionDraft))
            return false;
        return AppController.setManualSubtitleTreatment(draftTreatment);
    }

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Phụ đề gốc")
    }
    AppComboBox {
        Layout.fillWidth: true
        enabled: imagePane.inspector.editable
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
                imagePane.draftTreatment = String(selected.value || "keep");
        }
    }
    Text {
        Layout.fillWidth: true
        visible: Number((AppController.reviewPreviewMedia.ocrRegion || {}).width_percent || 0) > 0
        text: qsTr("Bấm vào vùng che trên preview để chỉnh. Chọn Áp dụng để lưu thay đổi.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
    }
    StudioButton {
        visible: Number((AppController.reviewPreviewMedia.detectedOcrRegion || {}).width_percent || 0) > 0
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
        onClicked: {
            imagePane.draftTreatment = imagePane.appliedTreatment;
            imagePane.inspector.ocrRegionDiscardRequested();
        }
    }
}
