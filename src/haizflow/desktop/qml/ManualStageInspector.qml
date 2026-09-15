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
    property var subtitleDrafts: ({})
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
    readonly property bool hasPublishedVoice: Boolean(toolState.hasPublishedArtifact)
    readonly property var selectedSubtitle: selectedSubtitleIndex >= 0
        && selectedSubtitleIndex < subtitleSegments.length
        ? subtitleSegments[selectedSubtitleIndex] : null
    readonly property ManualSubtitleEditorDialog subtitleEditorDialog:
        subtitleEditorDialogLoader.item as ManualSubtitleEditorDialog

    signal subtitleSelected(int index)
    signal subtitleDialogSelectionRequested(int index)
    signal subtitleEditorClosed()
    signal sourceLinkRequested()
    signal settingsCommitted()
    signal exportRequested()

    function dismissTextEditor() {
        if (subtitleEditorDialogLoader.status === Loader.Ready
                && root.subtitleEditorDialog !== null)
            root.subtitleEditorDialog.closeEditor();
    }
    function focusTextEditor() {
        if (root.toolId === "subtitle" && root.selectedSubtitle)
            subtitleEditorDialogLoader.invoke("openForSelection", []);
    }

    function rememberSubtitleDraft(segmentId, text, revision) {
        if (!segmentId)
            return;
        // Draft keystrokes stay in this inspector and must not invalidate QML
        // bindings or the preview scene on every input-method composition.
        subtitleDrafts[segmentId] = { "text": text, "revision": revision };
    }

    function clearSubtitleDraft(segmentId) {
        if (!segmentId || subtitleDrafts[segmentId] === undefined)
            return;
        delete subtitleDrafts[segmentId];
    }

    title: String(toolState.label || "")
    onCurrentStageChanged: inspectorScroll.contentY = 0

    Component.onDestruction: {
        // Persist the latest control value when navigation tears down this
        // inspector before the short settings debounce has elapsed.
        if (settingsSaveTimer.running && pendingSettingsVideoId.length > 0) {
            settingsSaveTimer.stop();
            AppController.persistVideoSettingsFor(pendingSettingsVideoId);
            pendingSettingsVideoId = "";
        }
    }

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

    function openVoiceDialog(initialScope) {
        const segment = root.selectedSubtitle;
        const segmentId = segment ? String(segment.segment_id || "") : "";
        const segmentText = segment ? String(segment.text || "") : "";
        const configuration = AppController.manualVoiceConfiguration(segmentId);
        voiceDialogLoader.invoke("openForVoice", [
            Boolean(configuration.hasPublishedVoice),
            segmentId,
            segmentText,
            configuration,
            initialScope || "all"
        ]);
    }

    function hasCurrentCache(requestedToolId) {
        for (let index = 0; index < root.toolModel.length; ++index) {
            const item = root.toolModel[index]
            if (String(item.toolId || "") === requestedToolId)
                return Boolean(item.cacheHit)
        }
        return false
    }

    Text {
        Layout.fillWidth: true
        visible: ["running", "queued", "paused", "error"].indexOf(
            String(root.toolState.state || "")) >= 0
        text: root.stateLabel(String(root.toolState.state || "blocked"))
        color: root.toolState.state === "error" ? Theme.danger : Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        font.weight: root.toolState.state === "error" ? Font.DemiBold : Font.Normal
        textFormat: Text.PlainText
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
                id: subtitlePane
                spacing: Theme.space8
                height: Math.max(300, inspectorScroll.height)
                readonly property string selectedSegmentId: root.selectedSubtitle
                    ? String(root.selectedSubtitle.segment_id || "") : ""
                readonly property var selectedDraft: root.subtitleDrafts[selectedSegmentId] || null

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space8
                    Text {
                        Layout.fillWidth: true
                        text: root.selectedSubtitle
                            ? qsTr("%1 / %2").arg(root.selectedSubtitleIndex + 1).arg(root.subtitleSegments.length)
                            : qsTr("Chưa chọn phụ đề")
                        color: root.selectedSubtitle ? Theme.text : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.control
                        font.weight: root.selectedSubtitle ? Font.DemiBold : Font.Normal
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
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 176
                    color: Theme.input
                    radius: Theme.radiusSmall
                    border.width: 1
                    border.color: Theme.outline

                    Text {
                        id: subtitleSummary
                        anchors.fill: parent
                        anchors.margins: Theme.space12
                        text: subtitlePane.selectedDraft !== null
                            ? String(subtitlePane.selectedDraft.text || "")
                            : root.selectedSubtitle
                                ? String(root.selectedSubtitle.text || "")
                                : qsTr("Chọn phụ đề trên video hoặc timeline.")
                        color: root.selectedSubtitle ? Theme.text : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.body
                        lineHeight: 1.35
                        lineHeightMode: Text.ProportionalHeight
                        wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        maximumLineCount: 9
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space8

                    Item { Layout.fillWidth: true }

                    StudioButton {
                        text: qsTr("Mở rộng")
                        iconName: "fullscreen"
                        variant: "secondary"
                        enabled: root.selectedSubtitle !== null
                        onClicked: root.focusTextEditor()
                    }
                }
            }
        }

        Component {
            id: imageInspectorComponent
            ColumnLayout {
                id: imagePane
                spacing: Theme.space8
                readonly property string appliedTreatment: !AppController.removeOriginalSubtitles
                    ? "keep" : AppController.originalSubtitleRemovalMode
                property string draftTreatment: appliedTreatment

                onAppliedTreatmentChanged: draftTreatment = appliedTreatment

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
                    currentIndex: imagePane.draftTreatment === "keep" ? 0
                        : imagePane.draftTreatment === "blur" ? 1 : 2
                    onActivated: function(index) {
                        const selected = model[index]
                        if (selected)
                            imagePane.draftTreatment = String(selected.value || "keep");
                    }
                }
                StudioButton {
                    Layout.fillWidth: true
                    visible: imagePane.draftTreatment !== imagePane.appliedTreatment
                    text: qsTr("Áp dụng")
                    variant: "primary"
                    enabled: root.editable && !root.taskQueued
                        && imagePane.draftTreatment !== imagePane.appliedTreatment
                    onClicked: AppController.setManualSubtitleTreatment(imagePane.draftTreatment)
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

                Text {
                    Layout.fillWidth: true
                    visible: root.hasPublishedVoice && !root.hasCurrentCache("voice")
                    text: qsTr("Giọng đọc chưa khớp thiết lập hiện tại.")
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                }

                StudioButton {
                    Layout.fillWidth: true
                    visible: !root.hasPublishedVoice
                    text: qsTr("Tạo giọng")
                    iconName: "volume"
                    variant: "primary"
                    enabled: root.editable && !root.taskQueued && root.toolState.canRun
                    onClicked: root.openVoiceDialog("all")
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: root.hasPublishedVoice
                    spacing: Theme.space8

                    StudioButton {
                        Layout.fillWidth: true
                        text: qsTr("Đổi giọng")
                        iconName: "edit"
                        variant: "primary"
                        enabled: root.editable && !root.taskQueued
                        onClicked: root.openVoiceDialog("all")
                    }

                    StudioButton {
                        Layout.fillWidth: true
                        text: qsTr("Tạo lại")
                        iconName: "refresh"
                        variant: "secondary"
                        enabled: root.editable && !root.taskQueued
                        onClicked: root.openVoiceDialog("all")
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
                    label: AppController.enableAudioSeparation && root.hasCurrentCache("source")
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
            Item {}
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
        visible: (root.taskBelongsToTool && (root.taskQueued || root.taskPaused))
            || ["translation", "voice", "export"].indexOf(root.toolId) >= 0
        spacing: Theme.space8

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.taskQueued && root.taskBelongsToTool
            ManualToolProgress {
                Layout.fillWidth: true
                status: AppController.selectedStatus
                stepId: AppController.selectedStepId
                detail: I18n.progressDetail(
                    AppController.selectedProgressDetail || AppController.selectedStep
                )
                progress: AppController.selectedProgress
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
            visible: (root.taskBelongsToTool && (root.taskQueued || root.taskPaused))
                || ["translation", "export"].indexOf(root.toolId) >= 0
            text: root.taskProcessing && root.taskBelongsToTool ? qsTr("Tạm dừng")
                : root.taskQueued && root.taskBelongsToTool ? qsTr("Hủy tác vụ")
                : root.taskPaused && root.taskBelongsToTool ? qsTr("Tiếp tục") : root.runLabel()
            iconName: root.taskProcessing && root.taskBelongsToTool ? "pause"
                : root.taskQueued && root.taskBelongsToTool ? "stop" : "play"
            variant: (root.taskProcessing || root.taskQueued) && root.taskBelongsToTool
                ? "danger" : "primary"
            enabled: root.taskProcessing && root.taskBelongsToTool
                || root.taskQueued && root.taskBelongsToTool
                || root.taskPaused && root.taskBelongsToTool
                || (root.editable && !root.taskQueued && root.toolState.canRun)
            onClicked: {
                if ((root.taskProcessing || root.taskQueued) && root.taskBelongsToTool)
                    AppController.cancelManualTool(AppController.manualTargetTool);
                else if (root.taskPaused && root.taskBelongsToTool)
                    AppController.resumeSelectedVideo();
                else {
                    root.saveNow();
                    const started = AppController.runManualTool(root.toolId);
                    if (root.toolId === "export" && started)
                        root.exportRequested();
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
        id: subtitleEditorDialogLoader
        parent: root
        sourceComponent: Component {
            ManualSubtitleEditorDialog {
                segment: root.selectedSubtitle
                selectedIndex: root.selectedSubtitleIndex
                segmentCount: root.subtitleSegments.length
                hasInitialDraft: root.subtitleDrafts[segmentId] !== undefined
                initialDraftText: hasInitialDraft
                    ? String(root.subtitleDrafts[segmentId].text || "") : ""
                onPreviousRequested: root.subtitleDialogSelectionRequested(root.selectedSubtitleIndex - 1)
                onNextRequested: root.subtitleDialogSelectionRequested(root.selectedSubtitleIndex + 1)
                onCommitRequested: function(id, text, version, request) {
                    AppController.saveManualSubtitleText(id, text, version, request);
                }
                onDraftChanged: function(id, text, version) {
                    root.rememberSubtitleDraft(id, text, version);
                }
                onDraftCleared: function(id) { root.clearSubtitleDraft(id); }
                onEditingClosed: root.subtitleEditorClosed()
                onClosed: subtitleEditorDialogLoader.release()
            }
        }
    }
    LazyDialogLoader {
        id: voiceDialogLoader
        parent: root
        sourceComponent: Component {
            ManualVoiceDialog {
                onConfirmed: function(provider, voice, scope, segmentId, speakerMode) {
                    if (AppController.configureAndRunManualVoice(
                            provider, voice, scope, segmentId, speakerMode))
                        root.settingsCommitted();
                }
                onCloneRequested: voiceCloneDialogLoader.invoke("openForSelectedVideo", [])
                onClosed: voiceDialogLoader.release()
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
