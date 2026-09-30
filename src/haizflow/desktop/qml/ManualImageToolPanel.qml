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
}
