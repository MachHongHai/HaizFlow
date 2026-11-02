pragma ComponentBehavior: Bound
// qmllint disable missing-property
import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property string selectedModel: "q4"
    property string reasoningEffort: ""
    property bool hasGuidance: false
    readonly property var configuration: AppController.translationApi
        ? AppController.translationApi.reasoningConfiguration(selectedModel, "", hasGuidance,
            AppController.translationApi.reasoningRevision) : ({})
    readonly property var values: configuration.values || []
    readonly property string effectiveEffort: values.indexOf(reasoningEffort) >= 0
        || (configuration.thinking && reasoningEffort === "disabled") ? reasoningEffort : configuration.default || ""
    readonly property var options: values.map(value => ({ value: value, label: displayLabel(value) }))
    readonly property string effortLabel: configuration.parameter === "thinkingLevel"
        ? qsTr("Mức") : configuration.parameter || "reasoning.effort"
    signal edited(string value)
    visible: values.length > 0 || Boolean(configuration.mandatory)
    spacing: Theme.space8
    function choose(value) { edited(value === configuration.default ? "" : value); }
    function displayLabel(value) { return value.charAt(0).toUpperCase() + value.slice(1); }

    RowLayout {
        Layout.fillWidth: true
        visible: Boolean(root.configuration.mandatory) && root.values.length === 0
        spacing: Theme.space12
        SettingLabel {
            Layout.fillWidth: true
            text: "reasoning:"
        }
        Text {
            objectName: "translationReasoningMandatoryState"
            text: "Enabled"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            textFormat: Text.PlainText
        }
    }

    RowLayout {
        Layout.fillWidth: true
        visible: Boolean(root.configuration.thinking)
        spacing: Theme.space12
        SettingLabel {
            Layout.fillWidth: true
            text: "thinking.type"
        }
        StudioComboBox {
            objectName: "translationThinkingTypeCombo"
            Layout.preferredWidth: 140
            textRole: "label"
            valueRole: "value"
            model: [{ value: "disabled", label: "Disabled" }, { value: "enabled", label: "Enabled" }]
            currentIndex: root.effectiveEffort === "disabled" ? 0 : 1
            Accessible.name: "thinking.type"
            onActivated: root.choose(currentIndex === 0 ? "disabled" : "low")
        }
    }
    RowLayout {
        Layout.fillWidth: true
        visible: root.values.length > 0 && (!root.configuration.thinking || root.effectiveEffort !== "disabled")
        spacing: Theme.space12
        SettingLabel {
            Layout.fillWidth: true
            text: root.effortLabel
            helpText: qsTr("Mức cao hơn có thể dùng nhiều token và mất thêm thời gian.")
        }
        StudioComboBox {
            objectName: "translationReasoningEffortCombo"
            Layout.preferredWidth: 140
            textRole: "label"
            valueRole: "value"
            model: root.options
            currentIndex: root.values.indexOf(root.effectiveEffort)
            Accessible.name: root.effortLabel
            onActivated: root.choose(String(currentValue))
        }
    }
}
