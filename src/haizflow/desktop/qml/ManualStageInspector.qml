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
    property var selectedEditorClip: ({})
    property var subtitleDrafts: ({})
    property var exportPreflight: ({ "canExport": false, "issues": [],
        "requiredBytes": 0, "availableBytes": 0 })
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
    readonly property real panelBodyHeight: inspectorScroll.height

    signal subtitleSelected(int index)
    signal subtitleDialogSelectionRequested(int index)
    signal subtitleEditorClosed()
    signal sourceLinkRequested()
    signal settingsCommitted()
    signal exportRequested()
    signal editorSeekRequested(real seconds)
    signal toolSelected(int index)

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
    showTitle: false
    padding: Theme.space16
    border.width: 0
    radius: 0
    onCurrentStageChanged: {
        inspectorScroll.contentY = 0;
        if (root.toolId === "export")
            root.refreshExportPreflight();
    }
    Component.onCompleted: {
        if (root.toolId === "export")
            root.refreshExportPreflight();
    }

    function formatBytes(value) {
        const bytes = Math.max(0, Number(value || 0));
        if (bytes >= 1073741824)
            return (bytes / 1073741824).toFixed(1) + " GiB";
        if (bytes >= 1048576)
            return Math.round(bytes / 1048576) + " MiB";
        return Math.round(bytes / 1024) + " KiB";
    }

    function refreshExportPreflight() {
        if (root.toolId === "export" && AppController.hasSelectedVideo)
            root.exportPreflight = AppController.manualExportPreflight();
    }

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

    function runLabel() {
        if (toolId === "translation") return toolState.cacheHit ? qsTr("Nhận dạng & dịch lại") : qsTr("Nhận dạng & dịch");
        if (toolId === "image") return toolState.cacheHit ? qsTr("Quét lại phụ đề gốc") : qsTr("Tìm vùng phụ đề gốc");
        if (toolId === "voice") return toolState.cacheHit ? qsTr("Tạo lại giọng") : qsTr("Tạo giọng");
        if (toolId === "audio") return toolState.cacheHit ? qsTr("Tạo lại bản phối") : qsTr("Tạo bản phối");
        if (toolId === "export") return toolState.cacheHit ? qsTr("Xuất lại video") : qsTr("Xuất video");
        return qsTr("Chạy công cụ");
    }

    function openVoiceDialog() {
        const configuration = AppController.manualVoiceConfiguration("");
        voiceDialogLoader.invoke("openForVoice", [
            Boolean(configuration.hasPublishedVoice),
            configuration
        ]);
    }

    function openBackgroundMusicLinkDialog() {
        backgroundMusicLinkDialogLoader.invoke("open", []);
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
        text: String(root.toolState.label || "")
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.section
        font.weight: Font.DemiBold
        textFormat: Text.PlainText
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: Theme.divider
    }

    Text {
        Layout.fillWidth: true
        visible: root.toolState.state === "error"
        text: qsTr("Tác vụ gặp lỗi. Mở log kỹ thuật để xem chi tiết.")
        color: Theme.danger
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        font.weight: Font.DemiBold
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
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
            ManualSourceToolPanel { inspector: root }
        }

        Component {
            id: translationInspectorComponent
            ManualTranslationToolPanel { inspector: root }
        }

        Component {
            id: subtitleInspectorComponent
            ManualSubtitleToolPanel { inspector: root }
        }

        Component {
            id: imageInspectorComponent
            ManualImageToolPanel { inspector: root }
        }

        Component {
            id: voiceInspectorComponent
            ManualVoiceToolPanel { inspector: root }
        }

        Component {
            id: audioInspectorComponent
            ManualAudioToolPanel { inspector: root }
        }

        Component {
            id: exportInspectorComponent
            ManualExportToolPanel { inspector: root }
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
        visible: (
            (root.taskBelongsToTool && (root.taskQueued || root.taskPaused))
            || ["translation", "image", "voice", "export"].indexOf(root.toolId) >= 0)
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
                || ["translation", "image", "export"].indexOf(root.toolId) >= 0
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
                || (root.editable && !root.taskQueued && root.toolState.canRun
                    && (root.toolId !== "export" || Boolean(root.exportPreflight.canExport)))
            onClicked: {
                if ((root.taskProcessing || root.taskQueued) && root.taskBelongsToTool)
                    AppController.cancelManualTool(AppController.manualTargetTool);
                else if (root.taskPaused && root.taskBelongsToTool)
                    AppController.resumeSelectedVideo();
                else {
                    root.saveNow();
                    if (root.toolId === "export")
                        root.refreshExportPreflight();
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
            if (root.toolId === "export")
                root.refreshExportPreflight();
        }
    }

    Connections {
        target: AppController.manualEditorDocumentModel
        function onChanged() {
            if (root.toolId === "export")
                root.refreshExportPreflight();
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
                onSelectionRequested: function(index) { root.subtitleDialogSelectionRequested(index); }
                onCommitRequested: function(id, text, version, request) {
                    AppController.saveManualSubtitleText(id, text, version, request);
                }
                onDraftChanged: function(id, text, version) {
                    root.rememberSubtitleDraft(id, text, version);
                }
                onDraftCleared: function(id) { root.clearSubtitleDraft(id); }
                onDeleteRequested: function(id) {
                    AppController.deleteSubtitleSegment(id);
                }
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
}
