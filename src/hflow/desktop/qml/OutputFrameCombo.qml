pragma ComponentBehavior: Bound
import QtQuick
import "."

StudioComboBox {
    id: root
    objectName: "outputFrameCombo"
    property string outputFormat: "keep_ratio"
    signal edited(string value)
    readonly property var options: [
        { "label": qsTr("Tỷ lệ gốc"), "value": "keep_ratio" },
        { "label": qsTr("9:16 Nền mờ"), "value": "blur_background_9_16" },
        { "label": qsTr("9:16 Đầy khung"), "value": "tiktok_9_16_crop" }
    ]
    model: root.options
    textRole: "label"
    valueRole: "value"
    currentIndex: Math.max(0, root.options.findIndex(option => option.value === root.outputFormat))
    implicitWidth: Math.max(originalLabelMetrics.advanceWidth, blurLabelMetrics.advanceWidth,
        fillLabelMetrics.advanceWidth) + leftPadding + rightPadding
    Accessible.name: qsTr("Khung hình đầu ra: %1").arg(displayText)
    onActivated: root.edited(currentValue)
    TextMetrics {
        id: originalLabelMetrics
        font: root.font
        text: root.options[0].label
    }
    TextMetrics {
        id: blurLabelMetrics
        font: root.font
        text: root.options[1].label
    }
    TextMetrics {
        id: fillLabelMetrics
        font: root.font
        text: root.options[2].label
    }
}
