import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "."

Dialog {
    id: root

    property bool audioSeparationEnabled: false
    property int originalVolume: 60
    property int ttsVolume: 100
    property int backgroundMusicVolume: 30
    property string targetLanguage: "vi"
    property string ttsVoice: ""
    property string backgroundMusicPath: ""
    readonly property bool sourceAudioAdjustable: !audioSeparationEnabled
    readonly property bool backgroundMusicAdjustable: backgroundMusicPath.length > 0

    signal audioLevelsEdited(int originalVolume, int ttsVolume, int backgroundMusicVolume)

    modal: true
    focus: true
    width: Math.min(520, parent ? parent.width - 48 : 520)
    height: Math.min(530, parent ? parent.height - 48 : 530)
    padding: 0
    title: I18n.t("Adjust audio levels")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    header: null
    footer: null

    function stopPreview() {
        previewStopTimer.stop()
        sourcePreviewPlayer.stop()
        musicPreviewPlayer.stop()
        voicePreviewPlayer.stop()
    }

    function playPreview() {
        stopPreview()
        sourcePreviewPlayer.play()
        if (AppController.audioPreviewBackgroundMusicSource.length > 0)
            musicPreviewPlayer.play()
        voicePreviewPlayer.play()
        previewStopTimer.start()
    }

    function updateLevels(original, voice, music) {
        originalVolume = original
        ttsVolume = voice
        backgroundMusicVolume = music
        audioLevelsEdited(original, voice, music)
    }

    onClosed: stopPreview()

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 70
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Adjust audio levels")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Balance source audio, voice and background music")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }

            IconButton {
                glyph: "\uE711"
                toolTipText: I18n.t("Close")
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.space24
            spacing: Theme.space20

            AudioLevelControl {
                label: I18n.t("Source audio volume")
                volume: root.originalVolume
                adjustable: root.sourceAudioAdjustable
                disabledHint: I18n.t("Source audio volume is unavailable while separating vocals")
                onVolumeEdited: function(value) {
                    root.updateLevels(value, root.ttsVolume, root.backgroundMusicVolume)
                }
            }

            AudioLevelControl {
                label: I18n.t("TTS volume")
                volume: root.ttsVolume
                onVolumeEdited: function(value) {
                    root.updateLevels(root.originalVolume, value, root.backgroundMusicVolume)
                }
            }

            AudioLevelControl {
                label: I18n.t("Background music volume")
                volume: root.backgroundMusicVolume
                adjustable: root.backgroundMusicAdjustable
                disabledHint: I18n.t("Choose background music to adjust its volume")
                onVolumeEdited: function(value) {
                    root.updateLevels(root.originalVolume, root.ttsVolume, value)
                }
            }

            Item { Layout.fillHeight: true }

            AppButton {
                Layout.fillWidth: true
                text: AppController.audioPreviewState === "preparing"
                    ? I18n.t("Preparing audio preview") : I18n.t("Preview audio mix")
                tone: "secondary"
                enabled: AppController.batchCount > 0 && AppController.audioPreviewState !== "preparing"
                onClicked: AppController.previewBatchAudioMix(
                    root.targetLanguage,
                    root.ttsVoice,
                    root.audioSeparationEnabled,
                    root.originalVolume,
                    root.backgroundMusicVolume,
                    root.ttsVolume,
                    root.backgroundMusicPath
                )
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 66
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space24

            Item { Layout.fillWidth: true }

            AppButton {
                text: I18n.t("Close")
                tone: "primary"
                onClicked: root.close()
            }
        }
    }

    Timer {
        id: previewStopTimer
        interval: 20000
        repeat: false
        onTriggered: root.stopPreview()
    }

    MediaPlayer {
        id: sourcePreviewPlayer
        source: AppController.audioPreviewOriginalSource
        audioOutput: AudioOutput { volume: root.originalVolume / 100.0 }
    }

    MediaPlayer {
        id: musicPreviewPlayer
        source: AppController.audioPreviewBackgroundMusicSource
        audioOutput: AudioOutput { volume: root.backgroundMusicVolume / 100.0 }
    }

    MediaPlayer {
        id: voicePreviewPlayer
        source: AppController.audioPreviewSource
        audioOutput: AudioOutput { volume: root.ttsVolume / 100.0 }
    }

    Connections {
        target: AppController

        function onAudioPreviewChanged() {
            if (AppController.audioPreviewState === "preparing")
                root.stopPreview()
            else if (AppController.audioPreviewState === "ready" && AppController.audioPreviewSource.length > 0)
                root.playPreview()
        }
    }
}
