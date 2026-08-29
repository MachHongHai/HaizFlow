pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

InspectorPanel {
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
        qsTr("Dịch"), qsTr("Hình ảnh"), qsTr("Giọng đọc"), qsTr("Âm thanh")
    ]

    signal subtitleSelected(int index)
    signal subtitleTextCommitted(int index, string text)

    title: toolTitles[currentStage]

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
            return toolComplete ? qsTr("Dịch lại") : qsTr("Dịch video")
        return toolComplete ? qsTr("Tạo lại giọng đọc") : qsTr("Tạo giọng đọc")
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
                    text: qsTr("Nhận dạng giọng nói")
                    helpText: qsTr("Turbo cho chất lượng cao hơn trên GPU. Small dùng ít bộ nhớ hơn và hỗ trợ cả CPU.")
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
                    text: qsTr("Dịch sang")
                    helpText: qsTr("Ngôn ngữ đã chọn được dùng cho cả phụ đề dịch và giọng đọc.")
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
                    text: qsTr("Âm thanh nhận diện")
                    helpText: qsTr("Tách giọng trước khi nhận diện nếu lời nói bị lẫn với nhạc hoặc hiệu ứng.")
                }
                SegmentedControl {
                    Layout.fillWidth: true
                    enabled: root.editable
                    currentValue: AppController.enableAudioSeparation ? "separated" : "original"
                    options: [
                        { "label": qsTr("Nguyên bản"), "value": "original" },
                        { "label": qsTr("Tách giọng"), "value": "separated" }
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
                    text: qsTr("Phụ đề gốc")
                    helpText: qsTr("Che phụ đề có sẵn hoặc giữ nguyên hình ảnh nguồn.")
                }
                SegmentedControl {
                    Layout.fillWidth: true
                    enabled: root.editable && root.subtitleSegments.length > 0
                    currentValue: AppController.removeOriginalSubtitles ? "remove" : "keep"
                    options: [
                        { "label": qsTr("Che"), "value": "remove" },
                        { "label": qsTr("Giữ nguyên"), "value": "keep" }
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
                        { "label": qsTr("Làm mờ"), "value": "blur" },
                        { "label": qsTr("Vá nền lân cận"), "value": "patch" }
                    ]
                    onActivated: function(value) {
                        AppController.originalSubtitleRemovalMode = value
                        root.scheduleSave()
                    }
                }

                AppButton {
                    Layout.fillWidth: true
                    text: qsTr("Kích thước và vị trí phụ đề")
                    iconGlyph: "\uE70F"
                    tone: "secondary"
                    compact: true
                    enabled: root.editable && root.subtitleSegments.length > 0
                    onClicked: subtitlePreviewDialogLoader.invoke("openWithLayout", [
                        AppController.subtitleFontSize,
                        AppController.subtitlePositionXPercent,
                        AppController.subtitlePositionYPercent,
                        AppController.subtitleBoxWidthPercent,
                        AppController.subtitleBoxHeightPercent])
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
                            : qsTr("Phụ đề")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }
                    IconButton {
                        glyph: "\uE72B"
                        toolTipText: qsTr("Phụ đề trước")
                        enabled: root.selectedSubtitleIndex > 0
                        onClicked: root.subtitleSelected(root.selectedSubtitleIndex - 1)
                    }
                    IconButton {
                        glyph: "\uE72A"
                        toolTipText: qsTr("Phụ đề sau")
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
                    placeholderText: qsTr("Chọn một phụ đề trên timeline")
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
                    text: qsTr("Watermark")
                    helpText: qsTr("Watermark chữ nhỏ được hiển thị trong bản xem trước và video xuất.")
                }
                AppButton {
                    Layout.fillWidth: true
                    text: AppController.watermarkText.length > 0
                        ? AppController.watermarkText : qsTr("Đặt watermark")
                    iconGlyph: "\uE70F"
                    tone: "secondary"
                    compact: true
                    enabled: root.editable
                    onClicked: watermarkDialogLoader.invoke("openWithText", [AppController.watermarkText])
                }
            }

            ColumnLayout {
                spacing: Theme.space8

                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Công cụ giọng đọc")
                    helpText: qsTr("OmniVoice chạy cục bộ. Edge TTS cần kết nối Internet ổn định.")
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
                    text: qsTr("Giọng đọc")
                    helpText: qsTr("Chọn giọng có sẵn hoặc mẫu giọng nhân bản mà bạn được phép sử dụng.")
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
                        ? qsTr("Giọng đã nhân bản") : qsTr("Nhân bản giọng")
                    iconGlyph: "\uE77B"
                    tone: AppController.ttsVoice === "omnivoice:clone" ? "primary" : "secondary"
                    compact: true
                    enabled: root.editable
                    onClicked: voiceCloneDialogLoader.invoke("openForSelectedVideo", [])
                }
                AppCheckBox {
                    Layout.fillWidth: true
                    enabled: root.editable && AppController.ttsProvider === "omnivoice"
                    text: qsTr("Nhận diện nhiều người nói")
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
                    text: qsTr("Điều chỉnh âm lượng")
                    iconGlyph: "\uE767"
                    tone: "secondary"
                    compact: true
                    enabled: root.editable
                    onClicked: audioMixDialogLoader.invoke("open", [])
                }

                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Nhạc nền")
                    helpText: qsTr("Đổi nhạc hoặc âm lượng chỉ cập nhật bản phối xem trước.")
                }
                Text {
                    Layout.fillWidth: true
                    text: AppController.backgroundMusicPath || qsTr("Chưa có nhạc nền")
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
                        text: qsTr("Chọn tệp")
                        tone: "secondary"
                        compact: true
                        enabled: root.editable
                        onClicked: AppController.browseBackgroundMusic()
                    }
                    AppButton {
                        Layout.fillWidth: true
                        text: qsTr("Từ liên kết")
                        tone: "secondary"
                        compact: true
                        enabled: root.editable
                        onClicked: backgroundMusicLinkDialogLoader.invoke("open", [])
                    }
                    IconButton {
                        visible: AppController.backgroundMusicPath.length > 0
                        glyph: "\uE74D"
                        toolTipText: qsTr("Xóa danh sách")
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
            text: root.taskProcessing && root.taskBelongsToTool ? qsTr("Tạm dừng")
                : root.taskQueued && root.taskBelongsToTool ? qsTr("Đang chờ xử lý")
                : root.taskPaused && root.taskBelongsToTool ? qsTr("Tiếp tục") : root.runLabel()
            iconGlyph: root.taskProcessing && root.taskBelongsToTool ? "\uE769"
                : root.taskQueued && root.taskBelongsToTool ? "\uE895" : "\uE768"
            tone: root.taskProcessing && root.taskBelongsToTool ? "danger" : "primary"
            enabled: root.taskProcessing && root.taskBelongsToTool
                || root.taskPaused && root.taskBelongsToTool
                || (root.editable && !root.taskQueued && root.prerequisiteReady)
            toolTipText: root.prerequisiteReady ? "" : qsTr("Hãy dịch video trước")
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
                    root.scheduleSave()
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
                    root.scheduleSave()
                }
            }
        }
    }
}
