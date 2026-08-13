pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root
    objectName: "batchSettingsDialog"

    property var baselineSettings: ({})
    property string draftWorkflowMode: "A"
    property string draftTargetLanguage: "vi"
    property string draftTtsProvider: "vieneu"
    property string draftTtsVoice: ""
    property bool draftEnableAudioSeparation: false
    property int draftOriginalVolume: 60
    property int draftBackgroundMusicVolume: 30
    property int draftTtsVolume: 100
    property string draftWatermarkText: ""
    property string draftBackgroundMusicPath: ""
    property bool draftRemoveOriginalSubtitles: true
    property string draftOriginalSubtitleRemovalMode: "blur"
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
    readonly property var draftProviderOptions: AppController.ttsProviderOptionsForLanguage(draftTargetLanguage)
    readonly property var draftVoiceOptions: AppController.voiceOptionsForLanguageAndProvider(
        draftTargetLanguage, draftTtsProvider)
    readonly property int draftTtsProviderIndex: {
        for (let index = 0; index < draftProviderOptions.length; ++index) {
            if (draftProviderOptions[index].provider === draftTtsProvider)
                return index
        }
        return 0
    }
    readonly property int draftTtsVoiceIndex: {
        for (let index = 0; index < draftVoiceOptions.length; ++index) {
            if (draftVoiceOptions[index].voice === draftTtsVoice)
                return index
        }
        return 0
    }

    function normalizedDraftVoice(languageCode, provider, preferredVoice) {
        const options = AppController.voiceOptionsForLanguageAndProvider(languageCode, provider)
        for (let index = 0; index < options.length; ++index) {
            if (options[index].voice === preferredVoice)
                return preferredVoice
        }
        return options.length > 0 ? options[0].voice : ""
    }

    function loadDraft() {
        const settings = AppController.batchSettings()
        baselineSettings = settings
        draftWorkflowMode = settings.workflowMode || "A"
        draftTargetLanguage = settings.targetLanguage || "vi"
        draftTtsProvider = settings.ttsProvider || "vieneu"
        draftTtsVoice = normalizedDraftVoice(
            draftTargetLanguage, draftTtsProvider, settings.ttsVoice || "")
        draftEnableAudioSeparation = Boolean(settings.enableAudioSeparation)
        draftOriginalVolume = Number(settings.originalVolume !== undefined ? settings.originalVolume : 60)
        draftBackgroundMusicVolume = Number(settings.backgroundMusicVolume !== undefined ? settings.backgroundMusicVolume : 30)
        draftTtsVolume = Number(settings.ttsVolume !== undefined ? settings.ttsVolume : 100)
        draftWatermarkText = settings.watermarkText || ""
        draftBackgroundMusicPath = settings.backgroundMusicPath || ""
        draftRemoveOriginalSubtitles = settings.removeOriginalSubtitles !== false
        draftOriginalSubtitleRemovalMode = settings.originalSubtitleRemovalMode || "blur"
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
        refreshSettingOverrides()
    }

    function hasDraftChanges() {
        return draftWorkflowMode !== (baselineSettings.workflowMode || "A")
            || draftTargetLanguage !== (baselineSettings.targetLanguage || "vi")
            || draftTtsProvider !== (baselineSettings.ttsProvider || "vieneu")
            || draftTtsVoice !== (baselineSettings.ttsVoice || "")
            || draftEnableAudioSeparation !== Boolean(baselineSettings.enableAudioSeparation)
            || draftOriginalVolume !== Number(baselineSettings.originalVolume !== undefined ? baselineSettings.originalVolume : 60)
            || draftBackgroundMusicVolume !== Number(baselineSettings.backgroundMusicVolume !== undefined ? baselineSettings.backgroundMusicVolume : 30)
            || draftTtsVolume !== Number(baselineSettings.ttsVolume !== undefined ? baselineSettings.ttsVolume : 100)
            || draftWatermarkText !== (baselineSettings.watermarkText || "")
            || draftBackgroundMusicPath !== (baselineSettings.backgroundMusicPath || "")
            || draftRemoveOriginalSubtitles !== (baselineSettings.removeOriginalSubtitles !== false)
            || draftOriginalSubtitleRemovalMode !== (baselineSettings.originalSubtitleRemovalMode || "blur")
            || draftSubtitleFontSize !== Number((baselineSettings.subtitleStyle || {}).font_size !== undefined ? baselineSettings.subtitleStyle.font_size : 60)
            || draftSubtitlePositionX !== Number((baselineSettings.subtitleStyle || {}).position_x_percent !== undefined ? baselineSettings.subtitleStyle.position_x_percent : 51)
            || draftSubtitlePositionY !== Number((baselineSettings.subtitleStyle || {}).position_y_percent !== undefined ? baselineSettings.subtitleStyle.position_y_percent : 96)
            || draftSubtitleBoxWidth !== Number((baselineSettings.subtitleStyle || {}).box_width_percent !== undefined ? baselineSettings.subtitleStyle.box_width_percent : 72)
            || draftSubtitleBoxHeight !== Number((baselineSettings.subtitleStyle || {}).box_height_percent !== undefined ? baselineSettings.subtitleStyle.box_height_percent : 6)
            || draftSubtitleManual !== Boolean((baselineSettings.subtitleStyle || {}).manual)
    }

    function saveDraft() {
        if (!hasDraftChanges() || AppController.batchCount <= 0)
            return
        if (AppController.applyBatchSettingsDraft(
                draftWorkflowMode,
                draftTargetLanguage,
                draftTtsProvider,
                draftTtsVoice,
                draftEnableAudioSeparation,
                draftOriginalVolume,
                draftBackgroundMusicVolume,
                draftTtsVolume,
                draftWatermarkText,
                draftBackgroundMusicPath,
                draftRemoveOriginalSubtitles,
                {
                    "font_size": draftSubtitleFontSize,
                    "margin_bottom": draftSubtitleMarginBottom,
                    "outline": draftSubtitleOutline,
                    "max_chars_per_line": draftSubtitleMaxChars,
                    "position_x_percent": draftSubtitlePositionX,
                    "position_y_percent": draftSubtitlePositionY,
                    "box_width_percent": draftSubtitleBoxWidth,
                    "box_height_percent": draftSubtitleBoxHeight,
                    "manual": draftSubtitleManual
                },
                draftOriginalSubtitleRemovalMode
            )) {
            baselineSettings = {
                "workflowMode": draftWorkflowMode,
                "targetLanguage": draftTargetLanguage,
                "ttsProvider": draftTtsProvider,
                "ttsVoice": draftTtsVoice,
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
            refreshSettingOverrides()
        }
    }

    function fileName(path) {
        const normalized = String(path || "").replace(/\\/g, "/")
        const parts = normalized.split("/")
        return parts.length > 0 ? parts[parts.length - 1] : normalized
    }

    function refreshSettingOverrides() {
        settingOverrides = AppController.batchSettingOverrides()
    }

    function overrideDifferenceLabel(key) {
        switch (key) {
        case "workflow": return I18n.t("Workflow")
        case "targetLanguage": return I18n.t("Target language")
        case "voice": return I18n.t("Voice")
        case "audioSource": return I18n.t("Audio source")
        case "sourceVolume": return I18n.t("Source audio volume")
        case "backgroundMusicVolume": return I18n.t("Background music volume")
        case "ttsVolume": return I18n.t("TTS volume")
        case "watermark": return I18n.t("Watermark")
        case "originalSubtitles": return I18n.t("Original subtitles")
        case "subtitleRemovalMode": return I18n.t("Removal method")
        case "subtitleLayout": return I18n.t("Subtitle layout")
        case "backgroundMusic": return I18n.t("Background music")
        default: return ""
        }
    }

    function overrideSummary(differences) {
        const labels = []
        for (let index = 0; index < differences.length; ++index)
            labels.push(overrideDifferenceLabel(differences[index]))
        return labels.join(", ")
    }

    modal: true
    focus: true
    width: Math.min(720, parent ? parent.width - 48 : 720)
    height: Math.min(700, parent ? parent.height - 48 : 700)
    padding: 0
    title: I18n.t("Batch settings")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    header: null
    footer: null

    onOpened: {
        loadDraft()
    }

    onClosed: saveDraft()

    Connections {
        target: AppController

        function onBatchChanged() {
            if (root.visible)
                root.refreshSettingOverrides()
        }
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionStandard }
            NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: Theme.motionStandard; easing.type: Easing.OutCubic }
        }
    }

    exit: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
            NumberAnimation { property: "scale"; from: 1; to: 0.99; duration: Theme.motionFast }
        }
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
                    text: I18n.t("Batch settings")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Configure dubbing settings for this batch")
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

        ScrollView {
            id: detailsScroll

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: detailsScroll.availableWidth
                spacing: Theme.space20

                Rectangle {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.space24
                    Layout.rightMargin: Theme.space24
                    Layout.topMargin: Theme.space20
                    Layout.preferredHeight: overrideContent.implicitHeight + Theme.space20
                    visible: root.settingOverrides.length > 0
                    radius: Theme.radiusSmall
                    color: Theme.violetMuted
                    border.width: 1
                    border.color: Theme.violetOutline

                    ColumnLayout {
                        id: overrideContent

                        anchors.fill: parent
                        anchors.margins: Theme.space12
                        spacing: Theme.space8

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space8

                            AppIcon {
                                Layout.preferredWidth: 18
                                Layout.preferredHeight: 18
                                glyph: "\uE7F8"
                                iconColor: Theme.violet
                                iconSize: Theme.iconSmall
                                Accessible.ignored: true
                            }

                            Text {
                                Layout.fillWidth: true
                                text: qsTr("%1 %2").arg(root.settingOverrides.length).arg(I18n.t("videos with custom settings"))
                                color: Theme.text
                                font.pixelSize: Theme.caption
                                font.weight: Font.DemiBold
                                textFormat: Text.PlainText
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: I18n.t("These differ from the batch settings")
                            color: Theme.textMuted
                            font.pixelSize: Theme.label
                            textFormat: Text.PlainText
                        }

                        ListView {
                            id: overrideList

                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.min(contentHeight, 132)
                            Layout.maximumHeight: 132
                            clip: true
                            model: root.settingOverrides
                            spacing: Theme.space4

                            delegate: RowLayout {
                                id: overrideRow

                                required property var modelData

                                width: overrideList.width
                                spacing: Theme.space8

                                Text {
                                    Layout.preferredWidth: Math.min(220, implicitWidth)
                                    text: overrideRow.modelData.fileName
                                    color: Theme.text
                                    font.pixelSize: Theme.label
                                    font.weight: Font.Medium
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: root.overrideSummary(overrideRow.modelData.differences)
                                    color: Theme.violet
                                    font.pixelSize: Theme.label
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                            }

                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.space24
                    Layout.rightMargin: Theme.space24
                    Layout.topMargin: Theme.space20
                    spacing: Theme.space12

                    Text {
                        text: I18n.t("Dubbing and audio")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space12

                        Text {
                            Layout.preferredWidth: 112
                            text: I18n.t("Workflow")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            font.weight: Font.Medium
                        }

                        SegmentedControl {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            currentValue: root.draftWorkflowMode
                            options: [
                                { "label": I18n.t("Full auto"), "value": "A" },
                                { "label": I18n.t("Review then dub"), "value": "review" }
                            ]
                            onActivated: function(value) {
                                root.draftWorkflowMode = value
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space4

                        Text {
                            text: I18n.t("Translate to")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            font.weight: Font.Medium
                        }

                        SearchableLanguageCombo {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 42
                            options: AppController.targetLanguageOptions
                            selectedCode: root.draftTargetLanguage
                            onSelected: function(code) {
                                root.draftTargetLanguage = code
                                if (root.draftTtsProvider === "vieneu"
                                        && code !== "vi" && code !== "en")
                                    root.draftTtsProvider = AppController.fallbackFromVieneuForLanguage(code)
                                root.draftTtsVoice = root.normalizedDraftVoice(
                                    code, root.draftTtsProvider, root.draftTtsVoice)
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space4

                        Text {
                            text: I18n.t("TTS engine")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            font.weight: Font.Medium
                        }

                        AppComboBox {
                            Layout.fillWidth: true
                            textRole: "label"
                            valueRole: "provider"
                            model: root.draftProviderOptions
                            currentIndex: root.draftTtsProviderIndex
                            onActivated: {
                                root.draftTtsProvider = currentValue === "vieneu"
                                        && root.draftTargetLanguage !== "vi"
                                        && root.draftTargetLanguage !== "en"
                                    ? AppController.fallbackFromVieneuForLanguage(root.draftTargetLanguage)
                                    : currentValue
                                root.draftTtsVoice = root.normalizedDraftVoice(
                                    root.draftTargetLanguage,
                                    root.draftTtsProvider,
                                    root.draftTtsVoice
                                )
                            }
                        }

                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space4

                        Text {
                            text: I18n.t("Voice")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            font.weight: Font.Medium
                        }

                        AppComboBox {
                            Layout.fillWidth: true
                            textRole: "label"
                            valueRole: "voice"
                            model: root.draftVoiceOptions
                            currentIndex: root.draftTtsVoiceIndex
                            onActivated: root.draftTtsVoice = currentValue
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space12

                            Text {
                                Layout.preferredWidth: 112
                                text: I18n.t("Original subtitles")
                                color: Theme.textMuted
                                font.pixelSize: Theme.caption
                                font.weight: Font.Medium
                            }

                            SegmentedControl {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 38
                                currentValue: root.draftRemoveOriginalSubtitles ? "remove" : "keep"
                                options: [
                                    { "label": I18n.t("Cover original subtitles"), "value": "remove" },
                                    { "label": I18n.t("Keep original video"), "value": "keep" }
                                ]
                                onActivated: function(value) {
                                    root.draftRemoveOriginalSubtitles = value === "remove"
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            visible: root.draftRemoveOriginalSubtitles
                            spacing: Theme.space12

                            Text {
                                Layout.preferredWidth: 112
                                text: I18n.t("Removal method")
                                color: Theme.textMuted
                                font.pixelSize: Theme.caption
                                font.weight: Font.Medium
                            }

                            SegmentedControl {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 38
                                currentValue: root.draftOriginalSubtitleRemovalMode
                                options: [
                                    { "label": I18n.t("Blur"), "value": "blur" },
                                    { "label": I18n.t("Nearby patch"), "value": "patch" }
                                ]
                                onActivated: function(value) {
                                    root.draftOriginalSubtitleRemovalMode = value
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.draftRemoveOriginalSubtitles
                                ? root.draftOriginalSubtitleRemovalMode === "patch"
                                    ? I18n.t("Copy a nearby clean picture strip over the original subtitles")
                                    : I18n.t("OCR locates burned-in subtitles and blurs that region")
                                : I18n.t("OCR and blur are skipped; the source picture remains unchanged")
                            color: Theme.textMuted
                            font.pixelSize: Theme.label
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                        }

                        AppButton {
                            Layout.fillWidth: true
                            visible: !root.draftRemoveOriginalSubtitles
                            text: I18n.t("Edit new subtitles")
                            compact: true
                            tone: "secondary"
                            enabled: AppController.batchCount > 0 && AppController.videoPath.length > 0
                            onClicked: batchSubtitlePreviewDialog.openWithLayout(
                                root.draftSubtitleFontSize,
                                root.draftSubtitlePositionX,
                                root.draftSubtitlePositionY,
                                root.draftSubtitleBoxWidth,
                                root.draftSubtitleBoxHeight
                            )
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        Layout.topMargin: Theme.space4
                        Layout.bottomMargin: Theme.space4
                        color: Theme.divider
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space12

                        Text {
                            Layout.preferredWidth: 112
                            text: I18n.t("Audio source")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            font.weight: Font.Medium
                        }

                        SegmentedControl {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            currentValue: root.draftEnableAudioSeparation ? "separated" : "original"
                            options: [
                                { "label": I18n.t("Keep original audio"), "value": "original" },
                                { "label": I18n.t("Separate vocals"), "value": "separated" }
                            ]
                            onActivated: function(value) {
                                root.draftEnableAudioSeparation = value === "separated"
                            }
                        }

                        AppButton {
                            text: I18n.t("Adjust audio levels")
                            tone: "secondary"
                            compact: true
                            onClicked: {
                                batchAudioMixDialog.audioSeparationEnabled = root.draftEnableAudioSeparation
                                batchAudioMixDialog.originalVolume = root.draftOriginalVolume
                                batchAudioMixDialog.ttsVolume = root.draftTtsVolume
                                batchAudioMixDialog.backgroundMusicVolume = root.draftBackgroundMusicVolume
                                batchAudioMixDialog.targetLanguage = root.draftTargetLanguage
                                batchAudioMixDialog.ttsProvider = root.draftTtsProvider
                                batchAudioMixDialog.ttsVoice = root.draftTtsVoice
                                batchAudioMixDialog.backgroundMusicPath = root.draftBackgroundMusicPath
                                batchAudioMixDialog.open()
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: AppController.cpuOnly && root.draftEnableAudioSeparation
                        text: I18n.t("Audio separation is slower in CPU mode")
                        color: Theme.warning
                        font.pixelSize: Theme.caption
                        wrapMode: Text.WordWrap
                        textFormat: Text.PlainText
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

                        Text {
                            Layout.preferredWidth: 112
                            text: I18n.t("Background music")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.draftBackgroundMusicPath.length > 0
                                ? root.fileName(root.draftBackgroundMusicPath) : I18n.t("No background music")
                            color: root.draftBackgroundMusicPath.length > 0 ? Theme.text : Theme.textMuted
                            font.pixelSize: Theme.caption
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                        }

                        AppButton {
                            id: batchBackgroundMusicButton

                            property bool menuWasOpenOnPress: false

                            text: root.draftBackgroundMusicPath.length > 0
                                ? I18n.t("Change music") : I18n.t("Add music")
                            compact: true
                            onPressed: menuWasOpenOnPress = batchBackgroundMusicMenu.visible
                            onClicked: {
                                if (menuWasOpenOnPress || batchBackgroundMusicMenu.visible)
                                    batchBackgroundMusicMenu.close()
                                else
                                    batchBackgroundMusicMenu.open()
                            }

                            Menu {
                                id: batchBackgroundMusicMenu

                                width: 220
                                y: batchBackgroundMusicButton.height + Theme.space4
                                padding: 6
                                closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside

                                background: Rectangle {
                                    color: Theme.surfaceElevated
                                    radius: Theme.radius
                                    border.width: 1
                                    border.color: Theme.outlineStrong
                                }

                                AppMenuItem {
                                    text: I18n.t("From file")
                                    iconGlyph: "\uE8B7"
                                    onTriggered: {
                                        const path = AppController.chooseBatchBackgroundMusic()
                                        if (path.length > 0)
                                            root.draftBackgroundMusicPath = path
                                    }
                                }

                                AppMenuItem {
                                    text: I18n.t("From link")
                                    iconGlyph: "\uE71B"
                                    onTriggered: batchBackgroundMusicLinkDialog.open()
                                }
                            }
                        }

                        IconButton {
                            visible: root.draftBackgroundMusicPath.length > 0
                            glyph: "\uE74D"
                            toolTipText: I18n.t("Remove background music")
                            onClicked: {
                                root.draftBackgroundMusicPath = ""
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

                        Text {
                            Layout.preferredWidth: 112
                            text: I18n.t("Watermark")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            font.weight: Font.Medium
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.draftWatermarkText.length > 0
                                ? root.draftWatermarkText : I18n.t("No watermark")
                            color: root.draftWatermarkText.length > 0 ? Theme.text : Theme.textMuted
                            font.pixelSize: Theme.caption
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }

                        AppButton {
                            text: root.draftWatermarkText.length > 0
                                ? I18n.t("Edit watermark") : I18n.t("Add watermark")
                            compact: true
                            onClicked: batchWatermarkDialog.openWithText(root.draftWatermarkText)
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

            }
        }

    }

    WatermarkDialog {
        id: batchWatermarkDialog
        onWatermarkAccepted: function(text) {
            root.draftWatermarkText = text
        }
    }

    BatchAudioMixDialog {
        id: batchAudioMixDialog

        onAudioLevelsEdited: function(originalVolume, ttsVolume, backgroundMusicVolume) {
            root.draftOriginalVolume = originalVolume
            root.draftTtsVolume = ttsVolume
            root.draftBackgroundMusicVolume = backgroundMusicVolume
        }
    }

    BackgroundMusicLinkDialog {
        id: batchBackgroundMusicLinkDialog
        batchMode: true
        onBatchMusicReady: function(path) {
            root.draftBackgroundMusicPath = path
        }
    }

    SubtitlePreviewDialog {
        id: batchSubtitlePreviewDialog

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
