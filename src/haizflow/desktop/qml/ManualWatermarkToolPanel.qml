pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: imagePane
    property var inspector
    spacing: Theme.space8
    readonly property string appliedWatermarkKind: AppController.watermarkKind
    readonly property string displayedVideoId: AppController.selectedVideoId
    property string draftWatermarkKind: appliedWatermarkKind
    onAppliedWatermarkKindChanged: draftWatermarkKind = appliedWatermarkKind
    onDisplayedVideoIdChanged: draftWatermarkKind = appliedWatermarkKind

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Watermark")
    }
    SegmentedControl {
        Layout.fillWidth: true
        enabled: imagePane.inspector.editable
        options: [
            { "label": qsTr("Chữ"), "value": "text" },
            { "label": qsTr("Ảnh"), "value": "image" },
            { "label": qsTr("Video"), "value": "video" }
        ]
        currentValue: imagePane.draftWatermarkKind
        onActivated: function(value) {
            imagePane.draftWatermarkKind = value;
        }
    }
    StudioButton {
        Layout.fillWidth: true
        visible: imagePane.draftWatermarkKind !== imagePane.appliedWatermarkKind
        text: qsTr("Áp dụng watermark")
        variant: "primary"
        enabled: imagePane.inspector.editable && !imagePane.inspector.taskQueued
        onClicked: {
            AppController.watermarkKind = imagePane.draftWatermarkKind;
            imagePane.inspector.scheduleSave();
        }
    }
    StudioField {
        Layout.fillWidth: true
        visible: imagePane.draftWatermarkKind === "text"
            && imagePane.draftWatermarkKind === imagePane.appliedWatermarkKind
        enabled: imagePane.inspector.editable
        placeholderText: qsTr("Nhập watermark")
        text: AppController.watermarkText
        maximumLength: 80
        onEditingFinished: {
            AppController.watermarkText = text;
            imagePane.inspector.scheduleSave();
        }
    }
    StudioButton {
        Layout.fillWidth: true
        visible: imagePane.draftWatermarkKind === "image"
        text: AppController.watermarkImagePath.length > 0
            ? qsTr("Đổi ảnh") : qsTr("Chọn ảnh")
        iconName: "folder"
        variant: "secondary"
        enabled: imagePane.inspector.editable
        onClicked: {
            const path = AppController.chooseWatermarkImage();
            if (path.length > 0 && AppController.setWatermarkImage(path)) {
                AppController.watermarkKind = "image";
                imagePane.draftWatermarkKind = "image";
                imagePane.inspector.saveNow();
            }
        }
    }
    StudioButton {
        Layout.fillWidth: true
        visible: imagePane.draftWatermarkKind === "video"
        text: AppController.watermarkVideoPath.length > 0
            ? qsTr("Đổi video thu nhỏ") : qsTr("Chọn video thu nhỏ")
        iconName: "video"
        variant: "secondary"
        enabled: imagePane.inspector.editable
        onClicked: {
            const path = AppController.chooseWatermarkVideo();
            if (path.length > 0 && AppController.setWatermarkVideo(path)) {
                AppController.watermarkKind = "video";
                imagePane.draftWatermarkKind = "video";
                imagePane.inspector.saveNow();
            }
        }
    }
    SettingLabel {
        Layout.fillWidth: true
        visible: imagePane.draftWatermarkKind === imagePane.appliedWatermarkKind
        text: qsTr("Độ hiển thị · %1%").arg(AppController.watermarkOpacityPercent)
    }
    StudioSlider {
        Layout.fillWidth: true
        visible: imagePane.draftWatermarkKind === imagePane.appliedWatermarkKind
        enabled: imagePane.inspector.editable
        from: 0; to: 100; stepSize: 1
        value: AppController.watermarkOpacityPercent
        Accessible.name: qsTr("Độ hiển thị watermark")
        onMoved: AppController.watermarkOpacityPercent = Math.round(value)
        onPressedChanged: if (!pressed) imagePane.inspector.saveNow()
    }
    ManualWatermarkStyleControls {
        Layout.fillWidth: true
        visible: imagePane.draftWatermarkKind === "text"
            && imagePane.draftWatermarkKind === imagePane.appliedWatermarkKind
        enabled: imagePane.inspector.editable
        onWatermarkStyleEdited: imagePane.inspector.scheduleSave()
    }
}
