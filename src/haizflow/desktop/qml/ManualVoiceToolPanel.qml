pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var inspector
    spacing: Theme.space8

    Text {
        Layout.fillWidth: true
        visible: root.inspector.hasPublishedVoice && !root.inspector.hasCurrentCache("voice")
        text: String(root.inspector.toolState.voiceNotice || "")
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }

    StudioButton {
        Layout.fillWidth: true
        visible: !root.inspector.hasPublishedVoice
        text: qsTr("Tạo giọng")
        iconName: "volume"
        variant: "primary"
        enabled: root.inspector.editable && !root.inspector.taskQueued && root.inspector.toolState.canRun
        onClicked: root.inspector.openVoiceDialog()
    }

    StudioButton {
        Layout.fillWidth: true
        visible: root.inspector.hasPublishedVoice
        text: qsTr("Đổi hoặc tạo lại giọng")
        iconName: "edit"
        variant: "primary"
        enabled: root.inspector.editable && !root.inspector.taskQueued
        onClicked: root.inspector.openVoiceDialog()
    }
}
