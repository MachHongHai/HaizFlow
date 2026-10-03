pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

InspectorPanel {
    id: root
    property string pendingSettingsVideoId: ""

    title: qsTr("Cài đặt xử lý")

    function scheduleVideoSettingsSave() {
        if (AppController.hasSelectedVideo && !AppController.isSelectedVideoQueued) {
            pendingSettingsVideoId = AppController.selectedVideoId
            AppController.captureVideoSettingsDraft(pendingSettingsVideoId)
            videoSettingsSaveTimer.restart()
        }
    }

    Flickable {
        id: setupScroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 0
        contentWidth: width
        contentHeight: settingsForm.implicitHeight
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        ProcessingSettingsForm {
            id: settingsForm
            width: setupScroll.width
            editable: AppController.canEditSelectedVideo
            cpuOnly: AppController.cpuOnly
            hasSource: AppController.videoPath.length > 0
            showCloneAction: AppController.ttsProvider.indexOf("omnivoice") === 0
            speechRecognitionModel: AppController.speechRecognitionModel
            translationModel: AppController.translationModel
            speechRecognitionOptions: AppController.speechRecognitionModelOptions
            speechRecognitionIndex: AppController.speechRecognitionModelIndex
            targetLanguage: AppController.targetLanguage
            targetLanguageOptions: AppController.targetLanguageOptions
            ttsProvider: AppController.ttsProvider
            ttsProviderOptions: AppController.ttsProviderOptions
            ttsProviderIndex: AppController.ttsProviderIndex
            ttsVoice: AppController.ttsVoice
            ttsVoiceOptions: AppController.ttsVoiceOptions
            voicePreviewSource: AppController.audioPreviewSource
            voicePreviewState: AppController.audioPreviewState
            speakerMode: AppController.speakerMode
            removeOriginalSubtitles: AppController.removeOriginalSubtitles
            subtitleRemovalMode: AppController.originalSubtitleRemovalMode
            enableAudioSeparation: AppController.enableAudioSeparation
            backgroundMusicPath: AppController.backgroundMusicPath
            watermarkText: AppController.watermarkText
            watermarkKind: AppController.watermarkKind
            watermarkImagePath: AppController.watermarkImagePath
            watermarkVideoPath: AppController.watermarkVideoPath
            backgroundMusicLoop: AppController.backgroundMusicLoop
            audioDuckingEnabled: AppController.audioDuckingEnabled
            audioDuckingReductionDb: AppController.audioDuckingReductionDb

            onBackgroundMusicLoopEdited: function(value) { AppController.backgroundMusicLoop = value; root.scheduleVideoSettingsSave() }
            onAudioDuckingEdited: function(value) { AppController.audioDuckingEnabled = value; root.scheduleVideoSettingsSave() }
            onAudioDuckingReductionEdited: function(value) { AppController.audioDuckingReductionDb = value; root.scheduleVideoSettingsSave() }

            onSpeechRecognitionEdited: function(value) { AppController.speechRecognitionModel = value; root.scheduleVideoSettingsSave() }
            onTranslationModelEdited: function(value) {
                AppController.translationModel = value
                if (AppController.translationModel === value)
                    root.scheduleVideoSettingsSave()
            }
            onTargetLanguageEdited: function(value) { AppController.targetLanguage = value; root.scheduleVideoSettingsSave() }
            onTtsProviderEdited: function(value) { AppController.ttsProvider = value; root.scheduleVideoSettingsSave() }
            onTtsVoiceEdited: function(value) { AppController.ttsVoice = value; root.scheduleVideoSettingsSave() }
            onTtsVoicePreviewRequested: function(value) {
                AppController.previewVoiceSample(AppController.ttsProvider, value, AppController.targetLanguage)
            }
            onCloneVoiceRequested: voiceCloneDialogLoader.invoke("openForSelectedVideo", [])
            onSpeakerModeEdited: function(value) { AppController.speakerMode = value; root.scheduleVideoSettingsSave() }
            onRemoveOriginalSubtitlesEdited: function(value) { AppController.removeOriginalSubtitles = value; root.scheduleVideoSettingsSave() }
            onSubtitleRemovalModeEdited: function(value) { AppController.originalSubtitleRemovalMode = value; root.scheduleVideoSettingsSave() }
            onSubtitleLayoutRequested: subtitlePreviewDialogLoader.invoke("openWithLayout", [
                AppController.subtitleFontSize,
                AppController.subtitlePositionXPercent,
                AppController.subtitlePositionYPercent,
                AppController.subtitleBoxWidthPercent,
                AppController.subtitleBoxHeightPercent])
            onAudioSeparationEdited: function(value) { AppController.enableAudioSeparation = value; root.scheduleVideoSettingsSave() }
            onAudioMixRequested: audioMixDialogLoader.invoke("open", [])
            onBackgroundMusicFileRequested: AppController.browseBackgroundMusic()
            onBackgroundMusicLinkRequested: backgroundMusicLinkDialogLoader.invoke("open", [])
            onBackgroundMusicClearRequested: AppController.clearBackgroundMusic()
            onWatermarkKindEdited: function(value) {
                AppController.watermarkKind = value
                root.scheduleVideoSettingsSave()
            }
            onWatermarkRequested: watermarkDialogLoader.invoke("openForSelectedVideo", [])
        }

        ScrollBar.vertical: ScrollBar {
            policy: setupScroll.contentHeight > setupScroll.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }
    }

    LazyDialogLoader {
        id: audioMixDialogLoader
        sourceComponent: Component {
            AudioMixDialog { onClosed: audioMixDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: backgroundMusicLinkDialogLoader
        sourceComponent: Component {
            BackgroundMusicLinkDialog { onClosed: backgroundMusicLinkDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: voiceCloneDialogLoader
        sourceComponent: Component {
            VoiceCloneDialog {
                onReferenceAccepted: function(path) {
                    // The backend has already committed this selection.
                    videoSettingsSaveTimer.stop();
                    root.pendingSettingsVideoId = "";
                }
                onClosed: voiceCloneDialogLoader.release()
            }
        }
    }

    LazyDialogLoader {
        id: watermarkDialogLoader
        sourceComponent: Component {
            AutoWatermarkPreviewDialog {
                onClosed: watermarkDialogLoader.release()
                onWatermarkSettingsEdited: root.scheduleVideoSettingsSave()
            }
        }
    }

    LazyDialogLoader {
        id: subtitlePreviewDialogLoader
        sourceComponent: Component {
            SubtitlePreviewDialog {
                onClosed: subtitlePreviewDialogLoader.release()
                onSubtitleLayoutEdited: function(fontSize, positionX, positionY, boxWidth, boxHeight) {
                    AppController.subtitleFontSize = fontSize
                    AppController.subtitlePositionXPercent = positionX
                    AppController.subtitlePositionYPercent = positionY
                    AppController.subtitleBoxWidthPercent = boxWidth
                    AppController.subtitleBoxHeightPercent = boxHeight
                    root.scheduleVideoSettingsSave()
                }
            }
        }
    }

    Timer {
        id: videoSettingsSaveTimer
        interval: 450
        repeat: false
        onTriggered: {
            AppController.persistVideoSettingsFor(root.pendingSettingsVideoId)
            root.pendingSettingsVideoId = ""
        }
    }

    Connections {
        target: AppController
        function onSelectedVideoChanged() {
            if (videoSettingsSaveTimer.running && root.pendingSettingsVideoId !== AppController.selectedVideoId) {
                videoSettingsSaveTimer.stop()
                AppController.persistVideoSettingsFor(root.pendingSettingsVideoId)
                root.pendingSettingsVideoId = ""
            }
        }
    }
}
