pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property string connectionId: ""
    property bool customApi: false
    signal modelSelected(string connectionId, string modelId, string outputFormat)
    title: qsTr("Chọn model dịch")
    preferredWidth: 460
    function openFor(identifier, modelId, outputFormat, custom) {
        connectionId = identifier;
        customApi = custom;
        modelInput.text = modelId;
        formatCombo.currentIndex = Math.max(0, formatCombo.model.findIndex(function(row) { return row.value === outputFormat; }));
        open();
        modelInput.forceActiveFocus();
    }
    SettingLabel { text: qsTr("Model ID") }
    AppTextField {
        id: modelInput
        objectName: "projectTranslationManualModelInput"
        Layout.fillWidth: true
        maximumLength: 200
        placeholderText: qsTr("Mã model từ nhà cung cấp")
        accessibleName: qsTr("Model ID dịch")
    }
    SettingLabel { visible: root.customApi; text: qsTr("Định dạng kết quả") }
    StudioComboBox {
        id: formatCombo
        objectName: "projectTranslationFormatCombo"
        Layout.fillWidth: true
        visible: root.customApi
        textRole: "label"
        valueRole: "value"
        model: [{label: "JSON mode", value: "json_object"}, {label: "JSON Schema", value: "json_schema"},
            {label: qsTr("JSON theo hướng dẫn"), value: "prompt"}]
        currentIndex: 0
    }
    footerActions: [
        StudioButton { text: qsTr("Hủy"); onClicked: root.close() },
        StudioButton {
            objectName: "projectTranslationApplyManualModelButton"
            text: qsTr("Áp dụng")
            variant: "primary"
            enabled: /^[A-Za-z0-9@~][A-Za-z0-9._:/@+~\-]{0,199}$/.test(modelInput.text.trim())
            onClicked: {
                root.modelSelected(root.connectionId, modelInput.text.trim(),
                    root.customApi ? String(formatCombo.currentValue) : "");
            }
        }
    ]
}
