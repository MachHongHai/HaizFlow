pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var inspector
    spacing: Theme.space12
    property var configuration: AppController.manualExportSettings()

    Connections {
        target: AppController
        function onSelectedVideoChanged() { root.configuration = AppController.manualExportSettings(); }
    }
    FormSection {
        Layout.fillWidth: true
        title: qsTr("Chất lượng video")
        StudioComboBox {
            Layout.fillWidth: true
            model: root.configuration.presets || []
            textRole: "label"
            valueRole: "value"
            currentIndex: Math.max(0, (root.configuration.presets || []).findIndex(item => item.value === root.configuration.preset))
            enabled: AppController.canEditSelectedVideo
            onActivated: AppController.setManualExportPreset(currentValue)
        }
    }

    StatusBadge {
        visible: Boolean(root.inspector.exportPreflight.canExport)
            && (root.inspector.exportPreflight.issues || []).length === 0
        status: "ready"
        label: qsTr("Sẵn sàng xuất")
    }

    Repeater {
        model: root.inspector.exportPreflight.issues || []
        delegate: InlineBanner {
            required property var modelData
            Layout.fillWidth: true
            tone: String(modelData.severity || "warning") === "error"
                ? "danger" : "warning"
            title: String(modelData.title || "")
            message: String(modelData.detail || "")
        }
    }

}
