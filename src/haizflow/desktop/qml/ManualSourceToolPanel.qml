pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var inspector
    readonly property bool appliedAudioSeparation: AppController.enableAudioSeparation
    property bool draftAudioSeparation: appliedAudioSeparation
    onAppliedAudioSeparationChanged: draftAudioSeparation = appliedAudioSeparation
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
            enabled: root.inspector.editable && !root.inspector.taskQueued
            onClicked: AppController.browseVideo()
        }
        StudioButton {
            Layout.fillWidth: true
            text: qsTr("Từ liên kết")
            iconName: "link"
            variant: "secondary"
            enabled: root.inspector.editable && !root.inspector.taskQueued
            onClicked: root.inspector.sourceLinkRequested()
        }
    }
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Âm thanh")
    }
    SegmentedControl {
        Layout.fillWidth: true
        enabled: root.inspector.editable && !root.inspector.taskQueued
        currentValue: root.draftAudioSeparation ? "separated" : "original"
        options: [
            { "label": qsTr("Giữ âm thanh gốc"), "value": "original" },
            { "label": qsTr("Tách giọng"), "value": "separated" }
        ]
        onActivated: function(value) {
            root.draftAudioSeparation = value === "separated";
        }
    }
    StudioButton {
        Layout.fillWidth: true
        visible: root.draftAudioSeparation !== root.appliedAudioSeparation
        text: qsTr("Áp dụng nguồn âm thanh")
        variant: "primary"
        enabled: root.inspector.editable && !root.inspector.taskQueued
        onClicked: {
            AppController.enableAudioSeparation = root.draftAudioSeparation;
            root.inspector.scheduleSave();
        }
    }
    StudioButton {
        Layout.fillWidth: true
        visible: root.appliedAudioSeparation && root.draftAudioSeparation
        text: root.inspector.toolState.cacheHit
            ? qsTr("Tách lại giọng") : qsTr("Chạy tách giọng")
        iconName: "volume"
        variant: "primary"
        enabled: root.inspector.editable && !root.inspector.taskQueued && root.inspector.toolState.canRun
        onClicked: {
            root.inspector.saveNow();
            AppController.runManualTool("separation");
        }
    }
}
