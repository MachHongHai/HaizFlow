pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var inspector
    spacing: Theme.space8

    AudioLevelControl {
        Layout.fillWidth: true
        label: AppController.enableAudioSeparation && root.inspector.hasCurrentCache("source")
            ? qsTr("Âm nền") : qsTr("Âm thanh gốc")
        volume: AppController.originalVolume
        adjustable: root.inspector.editable
        onVolumeEdited: function(value) {
            AppController.originalVolume = value;
            root.inspector.scheduleSave();
        }
    }
    AudioLevelControl {
        Layout.fillWidth: true
        label: qsTr("Giọng đọc")
        volume: AppController.ttsVolume
        adjustable: root.inspector.editable && root.inspector.hasCurrentCache("voice")
        disabledHint: qsTr("Chưa tạo giọng đọc")
        onVolumeEdited: function(value) {
            AppController.ttsVolume = value;
            root.inspector.scheduleSave();
        }
    }
    AudioLevelControl {
        Layout.fillWidth: true
        label: qsTr("Nhạc nền")
        volume: AppController.backgroundMusicVolume
        adjustable: root.inspector.editable && AppController.backgroundMusicPath.length > 0
        disabledHint: qsTr("Chưa chọn nhạc nền")
        onVolumeEdited: function(value) {
            AppController.backgroundMusicVolume = value;
            root.inspector.scheduleSave();
        }
    }
    ColumnLayout {
        id: duckingSection
        Layout.fillWidth: true
        spacing: Theme.space8
        readonly property var editorDocument: AppController.manualEditorDocumentModel.document || ({})
        readonly property bool duckingEnabled: Boolean(editorDocument.audio_ducking_enabled)
        readonly property var musicClip: (editorDocument.clips || []).find(function(clip) {
            return clip.track_id === "music";
        }) || ({})

        PropertyRow {
            label: qsTr("Lặp nhạc nền")
            AppSwitch {
                objectName: "manualMusicLoopSwitch"
                checked: Boolean(duckingSection.musicClip.loop)
                enabled: root.inspector.editable && AppController.backgroundMusicPath.length > 0
                onToggled: AppController.setMusicLoop(checked)
            }
        }

        PropertyRow {
            label: qsTr("Tự giảm nhạc khi có lời")
            AppSwitch {
                checked: duckingSection.duckingEnabled
                enabled: root.inspector.editable && AppController.backgroundMusicPath.length > 0
                onToggled: AppController.setAudioDucking(
                    checked,
                    Number(duckingSection.editorDocument.audio_ducking_reduction_db || -12),
                    Number(duckingSection.editorDocument.audio_ducking_attack_ms || 180),
                    Number(duckingSection.editorDocument.audio_ducking_release_ms || 420))
            }
        }
        PropertyRow {
            visible: duckingSection.duckingEnabled
            label: qsTr("Mức giảm")
            NumericField {
                from: -36; to: 0
                value: Math.round(Number(duckingSection.editorDocument.audio_ducking_reduction_db || -12))
                suffix: " dB"
                onValueModified: AppController.setAudioDucking(
                    true, value,
                    Number(duckingSection.editorDocument.audio_ducking_attack_ms || 180),
                    Number(duckingSection.editorDocument.audio_ducking_release_ms || 420))
            }
        }
    }
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Nhạc nền")
    }
    Text {
        Layout.fillWidth: true
        text: AppController.backgroundMusicPath || qsTr("Chưa có nhạc nền")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        textFormat: Text.PlainText
        elide: Text.ElideMiddle
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space4
        StudioButton {
            Layout.fillWidth: true
            text: qsTr("Chọn tệp")
            variant: "secondary"
            enabled: root.inspector.editable
            onClicked: AppController.browseBackgroundMusic()
        }
        StudioButton {
            Layout.fillWidth: true
            text: qsTr("Từ liên kết")
            variant: "secondary"
            enabled: root.inspector.editable
            onClicked: root.inspector.openBackgroundMusicLinkDialog()
        }
        IconButton {
            visible: AppController.backgroundMusicPath.length > 0
            glyph: "\uE74D"
            toolTipText: qsTr("Xóa nhạc nền")
            enabled: root.inspector.editable
            onClicked: AppController.clearBackgroundMusic()
        }
    }
}
