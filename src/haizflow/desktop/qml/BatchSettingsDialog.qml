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
    property string draftGeminiInstructions: ""
    property string draftGeminiGlossary: ""
    property string draftGeminiStyle: "balanced"
    property string draftTtsProvider: "omnivoice"
    property string draftTtsVoice: ""
    property string draftSpeakerMode: "single"
    property bool draftEnableAudioSeparation: true
    property string draftOutputFormat: "keep_ratio"
    property real draftOutputSpeed: 1.0
    property int draftOriginalVolume: 60
    property int draftBackgroundMusicVolume: 30
    property int draftTtsVolume: 100
    property string draftWatermarkText: ""
    property string draftBackgroundMusicPath: ""
    property bool draftRemoveOriginalSubtitles: true
    property string draftOriginalSubtitleRemovalMode: "patch"
    property var draftOriginalSubtitleRegion: ({})
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
    property var previewSources: []
    property int previewIndex: 0
    property var previewMedia: ({})
    readonly property var previewSource: previewSources[previewIndex] || ({})

    function refreshPreview() {
        previewMedia = AppController.batchPreviewMedia(String(previewSource.videoId || ""));
    }

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
            .filter(item => !item.voice.endsWith(":clone"));
        if (root.draftVoiceReferencePath.length > 0 && provider !== "edge")
            voices.push({"voice": provider.indexOf("vieneu") === 0 ? "vieneu:clone" : "omnivoice:clone", "label": qsTr("Giọng đã nhân bản"),
                "category": "clone", "categoryLabel": qsTr("Giọng của tôi"), "available": true, "previewAvailable": false});
        return voices;
    }

    function normalizedDraftVoice(languageCode, provider, preferredVoice) {
        if (preferredVoice.endsWith(":clone") && root.draftVoiceReferencePath.length > 0 && provider !== "edge")
            return provider.indexOf("vieneu") === 0 ? "vieneu:clone" : "omnivoice:clone";
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
        previewSources = AppController.batchPreviewSources();
        const selected = previewSources.findIndex(item => item.videoId === AppController.selectedVideoId);
        previewIndex = Math.max(0, selected);
        refreshPreview();
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
        draftTranslationModel = settings.translationModel || "q4"
        draftGeminiInstructions = settings.geminiTranslationInstructions || "";
        draftGeminiGlossary = settings.geminiTranslationGlossary || "";
        draftGeminiStyle = settings.geminiTranslationStyle || "balanced";
        draftTtsProvider = settings.ttsProvider || "omnivoice"
        draftTtsVoice = normalizedDraftVoice(draftTargetLanguage, draftTtsProvider, settings.ttsVoice || "")
        draftSpeakerMode = (draftTtsProvider.indexOf("omnivoice") === 0 || draftTtsProvider.indexOf("vieneu") === 0) && settings.speakerMode === "multiple"
            ? "multiple" : "single"
        draftEnableAudioSeparation = settings.enableAudioSeparation !== undefined ? Boolean(settings.enableAudioSeparation) : true
        draftOutputFormat = settings.outputFormat || "keep_ratio"
        draftOutputSpeed = settings.outputSpeed === undefined ? 1.0 : Number(settings.outputSpeed)
        draftOriginalVolume = Number(settings.originalVolume !== undefined ? settings.originalVolume : 60)
        draftBackgroundMusicVolume = Number(settings.backgroundMusicVolume !== undefined ? settings.backgroundMusicVolume : 30)
        draftTtsVolume = Number(settings.ttsVolume !== undefined ? settings.ttsVolume : 100)
        draftWatermarkText = settings.watermarkText || ""
        draftBackgroundMusicPath = settings.backgroundMusicPath || ""
        draftRemoveOriginalSubtitles = settings.removeOriginalSubtitles !== false
        draftOriginalSubtitleRemovalMode = settings.originalSubtitleRemovalMode || "patch"
        draftOriginalSubtitleRegion = Object.assign({}, settings.originalSubtitleRegion || ({}));
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
            "geminiTranslationInstructions": draftGeminiInstructions,
            "geminiTranslationGlossary": draftGeminiGlossary,
            "geminiTranslationStyle": draftGeminiStyle,
            "ttsProvider": draftTtsProvider,
            "ttsVoice": draftTtsVoice,
            "speakerMode": draftSpeakerMode,
            "enableAudioSeparation": draftEnableAudioSeparation,
            "outputFormat": draftOutputFormat,
            "outputSpeed": draftOutputSpeed,
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
            "originalSubtitleRegion": draftOriginalSubtitleRegion,
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
            if (root.visible) {
                root.settingOverrides = AppController.batchSettingOverrides();
                const owner = root.previewSource.videoId;
                root.previewSources = AppController.batchPreviewSources();
                root.previewIndex = Math.max(0, root.previewSources.findIndex(item => item.videoId === owner));
                root.refreshPreview();
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space12
        spacing: Theme.space8

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: qsTr("Video xem trước")
                color: Theme.textMuted
                font.pixelSize: TypeScale.label
            }
            StudioComboBox {
                Layout.fillWidth: true
                model: root.previewSources
                textRole: "fileName"
                currentIndex: root.previewIndex
                enabled: root.previewSources.length > 0
                onActivated: function(index) {
                    root.previewIndex = index;
                    root.refreshPreview();
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            visible: root.settingOverrides.length > 0
            implicitHeight: overrideRow.implicitHeight + Theme.space16
            color: Theme.warningMuted
            radius: Theme.radiusSmall
            border.width: 1
            border.color: Theme.warning

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
                    wrapMode: Text.Wrap
                }
                StudioButton {
                    text: qsTr("Chi tiết")
                    variant: "ghost"
                    onClicked: overrideDetailsLoader.invoke("open", [])
                }
                Text {
                    Layout.fillWidth: true
                    text: root.replaceOverrides ? qsTr("Sẽ thay thế cài đặt riêng sau khi xác nhận")
                        : qsTr("Cài đặt riêng của từng video được giữ nguyên")
                    color: Theme.interactive
                    font.pixelSize: Theme.label
                    wrapMode: Text.Wrap
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
                editable: !AppController.isBatchRunning
                cpuOnly: AppController.cpuOnly
                hasSource: root.previewSources.length > 0
                showCloneAction: true
                showMusicPlaybackSettings: true
                speechRecognitionModel: root.draftSpeechRecognitionModel
                translationModel: root.draftTranslationModel
                geminiInstructions: root.draftGeminiInstructions
                geminiGlossary: root.draftGeminiGlossary
                geminiStyle: root.draftGeminiStyle
                onGeminiGuidanceEdited: function(instructions, glossary, style) {
                    root.draftGeminiInstructions = instructions;
                    root.draftGeminiGlossary = glossary;
                    root.draftGeminiStyle = style;
                }
                speechRecognitionOptions: AppController.speechRecognitionModelOptions
                speechRecognitionIndex: root.draftSpeechRecognitionIndex
                targetLanguage: root.draftTargetLanguage
                targetLanguageOptions: AppController.targetLanguageOptions
                ttsProvider: root.draftTtsProvider
                ttsProviderOptions: root.draftProviderOptions
                ttsProviderIndex: root.draftTtsProviderIndex
                ttsVoice: root.draftTtsVoice
                ttsVoiceOptions: root.draftVoiceOptions
                voicePreviewSource: root.draftPreviewVoice.endsWith(":clone")
                    ? draftController.localUrl(root.draftVoiceReferencePath) : AppController.audioPreviewSource
                voicePreviewState: root.draftPreviewVoice.endsWith(":clone") ? "ready" : AppController.audioPreviewState
                speakerMode: root.draftSpeakerMode
                removeOriginalSubtitles: root.draftRemoveOriginalSubtitles
                subtitleRemovalMode: root.draftOriginalSubtitleRemovalMode
                enableAudioSeparation: root.draftEnableAudioSeparation
                outputFormat: root.draftOutputFormat
                outputSpeed: root.draftOutputSpeed
                onOutputSpeedEdited: function(value) { root.draftOutputSpeed = value; }
                onOutputFormatEdited: function(value) { root.draftOutputFormat = value; }
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
                    if (!AppController.validateTtsProviderForLanguage(value, root.draftTtsProvider))
                        return
                    root.draftTargetLanguage = value
                    root.draftTtsVoice = root.normalizedDraftVoice(value, root.draftTtsProvider, root.draftTtsVoice)
                }
                onTtsProviderEdited: function(value) {
                    if (!AppController.validateTtsProviderForLanguage(root.draftTargetLanguage, value))
                        return
                    root.draftTtsProvider = value
                    if (value.indexOf("omnivoice") !== 0 && value.indexOf("vieneu") !== 0)
                        root.draftSpeakerMode = "single"
                    root.draftTtsVoice = root.normalizedDraftVoice(root.draftTargetLanguage, value, root.draftTtsVoice)
                }
                onTtsVoiceEdited: function(value) { root.draftTtsVoice = value }
                onTtsVoicePreviewRequested: function(value) {
                    root.draftPreviewVoice = value;
                    if (!value.endsWith(":clone"))
                        AppController.previewVoiceSample(root.draftTtsProvider, value, root.draftTargetLanguage)
                }
                onCloneVoiceRequested: batchCloneDialogLoader.invoke("openForSelectedVideo", [])
                onSpeakerModeEdited: function(value) { root.draftSpeakerMode = value }
                onRemoveOriginalSubtitlesEdited: function(value) { root.draftRemoveOriginalSubtitles = value }
                onSubtitleRemovalModeEdited: function(value) { root.draftOriginalSubtitleRemovalMode = value }
                onSourceCoverRequested: batchSourceCoverDialogLoader.invoke("openForSource", [
                    AppController.sourceCoverPreviewMedia(String(root.previewSource.videoId || "")),
                    root.draftOriginalSubtitleRegion])
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
            enabled: !AppController.isBatchRunning
            onToggled: root.replaceOverrides = checked
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            StudioButton { text: qsTr("Hủy"); variant: "ghost"; onClicked: root.close() }
            StudioButton {
                text: qsTr("Áp dụng")
                variant: "primary"
                enabled: !AppController.isBatchRunning
                onClicked: if (root.saveDraft()) root.close()
            }
        }
    }

    LazyDialogLoader {
        id: batchSourceCoverDialogLoader
        sourceComponent: Component {
            SourceCoverDialog {
                selectedOwner: false
                toolSubtitle: root.previewSource.fileName || ""
                saveHandler: function(region) {
                    if (!root.visible || root.openedProjectKey !== AppController.projectKey || AppController.isBatchRunning)
                        return false;
                    root.draftOriginalSubtitleRegion = Object.assign({}, region);
                    return true;
                }
                onClosed: batchSourceCoverDialogLoader.release()
                Connections {
                    target: root
                    function onClosed() { batchSourceCoverDialogLoader.release(); }
                }
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
                    root.draftTtsVoice = root.draftTtsProvider.indexOf("vieneu") === 0 ? "vieneu:clone" : "omnivoice:clone";
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
        readonly property string videoThumbnailSource: root.previewSource.thumbnailSource || ""
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
                toolSubtitle: root.previewSource.fileName || ""
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
                toolSubtitle: root.previewSource.fileName || ""
                previewMedia: root.previewMedia
                previewSource: root.previewSource.thumbnailSource || ""
                appearance: Object.assign({}, root.draftSubtitleStyle, {
                    font_size: root.draftSubtitleFontSize, outline: root.draftSubtitleOutline
                })
                coverEnabled: root.draftRemoveOriginalSubtitles
                autoAlignToCover: !root.draftSubtitleManual
                coverLayout: root.previewMedia.subtitleAutoCoverLayout || ({})
                onAutoAlignmentEdited: function(enabled) { root.draftSubtitleManual = !enabled; }
                onSubtitleAppearanceEdited: function(patch) {
                    root.draftSubtitleStyle = Object.assign({}, root.draftSubtitleStyle, patch);
                    if (patch.font_size !== undefined) root.draftSubtitleFontSize = Number(patch.font_size);
                    if (patch.outline !== undefined) root.draftSubtitleOutline = Number(patch.outline);
                }
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

    LazyDialogLoader {
        id: overrideDetailsLoader
        sourceComponent: Component {
            BatchDetailsDialog {
                overrides: true
                rows: root.settingOverrides
                onClosed: overrideDetailsLoader.release()
            }
        }
    }
}
