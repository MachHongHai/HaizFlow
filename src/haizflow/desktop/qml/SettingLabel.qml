pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string text: ""
    property string helpText: ""
    property bool labelVisible: true

    spacing: Theme.space4

    Text {
        visible: root.labelVisible
        Layout.fillWidth: true
        text: root.text
        color: Theme.textMuted
        font.pixelSize: Theme.caption
        textFormat: Text.PlainText
    }

    HelpPopover {
        visible: root.helpText.length > 0
        helpText: root.helpText
        accessibleLabel: qsTr("Trợ giúp cho %1").arg(root.text)
    }
}
