import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Panel {
    id: root
    property string pendingSettingsVideoId: ""

    title: I18n.t("Settings")
    subtitle: I18n.t("Language, voice, picture and audio")
    tone: "violet"
    contentPadding: Theme.space12
    contentSpacing: Theme.space8
    headerSpacing: Theme.space8

    function scheduleVideoSettingsSave() {
        if (AppController.hasSelectedVideo && !AppController.isSelectedVideoQueued) {
            pendingSettingsVideoId = AppController.selectedVideoId
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
            showCloneAction: AppController.ttsProvider === "omnivoice"
            cloneActive: AppController.ttsVoice === "omnivoice:clone"
            speechRecognitionModel: AppController.speechRecognitionModel
            speechRecognitionOptions: AppController.speechRecognitionModelOptions
            speechRecognitionIndex: AppController.speechRecognitionModelIndex
            targetLanguage: AppController.targetLanguage
            targetLanguageOptions: AppController.targetLanguageOptions
            ttsProvider: AppController.ttsProvider
            ttsProviderOptions: AppController.ttsProviderOptions
            ttsProviderIndex: AppController.ttsProviderIndex
            ttsVoice: AppController.ttsVoice
            ttsVoiceOptions: AppController.ttsVoiceOptions
            speakerMode: AppController.speakerMode
            removeOriginalSubtitles: AppController.removeOriginalSubtitles
            subtitleRemovalMode: AppController.originalSubtitleRemovalMode
            enableAudioSeparation: AppController.enableAudioSeparation
            backgroundMusicPath: AppController.backgroundMusicPath
            watermarkText: AppController.watermarkText

            onSpeechRecognitionEdited: function(value) { AppController.speechRecognitionModel = value; root.scheduleVideoSettingsSave() }
            onTargetLanguageEdited: function(value) { AppController.targetLanguage = value; root.scheduleVideoSettingsSave() }
            onTtsProviderEdited: function(value) { AppController.ttsProvider = value; root.scheduleVideoSettingsSave() }
            onTtsVoiceEdited: function(value) { AppController.ttsVoice = value; root.scheduleVideoSettingsSave() }
            onCloneVoiceRequested: voiceCloneDialog.openForSelectedVideo()
            onSpeakerModeEdited: function(value) { AppController.speakerMode = value; root.scheduleVideoSettingsSave() }
            onRemoveOriginalSubtitlesEdited: function(value) { AppController.removeOriginalSubtitles = value; root.scheduleVideoSettingsSave() }
            onSubtitleRemovalModeEdited: function(value) { AppController.originalSubtitleRemovalMode = value; root.scheduleVideoSettingsSave() }
            onSubtitleLayoutRequested: subtitlePreviewDialog.openWithLayout(
                AppController.subtitleFontSize,
                AppController.subtitlePositionXPercent,
                AppController.subtitlePositionYPercent,
                AppController.subtitleBoxWidthPercent,
                AppController.subtitleBoxHeightPercent)
            onAudioSeparationEdited: function(value) { AppController.enableAudioSeparation = value; root.scheduleVideoSettingsSave() }
            onAudioMixRequested: audioMixDialog.open()
            onBackgroundMusicFileRequested: AppController.browseBackgroundMusic()
            onBackgroundMusicLinkRequested: backgroundMusicLinkDialog.open()
            onBackgroundMusicClearRequested: AppController.clearBackgroundMusic()
            onWatermarkRequested: watermarkDialog.openWithText(AppController.watermarkText)
        }

        ScrollBar.vertical: ScrollBar {
            policy: setupScroll.contentHeight > setupScroll.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }
    }

    AudioMixDialog { id: audioMixDialog }
    BackgroundMusicLinkDialog { id: backgroundMusicLinkDialog }
    VoiceCloneDialog { id: voiceCloneDialog }

    WatermarkDialog {
        id: watermarkDialog
        onWatermarkAccepted: function(text) {
            AppController.watermarkText = text
            root.scheduleVideoSettingsSave()
        }
    }

    SubtitlePreviewDialog {
        id: subtitlePreviewDialog
        onSubtitleLayoutEdited: function(fontSize, positionX, positionY, boxWidth, boxHeight) {
            AppController.subtitleFontSize = fontSize
            AppController.subtitlePositionXPercent = positionX
            AppController.subtitlePositionYPercent = positionY
            AppController.subtitleBoxWidthPercent = boxWidth
            AppController.subtitleBoxHeightPercent = boxHeight
            root.scheduleVideoSettingsSave()
        }
    }

    AppButton {
        Layout.fillWidth: true
        visible: !AppController.hasSelectedVideo
        text: AppController.isProcessing ? I18n.t("Add to processing queue") : I18n.t("Create and process")
        iconGlyph: "\uE768"
        tone: "primary"
        enabled: AppController.canEditSelectedVideo && AppController.videoPath.length > 0
        onClicked: AppController.startProjectVideo()
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

    Connections {
        target: AppController
        function onSelectedVideoChanged() {
            if (videoSettingsSaveTimer.running && root.pendingSettingsVideoId !== AppController.selectedVideoId) {
                videoSettingsSaveTimer.stop()
                root.pendingSettingsVideoId = ""
            }
        }
    }
}
