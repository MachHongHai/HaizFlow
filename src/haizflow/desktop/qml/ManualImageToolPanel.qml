pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    property var inspector
    id: imagePane
    spacing: Theme.space8
    readonly property string appliedTreatment: !AppController.removeOriginalSubtitles
        ? "keep" : AppController.originalSubtitleRemovalMode
    property string draftTreatment: appliedTreatment

    onAppliedTreatmentChanged: draftTreatment = appliedTreatment

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Phụ đề gốc")
    }
    AppComboBox {
        Layout.fillWidth: true
        enabled: inspector.editable
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
    StudioButton {
        Layout.fillWidth: true
        visible: imagePane.draftTreatment !== imagePane.appliedTreatment
        text: qsTr("Áp dụng")
        variant: "primary"
        enabled: inspector.editable && !inspector.taskQueued
            && imagePane.draftTreatment !== imagePane.appliedTreatment
        onClicked: AppController.setManualSubtitleTreatment(imagePane.draftTreatment)
    }
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Watermark")
    }
    SegmentedControl {
        Layout.fillWidth: true
        enabled: inspector.editable
        options: [
            { "label": qsTr("Chữ"), "value": "text" },
            { "label": qsTr("Ảnh"), "value": "image" },
            { "label": qsTr("Video"), "value": "video" }
        ]
        currentValue: AppController.watermarkKind
        onActivated: function(value) {
            AppController.watermarkKind = value;
            inspector.scheduleSave();
        }
    }
    StudioField {
        Layout.fillWidth: true
        visible: AppController.watermarkKind === "text"
        enabled: inspector.editable
        placeholderText: qsTr("Nhập watermark")
        text: AppController.watermarkText
        maximumLength: 80
        onEditingFinished: {
            AppController.watermarkText = text;
            inspector.scheduleSave();
        }
    }
    StudioButton {
        Layout.fillWidth: true
        visible: AppController.watermarkKind === "image"
        text: AppController.watermarkImagePath.length > 0
            ? qsTr("Đổi ảnh") : qsTr("Chọn ảnh")
        iconName: "folder"
        variant: "secondary"
        enabled: inspector.editable
        onClicked: {
            const path = AppController.chooseWatermarkImage();
            if (path.length > 0 && AppController.setWatermarkImage(path)) {
                AppController.watermarkKind = "image";
                inspector.saveNow();
            }
        }
    }
    StudioButton {
        Layout.fillWidth: true
        visible: AppController.watermarkKind === "video"
        text: AppController.watermarkVideoPath.length > 0
            ? qsTr("Đổi video thu nhỏ") : qsTr("Chọn video thu nhỏ")
        iconName: "video"
        variant: "secondary"
        enabled: inspector.editable
        onClicked: {
            const path = AppController.chooseWatermarkVideo();
            if (path.length > 0 && AppController.setWatermarkVideo(path)) {
                AppController.watermarkKind = "video";
                inspector.saveNow();
            }
        }
    }
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Độ mờ · %1%").arg(AppController.watermarkOpacityPercent)
    }
    StudioSlider {
        Layout.fillWidth: true
        enabled: inspector.editable
        from: 0; to: 100; stepSize: 1
        value: AppController.watermarkOpacityPercent
        onMoved: AppController.watermarkOpacityPercent = Math.round(value)
        onPressedChanged: if (!pressed) inspector.saveNow()
    }
    ManualWatermarkStyleControls {
        Layout.fillWidth: true
        visible: AppController.watermarkKind === "text"
        enabled: inspector.editable
        onWatermarkStyleEdited: inspector.scheduleSave()
    }
}
