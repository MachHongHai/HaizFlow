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
            onWatermarkRequested: watermarkDialogLoader.invoke("openWithText", [AppController.watermarkText])
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
            VoiceCloneDialog { onClosed: voiceCloneDialogLoader.release() }
        }
    }

    LazyDialogLoader {
        id: watermarkDialogLoader
        sourceComponent: Component {
            WatermarkDialog {
                onClosed: watermarkDialogLoader.release()
                onWatermarkAccepted: function(text) {
                    AppController.watermarkText = text
                    root.scheduleVideoSettingsSave()
                }
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

    AppButton {
        Layout.fillWidth: true
        visible: !AppController.hasSelectedVideo
        text: AppController.isProcessing ? qsTr("Đưa vào hàng đợi xử lý") : qsTr("Tạo và xử lý")
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
