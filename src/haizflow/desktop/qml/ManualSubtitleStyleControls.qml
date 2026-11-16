pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    objectName: "manualSubtitleStyleControls"

    property bool editable: true
    property var controller: AppController
    signal styleCommitted()

    readonly property var projectStyle: controller.manualEditorDocumentModel.defaultSubtitleStyle || ({})

    spacing: Theme.space8

    CompactTextStyleBar {
        Layout.fillWidth: true
        style: root.projectStyle
        karaokeEnabled: true
        fontLanguage: String(root.controller.manualVoiceLanguage || "vi")
        enabled: root.editable
        onChangeRequested: function(patch) {
            if (root.controller.applyTextStyle([], patch, "project"))
                root.styleCommitted();
        }
    }

}
