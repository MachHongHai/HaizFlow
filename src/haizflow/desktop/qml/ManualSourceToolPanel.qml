pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    property var inspector
    spacing: Theme.space8

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Video nguồn")
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space4
        StudioButton {
            Layout.fillWidth: true
            text: qsTr("Từ tệp")
            iconName: "folder"
            variant: "secondary"
            enabled: inspector.editable && !inspector.taskQueued
            onClicked: AppController.browseVideo()
        }
        StudioButton {
            Layout.fillWidth: true
            text: qsTr("Từ liên kết")
            iconName: "link"
            variant: "secondary"
            enabled: inspector.editable && !inspector.taskQueued
            onClicked: inspector.sourceLinkRequested()
        }
    }
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Âm thanh")
    }
    SegmentedControl {
        Layout.fillWidth: true
        enabled: inspector.editable && !inspector.taskQueued
        currentValue: AppController.enableAudioSeparation ? "separated" : "original"
        options: [
            { "label": qsTr("Giữ âm thanh gốc"), "value": "original" },
            { "label": qsTr("Tách giọng"), "value": "separated" }
        ]
        onActivated: function(value) {
            AppController.enableAudioSeparation = value === "separated";
            inspector.scheduleSave();
        }
    }
    StudioButton {
        Layout.fillWidth: true
        visible: AppController.enableAudioSeparation
        text: inspector.toolState.cacheHit
            ? qsTr("Tách lại giọng") : qsTr("Chạy tách giọng")
        iconName: "volume"
        variant: "primary"
        enabled: inspector.editable && !inspector.taskQueued && inspector.toolState.canRun
        onClicked: {
            inspector.saveNow();
            AppController.runManualTool("separation");
        }
    }
}

