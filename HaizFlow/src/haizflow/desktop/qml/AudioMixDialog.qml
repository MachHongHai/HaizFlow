import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "."

Dialog {
    id: root

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

    readonly property bool sourceAudioAdjustable: AppController.canEditSelectedVideo
        && !AppController.enableAudioSeparation
    readonly property bool backgroundMusicAdjustable: AppController.canEditSelectedVideo
        && AppController.backgroundMusicPath.length > 0
    readonly property bool previewReady: AppController.audioPreviewState === "ready"
        && AppController.audioPreviewSource.length > 0
    readonly property bool previewPlaying: voicePreviewPlayer.playbackState === MediaPlayer.PlayingState

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

    function pausePreview() {
        previewStopTimer.stop()
        sourcePreviewPlayer.pause()
        musicPreviewPlayer.pause()
        voicePreviewPlayer.pause()
    }

    function requestPreview() {
        if (root.previewReady)
            root.playPreview()
        else
            AppController.previewAudioMix()
    }

    function scheduleVideoSettingsSave() {
        if (AppController.hasSelectedVideo && !AppController.isSelectedVideoProcessing)
            videoSettingsSaveTimer.restart()
    }

    onClosed: pausePreview()
    onVisibleChanged: {
        if (!visible)
            pausePreview()
    }

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
                volume: AppController.originalVolume
                adjustable: root.sourceAudioAdjustable
                disabledHint: I18n.t("Source audio volume is unavailable while separating vocals")
                onVolumeEdited: function(value) {
                    AppController.originalVolume = value
                    root.scheduleVideoSettingsSave()
                }
            }

            AudioLevelControl {
                label: I18n.t("TTS volume")
                volume: AppController.ttsVolume
                adjustable: AppController.canEditSelectedVideo
                onVolumeEdited: function(value) {
                    AppController.ttsVolume = value
                    root.scheduleVideoSettingsSave()
                }
            }

            AudioLevelControl {
                label: I18n.t("Background music volume")
                volume: AppController.backgroundMusicVolume
                adjustable: root.backgroundMusicAdjustable
                disabledHint: I18n.t("Choose background music to adjust its volume")
                onVolumeEdited: function(value) {
                    AppController.backgroundMusicVolume = value
                    root.scheduleVideoSettingsSave()
                }
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    Layout.fillWidth: true
                    text: AppController.audioPreviewState === "preparing"
                        ? I18n.t("Preparing audio preview") : I18n.t("Preview audio mix")
                    color: Theme.text
                    font.pixelSize: Theme.body
                    textFormat: Text.PlainText
                }

                IconButton {
                    glyph: root.previewPlaying ? "\uE769" : "\uE768"
                    toolTipText: root.previewPlaying ? I18n.t("Pause") : I18n.t("Play")
                    enabled: AppController.canEditSelectedVideo && AppController.videoPath.length > 0
                        && AppController.audioPreviewState !== "preparing"
                    onClicked: {
                        if (root.previewPlaying)
                            root.pausePreview()
                        else
                            root.requestPreview()
                    }
                }
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

    Timer {
        id: videoSettingsSaveTimer

        interval: 250
        repeat: false
        onTriggered: AppController.persistSelectedVideoSettings()
    }

    MediaPlayer {
        id: sourcePreviewPlayer
        source: AppController.audioPreviewOriginalSource
        audioOutput: AudioOutput {
            volume: AppController.originalVolume / 100.0
        }
    }

    MediaPlayer {
        id: musicPreviewPlayer
        source: AppController.audioPreviewBackgroundMusicSource
        audioOutput: AudioOutput {
            volume: AppController.backgroundMusicVolume / 100.0
        }
    }

    MediaPlayer {
        id: voicePreviewPlayer
        source: AppController.audioPreviewSource
        audioOutput: AudioOutput {
            volume: AppController.ttsVolume / 100.0
        }
    }

    Connections {
        target: AppController

        function onAudioPreviewChanged() {
            if (AppController.audioPreviewState === "preparing")
                root.stopPreview()
            else if (root.visible && AppController.audioPreviewState === "ready"
                     && AppController.audioPreviewSource.length > 0)
                root.playPreview()
        }
    }
}
