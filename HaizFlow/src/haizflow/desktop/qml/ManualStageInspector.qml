pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

InspectorPanel {
    id: root

    property int currentStage: 0
    property var toolModel: []
    property string pendingSettingsVideoId: ""
    property var subtitleSegments: []
    property int selectedSubtitleIndex: -1
    readonly property var toolIds: [
        "source", "translation", "subtitle", "image", "voice", "audio", "export"
    ]
    readonly property string toolId: toolIds[Math.max(0, Math.min(currentStage, toolIds.length - 1))]
    readonly property var toolState: currentStage >= 0 && currentStage < toolModel.length
        ? toolModel[currentStage] : ({
            "label": "", "state": "blocked", "canRun": false,
            "blockedReason": "", "cacheHit": false, "progress": 0
        })
    readonly property bool editable: AppController.canEditSelectedVideo && AppController.hasSelectedVideo
    readonly property bool taskQueued: AppController.isSelectedVideoQueued
    readonly property bool taskProcessing: AppController.isSelectedVideoProcessing
    readonly property bool taskPaused: AppController.selectedStatus === "paused" && !taskQueued
    readonly property bool taskBelongsToTool: AppController.manualTargetTool === toolId
        || (toolId === "source" && AppController.manualTargetTool === "separation")
    readonly property var selectedSubtitle: selectedSubtitleIndex >= 0
        && selectedSubtitleIndex < subtitleSegments.length
        ? subtitleSegments[selectedSubtitleIndex] : null

    signal subtitleSelected(int index)
    signal subtitleTextCommitted(int index, string text)
    signal toolRequested(int index)
    signal sourceLinkRequested()
    signal settingsCommitted()

    title: String(toolState.label || "")
    onCurrentStageChanged: inspectorScroll.contentY = 0

    function scheduleSave() {
        if (!AppController.hasSelectedVideo || AppController.isSelectedVideoQueued)
            return;
        pendingSettingsVideoId = AppController.selectedVideoId;
        AppController.captureVideoSettingsDraft(pendingSettingsVideoId);
        settingsSaveTimer.restart();
    }

    function saveNow() {
        settingsSaveTimer.stop();
        if (AppController.hasSelectedVideo) {
            AppController.captureVideoSettingsDraft(AppController.selectedVideoId);
            AppController.persistVideoSettingsFor(AppController.selectedVideoId);
            settingsCommitted();
        }
        pendingSettingsVideoId = "";
    }

    function stateLabel(state) {
        if (state === "cached") return qsTr("Đã lưu");
        if (state === "ready") return qsTr("Sẵn sàng");
        if (state === "running") return qsTr("Đang chạy");
        if (state === "queued") return qsTr("Đang chờ");
        if (state === "paused") return qsTr("Đã tạm dừng");
        if (state === "error") return qsTr("Có lỗi");
        return qsTr("Thiếu dữ liệu");
    }

    function runLabel() {
        if (toolId === "translation") return toolState.cacheHit ? qsTr("Tạo lại phụ đề") : qsTr("Tạo phụ đề");
        if (toolId === "voice") return toolState.cacheHit ? qsTr("Tạo lại giọng") : qsTr("Tạo giọng");
        if (toolId === "audio") return toolState.cacheHit ? qsTr("Tạo lại bản phối") : qsTr("Tạo bản phối");
        if (toolId === "export") return toolState.cacheHit ? qsTr("Xuất lại video") : qsTr("Xuất video");
        return qsTr("Chạy công cụ");
    }

    function hasCurrentCache(requestedToolId) {
        for (let index = 0; index < root.toolModel.length; ++index) {
            const item = root.toolModel[index]
            if (String(item.toolId || "") === requestedToolId)
                return Boolean(item.cacheHit)
        }
        return false
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Rectangle {
            Layout.preferredWidth: 7
            Layout.preferredHeight: 7
            radius: 4
            color: root.toolState.state === "error" ? Theme.danger
                : root.toolState.state === "running" ? Theme.warning
                : root.toolState.cacheHit ? Theme.success
                : root.toolState.canRun ? Theme.interactive : Theme.textDisabled
        }
        Text {
            Layout.fillWidth: true
            text: root.stateLabel(String(root.toolState.state || "blocked"))
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
        }
    }

    Flickable {
        id: inspectorScroll
        objectName: "manualInspectorScroll"

        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 0
        contentWidth: width
        contentHeight: stageLoader.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Loader {
            id: stageLoader
            objectName: "manualInspectorStageLoader"
            width: inspectorScroll.width
            sourceComponent: [
                sourceInspectorComponent,
                translationInspectorComponent,
                subtitleInspectorComponent,
                imageInspectorComponent,
                voiceInspectorComponent,
                audioInspectorComponent,
                exportInspectorComponent
            ][root.currentStage]
        }

        Component {
            id: sourceInspectorComponent
            ColumnLayout {
                spacing: Theme.space8

                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Video nguồn")
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4
                    StudioButton {
                        Layout.fillWidth: true
                        text: qsTr("Từ tệp")
                        iconName: "folder"
                        variant: "secondary"
                        enabled: root.editable && !root.taskQueued
                        onClicked: AppController.browseVideo()
                    }
                    StudioButton {
                        Layout.fillWidth: true
                        text: qsTr("Từ liên kết")
                        iconName: "link"
                        variant: "secondary"
                        enabled: root.editable && !root.taskQueued
                        onClicked: root.sourceLinkRequested()
                    }
                }
                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Âm thanh")
                }
                SegmentedControl {
                    Layout.fillWidth: true
                    enabled: root.editable && !root.taskQueued
                    currentValue: AppController.enableAudioSeparation ? "separated" : "original"
                    options: [
                        { "label": qsTr("Giữ âm thanh gốc"), "value": "original" },
                        { "label": qsTr("Tách giọng"), "value": "separated" }
                    ]
                    onActivated: function(value) {
                        AppController.enableAudioSeparation = value === "separated";
                        root.scheduleSave();
                    }
                }
                StudioButton {
                    Layout.fillWidth: true
                    visible: AppController.enableAudioSeparation
                    text: root.toolState.cacheHit
                        ? qsTr("Tách lại giọng") : qsTr("Chạy tách giọng")
                    iconName: "volume"
                    variant: "primary"
                    enabled: root.editable && !root.taskQueued && root.toolState.canRun
                    onClicked: {
                        root.saveNow();
                        AppController.runManualTool("separation");
                    }
                }
            }
        }

        Component {
            id: translationInspectorComponent
            ColumnLayout {
                spacing: Theme.space8
                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Model nhận dạng")
                    helpText: qsTr("Turbo cần GPU. Small dùng ít bộ nhớ hơn và hỗ trợ CPU.")
                }
                AppComboBox {
                    Layout.fillWidth: true
                    enabled: root.editable
                    textRole: "label"
                    valueRole: "value"
                    model: AppController.speechRecognitionModelOptions
                    currentIndex: AppController.speechRecognitionModelIndex
                    onActivated: {
                        AppController.speechRecognitionModel = currentValue;
                        root.scheduleSave();
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: AppController.enableAudioSeparation
                        ? qsTr("Nguồn nhận dạng: track giọng đã tách")
                        : qsTr("Nguồn nhận dạng: âm thanh gốc")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                }
                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Dịch sang")
                }
                SearchableLanguageCombo {
                    Layout.fillWidth: true
                    enabled: root.editable
                    options: AppController.targetLanguageOptions
                    selectedCode: AppController.targetLanguage
                    onSelected: function(code) {
                        AppController.targetLanguage = code;
                        root.scheduleSave();
                    }
                }
            }
        }

        Component {
            id: subtitleInspectorComponent
            ColumnLayout {
                spacing: Theme.space8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4
                    Text {
                        Layout.fillWidth: true
                        text: root.selectedSubtitle
                            ? qsTr("Đoạn %1/%2").arg(root.selectedSubtitleIndex + 1).arg(root.subtitleSegments.length)
                            : qsTr("Chọn một đoạn trên timeline")
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
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
                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Nội dung")
                }
                TextArea {
                    id: subtitleTextEditor
                    Layout.fillWidth: true
                    Layout.preferredHeight: 104
                    enabled: root.editable && root.selectedSubtitle !== null
                    text: root.selectedSubtitle ? String(root.selectedSubtitle.text || "") : ""
                    placeholderText: qsTr("Chọn một phụ đề trên timeline")
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
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
                            root.subtitleTextCommitted(root.selectedSubtitleIndex, text);
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Kéo khung trên video để di chuyển. Kéo góc khung để đổi cỡ chữ.")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                }
            }
        }

        Component {
            id: imageInspectorComponent
            ColumnLayout {
                spacing: Theme.space8

                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Phụ đề gốc")
                }
                AppComboBox {
                    Layout.fillWidth: true
                    enabled: root.editable
                    textRole: "label"
                    valueRole: "value"
                    model: [
                        { "label": qsTr("Giữ nguyên"), "value": "keep" },
                        { "label": qsTr("Che · Làm mờ"), "value": "blur" },
                        { "label": qsTr("Che · Vá nền"), "value": "patch" }
                    ]
                    currentIndex: !AppController.removeOriginalSubtitles ? 0
                        : AppController.originalSubtitleRemovalMode === "blur" ? 1 : 2
                    onActivated: function(index) {
                        const selected = model[index]
                        if (selected)
                            AppController.setManualSubtitleTreatment(String(selected.value || "keep"));
                    }
                }
                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Watermark")
                }
                StudioButton {
                    Layout.fillWidth: true
                    text: AppController.watermarkText.length > 0
                        ? AppController.watermarkText : qsTr("Đặt watermark")
                    iconName: "edit"
                    variant: "secondary"
                    enabled: root.editable
                    onClicked: watermarkDialogLoader.invoke("openWithText", [AppController.watermarkText])
                }
            }
        }

        Component {
            id: voiceInspectorComponent
            ColumnLayout {
                spacing: Theme.space8

                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Công cụ giọng đọc")
                }
                AppComboBox {
                    Layout.fillWidth: true
                    enabled: root.editable
                    textRole: "label"
                    valueRole: "provider"
                    model: AppController.ttsProviderOptions
                    currentIndex: AppController.ttsProviderIndex
                    onActivated: {
                        AppController.ttsProvider = currentValue;
                        root.scheduleSave();
                    }
                }
                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Giọng đọc")
                }
                VoicePicker {
                    Layout.fillWidth: true
                    enabled: root.editable
                    model: AppController.ttsVoiceOptions
                    currentValue: AppController.ttsVoice
                    allowVoiceClone: false
                    previewEnabled: false
                    onSelected: function(voice) {
                        AppController.ttsVoice = voice;
                        root.scheduleSave();
                    }
                }
                StudioButton {
                    Layout.fillWidth: true
                    visible: AppController.ttsProvider === "omnivoice"
                    text: AppController.ttsVoice === "omnivoice:clone"
                        ? qsTr("Giọng đã nhân bản") : qsTr("Nhân bản giọng")
                    iconName: "volume"
                    variant: AppController.ttsVoice === "omnivoice:clone" ? "primary" : "secondary"
                    enabled: root.editable
                    onClicked: voiceCloneDialogLoader.invoke("openForSelectedVideo", [])
                }
                AppCheckBox {
                    Layout.fillWidth: true
                    visible: AppController.ttsProvider === "omnivoice"
                    enabled: root.editable && AppController.ttsProvider === "omnivoice"
                    text: qsTr("Nhận diện nhiều người nói")
                    checked: AppController.speakerMode === "multiple"
                    onToggled: {
                        AppController.speakerMode = checked ? "multiple" : "single";
                        root.scheduleSave();
                    }
                }
            }
        }

        Component {
            id: audioInspectorComponent
            ColumnLayout {
                spacing: Theme.space8

                AudioLevelControl {
                    Layout.fillWidth: true
                    label: AppController.enableAudioSeparation
                        ? qsTr("Âm nền") : qsTr("Âm thanh gốc")
                    volume: AppController.originalVolume
                    adjustable: root.editable
                    onVolumeEdited: function(value) {
                        AppController.originalVolume = value;
                        root.scheduleSave();
                    }
                }
                AudioLevelControl {
                    Layout.fillWidth: true
                    label: qsTr("Giọng đọc")
                    volume: AppController.ttsVolume
                    adjustable: root.editable && root.hasCurrentCache("voice")
                    disabledHint: qsTr("Chưa tạo giọng đọc")
                    onVolumeEdited: function(value) {
                        AppController.ttsVolume = value;
                        root.scheduleSave();
                    }
                }
                AudioLevelControl {
                    Layout.fillWidth: true
                    label: qsTr("Nhạc nền")
                    volume: AppController.backgroundMusicVolume
                    adjustable: root.editable && AppController.backgroundMusicPath.length > 0
                    disabledHint: qsTr("Chưa chọn nhạc nền")
                    onVolumeEdited: function(value) {
                        AppController.backgroundMusicVolume = value;
                        root.scheduleSave();
                    }
                }
                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Nhạc nền")
                }
                Text {
                    Layout.fillWidth: true
                    text: AppController.backgroundMusicPath || qsTr("Chưa có nhạc nền")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    textFormat: Text.PlainText
                    elide: Text.ElideMiddle
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4
                    StudioButton {
                        Layout.fillWidth: true
                        text: qsTr("Chọn tệp")
                        variant: "secondary"
                        enabled: root.editable
                        onClicked: AppController.browseBackgroundMusic()
                    }
                    StudioButton {
                        Layout.fillWidth: true
                        text: qsTr("Từ liên kết")
                        variant: "secondary"
                        enabled: root.editable
                        onClicked: backgroundMusicLinkDialogLoader.invoke("open", [])
                    }
                    IconButton {
                        visible: AppController.backgroundMusicPath.length > 0
                        glyph: "\uE74D"
                        toolTipText: qsTr("Xóa nhạc nền")
                        enabled: root.editable
                        onClicked: AppController.clearBackgroundMusic()
                    }
                }
            }
        }

        Component {
            id: exportInspectorComponent
            ColumnLayout {
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Xuất trạng thái hiện tại. Chỉ các lớp đã bật và có dữ liệu mới xuất hiện trong video.")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                }
                StudioButton {
                    Layout.fillWidth: true
                    text: qsTr("Dọn dữ liệu tạm")
                    iconName: "delete"
                    variant: "secondary"
                    enabled: !root.taskQueued
                    onClicked: AppController.clearManualCache("project")
                }
            }
        }

        ScrollBar.vertical: ScrollBar {
            policy: inspectorScroll.contentHeight > inspectorScroll.height
                ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }
    }

    ColumnLayout {
        id: actionFooter
        objectName: "manualInspectorActionFooter"

        Layout.fillWidth: true
        Layout.fillHeight: false
        Layout.preferredHeight: implicitHeight
        Layout.maximumHeight: implicitHeight
        visible: ["translation", "voice", "export"].indexOf(root.toolId) >= 0
        spacing: Theme.space8

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.taskQueued && root.taskBelongsToTool
            spacing: Theme.space4
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: I18n.progressDetail(AppController.selectedProgressDetail || AppController.selectedStep)
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
                Text {
                    text: qsTr("%1%").arg(AppController.selectedProgress)
                    color: Theme.interactive
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }
            AppProgressBar {
                Layout.fillWidth: true
                value: AppController.selectedProgress
            }
        }

        Text {
            Layout.fillWidth: true
            visible: !root.toolState.canRun && String(root.toolState.blockedReason || "").length > 0
            text: String(root.toolState.blockedReason || "")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
        }

        StudioButton {
            Layout.fillWidth: true
            visible: root.toolId !== "image"
                || (root.taskBelongsToTool && (root.taskQueued || root.taskProcessing || root.taskPaused))
            text: root.taskProcessing && root.taskBelongsToTool ? qsTr("Tạm dừng")
                : root.taskQueued && root.taskBelongsToTool ? qsTr("Đang chờ")
                : root.taskPaused && root.taskBelongsToTool ? qsTr("Tiếp tục") : root.runLabel()
            iconName: root.taskProcessing && root.taskBelongsToTool ? "pause" : "play"
            variant: root.taskProcessing && root.taskBelongsToTool ? "danger" : "primary"
            enabled: root.taskProcessing && root.taskBelongsToTool
                || root.taskPaused && root.taskBelongsToTool
                || (root.editable && !root.taskQueued && root.toolState.canRun)
            onClicked: {
                if (root.taskProcessing && root.taskBelongsToTool)
                    AppController.cancelManualTool(AppController.manualTargetTool);
                else if (root.taskPaused && root.taskBelongsToTool)
                    AppController.resumeSelectedVideo();
                else {
                    root.saveNow();
                    AppController.runManualTool(root.toolId);
                }
            }
        }
    }

    Timer {
        id: settingsSaveTimer
        interval: 220
        repeat: false
        onTriggered: {
            AppController.persistVideoSettingsFor(root.pendingSettingsVideoId);
            root.pendingSettingsVideoId = "";
            root.settingsCommitted();
        }
    }

    Connections {
        target: AppController
        function onSelectedVideoChanged() {
            if (settingsSaveTimer.running && root.pendingSettingsVideoId !== AppController.selectedVideoId) {
                settingsSaveTimer.stop();
                AppController.persistVideoSettingsFor(root.pendingSettingsVideoId);
                root.pendingSettingsVideoId = "";
            }
        }
    }

    LazyDialogLoader {
        id: backgroundMusicLinkDialogLoader
        parent: root
        sourceComponent: Component { BackgroundMusicLinkDialog { onClosed: backgroundMusicLinkDialogLoader.release() } }
    }
    LazyDialogLoader {
        id: voiceCloneDialogLoader
        parent: root
        sourceComponent: Component { VoiceCloneDialog { onClosed: voiceCloneDialogLoader.release() } }
    }
    LazyDialogLoader {
        id: watermarkDialogLoader
        parent: root
        sourceComponent: Component {
            WatermarkDialog {
                onClosed: watermarkDialogLoader.release()
                onWatermarkAccepted: function(text) {
                    AppController.watermarkText = text;
                    root.scheduleSave();
                }
            }
        }
    }
}
