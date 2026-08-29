import QtQuick
import QtQuick.Layouts
import QtMultimedia
import "."

AppDialog {
    id: root

    property string pendingSettingsVideoId: ""

    readonly property bool sourceAudioAdjustable: AppController.canEditSelectedVideo
        && !AppController.enableAudioSeparation
    readonly property bool backgroundMusicAdjustable: AppController.canEditSelectedVideo
        && AppController.backgroundMusicPath.length > 0
    readonly property bool previewReady: AppController.audioPreviewState === "ready"
        && AppController.audioPreviewSource.length > 0
    readonly property bool previewPlaying: voicePreviewPlayer.playbackState === MediaPlayer.PlayingState

    title: qsTr("Âm lượng")
    subtitle: qsTr("Cân bằng âm thanh gốc, giọng đọc và nhạc nền")
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
        if (AppController.hasSelectedVideo && !AppController.isSelectedVideoQueued) {
            pendingSettingsVideoId = AppController.selectedVideoId
            videoSettingsSaveTimer.restart()
        }
    }

    function flushVideoSettingsSave() {
        if (!videoSettingsSaveTimer.running)
            return
        videoSettingsSaveTimer.stop()
        AppController.persistVideoSettingsFor(root.pendingSettingsVideoId)
        root.pendingSettingsVideoId = ""
    }

    onClosed: {
        pausePreview()
        flushVideoSettingsSave()
    }
    onVisibleChanged: {
        if (!visible)
            pausePreview()
    }

    AudioLevelControl {
        Layout.fillWidth: true
        label: qsTr("Âm thanh gốc")
        volume: AppController.originalVolume
        adjustable: root.sourceAudioAdjustable
        disabledHint: qsTr("Không chỉnh được khi đang tách giọng")
        onVolumeEdited: function(value) {
            AppController.originalVolume = value
            root.scheduleVideoSettingsSave()
        }
    }

    AudioLevelControl {
        Layout.fillWidth: true
        label: qsTr("Giọng đọc")
        volume: AppController.ttsVolume
        adjustable: AppController.canEditSelectedVideo
        onVolumeEdited: function(value) {
            AppController.ttsVolume = value
            root.scheduleVideoSettingsSave()
        }
    }

    AudioLevelControl {
        Layout.fillWidth: true
        label: qsTr("Nhạc nền")
        volume: AppController.backgroundMusicVolume
        adjustable: root.backgroundMusicAdjustable
        disabledHint: qsTr("Chọn nhạc nền trước khi chỉnh âm lượng")
        onVolumeEdited: function(value) {
            AppController.backgroundMusicVolume = value
            root.scheduleVideoSettingsSave()
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
            enabled: AppController.canEditSelectedVideo && AppController.videoPath.length > 0
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

    Timer {
        id: videoSettingsSaveTimer
        interval: 250
        repeat: false
        onTriggered: {
            AppController.persistVideoSettingsFor(root.pendingSettingsVideoId)
            root.pendingSettingsVideoId = ""
        }
    }

    MediaPlayer {
        id: sourcePreviewPlayer
        source: AppController.audioPreviewOriginalSource
        audioOutput: AudioOutput { volume: AppController.originalVolume / 100.0 }
    }

    MediaPlayer {
        id: musicPreviewPlayer
        source: AppController.audioPreviewBackgroundMusicSource
        audioOutput: AudioOutput { volume: AppController.backgroundMusicVolume / 100.0 }
    }

    MediaPlayer {
        id: voicePreviewPlayer
        source: AppController.audioPreviewSource
        audioOutput: AudioOutput { volume: AppController.ttsVolume / 100.0 }
    }

    Connections {
        target: AppController

        function onSelectedVideoChanged() {
            if (videoSettingsSaveTimer.running
                    && root.pendingSettingsVideoId !== AppController.selectedVideoId) {
                videoSettingsSaveTimer.stop()
                root.pendingSettingsVideoId = ""
            }
        }

        function onAudioPreviewChanged() {
            if (AppController.audioPreviewState === "preparing")
                root.stopPreview()
            else if (root.visible && AppController.audioPreviewState === "ready"
                     && AppController.audioPreviewSource.length > 0)
                root.playPreview()
            else
                root.stopPreview()
        }
    }
}
