import QtQuick
import QtQuick.Layouts
import "."

GridLayout {
    id: root

    property bool editable: true
    property bool cpuOnly: false
    property bool hasSource: false
    property bool showCloneAction: false
    property bool cloneActive: false
    property string speechRecognitionModel: "small"
    property var speechRecognitionOptions: []
    property int speechRecognitionIndex: 0
    property string targetLanguage: "vi"
    property var targetLanguageOptions: []
    property string ttsProvider: "omnivoice"
    property var ttsProviderOptions: []
    property int ttsProviderIndex: 0
    property string ttsVoice: ""
    property var ttsVoiceOptions: []
    property string speakerMode: "single"
    property bool removeOriginalSubtitles: true
    property string subtitleRemovalMode: "patch"
    property bool enableAudioSeparation: true
    property string backgroundMusicPath: ""
    property string watermarkText: ""

    signal speechRecognitionEdited(string value)
    signal targetLanguageEdited(string value)
    signal ttsProviderEdited(string value)
    signal ttsVoiceEdited(string value)
    signal cloneVoiceRequested()
    signal speakerModeEdited(string value)
    signal removeOriginalSubtitlesEdited(bool value)
    signal subtitleRemovalModeEdited(string value)
    signal subtitleLayoutRequested()
    signal audioSeparationEdited(bool value)
    signal audioMixRequested()
    signal backgroundMusicFileRequested()
    signal backgroundMusicLinkRequested()
    signal backgroundMusicClearRequested()
    signal watermarkRequested()

    columns: width >= 760 ? 2 : 1
    columnSpacing: Theme.space12
    rowSpacing: Theme.space12

    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: root.columns === 2
        Layout.alignment: Qt.AlignTop
        implicitHeight: voiceColumn.implicitHeight + Theme.space24
        color: Theme.surfaceElevated
        radius: Theme.radiusSmall
        border.width: 1
        border.color: Theme.outline

        ColumnLayout {
            id: voiceColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Theme.space12
            spacing: Theme.space8

            Text {
                text: I18n.t("Language and voice")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

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
                model: root.speechRecognitionOptions
                currentIndex: root.speechRecognitionIndex
                onActivated: root.speechRecognitionEdited(currentValue)
            }

            SettingLabel {
                Layout.fillWidth: true
                text: I18n.t("Translate to")
                helpText: I18n.t("The selected language is used for both translated subtitles and generated speech.")
            }
            SearchableLanguageCombo {
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                enabled: root.editable
                options: root.targetLanguageOptions
                selectedCode: root.targetLanguage
                onSelected: function(code) { root.targetLanguageEdited(code) }
            }

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
                model: root.ttsProviderOptions
                currentIndex: root.ttsProviderIndex
                onActivated: root.ttsProviderEdited(currentValue)
            }

            SettingLabel {
                Layout.fillWidth: true
                text: I18n.t("Voice")
                helpText: I18n.t("Choose a preset narrator or an authorised cloned voice sample.")
            }
            VoicePicker {
                Layout.fillWidth: true
                enabled: root.editable
                model: root.ttsVoiceOptions
                currentValue: root.ttsVoice
                allowVoiceClone: false
                onSelected: function(voice) { root.ttsVoiceEdited(voice) }
            }
            AppButton {
                Layout.fillWidth: true
                visible: root.showCloneAction
                text: root.cloneActive ? I18n.t("Cloned voice") : I18n.t("Clone voice")
                iconGlyph: "\uE77B"
                tone: root.cloneActive ? "primary" : "secondary"
                compact: true
                enabled: root.editable
                onClicked: root.cloneVoiceRequested()
            }

            RowLayout {
                Layout.fillWidth: true
                AppCheckBox {
                    Layout.fillWidth: true
                    enabled: root.editable && root.ttsProvider === "omnivoice"
                    text: I18n.t("Detect multiple speakers")
                    checked: root.speakerMode === "multiple"
                    onToggled: root.speakerModeEdited(checked ? "multiple" : "single")
                }
                SettingLabel {
                    labelVisible: false
                    text: I18n.t("Detect multiple speakers")
                    helpText: I18n.t("Enable this only when the source contains multiple speakers. Each detected speaker receives a separate voice identity.")
                }
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: root.columns === 2
        Layout.alignment: Qt.AlignTop
        implicitHeight: mediaColumn.implicitHeight + Theme.space24
        color: Theme.surfaceElevated
        radius: Theme.radiusSmall
        border.width: 1
        border.color: Theme.outline

        ColumnLayout {
            id: mediaColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Theme.space12
            spacing: Theme.space8

            Text {
                text: I18n.t("Picture and audio")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            SettingLabel {
                Layout.fillWidth: true
                text: I18n.t("Original subtitles")
                helpText: I18n.t("Cover burned-in source subtitles or keep the original picture unchanged.")
            }
            SegmentedControl {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                enabled: root.editable
                currentValue: root.removeOriginalSubtitles ? "remove" : "keep"
                options: [
                    { "label": I18n.t("Cover original subtitles"), "value": "remove" },
                    { "label": I18n.t("Keep original video"), "value": "keep" }
                ]
                onActivated: function(value) { root.removeOriginalSubtitlesEdited(value === "remove") }
            }

            SettingLabel {
                Layout.fillWidth: true
                visible: root.removeOriginalSubtitles
                text: I18n.t("Removal method")
                helpText: I18n.t("Blur softens detected text. Nearby patch fills it with clean pixels from the surrounding image.")
            }
            SegmentedControl {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                visible: root.removeOriginalSubtitles
                enabled: root.editable
                currentValue: root.subtitleRemovalMode
                options: [
                    { "label": I18n.t("Blur"), "value": "blur" },
                    { "label": I18n.t("Nearby patch"), "value": "patch" }
                ]
                onActivated: function(value) { root.subtitleRemovalModeEdited(value) }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: root.removeOriginalSubtitles
                        ? root.subtitleRemovalMode === "patch"
                            ? I18n.t("Use nearby clean pixels to cover burned-in text")
                            : I18n.t("Detect and blur burned-in text")
                        : I18n.t("Keep the source picture unchanged")
                    color: Theme.textMuted
                    font.pixelSize: Theme.label
                    wrapMode: Text.WordWrap
                }
                AppButton {
                    visible: !root.removeOriginalSubtitles
                    text: I18n.t("Edit new subtitles")
                    compact: true
                    tone: "secondary"
                    enabled: root.editable && root.hasSource
                    onClicked: root.subtitleLayoutRequested()
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }

            SettingLabel {
                Layout.fillWidth: true
                text: I18n.t("Audio source")
                helpText: I18n.t("Keep source audio or separate vocals from background sound before mixing.")
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                SegmentedControl {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    enabled: root.editable
                    currentValue: root.enableAudioSeparation ? "separated" : "original"
                    options: [
                        { "label": I18n.t("Keep original audio"), "value": "original" },
                        { "label": I18n.t("Separate vocals"), "value": "separated" }
                    ]
                    onActivated: function(value) { root.audioSeparationEdited(value === "separated") }
                }
                AppButton {
                    text: I18n.t("Levels")
                    tone: "secondary"
                    compact: true
                    enabled: root.editable
                    onClicked: root.audioMixRequested()
                }
            }
            Text {
                Layout.fillWidth: true
                visible: root.cpuOnly && root.enableAudioSeparation
                text: I18n.t("Audio separation is slower in CPU mode")
                color: Theme.warning
                font.pixelSize: Theme.label
                wrapMode: Text.WordWrap
            }

            SettingLabel {
                Layout.fillWidth: true
                text: I18n.t("Background music")
                helpText: I18n.t("Optional music is mixed after source-audio processing.")
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: root.backgroundMusicPath.length > 0 ? root.backgroundMusicPath : I18n.t("No background music")
                    color: root.backgroundMusicPath.length > 0 ? Theme.text : Theme.textMuted
                    font.pixelSize: Theme.label
                    elide: Text.ElideMiddle
                }
                AppButton { text: I18n.t("File"); compact: true; enabled: root.editable; onClicked: root.backgroundMusicFileRequested() }
                AppButton { text: I18n.t("Link"); compact: true; enabled: root.editable; onClicked: root.backgroundMusicLinkRequested() }
                IconButton {
                    visible: root.backgroundMusicPath.length > 0
                    glyph: "\uE74D"
                    toolTipText: I18n.t("Remove background music")
                    enabled: root.editable
                    onClicked: root.backgroundMusicClearRequested()
                }
            }

            SettingLabel {
                Layout.fillWidth: true
                text: I18n.t("Watermark")
                helpText: I18n.t("Add subtle moving text to the exported video.")
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: root.watermarkText.length > 0 ? root.watermarkText : I18n.t("No watermark")
                    color: root.watermarkText.length > 0 ? Theme.text : Theme.textMuted
                    font.pixelSize: Theme.label
                    elide: Text.ElideRight
                }
                AppButton {
                    text: root.watermarkText.length > 0 ? I18n.t("Edit") : I18n.t("Add")
                    compact: true
                    enabled: root.editable
                    onClicked: root.watermarkRequested()
                }
            }
        }
    }
}
