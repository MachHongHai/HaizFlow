import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Panel {
    id: root

    title: I18n.t("Settings")
    subtitle: I18n.t("Language, voice and audio")
    tone: "violet"
    contentPadding: Theme.space12
    contentSpacing: Theme.space8
    headerSpacing: Theme.space12

    function scheduleVideoSettingsSave() {
        if (AppController.hasSelectedVideo && !AppController.isSelectedVideoProcessing)
            videoSettingsSaveTimer.restart()
    }

    Flickable {
        id: setupScroll

        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 0
        contentWidth: width
        contentHeight: settingsColumn.implicitHeight
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        ColumnLayout {
            id: settingsColumn

            width: setupScroll.width
            spacing: Theme.space8

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        Text {
            Layout.preferredWidth: 92
            text: I18n.t("Workflow")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            textFormat: Text.PlainText
        }

        SegmentedControl {
            Layout.fillWidth: true
            Layout.preferredHeight: 38
            enabled: AppController.canEditSelectedVideo
            currentValue: AppController.workflowMode
            options: [
                { "label": I18n.t("Full auto"), "value": "A" },
                { "label": I18n.t("Review then dub"), "value": "review" }
            ]
            onActivated: function(value) {
                AppController.workflowMode = value
                root.scheduleVideoSettingsSave()
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
            textFormat: Text.PlainText
        }

        SearchableLanguageCombo {
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            enabled: AppController.canEditSelectedVideo
            options: AppController.targetLanguageOptions
            selectedCode: AppController.targetLanguage
            onSelected: function(code) {
                AppController.targetLanguage = code
                root.scheduleVideoSettingsSave()
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
            textFormat: Text.PlainText
        }

        AppComboBox {
            Layout.fillWidth: true
            enabled: AppController.canEditSelectedVideo
            textRole: "label"
            valueRole: "voice"
            model: AppController.ttsVoiceOptions
            currentIndex: AppController.ttsVoiceIndex
            onActivated: {
                AppController.ttsVoice = currentValue
                root.scheduleVideoSettingsSave()
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space4

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            Text {
                Layout.preferredWidth: 92
                text: I18n.t("Original subtitles")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                font.weight: Font.Medium
                textFormat: Text.PlainText
            }

            SegmentedControl {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                enabled: AppController.canEditSelectedVideo
                currentValue: AppController.removeOriginalSubtitles ? "remove" : "keep"
                options: [
                    { "label": I18n.t("Cover original subtitles"), "value": "remove" },
                    { "label": I18n.t("Keep original video"), "value": "keep" }
                ]
                onActivated: function(value) {
                    AppController.removeOriginalSubtitles = value === "remove"
                    root.scheduleVideoSettingsSave()
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: AppController.removeOriginalSubtitles
            spacing: Theme.space12

            Text {
                Layout.preferredWidth: 92
                text: I18n.t("Removal method")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                font.weight: Font.Medium
                textFormat: Text.PlainText
            }

            SegmentedControl {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                enabled: AppController.canEditSelectedVideo
                currentValue: AppController.originalSubtitleRemovalMode
                options: [
                    { "label": I18n.t("Blur"), "value": "blur" },
                    { "label": I18n.t("Nearby patch"), "value": "patch" }
                ]
                onActivated: function(value) {
                    AppController.originalSubtitleRemovalMode = value
                    root.scheduleVideoSettingsSave()
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: AppController.removeOriginalSubtitles
                ? AppController.originalSubtitleRemovalMode === "patch"
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
            visible: !AppController.removeOriginalSubtitles
            text: I18n.t("Edit new subtitles")
            tone: "secondary"
            compact: true
            enabled: AppController.canEditSelectedVideo && AppController.videoPath.length > 0
            onClicked: subtitlePreviewDialog.openWithLayout(
                AppController.subtitleFontSize,
                AppController.subtitlePositionXPercent,
                AppController.subtitlePositionYPercent,
                AppController.subtitleBoxWidthPercent,
                AppController.subtitleBoxHeightPercent
            )
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        Layout.topMargin: Theme.space8
        Layout.bottomMargin: Theme.space4
        color: Theme.divider
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        Text {
            Layout.preferredWidth: 92
            text: I18n.t("Audio source")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            textFormat: Text.PlainText
        }

        SegmentedControl {
            Layout.fillWidth: true
            Layout.preferredHeight: 38
            enabled: AppController.canEditSelectedVideo
            currentValue: AppController.enableAudioSeparation ? "separated" : "original"
            options: [
                { "label": I18n.t("Keep original audio"), "value": "original" },
                { "label": I18n.t("Separate vocals"), "value": "separated" }
            ]
            onActivated: function(value) {
                AppController.enableAudioSeparation = value === "separated"
                root.scheduleVideoSettingsSave()
            }
        }

        AppButton {
            text: I18n.t("Adjust audio levels")
            tone: "secondary"
            compact: true
            enabled: AppController.canEditSelectedVideo
            onClicked: audioMixDialog.open()
        }
    }

    Text {
        Layout.fillWidth: true
        visible: AppController.cpuOnly && AppController.enableAudioSeparation
        text: I18n.t("Audio separation is slower in CPU mode")
        color: Theme.warning
        font.pixelSize: Theme.caption
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            Layout.preferredWidth: 92
            text: I18n.t("Background music")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }

        Text {
            Layout.fillWidth: true
            text: AppController.backgroundMusicPath.length > 0
                ? AppController.backgroundMusicPath : I18n.t("No background music")
            color: AppController.backgroundMusicPath.length > 0 ? Theme.text : Theme.textMuted
            font.pixelSize: Theme.caption
            elide: Text.ElideMiddle
            textFormat: Text.PlainText
        }

        AppButton {
            id: backgroundMusicButton

            property bool menuWasOpenOnPress: false

            text: AppController.backgroundMusicPath.length > 0
                ? I18n.t("Replace background music") : I18n.t("Choose background music")
            compact: true
            enabled: AppController.canEditSelectedVideo
            onPressed: menuWasOpenOnPress = backgroundMusicMenu.visible
            onClicked: {
                if (menuWasOpenOnPress || backgroundMusicMenu.visible)
                    backgroundMusicMenu.close()
                else
                    backgroundMusicMenu.open()
            }

            Menu {
                id: backgroundMusicMenu

                width: 220
                y: backgroundMusicButton.height + Theme.space4
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
                    onTriggered: AppController.browseBackgroundMusic()
                }

                AppMenuItem {
                    text: I18n.t("From link")
                    iconGlyph: "\uE71B"
                    onTriggered: backgroundMusicLinkDialog.open()
                }
            }
        }

        IconButton {
            visible: AppController.backgroundMusicPath.length > 0
            glyph: "\uE74D"
            toolTipText: I18n.t("Remove background music")
            enabled: AppController.canEditSelectedVideo
            onClicked: AppController.clearBackgroundMusic()
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            Layout.preferredWidth: 92
            text: I18n.t("Watermark")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }

        Text {
            Layout.fillWidth: true
            text: AppController.watermarkText.length > 0
                ? AppController.watermarkText : I18n.t("No watermark")
            color: AppController.watermarkText.length > 0 ? Theme.text : Theme.textMuted
            font.pixelSize: Theme.caption
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }

        AppButton {
            text: AppController.watermarkText.length > 0
                ? I18n.t("Edit watermark") : I18n.t("Add watermark")
            compact: true
            enabled: AppController.canEditSelectedVideo
            onClicked: watermarkDialog.openWithText(AppController.watermarkText)
        }
    }

        }

        ScrollBar.vertical: ScrollBar {
            policy: setupScroll.contentHeight > setupScroll.height
                ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }
    }

    AudioMixDialog {
        id: audioMixDialog
    }

    BackgroundMusicLinkDialog {
        id: backgroundMusicLinkDialog
    }

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
        onTriggered: AppController.persistSelectedVideoSettings()
    }
}
