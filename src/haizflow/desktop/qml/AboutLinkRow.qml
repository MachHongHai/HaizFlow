pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string label: ""
    property string value: ""
    property url destination
    property string copyValue: value
    property bool linkEnabled: true

    Layout.fillWidth: true
    Layout.minimumHeight: 36
    spacing: Theme.space12

    Text {
        Layout.preferredWidth: 112
        text: root.label
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        textFormat: Text.PlainText
    }

    ExternalTextLink {
        visible: root.linkEnabled
        Layout.fillWidth: true
        text: root.value
        destination: root.destination
    }

    Text {
        visible: !root.linkEnabled
        Layout.fillWidth: true
        text: root.value
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.control
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }

    IconButton {
        Layout.preferredWidth: 28
        Layout.preferredHeight: 28
        controlSize: 28
        glyph: "\uE8C8"
        toolTipText: qsTr("Sao chép")
        onClicked: AppController.copyText(root.copyValue)
    }
}
