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
    readonly property var displayLabels: ({
        enabled: qsTr("Bật"), disabled: qsTr("Tắt"), none: qsTr("Tắt", "reasoning effort none"),
        minimal: qsTr("Tối thiểu"), low: qsTr("Thấp"), medium: qsTr("Trung bình"),
        high: qsTr("Cao"), xhigh: qsTr("Rất cao"), max: qsTr("Tối đa")
    })
    readonly property var options: values.map(value => ({ value: value, label: root.displayLabels[value] || value }))
    readonly property string effortLabel: configuration.parameter === "reasoning.enabled"
        ? qsTr("Suy luận") : qsTr("Mức")
    signal edited(string value)
    visible: values.length > 0 || Boolean(configuration.mandatory)
    spacing: Theme.space8
    function choose(value) { edited(value === configuration.default ? "" : value); }
    function restoreSelection() {
        effortCombo.currentIndex = Qt.binding(function() { return root.values.indexOf(root.effectiveEffort); });
        thinkingCombo.currentIndex = Qt.binding(function() { return root.effectiveEffort === "disabled" ? 0 : 1; });
    }

    RowLayout {
        Layout.fillWidth: true
        visible: Boolean(root.configuration.mandatory) && root.values.length === 0
        spacing: Theme.space12
        SettingLabel {
            Layout.fillWidth: true
            text: qsTr("Suy luận")
        }
        Text {
            objectName: "translationReasoningMandatoryState"
            text: qsTr("Bật")
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
            text: qsTr("Suy luận")
        }
        StudioComboBox {
            id: thinkingCombo
            objectName: "translationThinkingTypeCombo"
            Layout.preferredWidth: 140
            textRole: "label"
            valueRole: "value"
            model: [{ value: "disabled", label: qsTr("Tắt") }, { value: "enabled", label: qsTr("Bật") }]
            currentIndex: root.effectiveEffort === "disabled" ? 0 : 1
            onModelChanged: Qt.callLater(root.restoreSelection)
            Accessible.name: qsTr("Suy luận")
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
            helpText: root.configuration.parameter === "reasoning.enabled" ? ""
                : qsTr("Mức cao hơn có thể dùng nhiều token và mất thêm thời gian.")
        }
        StudioComboBox {
            id: effortCombo
            objectName: "translationReasoningEffortCombo"
            Layout.preferredWidth: 140
            textRole: "label"
            valueRole: "value"
            model: root.options
            currentIndex: root.values.indexOf(root.effectiveEffort)
            onModelChanged: Qt.callLater(root.restoreSelection)
            Accessible.name: root.effortLabel
            onActivated: root.choose(String(currentValue))
        }
    }
}
