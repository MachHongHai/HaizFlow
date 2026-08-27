pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Panel {
    id: root

    property int currentStage: 0
    property var completedStages: []
    property string pendingSettingsVideoId: ""
    property var subtitleSegments: []
    property int selectedSubtitleIndex: -1
    readonly property bool editable: AppController.canEditSelectedVideo && AppController.hasSelectedVideo
    readonly property bool taskQueued: AppController.isSelectedVideoQueued
    readonly property bool taskProcessing: AppController.isSelectedVideoProcessing
    readonly property bool taskPaused: AppController.selectedStatus === "paused" && !taskQueued
    readonly property string toolId: ["translation", "visual", "voice", "audio"][currentStage]
    readonly property bool toolComplete: toolId === "translation"
        ? completedStages.indexOf("translation") >= 0
        : toolId === "voice" && completedStages.indexOf("voice") >= 0
    readonly property bool prerequisiteReady: toolId !== "voice"
        || completedStages.indexOf("translation") >= 0
    readonly property bool runnableTool: toolId === "translation" || toolId === "voice"
    readonly property bool taskBelongsToTool: AppController.manualTargetStage === toolId
    readonly property var selectedSubtitle: selectedSubtitleIndex >= 0
        && selectedSubtitleIndex < subtitleSegments.length
        ? subtitleSegments[selectedSubtitleIndex] : null
    readonly property var toolTitles: [
        I18n.t("Translate"), I18n.t("Visuals"), I18n.t("Voice"), I18n.t("Audio")
    ]

    signal subtitleSelected(int index)
    signal subtitleTextCommitted(int index, string text)

    title: toolTitles[currentStage]
    tone: "violet"
    contentPadding: Theme.space8
    contentSpacing: Theme.space8

    function scheduleSave() {
        if (!AppController.hasSelectedVideo || AppController.isSelectedVideoQueued)
            return
        pendingSettingsVideoId = AppController.selectedVideoId
        settingsSaveTimer.restart()
    }

    function saveNow() {
        settingsSaveTimer.stop()
        if (AppController.hasSelectedVideo)
            AppController.persistVideoSettingsFor(AppController.selectedVideoId)
        pendingSettingsVideoId = ""
    }

    function runLabel() {
        if (toolId === "translation")
            return toolComplete ? I18n.t("Translate again") : I18n.t("Translate video")
        return toolComplete ? I18n.t("Regenerate voice") : I18n.t("Generate voice")
    }

    Flickable {
        id: inspectorScroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 0
        contentWidth: width
        contentHeight: inspectorStack.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        StackLayout {
            id: inspectorStack
            width: inspectorScroll.width
            currentIndex: root.currentStage

            ColumnLayout {
                spacing: Theme.space8

                SettingLabel {
                    Layout.fillWidth: true
                    text: I18n.t("Speech recognition")
                    helpText: I18n.t("Turbo provides higher GPU quality. Small uses less memory and also supports CPU processing.")
                }
                AppComboBox {
                    Layout.fillWidth: true
                    enabled: root.editable
                    textRole: "label"
                    valueRole: "value"
                    model: AppController.speechRecognitionModelOptions
                    currentIndex: AppController.speechRecognitionModelIndex
                    onActivated: {
                        AppController.speechRecognitionModel = currentValue
                        root.scheduleSave()
                    }
                }

                SettingLabel {
                    Layout.fillWidth: true
                    text: I18n.t("Translate to")
                    helpText: I18n.t("The selected language is used for both translated subtitles and generated speech.")
                }
                SearchableLanguageCombo {
                    Layout.fillWidth: true
                    enabled: root.editable
                    options: AppController.targetLanguageOptions
                    selectedCode: AppController.targetLanguage
                    onSelected: function(code) {
                        AppController.targetLanguage = code
                        root.scheduleSave()
                    }
                }

                SettingLabel {
                    Layout.fillWidth: true
                    text: I18n.t("Recognition audio")
                    helpText: I18n.t("Separate vocals before recognition when speech competes with music or effects.")
                }
                SegmentedControl {
                    Layout.fillWidth: true
                    enabled: root.editable
                    currentValue: AppController.enableAudioSeparation ? "separated" : "original"
                    options: [
                        { "label": I18n.t("Original"), "value": "original" },
                        { "label": I18n.t("Separate vocals"), "value": "separated" }
                    ]
                    onActivated: function(value) {
                        AppController.enableAudioSeparation = value === "separated"
                        root.scheduleSave()
                    }
                }
            }

            ColumnLayout {
                spacing: Theme.space8

                SettingLabel {
                    Layout.fillWidth: true
                    text: I18n.t("Original subtitles")
                    helpText: I18n.t("Cover burned-in source subtitles or leave the source image unchanged.")
                }
                SegmentedControl {
                    Layout.fillWidth: true
                    enabled: root.editable && root.subtitleSegments.length > 0
                    currentValue: AppController.removeOriginalSubtitles ? "remove" : "keep"
                    options: [
                        { "label": I18n.t("Cover"), "value": "remove" },
                        { "label": I18n.t("Keep"), "value": "keep" }
                    ]
                    onActivated: function(value) {
                        AppController.removeOriginalSubtitles = value === "remove"
                        root.scheduleSave()
                    }
                }
                SegmentedControl {
                    Layout.fillWidth: true
                    visible: AppController.removeOriginalSubtitles
                    enabled: root.editable && root.subtitleSegments.length > 0
                    currentValue: AppController.originalSubtitleRemovalMode
                    options: [
                        { "label": I18n.t("Blur"), "value": "blur" },
                        { "label": I18n.t("Nearby patch"), "value": "patch" }
                    ]
                    onActivated: function(value) {
                        AppController.originalSubtitleRemovalMode = value
                        root.scheduleSave()
                    }
                }

                AppButton {
                    Layout.fillWidth: true
                    text: I18n.t("Subtitle size and position")
                    iconGlyph: "\uE70F"
                    tone: "secondary"
                    compact: true
                    enabled: root.editable && root.subtitleSegments.length > 0
                    onClicked: subtitlePreviewDialog.openWithLayout(
                        AppController.subtitleFontSize,
                        AppController.subtitlePositionXPercent,
                        AppController.subtitlePositionYPercent,
                        AppController.subtitleBoxWidthPercent,
                        AppController.subtitleBoxHeightPercent)
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: root.subtitleSegments.length > 0
                    spacing: Theme.space4

                    Text {
                        Layout.fillWidth: true
                        text: root.selectedSubtitle
                            ? qsTr("%1/%2").arg(root.selectedSubtitleIndex + 1).arg(root.subtitleSegments.length)
                            : I18n.t("Subtitle")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }
                    IconButton {
                        glyph: "\uE72B"
                        toolTipText: I18n.t("Previous subtitle")
                        enabled: root.selectedSubtitleIndex > 0
                        onClicked: root.subtitleSelected(root.selectedSubtitleIndex - 1)
                    }
                    IconButton {
                        glyph: "\uE72A"
                        toolTipText: I18n.t("Next subtitle")
                        enabled: root.selectedSubtitleIndex >= 0
                            && root.selectedSubtitleIndex < root.subtitleSegments.length - 1
                        onClicked: root.subtitleSelected(root.selectedSubtitleIndex + 1)
                    }
                }
                TextArea {
                    id: subtitleTextEditor
                    Layout.fillWidth: true
                    Layout.preferredHeight: 72
                    visible: root.subtitleSegments.length > 0
                    enabled: root.editable && root.selectedSubtitle !== null
                    text: root.selectedSubtitle ? String(root.selectedSubtitle.text || "") : ""
                    placeholderText: I18n.t("Select a subtitle on the timeline")
                    color: Theme.text
                    font.pixelSize: Theme.caption
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    background: Rectangle {
                        color: Theme.input
                        radius: Theme.radiusSmall
                        border.width: subtitleTextEditor.activeFocus ? 2 : 1
                        border.color: subtitleTextEditor.activeFocus ? Theme.focus : Theme.outline
                    }
                    onEditingFinished: {
                        if (root.selectedSubtitle && text.trim() !== String(root.selectedSubtitle.text || ""))
                            root.subtitleTextCommitted(root.selectedSubtitleIndex, text)
                    }
                }

                SettingLabel {
                    Layout.fillWidth: true
                    text: I18n.t("Watermark")
                    helpText: I18n.t("A small text watermark is included in preview and export.")
                }
                AppButton {
                    Layout.fillWidth: true
                    text: AppController.watermarkText.length > 0
                        ? AppController.watermarkText : I18n.t("Set watermark")
                    iconGlyph: "\uE70F"
                    tone: "secondary"
                    compact: true
                    enabled: root.editable
                    onClicked: watermarkDialog.openWithText(AppController.watermarkText)
                }
            }

            ColumnLayout {
                spacing: Theme.space8

                SettingLabel {
                    Layout.fillWidth: true
                    text: I18n.t("TTS engine")
                    helpText: I18n.t("OmniVoice runs locally. Edge TTS requires a stable internet connection.")
                }
                AppComboBox {
                    Layout.fillWidth: true
                    enabled: root.editable
                    textRole: "label"
                    valueRole: "provider"
                    model: AppController.ttsProviderOptions
                    currentIndex: AppController.ttsProviderIndex
                    onActivated: {
                        AppController.ttsProvider = currentValue
                        root.scheduleSave()
                    }
                }

                SettingLabel {
                    Layout.fillWidth: true
                    text: I18n.t("Voice")
                    helpText: I18n.t("Choose a preset narrator or an authorised cloned voice sample.")
                }
                VoicePicker {
                    Layout.fillWidth: true
                    enabled: root.editable
                    model: AppController.ttsVoiceOptions
                    currentValue: AppController.ttsVoice
                    allowVoiceClone: false
                    onSelected: function(voice) {
                        AppController.ttsVoice = voice
                        root.scheduleSave()
                    }
                }
                AppButton {
                    Layout.fillWidth: true
                    visible: AppController.ttsProvider === "omnivoice"
                    text: AppController.ttsVoice === "omnivoice:clone"
                        ? I18n.t("Cloned voice") : I18n.t("Clone voice")
                    iconGlyph: "\uE77B"
                    tone: AppController.ttsVoice === "omnivoice:clone" ? "primary" : "secondary"
                    compact: true
                    enabled: root.editable
                    onClicked: voiceCloneDialog.openForSelectedVideo()
                }
                AppCheckBox {
                    Layout.fillWidth: true
                    enabled: root.editable && AppController.ttsProvider === "omnivoice"
                    text: I18n.t("Detect multiple speakers")
                    checked: AppController.speakerMode === "multiple"
                    onToggled: {
                        AppController.speakerMode = checked ? "multiple" : "single"
                        root.scheduleSave()
                    }
                }
            }

            ColumnLayout {
                spacing: Theme.space8

                AppButton {
                    Layout.fillWidth: true
                    text: I18n.t("Adjust audio levels")
                    iconGlyph: "\uE767"
                    tone: "secondary"
                    compact: true
                    enabled: root.editable
                    onClicked: audioMixDialog.open()
                }

                SettingLabel {
                    Layout.fillWidth: true
                    text: I18n.t("Background music")
                    helpText: I18n.t("Music and volume changes update only the preview mix.")
                }
                Text {
                    Layout.fillWidth: true
                    text: AppController.backgroundMusicPath || I18n.t("No background music")
                    color: Theme.textMuted
                    font.pixelSize: Theme.label
                    textFormat: Text.PlainText
                    elide: Text.ElideMiddle
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4

                    AppButton {
                        Layout.fillWidth: true
                        text: I18n.t("Choose file")
                        tone: "secondary"
                        compact: true
                        enabled: root.editable
                        onClicked: AppController.browseBackgroundMusic()
                    }
                    AppButton {
                        Layout.fillWidth: true
                        text: I18n.t("From link")
                        tone: "secondary"
                        compact: true
                        enabled: root.editable
                        onClicked: backgroundMusicLinkDialog.open()
                    }
                    IconButton {
                        visible: AppController.backgroundMusicPath.length > 0
                        glyph: "\uE74D"
                        toolTipText: I18n.t("Clear")
                        enabled: root.editable
                        onClicked: AppController.clearBackgroundMusic()
                    }
                }
            }
        }

        ScrollBar.vertical: ScrollBar {
            policy: inspectorScroll.contentHeight > inspectorScroll.height
                ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space4

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.taskQueued
            spacing: Theme.space4

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: I18n.progressDetail(AppController.selectedProgressDetail || AppController.selectedStep)
                    color: Theme.textMuted
                    font.pixelSize: Theme.label
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
                Text {
                    text: qsTr("%1%").arg(AppController.selectedProgress)
                    color: Theme.interactive
                    font.pixelSize: Theme.label
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }
            AppProgressBar {
                Layout.fillWidth: true
                value: AppController.selectedProgress
            }
        }

        AppButton {
            Layout.fillWidth: true
            visible: root.runnableTool
            // qmllint disable missing-property
            text: root.taskProcessing && root.taskBelongsToTool ? I18n.t("Pause")
                : root.taskQueued && root.taskBelongsToTool ? I18n.t("Waiting in queue")
                : root.taskPaused && root.taskBelongsToTool ? I18n.t("Continue") : root.runLabel()
            iconGlyph: root.taskProcessing && root.taskBelongsToTool ? "\uE769"
                : root.taskQueued && root.taskBelongsToTool ? "\uE895" : "\uE768"
            tone: root.taskProcessing && root.taskBelongsToTool ? "danger" : "primary"
            enabled: root.taskProcessing && root.taskBelongsToTool
                || root.taskPaused && root.taskBelongsToTool
                || (root.editable && !root.taskQueued && root.prerequisiteReady)
            toolTipText: root.prerequisiteReady ? "" : I18n.t("Translate the video first")
            onClicked: {
                if (root.taskProcessing && root.taskBelongsToTool)
                    AppController.stopVideo()
                else if (root.taskPaused && root.taskBelongsToTool)
                    AppController.resumeSelectedVideo()
                else {
                    root.saveNow()
                    AppController.runManualStage(root.toolId)
                }
            }
            // qmllint enable missing-property
        }
    }

    Timer {
        id: settingsSaveTimer
        interval: 220
        repeat: false
        onTriggered: {
            AppController.persistVideoSettingsFor(root.pendingSettingsVideoId)
            root.pendingSettingsVideoId = ""
        }
    }

    Connections {
        target: AppController
        function onSelectedVideoChanged() {
            if (settingsSaveTimer.running && root.pendingSettingsVideoId !== AppController.selectedVideoId) {
                settingsSaveTimer.stop()
                root.pendingSettingsVideoId = ""
            }
        }
    }

    AudioMixDialog { id: audioMixDialog }
    BackgroundMusicLinkDialog { id: backgroundMusicLinkDialog }
    VoiceCloneDialog { id: voiceCloneDialog }

    WatermarkDialog {
        id: watermarkDialog
        onWatermarkAccepted: function(text) {
            AppController.watermarkText = text
            root.scheduleSave()
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
            root.scheduleSave()
        }
    }
}
