pragma ComponentBehavior: Bound
// qmllint disable missing-property
import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    required property var api
    property string selectedModel: ""
    property string modelId: ""
    readonly property string selectedId: selectedModel.split(":")[1] || ""
    readonly property var profiles: api ? api.profiles : []
    readonly property var profile: profiles.find(function(row) { return row.id === root.selectedId; }) || null
    readonly property var options: profile ? profiles.filter(function(row) {
        return row.provider === root.profile.provider;
    }) : []
    signal choiceEdited(string value)
    spacing: Theme.space8
    visible: selectedModel.indexOf("api:") === 0

    SettingLabel { text: qsTr("API sử dụng") }
    AppComboBox {
        objectName: "projectTranslationActiveConnectionPicker"
        Layout.fillWidth: true
        model: root.options
        textRole: "label"
        valueRole: "id"
        currentIndex: root.options.findIndex(function(row) { return row.id === root.selectedId; })
        enabled: root.profile !== null
        Accessible.name: qsTr("API sử dụng cho dự án")
        onActivated: {
            if (!root.api || !root.profile || String(currentValue) === root.selectedId) return;
            const format = root.profile.provider === "custom"
                ? root.selectedModel.indexOf("#") >= 0 ? root.selectedModel.split("#")[1] : root.profile.format : "";
            const choice = root.api.modelChoice(String(currentValue), root.modelId, format);
            if (choice) root.choiceEdited(choice);
        }
    }
}
