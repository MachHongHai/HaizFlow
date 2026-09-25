pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    property var inspector
    spacing: Theme.space8

    Text {
        Layout.fillWidth: true
        visible: inspector.hasPublishedVoice && !inspector.hasCurrentCache("voice")
        text: String(inspector.toolState.voiceNotice || "")
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }

    StudioButton {
        Layout.fillWidth: true
        visible: !inspector.hasPublishedVoice
        text: qsTr("Tạo giọng")
        iconName: "volume"
        variant: "primary"
        enabled: inspector.editable && !inspector.taskQueued && inspector.toolState.canRun
        onClicked: inspector.openVoiceDialog()
    }

    StudioButton {
        Layout.fillWidth: true
        visible: inspector.hasPublishedVoice
        text: qsTr("Đổi hoặc tạo lại giọng")
        iconName: "edit"
        variant: "primary"
        enabled: inspector.editable && !inspector.taskQueued
        onClicked: inspector.openVoiceDialog()
    }
}
