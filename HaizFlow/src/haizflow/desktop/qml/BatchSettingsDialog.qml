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
    property string draftTtsVoice: ""
    property bool draftEnableAudioSeparation: false
    property int draftOriginalVolume: 60
    property int draftBackgroundMusicVolume: 30
    property int draftTtsVolume: 100
    property string draftWatermarkText: ""
    property string draftBackgroundMusicPath: ""
    property var settingOverrides: []
    readonly property var draftVoiceOptions: AppController.voiceOptionsForLanguage(draftTargetLanguage)
    readonly property int draftTtsVoiceIndex: {
        for (let index = 0; index < draftVoiceOptions.length; ++index) {
            if (draftVoiceOptions[index].voice === draftTtsVoice)
                return index
        }
        return 0
    }

    function normalizedDraftVoice(languageCode, preferredVoice) {
        const options = AppController.voiceOptionsForLanguage(languageCode)
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
        draftTtsVoice = normalizedDraftVoice(draftTargetLanguage, settings.ttsVoice || "")
        draftEnableAudioSeparation = Boolean(settings.enableAudioSeparation)
        draftOriginalVolume = Number(settings.originalVolume !== undefined ? settings.originalVolume : 60)
        draftBackgroundMusicVolume = Number(settings.backgroundMusicVolume !== undefined ? settings.backgroundMusicVolume : 30)
        draftTtsVolume = Number(settings.ttsVolume !== undefined ? settings.ttsVolume : 100)
        draftWatermarkText = settings.watermarkText || ""
        draftBackgroundMusicPath = settings.backgroundMusicPath || ""
        refreshSettingOverrides()
    }

    function hasDraftChanges() {
        return draftWorkflowMode !== (baselineSettings.workflowMode || "A")
            || draftTargetLanguage !== (baselineSettings.targetLanguage || "vi")
            || draftTtsVoice !== (baselineSettings.ttsVoice || "")
            || draftEnableAudioSeparation !== Boolean(baselineSettings.enableAudioSeparation)
            || draftOriginalVolume !== Number(baselineSettings.originalVolume !== undefined ? baselineSettings.originalVolume : 60)
            || draftBackgroundMusicVolume !== Number(baselineSettings.backgroundMusicVolume !== undefined ? baselineSettings.backgroundMusicVolume : 30)
            || draftTtsVolume !== Number(baselineSettings.ttsVolume !== undefined ? baselineSettings.ttsVolume : 100)
            || draftWatermarkText !== (baselineSettings.watermarkText || "")
            || draftBackgroundMusicPath !== (baselineSettings.backgroundMusicPath || "")
    }

    function saveDraft() {
        if (!hasDraftChanges() || AppController.batchCount <= 0)
            return
        if (AppController.applyBatchSettingsDraft(
                draftWorkflowMode,
                draftTargetLanguage,
                draftTtsVoice,
                draftEnableAudioSeparation,
                draftOriginalVolume,
                draftBackgroundMusicVolume,
                draftTtsVolume,
                draftWatermarkText,
                draftBackgroundMusicPath
            )) {
            baselineSettings = {
                "workflowMode": draftWorkflowMode,
                "targetLanguage": draftTargetLanguage,
                "ttsVoice": draftTtsVoice,
                "enableAudioSeparation": draftEnableAudioSeparation,
                "originalVolume": draftOriginalVolume,
                "backgroundMusicVolume": draftBackgroundMusicVolume,
                "ttsVolume": draftTtsVolume,
                "watermarkText": draftWatermarkText,
                "backgroundMusicPath": draftBackgroundMusicPath
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

                GridLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.space24
                    Layout.rightMargin: Theme.space24
                    Layout.topMargin: Theme.space20
                    columns: 2
                    columnSpacing: Theme.space24
                    rowSpacing: Theme.space16

                    Text {
                        Layout.columnSpan: 2
                        text: I18n.t("Dubbing and audio")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    Text {
                        text: I18n.t("Workflow")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    SegmentedControl {
                        Layout.fillWidth: true
                        currentValue: root.draftWorkflowMode
                        options: [
                            { "label": I18n.t("Full auto"), "value": "A" },
                            { "label": I18n.t("Review then dub"), "value": "review" }
                        ]
                        onActivated: function(value) {
                            root.draftWorkflowMode = value
                        }
                    }

                    Text {
                        text: I18n.t("Translate to")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    SearchableLanguageCombo {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        options: AppController.targetLanguageOptions
                        selectedCode: root.draftTargetLanguage
                        onSelected: function(code) {
                            root.draftTargetLanguage = code
                            root.draftTtsVoice = root.normalizedDraftVoice(code, root.draftTtsVoice)
                        }
                    }

                    Text {
                        text: I18n.t("Voice")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    AppComboBox {
                        Layout.fillWidth: true
                        textRole: "label"
                        valueRole: "voice"
                        model: root.draftVoiceOptions
                        currentIndex: root.draftTtsVoiceIndex
                        onActivated: {
                            root.draftTtsVoice = currentValue
                        }
                    }

                    Rectangle {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.divider
                    }

                    Text {
                        text: I18n.t("Audio source")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    SegmentedControl {
                        Layout.fillWidth: true
                        currentValue: root.draftEnableAudioSeparation ? "separated" : "original"
                        options: [
                            { "label": I18n.t("Keep original audio"), "value": "original" },
                            { "label": I18n.t("Separate vocals"), "value": "separated" }
                        ]
                        onActivated: function(value) {
                            root.draftEnableAudioSeparation = value === "separated"
                        }
                    }

                    Text {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        visible: AppController.cpuOnly && root.draftEnableAudioSeparation
                        text: I18n.t("Audio separation is slower in CPU mode")
                        color: Theme.warning
                        font.pixelSize: Theme.caption
                        wrapMode: Text.WordWrap
                        textFormat: Text.PlainText
                    }

                    AppButton {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        text: I18n.t("Adjust audio levels")
                        tone: "secondary"
                        compact: true
                        onClicked: {
                            batchAudioMixDialog.audioSeparationEnabled = root.draftEnableAudioSeparation
                            batchAudioMixDialog.originalVolume = root.draftOriginalVolume
                            batchAudioMixDialog.ttsVolume = root.draftTtsVolume
                            batchAudioMixDialog.backgroundMusicVolume = root.draftBackgroundMusicVolume
                            batchAudioMixDialog.targetLanguage = root.draftTargetLanguage
                            batchAudioMixDialog.ttsVoice = root.draftTtsVoice
                            batchAudioMixDialog.backgroundMusicPath = root.draftBackgroundMusicPath
                            batchAudioMixDialog.open()
                        }
                    }

                    Text {
                        text: I18n.t("Background music")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

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
                            text: root.draftBackgroundMusicPath.length > 0
                                ? I18n.t("Change music") : I18n.t("Add music")
                            compact: true
                            onClicked: {
                                const path = AppController.chooseBatchBackgroundMusic()
                                if (path.length > 0) {
                                    root.draftBackgroundMusicPath = path
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

                    Text {
                        text: I18n.t("Watermark")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

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
}
