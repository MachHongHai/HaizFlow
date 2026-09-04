import QtQuick
import QtQuick.Layouts
import QtMultimedia
import "."

AppDialog {
    id: root

    property bool audioSeparationEnabled: false
    property int originalVolume: 60
    property int ttsVolume: 100
    property int backgroundMusicVolume: 30
    property string targetLanguage: "vi"
    property string ttsProvider: "omnivoice"
    property string ttsVoice: ""
    property string backgroundMusicPath: ""
    readonly property bool sourceAudioAdjustable: true
    readonly property bool backgroundMusicAdjustable: backgroundMusicPath.length > 0
    readonly property bool previewReady: AppController.audioPreviewState === "ready"
        && (AppController.audioPreviewSource.length > 0
            || AppController.audioPreviewOriginalSource.length > 0
            || AppController.audioPreviewBackgroundMusicSource.length > 0)
    readonly property bool previewPlaying:
        voicePreviewPlayer.playbackState === MediaPlayer.PlayingState
        || sourcePreviewPlayer.playbackState === MediaPlayer.PlayingState
        || musicPreviewPlayer.playbackState === MediaPlayer.PlayingState

    signal audioLevelsEdited(int originalVolume, int ttsVolume, int backgroundMusicVolume)

    title: qsTr("Âm lượng hàng loạt")
    subtitle: qsTr("Mức âm lượng mặc định cho các video trong dự án")
    preferredWidth: 480
    preferredHeight: 430
    maximumWidth: 520
    maximumHeight: 560

    function stopPreview() {
        previewStopTimer.stop()
        sourcePreviewPlayer.stop()
        musicPreviewPlayer.stop()
        voicePreviewPlayer.stop()
    }

    function playPreview() {
        stopPreview()
        if (AppController.audioPreviewOriginalSource.length > 0)
            sourcePreviewPlayer.play()
        if (AppController.audioPreviewBackgroundMusicSource.length > 0)
            musicPreviewPlayer.play()
        if (AppController.audioPreviewSource.length > 0)
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
        // Audio preview state is shared with single-video voice rows. Always
        // resolve this batch's existing media before playback; no model runs.
        AppController.previewBatchAudioMix(
            root.targetLanguage,
            root.ttsProvider,
            root.ttsVoice,
            root.audioSeparationEnabled,
            root.originalVolume,
            root.backgroundMusicVolume,
            root.ttsVolume,
            root.backgroundMusicPath
        )
    }

    function updateLevels(original, voice, music) {
        originalVolume = original
        ttsVolume = voice
        backgroundMusicVolume = music
        audioLevelsEdited(original, voice, music)
    }

    onClosed: pausePreview()
    onVisibleChanged: {
        if (!visible)
            pausePreview()
    }

    AudioLevelControl {
        Layout.fillWidth: true
        label: root.audioSeparationEnabled ? qsTr("Âm thanh nền") : qsTr("Âm thanh gốc")
        volume: root.originalVolume
        adjustable: root.sourceAudioAdjustable
        onVolumeEdited: function(value) {
            root.updateLevels(value, root.ttsVolume, root.backgroundMusicVolume)
        }
    }

    AudioLevelControl {
        Layout.fillWidth: true
        label: qsTr("Giọng đọc")
        volume: root.ttsVolume
        onVolumeEdited: function(value) {
            root.updateLevels(root.originalVolume, value, root.backgroundMusicVolume)
        }
    }

    AudioLevelControl {
        Layout.fillWidth: true
        label: qsTr("Nhạc nền")
        volume: root.backgroundMusicVolume
        adjustable: root.backgroundMusicAdjustable
        disabledHint: qsTr("Chọn nhạc nền trước khi chỉnh âm lượng")
        onVolumeEdited: function(value) {
            root.updateLevels(root.originalVolume, root.ttsVolume, value)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.topMargin: Theme.space4
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            text: AppController.audioPreviewState === "preparing"
                ? qsTr("Đang chuẩn bị bản nghe thử") : qsTr("Nghe thử bản phối")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            textFormat: Text.PlainText
        }

        StudioIconButton {
            iconName: root.previewPlaying ? "pause" : "play"
            toolTipText: root.previewPlaying ? qsTr("Tạm dừng") : qsTr("Nghe thử")
            enabled: AppController.batchCount > 0
                && AppController.audioPreviewState !== "preparing"
            onClicked: root.previewPlaying ? root.pausePreview() : root.requestPreview()
        }
    }

    footerActions: [
        StudioButton {
            text: qsTr("Đóng")
            variant: "primary"
            onClicked: root.close()
        }
    ]

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
            else if (root.visible && root.previewReady)
                root.playPreview()
            else
                root.stopPreview()
        }
    }
}
