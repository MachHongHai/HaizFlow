pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property bool editable: true
    signal styleCommitted()

    readonly property var projectStyle: AppController.manualEditorDocumentModel.defaultSubtitleStyle || ({})

    spacing: Theme.space8

    CompactTextStyleBar {
        Layout.fillWidth: true
        style: root.projectStyle
        karaokeEnabled: true
        enabled: root.editable
        onChangeRequested: function(patch) {
            if (AppController.applyTextStyle([], patch, "project"))
                root.styleCommitted();
        }
    }
}
