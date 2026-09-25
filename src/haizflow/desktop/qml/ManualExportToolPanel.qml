pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var inspector
    spacing: Theme.space12

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
