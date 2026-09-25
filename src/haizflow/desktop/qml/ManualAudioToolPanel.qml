pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    property var inspector
    spacing: Theme.space8

    AudioLevelControl {
        Layout.fillWidth: true
        label: AppController.enableAudioSeparation && inspector.hasCurrentCache("source")
            ? qsTr("Âm nền") : qsTr("Âm thanh gốc")
        volume: AppController.originalVolume
        adjustable: inspector.editable
        onVolumeEdited: function(value) {
            AppController.originalVolume = value;
            inspector.scheduleSave();
        }
    }
    AudioLevelControl {
        Layout.fillWidth: true
        label: qsTr("Giọng đọc")
        volume: AppController.ttsVolume
        adjustable: inspector.editable && inspector.hasCurrentCache("voice")
        disabledHint: qsTr("Chưa tạo giọng đọc")
        onVolumeEdited: function(value) {
            AppController.ttsVolume = value;
            inspector.scheduleSave();
        }
    }
    AudioLevelControl {
        Layout.fillWidth: true
        label: qsTr("Nhạc nền")
        volume: AppController.backgroundMusicVolume
        adjustable: inspector.editable && AppController.backgroundMusicPath.length > 0
        disabledHint: qsTr("Chưa chọn nhạc nền")
        onVolumeEdited: function(value) {
            AppController.backgroundMusicVolume = value;
            inspector.scheduleSave();
        }
    }
    InspectorSection {
        id: duckingSection
        Layout.fillWidth: true
        title: qsTr("Tự giảm nhạc khi có lời")
        collapsible: true
        readonly property var editorDocument: AppController.manualEditorDocumentModel.document || ({})
        readonly property bool duckingEnabled: Boolean(editorDocument.audio_ducking_enabled)

        PropertyRow {
            label: qsTr("Bật tự giảm")
            AppSwitch {
                checked: duckingSection.duckingEnabled
                enabled: inspector.editable && AppController.backgroundMusicPath.length > 0
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
        PropertyRow {
            visible: duckingSection.duckingEnabled
            label: qsTr("Vào / ra")
            RowLayout {
                spacing: Theme.space8
                NumericField {
                    from: 0; to: 3000
                    value: Math.round(Number(duckingSection.editorDocument.audio_ducking_attack_ms || 180))
                    suffix: " ms"
                    onValueModified: AppController.setAudioDucking(
                        true,
                        Number(duckingSection.editorDocument.audio_ducking_reduction_db || -12),
                        value,
                        Number(duckingSection.editorDocument.audio_ducking_release_ms || 420))
                }
                NumericField {
                    from: 0; to: 3000
                    value: Math.round(Number(duckingSection.editorDocument.audio_ducking_release_ms || 420))
                    suffix: " ms"
                    onValueModified: AppController.setAudioDucking(
                        true,
                        Number(duckingSection.editorDocument.audio_ducking_reduction_db || -12),
                        Number(duckingSection.editorDocument.audio_ducking_attack_ms || 180),
                        value)
                }
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
            enabled: inspector.editable
            onClicked: AppController.browseBackgroundMusic()
        }
        StudioButton {
            Layout.fillWidth: true
            text: qsTr("Từ liên kết")
            variant: "secondary"
            enabled: inspector.editable
            onClicked: inspector.openBackgroundMusicLinkDialog()
        }
        IconButton {
            visible: AppController.backgroundMusicPath.length > 0
            glyph: "\uE74D"
            toolTipText: qsTr("Xóa nhạc nền")
            enabled: inspector.editable
            onClicked: AppController.clearBackgroundMusic()
        }
    }
}

