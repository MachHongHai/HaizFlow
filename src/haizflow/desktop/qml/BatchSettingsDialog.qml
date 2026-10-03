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
    property string draftTranslationModel: "auto"
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
    property string openedProjectKey: ""
    property bool replaceOverrides: false
    property bool draftBackgroundMusicLoop: true
    property bool draftAudioDuckingEnabled: false
    property int draftAudioDuckingReductionDb: -12
    property string draftVoiceReferencePath: ""
    property string draftWatermarkKind: "text"
    property string draftWatermarkImagePath: ""
    property string draftWatermarkVideoPath: ""
    property int draftWatermarkScalePercent: 100
    property int draftWatermarkOpacityPercent: 46
    property int draftWatermarkOutlinePercent: 100
    property string draftWatermarkFontFamily: "Arial"
    property string draftWatermarkTextColor: "#FFFFFF"
    property bool draftWatermarkBold: true
    property bool draftWatermarkItalic: true
    property var draftSubtitleStyle: ({})
    property string draftPreviewVoice: ""

    readonly property var draftProviderOptions: localizedProviderOptions(
        draftTargetLanguage, AppController.settingsLanguage, AppController.processingDevice)
    readonly property var draftVoiceOptions: localizedVoiceOptions(
        draftTargetLanguage, draftTtsProvider, AppController.settingsLanguage)
    readonly property int draftTtsProviderIndex: findIndex(draftProviderOptions, "provider", draftTtsProvider)
    readonly property int draftSpeechRecognitionIndex: findIndex(
        AppController.speechRecognitionModelOptions, "value", draftSpeechRecognitionModel === "small"
            ? (AppController.processingDevice === "gpu" ? "small-gpu" : "small-cpu") : draftSpeechRecognitionModel)

    function findIndex(options, role, value) {
        for (let index = 0; index < options.length; ++index) {
            if (String(options[index][role]) === String(value))
                return index
        }
        return 0
    }

    function localizedProviderOptions(languageCode, interfaceLanguage, processingDevice) {
        return AppController.ttsProviderOptionsForLanguage(languageCode)
    }

    function localizedVoiceOptions(languageCode, provider, interfaceLanguage) {
        const voices = AppController.voiceOptionsForLanguageAndProvider(languageCode, provider)
            .filter(item => item.voice !== "omnivoice:clone");
        if (root.draftVoiceReferencePath.length > 0)
            voices.push({"voice": "omnivoice:clone", "label": qsTr("Giọng đã nhân bản"),
                "category": "clone", "categoryLabel": qsTr("Giọng của tôi"), "available": true, "previewAvailable": true});
        return voices;
    }

    function normalizedDraftVoice(languageCode, provider, preferredVoice) {
        if (preferredVoice === "omnivoice:clone" && root.draftVoiceReferencePath.length > 0)
            return preferredVoice;
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
        openedProjectKey = AppController.projectKey;
        replaceOverrides = false;
        draftVoiceReferencePath = settings.voiceReferencePath || "";
        draftBackgroundMusicLoop = settings.backgroundMusicLoop !== false;
        draftAudioDuckingEnabled = Boolean(settings.audioDuckingEnabled);
        draftAudioDuckingReductionDb = Number(settings.audioDuckingReductionDb ?? -12);
        draftWatermarkKind = settings.watermarkKind || "text";
        draftWatermarkImagePath = settings.watermarkImagePath || "";
        draftWatermarkVideoPath = settings.watermarkVideoPath || "";
        draftWatermarkScalePercent = Number(settings.watermarkScalePercent ?? 100);
        draftWatermarkOpacityPercent = Number(settings.watermarkOpacityPercent ?? 46);
        draftWatermarkOutlinePercent = Number(settings.watermarkOutlinePercent ?? 100);
        draftWatermarkFontFamily = settings.watermarkFontFamily || "Arial";
        draftWatermarkTextColor = settings.watermarkTextColor || "#FFFFFF";
        draftWatermarkBold = settings.watermarkBold !== false;
        draftWatermarkItalic = settings.watermarkItalic !== false;
        draftSubtitleStyle = settings.subtitleStyle || ({});
        baselineSettings = settings
        draftTargetLanguage = settings.targetLanguage || "vi"
        draftSpeechRecognitionModel = settings.speechRecognitionModel || "small"
        draftTranslationModel = settings.translationModel || "auto"
        draftTtsProvider = settings.ttsProvider || "omnivoice"
        draftTtsVoice = normalizedDraftVoice(draftTargetLanguage, draftTtsProvider, settings.ttsVoice || "")
        draftSpeakerMode = draftTtsProvider.indexOf("omnivoice") === 0 && settings.speakerMode === "multiple"
            ? "multiple" : "single"
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
            "translationModel": draftTranslationModel,
            "ttsProvider": draftTtsProvider,
            "ttsVoice": draftTtsVoice,
            "speakerMode": draftSpeakerMode,
            "enableAudioSeparation": draftEnableAudioSeparation,
            "originalVolume": draftOriginalVolume,
            "backgroundMusicVolume": draftBackgroundMusicVolume,
            "ttsVolume": draftTtsVolume,
            "watermarkText": draftWatermarkText,
            "backgroundMusicPath": draftBackgroundMusicPath,
            "backgroundMusicLoop": draftBackgroundMusicLoop,
            "audioDuckingEnabled": draftAudioDuckingEnabled,
            "audioDuckingReductionDb": draftAudioDuckingReductionDb,
            "voiceReferencePath": draftVoiceReferencePath,
            "watermarkKind": draftWatermarkKind,
            "watermarkImagePath": draftWatermarkImagePath,
            "watermarkVideoPath": draftWatermarkVideoPath,
            "watermarkScalePercent": draftWatermarkScalePercent,
            "watermarkOpacityPercent": draftWatermarkOpacityPercent,
            "watermarkOutlinePercent": draftWatermarkOutlinePercent,
            "watermarkFontFamily": draftWatermarkFontFamily,
            "watermarkTextColor": draftWatermarkTextColor,
            "watermarkBold": draftWatermarkBold,
            "watermarkItalic": draftWatermarkItalic,
            "removeOriginalSubtitles": draftRemoveOriginalSubtitles,
            "originalSubtitleRemovalMode": draftOriginalSubtitleRemovalMode,
            "subtitleStyle": Object.assign({}, draftSubtitleStyle, {
                "font_size": draftSubtitleFontSize,
                "margin_bottom": draftSubtitleMarginBottom,
                "outline": draftSubtitleOutline,
                "max_chars_per_line": draftSubtitleMaxChars,
                "position_x_percent": draftSubtitlePositionX,
                "position_y_percent": draftSubtitlePositionY,
                "box_width_percent": draftSubtitleBoxWidth,
                "box_height_percent": draftSubtitleBoxHeight,
                "manual": draftSubtitleManual
            })
        }
    }

    function hasDraftChanges() { return JSON.stringify(currentDraft()) !== JSON.stringify(baselineSettings) }

    function saveDraft() {
        if (!hasDraftChanges() && !replaceOverrides)
            return true;
        if (AppController.applyBatchSettingsValues(openedProjectKey, currentDraft(), replaceOverrides)) {
            baselineSettings = currentDraft()
            settingOverrides = AppController.batchSettingOverrides()
            return true;
        }
        return false;
    }

    onAboutToShow: {
        loadDraft();
        placeInCenter();
    }
    onClosed: AppController.cancelBatchVoiceRecording()

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
                    text: root.replaceOverrides ? qsTr("Sẽ thay thế cài đặt riêng sau khi xác nhận")
                        : qsTr("Cài đặt riêng của từng video được giữ nguyên")
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
                showCloneAction: true
                showMusicPlaybackSettings: true
                speechRecognitionModel: root.draftSpeechRecognitionModel
                translationModel: root.draftTranslationModel
                speechRecognitionOptions: AppController.speechRecognitionModelOptions
                speechRecognitionIndex: root.draftSpeechRecognitionIndex
                targetLanguage: root.draftTargetLanguage
                targetLanguageOptions: AppController.targetLanguageOptions
                ttsProvider: root.draftTtsProvider
                ttsProviderOptions: root.draftProviderOptions
                ttsProviderIndex: root.draftTtsProviderIndex
                ttsVoice: root.draftTtsVoice
                ttsVoiceOptions: root.draftVoiceOptions
                voicePreviewSource: root.draftPreviewVoice === "omnivoice:clone"
                    ? draftController.localUrl(root.draftVoiceReferencePath) : AppController.audioPreviewSource
                voicePreviewState: root.draftPreviewVoice === "omnivoice:clone" ? "ready" : AppController.audioPreviewState
                speakerMode: root.draftSpeakerMode
                removeOriginalSubtitles: root.draftRemoveOriginalSubtitles
                subtitleRemovalMode: root.draftOriginalSubtitleRemovalMode
                enableAudioSeparation: root.draftEnableAudioSeparation
                backgroundMusicPath: root.draftBackgroundMusicPath
                backgroundMusicLoop: root.draftBackgroundMusicLoop
                audioDuckingEnabled: root.draftAudioDuckingEnabled
                audioDuckingReductionDb: root.draftAudioDuckingReductionDb
                watermarkText: root.draftWatermarkText
                watermarkKind: root.draftWatermarkKind
                watermarkImagePath: root.draftWatermarkImagePath
                watermarkVideoPath: root.draftWatermarkVideoPath

                onSpeechRecognitionEdited: function(value) { root.draftSpeechRecognitionModel = value }
                onTranslationModelEdited: function(value) {
                    root.draftTranslationModel = value;
                    // The generated QML type metadata does not include this runtime property yet.
                    // qmllint disable missing-property
                    if (value.indexOf("gemini-") === 0 && !AppController.geminiKeyConfigured) {
                        root.close();
                        AppController.requestGeminiSetup();
                    }
                    // qmllint enable missing-property
                }
                onTargetLanguageEdited: function(value) {
                    root.draftTargetLanguage = value
                    root.draftTtsVoice = root.normalizedDraftVoice(value, root.draftTtsProvider, root.draftTtsVoice)
                }
                onTtsProviderEdited: function(value) {
                    root.draftTtsProvider = value
                    if (value.indexOf("omnivoice") !== 0)
                        root.draftSpeakerMode = "single"
                    root.draftTtsVoice = root.normalizedDraftVoice(root.draftTargetLanguage, value, root.draftTtsVoice)
                }
                onTtsVoiceEdited: function(value) { root.draftTtsVoice = value }
                onTtsVoicePreviewRequested: function(value) {
                    root.draftPreviewVoice = value;
                    if (value !== "omnivoice:clone")
                        AppController.previewVoiceSample(root.draftTtsProvider, value, root.draftTargetLanguage)
                }
                onCloneVoiceRequested: batchCloneDialogLoader.invoke("openForSelectedVideo", [])
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
                onBackgroundMusicLoopEdited: function(value) { root.draftBackgroundMusicLoop = value; }
                onAudioDuckingEdited: function(value) { root.draftAudioDuckingEnabled = value; }
                onAudioDuckingReductionEdited: function(value) { root.draftAudioDuckingReductionDb = value; }
                onWatermarkKindEdited: function(value) { root.draftWatermarkKind = value; }
                onWatermarkRequested: batchWatermarkDialogLoader.invoke("openForSelectedVideo", [])
            }

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }
        AppCheckBox {
            Layout.fillWidth: true
            visible: root.settingOverrides.length > 0
            text: qsTr("Thay thế cả cài đặt riêng bằng cài đặt chung")
            checked: root.replaceOverrides
            onToggled: root.replaceOverrides = checked
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            StudioButton { text: qsTr("Hủy"); variant: "ghost"; onClicked: root.close() }
            StudioButton {
                text: qsTr("Áp dụng")
                variant: "primary"
                onClicked: if (root.saveDraft()) root.close()
            }
        }
    }

    LazyDialogLoader {
        id: batchCloneDialogLoader
        sourceComponent: Component {
            VoiceCloneDialog {
                controller: draftController
                preferredProvider: root.draftTtsProvider
                onClosed: batchCloneDialogLoader.release()
                onReferenceAccepted: function(path) {
                    root.draftVoiceReferencePath = path;
                    root.draftTtsVoice = "omnivoice:clone";
                    root.draftSpeakerMode = "single";
                }
            }
        }
    }

    QtObject {
        id: draftController
        signal selectedVideoChanged()
        readonly property string selectedVideoId: root.openedProjectKey
        readonly property bool canEditSelectedVideo: !AppController.isBatchRunning
        readonly property string videoThumbnailSource: AppController.videoThumbnailSource
        property alias ttsProvider: root.draftTtsProvider
        property alias voiceCloneReferencePath: root.draftVoiceReferencePath
        property alias watermarkKind: root.draftWatermarkKind
        property alias watermarkText: root.draftWatermarkText
        property alias watermarkImagePath: root.draftWatermarkImagePath
        property alias watermarkVideoPath: root.draftWatermarkVideoPath
        property alias watermarkScalePercent: root.draftWatermarkScalePercent
        property alias watermarkOpacityPercent: root.draftWatermarkOpacityPercent
        property alias watermarkOutlinePercent: root.draftWatermarkOutlinePercent
        property alias watermarkFontFamily: root.draftWatermarkFontFamily
        property alias watermarkTextColor: root.draftWatermarkTextColor
        property alias watermarkBold: root.draftWatermarkBold
        property alias watermarkItalic: root.draftWatermarkItalic
        readonly property string watermarkImageSource: localUrl(watermarkImagePath)
        readonly property string watermarkVideoSource: localUrl(watermarkVideoPath)
        function localUrl(path) { return path ? "file:///" + path.replace(/\\/g, "/") : ""; }
        function chooseWatermarkImage() { return AppController.chooseWatermarkImage(); }
        function chooseWatermarkVideo() { return AppController.chooseWatermarkVideo(); }
        function setWatermarkImage(path) {
            const staged = AppController.stageBatchSettingsAsset(root.openedProjectKey, "watermarkImagePath", path);
            if (staged) root.draftWatermarkImagePath = staged;
            return staged.length > 0;
        }
        function setWatermarkVideo(path) {
            const staged = AppController.stageBatchSettingsAsset(root.openedProjectKey, "watermarkVideoPath", path);
            if (staged) root.draftWatermarkVideoPath = staged;
            return staged.length > 0;
        }
        function chooseVoiceCloneReference() { return AppController.chooseVoiceCloneReference(); }
        function setVoiceCloneReference(path, _transcript) {
            const staged = AppController.stageBatchSettingsAsset(root.openedProjectKey, "voiceReferencePath", path);
            if (staged) root.draftVoiceReferencePath = staged;
            return staged.length > 0;
        }
        function applyVoiceCloneReference(owner, _provider) {
            return owner === AppController.projectKey && root.draftVoiceReferencePath.length > 0;
        }
        function voiceCloneReferenceAnalysis(path, count) { return AppController.voiceCloneReferenceAnalysis(path, count); }
        function voiceCloneInputDevices() { return AppController.voiceCloneInputDevices(); }
        function selectVoiceCloneInputDevice(id) { return AppController.selectVoiceCloneInputDevice(id); }
        function startVoiceCloneRecording() { return AppController.startBatchVoiceRecording(root.openedProjectKey); }
        function voiceCloneRecordingState() { return AppController.batchVoiceRecordingState(); }
        function finishVoiceCloneRecording() {
            const staged = AppController.finishBatchVoiceRecording(root.openedProjectKey);
            if (staged) root.draftVoiceReferencePath = staged;
            return staged.length > 0;
        }
        function cancelVoiceCloneRecording() { AppController.cancelBatchVoiceRecording(); }
    }

    LazyDialogLoader {
        id: batchWatermarkDialogLoader
        sourceComponent: Component {
            AutoWatermarkPreviewDialog {
                controller: draftController
                onClosed: batchWatermarkDialogLoader.release()
            }
        }
    }

    LazyDialogLoader {
        id: batchAudioMixDialogLoader
        sourceComponent: Component {
            BatchAudioMixDialog {
                voiceReferencePath: root.draftVoiceReferencePath
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
