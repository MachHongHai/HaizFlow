pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

FloatingToolDialog {
    id: root
    objectName: "batchSettingsDialog"
    modal: true
    expandedWidth: 1120
    expandedHeight: 760
    toolTitle: qsTr("Cài đặt hàng loạt")
    toolSubtitle: qsTr("Cài đặt mặc định cho mọi video trong dự án")

    property var baselineSettings: ({})
    property string draftTargetLanguage: "vi"
    property string draftSpeechRecognitionModel: "small"
    property string draftTtsProvider: "omnivoice"
    property string draftTtsVoice: ""
    property string draftSpeakerMode: "single"
    property bool draftEnableAudioSeparation: true
    property int draftOriginalVolume: 60
    property int draftBackgroundMusicVolume: 30
    property int draftTtsVolume: 100
    property string draftWatermarkText: ""
    property string draftBackgroundMusicPath: ""
    property bool draftRemoveOriginalSubtitles: true
    property string draftOriginalSubtitleRemovalMode: "patch"
    property int draftSubtitleFontSize: 60
    property int draftSubtitlePositionX: 51
    property int draftSubtitlePositionY: 96
    property int draftSubtitleBoxWidth: 72
    property int draftSubtitleBoxHeight: 6
    property bool draftSubtitleManual: false
    property int draftSubtitleMarginBottom: 40
    property int draftSubtitleOutline: 2
    property int draftSubtitleMaxChars: 32
    property var settingOverrides: []

    readonly property var draftProviderOptions: localizedProviderOptions(
        draftTargetLanguage, AppController.settingsLanguage)
    readonly property var draftVoiceOptions: localizedVoiceOptions(
        draftTargetLanguage, draftTtsProvider, AppController.settingsLanguage)
    readonly property int draftTtsProviderIndex: findIndex(draftProviderOptions, "provider", draftTtsProvider)
    readonly property int draftSpeechRecognitionIndex: findIndex(
        AppController.speechRecognitionModelOptions, "value", draftSpeechRecognitionModel)

    function findIndex(options, role, value) {
        for (let index = 0; index < options.length; ++index) {
            if (String(options[index][role]) === String(value))
                return index
        }
        return 0
    }

    function localizedProviderOptions(languageCode, interfaceLanguage) {
        return AppController.ttsProviderOptionsForLanguage(languageCode)
    }

    function localizedVoiceOptions(languageCode, provider, interfaceLanguage) {
        return AppController.voiceOptionsForLanguageAndProvider(languageCode, provider)
    }

    function normalizedDraftVoice(languageCode, provider, preferredVoice) {
        const options = AppController.voiceOptionsForLanguageAndProvider(languageCode, provider)
        for (let index = 0; index < options.length; ++index) {
            if (options[index].voice === preferredVoice && options[index].available !== false)
                return preferredVoice
        }
        for (let index = 0; index < options.length; ++index) {
            if (options[index].available !== false)
                return options[index].voice
        }
        return ""
    }

    function loadDraft() {
        const settings = AppController.batchSettings()
        baselineSettings = settings
        draftTargetLanguage = settings.targetLanguage || "vi"
        draftSpeechRecognitionModel = settings.speechRecognitionModel || "small"
        draftTtsProvider = settings.ttsProvider || "omnivoice"
        draftTtsVoice = normalizedDraftVoice(draftTargetLanguage, draftTtsProvider, settings.ttsVoice || "")
        draftSpeakerMode = settings.speakerMode === "multiple" ? "multiple" : "single"
        draftEnableAudioSeparation = settings.enableAudioSeparation !== undefined ? Boolean(settings.enableAudioSeparation) : true
        draftOriginalVolume = Number(settings.originalVolume !== undefined ? settings.originalVolume : 60)
        draftBackgroundMusicVolume = Number(settings.backgroundMusicVolume !== undefined ? settings.backgroundMusicVolume : 30)
        draftTtsVolume = Number(settings.ttsVolume !== undefined ? settings.ttsVolume : 100)
        draftWatermarkText = settings.watermarkText || ""
        draftBackgroundMusicPath = settings.backgroundMusicPath || ""
        draftRemoveOriginalSubtitles = settings.removeOriginalSubtitles !== false
        draftOriginalSubtitleRemovalMode = settings.originalSubtitleRemovalMode || "patch"
        const style = settings.subtitleStyle || ({})
        draftSubtitleFontSize = Number(style.font_size !== undefined ? style.font_size : 60)
        draftSubtitlePositionX = Number(style.position_x_percent !== undefined ? style.position_x_percent : 51)
        draftSubtitlePositionY = Number(style.position_y_percent !== undefined ? style.position_y_percent : 96)
        draftSubtitleBoxWidth = Number(style.box_width_percent !== undefined ? style.box_width_percent : 72)
        draftSubtitleBoxHeight = Number(style.box_height_percent !== undefined ? style.box_height_percent : 6)
        draftSubtitleManual = Boolean(style.manual)
        draftSubtitleMarginBottom = Number(style.margin_bottom !== undefined ? style.margin_bottom : 40)
        draftSubtitleOutline = Number(style.outline !== undefined ? style.outline : 2)
        draftSubtitleMaxChars = Number(style.max_chars_per_line !== undefined ? style.max_chars_per_line : 32)
        settingOverrides = AppController.batchSettingOverrides()
        baselineSettings = currentDraft()
    }

    function currentDraft() {
        return {
            "workflowMode": "A",
            "targetLanguage": draftTargetLanguage,
            "speechRecognitionModel": draftSpeechRecognitionModel,
            "ttsProvider": draftTtsProvider,
            "ttsVoice": draftTtsVoice,
            "speakerMode": draftSpeakerMode,
            "enableAudioSeparation": draftEnableAudioSeparation,
            "originalVolume": draftOriginalVolume,
            "backgroundMusicVolume": draftBackgroundMusicVolume,
            "ttsVolume": draftTtsVolume,
            "watermarkText": draftWatermarkText,
            "backgroundMusicPath": draftBackgroundMusicPath,
            "removeOriginalSubtitles": draftRemoveOriginalSubtitles,
            "originalSubtitleRemovalMode": draftOriginalSubtitleRemovalMode,
            "subtitleStyle": {
                "font_size": draftSubtitleFontSize,
                "margin_bottom": draftSubtitleMarginBottom,
                "outline": draftSubtitleOutline,
                "max_chars_per_line": draftSubtitleMaxChars,
                "position_x_percent": draftSubtitlePositionX,
                "position_y_percent": draftSubtitlePositionY,
                "box_width_percent": draftSubtitleBoxWidth,
                "box_height_percent": draftSubtitleBoxHeight,
                "manual": draftSubtitleManual
            }
        }
    }

    function hasDraftChanges() { return JSON.stringify(currentDraft()) !== JSON.stringify(baselineSettings) }

    function saveDraft() {
        if (!hasDraftChanges() || AppController.batchCount <= 0)
            return
        if (AppController.applyBatchSettingsDraft(
                "A", draftTargetLanguage, draftSpeechRecognitionModel,
                draftTtsProvider, draftTtsVoice, draftEnableAudioSeparation,
                draftOriginalVolume, draftBackgroundMusicVolume, draftTtsVolume,
                draftWatermarkText, draftBackgroundMusicPath, draftRemoveOriginalSubtitles,
                currentDraft().subtitleStyle, draftOriginalSubtitleRemovalMode, draftSpeakerMode)) {
            baselineSettings = currentDraft()
            settingOverrides = AppController.batchSettingOverrides()
        }
    }

    onOpened: loadDraft()
    onClosed: saveDraft()

    Connections {
        target: AppController
        function onBatchChanged() {
            if (root.visible)
                root.settingOverrides = AppController.batchSettingOverrides()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space12
        spacing: Theme.space8

        Rectangle {
            Layout.fillWidth: true
            visible: root.settingOverrides.length > 0
            implicitHeight: overrideRow.implicitHeight + Theme.space16
            color: Theme.interactiveMuted
            radius: Theme.radiusSmall
            border.width: 1
            border.color: Theme.interactiveOutline

            RowLayout {
                id: overrideRow
                anchors.fill: parent
                anchors.margins: Theme.space8
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: qsTr("%1 %2").arg(root.settingOverrides.length).arg(qsTr("video có cài đặt riêng"))
                    color: Theme.text
                    font.pixelSize: Theme.caption
                    font.weight: Font.DemiBold
                }
                Text {
                    text: qsTr("Cài đặt riêng của từng video được giữ nguyên")
                    color: Theme.interactive
                    font.pixelSize: Theme.label
                }
            }
        }

        Flickable {
            id: settingsScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: width
            contentHeight: settingsForm.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            ProcessingSettingsForm {
                id: settingsForm
                width: settingsScroll.width
                editable: true
                cpuOnly: AppController.cpuOnly
                hasSource: AppController.batchCount > 0 && AppController.videoPath.length > 0
                showCloneAction: false
                speechRecognitionModel: root.draftSpeechRecognitionModel
                speechRecognitionOptions: AppController.speechRecognitionModelOptions
                speechRecognitionIndex: root.draftSpeechRecognitionIndex
                targetLanguage: root.draftTargetLanguage
                targetLanguageOptions: AppController.targetLanguageOptions
                ttsProvider: root.draftTtsProvider
                ttsProviderOptions: root.draftProviderOptions
                ttsProviderIndex: root.draftTtsProviderIndex
                ttsVoice: root.draftTtsVoice
                ttsVoiceOptions: root.draftVoiceOptions
                speakerMode: root.draftSpeakerMode
                removeOriginalSubtitles: root.draftRemoveOriginalSubtitles
                subtitleRemovalMode: root.draftOriginalSubtitleRemovalMode
                enableAudioSeparation: root.draftEnableAudioSeparation
                backgroundMusicPath: root.draftBackgroundMusicPath
                watermarkText: root.draftWatermarkText

                onSpeechRecognitionEdited: function(value) { root.draftSpeechRecognitionModel = value }
                onTargetLanguageEdited: function(value) {
                    root.draftTargetLanguage = value
                    root.draftTtsVoice = root.normalizedDraftVoice(value, root.draftTtsProvider, root.draftTtsVoice)
                }
                onTtsProviderEdited: function(value) {
                    root.draftTtsProvider = value
                    root.draftTtsVoice = root.normalizedDraftVoice(root.draftTargetLanguage, value, root.draftTtsVoice)
                }
                onTtsVoiceEdited: function(value) { root.draftTtsVoice = value }
                onSpeakerModeEdited: function(value) { root.draftSpeakerMode = value }
                onRemoveOriginalSubtitlesEdited: function(value) { root.draftRemoveOriginalSubtitles = value }
                onSubtitleRemovalModeEdited: function(value) { root.draftOriginalSubtitleRemovalMode = value }
                onSubtitleLayoutRequested: batchSubtitlePreviewDialogLoader.invoke("openWithLayout", [
                    root.draftSubtitleFontSize, root.draftSubtitlePositionX, root.draftSubtitlePositionY,
                    root.draftSubtitleBoxWidth, root.draftSubtitleBoxHeight])
                onAudioSeparationEdited: function(value) { root.draftEnableAudioSeparation = value }
                onAudioMixRequested: batchAudioMixDialogLoader.invoke("open", [])
                onBackgroundMusicFileRequested: {
                    const path = AppController.chooseBatchBackgroundMusic()
                    if (path.length > 0)
                        root.draftBackgroundMusicPath = path
                }
                onBackgroundMusicLinkRequested: batchBackgroundMusicLinkDialogLoader.invoke("open", [])
                onBackgroundMusicClearRequested: root.draftBackgroundMusicPath = ""
                onWatermarkRequested: batchWatermarkDialogLoader.invoke("openWithText", [root.draftWatermarkText])
            }

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }
    }

    LazyDialogLoader {
        id: batchWatermarkDialogLoader
        sourceComponent: Component {
            WatermarkDialog {
                onClosed: batchWatermarkDialogLoader.release()
                onWatermarkAccepted: function(text) { root.draftWatermarkText = text }
            }
        }
    }

    LazyDialogLoader {
        id: batchAudioMixDialogLoader
        sourceComponent: Component {
            BatchAudioMixDialog {
                audioSeparationEnabled: root.draftEnableAudioSeparation
                originalVolume: root.draftOriginalVolume
                ttsVolume: root.draftTtsVolume
                backgroundMusicVolume: root.draftBackgroundMusicVolume
                targetLanguage: root.draftTargetLanguage
                ttsProvider: root.draftTtsProvider
                ttsVoice: root.draftTtsVoice
                backgroundMusicPath: root.draftBackgroundMusicPath
                onClosed: batchAudioMixDialogLoader.release()
                onAudioLevelsEdited: function(originalVolume, ttsVolume, backgroundMusicVolume) {
                    root.draftOriginalVolume = originalVolume
                    root.draftTtsVolume = ttsVolume
                    root.draftBackgroundMusicVolume = backgroundMusicVolume
                }
            }
        }
    }

    LazyDialogLoader {
        id: batchBackgroundMusicLinkDialogLoader
        sourceComponent: Component {
            BackgroundMusicLinkDialog {
                batchMode: true
                onClosed: batchBackgroundMusicLinkDialogLoader.release()
                onBatchMusicReady: function(path) { root.draftBackgroundMusicPath = path }
            }
        }
    }

    LazyDialogLoader {
        id: batchSubtitlePreviewDialogLoader
        sourceComponent: Component {
            SubtitlePreviewDialog {
                onClosed: batchSubtitlePreviewDialogLoader.release()
                onSubtitleLayoutEdited: function(fontSize, positionX, positionY, boxWidth, boxHeight) {
                    root.draftSubtitleFontSize = fontSize
                    root.draftSubtitlePositionX = positionX
                    root.draftSubtitlePositionY = positionY
                    root.draftSubtitleBoxWidth = boxWidth
                    root.draftSubtitleBoxHeight = boxHeight
                    root.draftSubtitleManual = true
                }
            }
        }
    }
}
