pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    focus: true
    clip: true

    signal requestUrlImport()
    signal requestDownloadProjectImport()

    property int selectedStageIndex: 0
    property int selectedSubtitleIndex: -1
    property bool comparing: Boolean(AppController.manualEditorLayout.compare)
    readonly property var dockPlacements: ({ "tools": "left", "properties": "right", "tasks": "right" })
    property string rightActivePanel: String(AppController.manualEditorWorkspace.rightActive || "tasks")
    property int leftDockWidth: Number(AppController.manualEditorWorkspace.leftWidth || 240)
    property string activeMonitor: String(AppController.manualEditorWorkspace.monitor || "result")
    readonly property var dockOrder: ["tools", "properties", "tasks"]
    property bool layoutReady: false
    onComparingChanged: {
        if (layoutReady)
            layoutSaveTimer.restart();
    }
    function panelsFor(side) {
        // The right side is one contextual inspector, not two competing tabs.
        return side === "left" ? ["tools"] : ["tasks"];
    }
    function activePanelFor(side) {
        return side === "left" ? "tools"
            : rightActivePanel === "properties" ? "properties" : "tasks";
    }
    function isPanelActive(panelId) {
        const side = String(dockPlacements[panelId] || "");
        return side.length > 0 && activePanelFor(side) === panelId;
    }
    function panelHost(panelId) {
        const side = String(dockPlacements[panelId] || "");
        if (side === "left") return leftDock.contentHost;
        return rightDock.contentHost;
    }
    function activatePanel(panelId, side) {
        if (side === "right" && (panelId === "properties" || panelId === "tasks"))
            rightActivePanel = panelId;
        layoutSaveTimer.restart();
    }
    function saveWorkspaceLayout() {
        AppController.saveManualEditorWorkspace({
            "placements": dockPlacements,
            "leftActive": "tools",
            "rightActive": activePanelFor("right"),
            "leftWidth": Math.round(leftDock.width),
            "monitor": activeMonitor
        });
    }
    function resetWorkspaceLayout() {
        rightActivePanel = "tasks";
        leftDockWidth = 240;
        activeMonitor = "result";
        comparing = false;
        layoutSaveTimer.restart();
    }
    readonly property var segments: AppController.manualSubtitleModel.segments
    readonly property var editorModel: AppController.manualEditorDocumentModel
    readonly property var rendererSegments: editorModel.subtitleSegments.length > 0
        ? editorModel.subtitleSegments : segments
    readonly property var editorSubtitleStyle: editorModel.defaultSubtitleStyle || ({})
    readonly property var selectedEditorClip: editorModel.selectedClip || ({})
    readonly property var selectedEditorClipIds: editorModel.selectedClipIds || []
    readonly property bool editorHasSelection: selectedEditorClipIds.length > 0
    readonly property bool editorSourceSelected: String(selectedEditorClip.track_id || "") === "source-video"
    property bool timelineSnappingEnabled: true
    property string previewVideoId: ""
    property bool applyingSubtitleEdit: false
    property bool subtitleTransformActive: false
    property bool watermarkTransformActive: false
    property bool subtitleAudioRefreshPending: false
    property bool subtitleVisualRefreshPending: false
    property bool exportCompletionArmed: false
    property string pendingExportPath: ""
    property bool initialMediaLoad: true
    readonly property int subtitleToolIndex: 2
    readonly property int imageToolIndex: 3
    readonly property var stageIds: [
        "source", "translation", "subtitle", "image", "voice", "audio", "export"
    ]
    // qmllint disable missing-property
    readonly property var toolModel: AppController.manualToolModel || []
    readonly property var previewMedia: AppController.reviewPreviewMedia || ({})
    readonly property var previewRenderLayout: previewMedia.subtitleRenderLayout || ({})
    readonly property bool subtitleLayoutOverride: Boolean(AppController.subtitleLayoutOverride)
    readonly property int activeSubtitleFontSize: Number(
        editorSubtitleStyle.font_size !== undefined ? editorSubtitleStyle.font_size
        : (previewRenderLayout.fontSize || AppController.subtitleFontSize))
    readonly property int activeSubtitlePositionX: Number(
        editorSubtitleStyle.position_x_percent !== undefined ? editorSubtitleStyle.position_x_percent
        : (previewRenderLayout.positionXPercent || AppController.subtitlePositionXPercent))
    readonly property int activeSubtitlePositionY: Number(
        editorSubtitleStyle.position_y_percent !== undefined ? editorSubtitleStyle.position_y_percent
        : (previewRenderLayout.positionYPercent || AppController.subtitlePositionYPercent))
    readonly property int activeSubtitleBoxWidth: Number(
        editorSubtitleStyle.max_width_percent !== undefined ? editorSubtitleStyle.max_width_percent
        : (previewRenderLayout.boxWidthPercent || AppController.subtitleBoxWidthPercent))
    readonly property int activeSubtitleOutline: Number(
        editorSubtitleStyle.outline_width !== undefined ? editorSubtitleStyle.outline_width
        : (previewRenderLayout.outline || Math.max(2, Math.round(activeSubtitleFontSize * 0.09))))
    readonly property int subtitleOutputHeight: Math.max(
        1,
        Number(previewRenderLayout.outputHeight || previewMedia.videoHeight || 1080)
    )
    readonly property url currentResultSource: String(AppController.editorPreviewSource || "").length > 0
        ? AppController.editorPreviewSource
        : AppController.hasSelectedOutput
            ? AppController.selectedOutputSource
            : ""
    readonly property int previewSubtitleIndex: subtitleIndexAt(comparePreview.positionSeconds)
    readonly property var previewSubtitle: previewSubtitleIndex >= 0
        && previewSubtitleIndex < segments.length
        ? segments[previewSubtitleIndex] : ({})
    readonly property int subtitleOutputWidth: Math.max(
        1,
        Number(previewRenderLayout.outputWidth || previewMedia.videoWidth || 1920)
    )
    readonly property int subtitleLayoutWidth: Math.max(
        24, Math.round(subtitleOutputWidth * activeSubtitleBoxWidth / 100))
    readonly property int subtitleLayoutHeight: Math.max(20, Math.round(
        subtitleOutputHeight * Number(
            editorSubtitleStyle.box_height_percent !== undefined
                ? editorSubtitleStyle.box_height_percent
                : AppController.subtitleBoxHeightPercent) / 100))
    readonly property var previewSubtitleFrame: AppController.subtitleOverlayRenderer.frame
    readonly property ActivityLogDialog technicalLogDialog: technicalLogLoader.item as ActivityLogDialog
    readonly property ExportCompletedDialog exportCompletedDialog:
        exportCompletedDialogLoader.item as ExportCompletedDialog
    readonly property string previewSubtitleFragment: String(previewSubtitleFrame.text || "")
    readonly property real previewSubtitleKaraokeProgress: Number(previewSubtitleFrame.progress || 0)
    // qmllint enable missing-property

    onSelectedStageIndexChanged: {
        if (selectedStageIndex !== subtitleToolIndex)
            subtitleTransformActive = false;
        if (selectedStageIndex !== imageToolIndex)
            watermarkTransformActive = false;
    }

    function nextStageIndex() {
        return selectedStageIndex;
    }

    function warmTool(index) {
        const capability = ({
            0: "separation",
            1: "recognition",
            3: "ocr",
            4: "voice"
        })[index] || "";
        if (capability.length === 0)
            return;
        AppController.warmCapabilities(capability, {
            device: AppController.processingDevice,
            model: AppController.speechRecognitionModel,
            language: AppController.targetLanguage,
            provider: AppController.ttsProvider
        });
        if (index === 1)
            AppController.warmCapabilities("translation", {
                device: AppController.processingDevice,
                language: AppController.targetLanguage
            });
    }

    function subtitleIndexAt(seconds) {
        const time = Math.max(0, Number(seconds || 0));
        for (let index = 0; index < segments.length; ++index) {
            const start = Number(segments[index].start || 0);
            const end = Number(segments[index].end || 0);
            if (time >= start && (time < end || (index === segments.length - 1 && time <= end)))
                return index;
        }
        return -1;
    }

    function reloadSegments() {
        if (applyingSubtitleEdit)
            return;
        AppController.loadManualSubtitles();
        if (segments.length === 0) {
            selectedSubtitleIndex = -1;
            subtitleTransformActive = false;
        } else {
            selectedSubtitleIndex = Math.max(0, Math.min(selectedSubtitleIndex, segments.length - 1));
        }
    }

    function schedulePreview() {
        if (AppController.projectType !== "manual" || AppController.isSelectedVideoQueued)
            return;
        previewTimer.restart();
    }

    function commitSubtitleTiming(index, start, end) {
        if (index < 0 || index >= segments.length)
            return false;
        return AppController.saveManualSubtitleTiming(String(segments[index].segment_id), start, end);
    }

    function dismissSubtitleEditor() {
        stageInspector.dismissTextEditor();
        subtitleTransformActive = false;
        AppController.endManualSubtitleEdit();
        root.forceActiveFocus();
    }

    function dismissWatermarkEditor() {
        watermarkTransformActive = false;
        root.forceActiveFocus();
    }

    function selectWatermark() {
        dismissSubtitleEditor();
        selectedStageIndex = imageToolIndex;
        watermarkTransformActive = true;
        AppController.manualEditorDocumentModel.selectClip("watermark-1", false);
        activatePanel("properties", "right");
    }

    function selectEditorClip(clipId) {
        AppController.manualEditorDocumentModel.selectClip(clipId, false);
        const selected = AppController.manualEditorDocumentModel.selectedClip;
        const trackId = String(selected.track_id || "");
        const stageByTrack = {
            "source-video": 0, "subtitles": 2, "overlays": 3,
            "voice": 4, "source-audio": 5, "music": 5
        };
        if (stageByTrack[trackId] !== undefined)
            selectedStageIndex = stageByTrack[trackId];
        activatePanel(trackId === "subtitles" ? "tasks" : "properties", "right");
        root.forceActiveFocus();
    }

    function selectSubtitle(index, seek) {
        stageInspector.dismissTextEditor();
        if (index < 0 || index >= segments.length)
            return;
        selectedSubtitleIndex = index;
        watermarkTransformActive = false;
        selectedStageIndex = subtitleToolIndex;
        subtitleTransformActive = true;
        AppController.beginManualSubtitleEdit(String(segments[index].segment_id));
        AppController.manualEditorDocumentModel.selectClip(
            "subtitle-" + String(segments[index].segment_id), false);
        activatePanel("tasks", "right");
        if (seek)
            comparePreview.seekTo(Number(segments[index].start || 0));
    }

    function selectSubtitleInDialog(index) {
        if (index < 0 || index >= segments.length)
            return;
        selectedSubtitleIndex = index;
        selectedStageIndex = subtitleToolIndex;
        subtitleTransformActive = true;
        AppController.beginManualSubtitleEdit(String(segments[index].segment_id));
        comparePreview.seekTo(Number(segments[index].start || 0));
    }

    function finishSubtitleDialogEditing() {
        subtitleTransformActive = false;
        AppController.endManualSubtitleEdit();
        root.forceActiveFocus();
    }

    readonly property string overlayLayoutJson: JSON.stringify({
        outputWidth: subtitleOutputWidth, outputHeight: subtitleOutputHeight,
        layoutWidth: subtitleLayoutWidth, layoutHeight: subtitleLayoutHeight,
        fontSize: activeSubtitleFontSize, outline: activeSubtitleOutline,
        positionXPercent: activeSubtitlePositionX, positionYPercent: activeSubtitlePositionY,
        fontFamily: editorSubtitleStyle.font_family || AppController.subtitleFontFamily,
        textColor: editorSubtitleStyle.text_color || AppController.subtitleTextColor,
        karaokeColor: editorSubtitleStyle.karaoke_color || AppController.subtitleKaraokeColor,
        outlineColor: editorSubtitleStyle.outline_color || AppController.subtitleOutlineColor,
        bold: editorSubtitleStyle.font_weight === undefined
            ? AppController.subtitleBold : Number(editorSubtitleStyle.font_weight) >= 600,
        italic: editorSubtitleStyle.italic === undefined
            ? AppController.subtitleItalic : Boolean(editorSubtitleStyle.italic),
        uppercase: editorSubtitleStyle.uppercase === undefined
            ? AppController.subtitleUppercase : Boolean(editorSubtitleStyle.uppercase),
        shadow: Math.max(
            Math.abs(Number(editorSubtitleStyle.shadow_offset_x || 0)),
            Math.abs(Number(editorSubtitleStyle.shadow_offset_y || AppController.subtitleShadow))
        )
    })
    onOverlayLayoutJsonChanged: overlayTimer.restart()
    onRendererSegmentsChanged: overlayTimer.restart()
    Timer {
        id: overlayTimer
        interval: root.initialMediaLoad ? 300 : 160
        onTriggered: {
            AppController.subtitleOverlayRenderer.configure(
                JSON.stringify(root.rendererSegments), root.overlayLayoutJson, true);
            AppController.subtitleOverlayRenderer.seek(comparePreview.positionSeconds);
        }
    }

    function syncVolumes() {
        AppController.manualPreviewAudio.setVolumes(AppController.originalVolume,
            AppController.ttsVolume, AppController.backgroundMusicVolume);
    }

    function showExportCompleted(outputPath) {
        pendingExportPath = String(outputPath || "");
        if (exportCompletedDialogLoader.status === Loader.Ready && exportCompletedDialog) {
            exportCompletedDialog.showForOutput(pendingExportPath);
            return;
        }
        exportCompletedDialogLoader.active = true;
    }

    Component.onCompleted: {
        previewVideoId = AppController.selectedVideoId;
        selectedStageIndex = nextStageIndex();
        reloadSegments();
        syncVolumes();
        schedulePreview();
        initialLoadTimer.start();
        root.forceActiveFocus();
    }
    Component.onDestruction: {
        layoutSaveTimer.stop();
        if (layoutReady)
            AppController.saveManualEditorLayout(
                Math.round(rightDock.width), Math.round(manualSubtitleTimeline.height), comparing);
        if (layoutReady)
            saveWorkspaceLayout();
        // Close the explicit-save editor before detaching native preview
        // resources. Unsaved text remains a draft and is never committed by
        // route teardown.
        stageInspector.dismissTextEditor();
        AppController.endManualSubtitleEdit();
        AppController.releaseEditorPreview();
    }

    Timer {
        id: layoutSaveTimer
        interval: 400
        repeat: false
        onTriggered: {
            if (root.layoutReady && AppController.hasSelectedVideo)
                AppController.saveManualEditorLayout(
                    Math.round(rightDock.width), Math.round(manualSubtitleTimeline.height), root.comparing);
            if (root.layoutReady && AppController.hasSelectedVideo)
                root.saveWorkspaceLayout();
        }
    }

    Timer {
        id: previewTimer
        interval: root.initialMediaLoad ? 680 : 180
        repeat: false
        onTriggered: AppController.requestEditorPreview(JSON.stringify(root.segments), comparePreview.positionSeconds)
    }

    Timer {
        id: initialLoadTimer
        interval: 900
        repeat: false
        onTriggered: {
            root.initialMediaLoad = false;
            root.layoutReady = true;
        }
    }

    Connections {
        target: AppController

        function onSelectedVideoChanged() {
            // qmllint disable missing-property
            if (root.previewVideoId !== AppController.selectedVideoId) {
                AppController.releaseEditorPreview();
                root.previewVideoId = AppController.selectedVideoId;
                root.selectedStageIndex = 0;
                root.selectedSubtitleIndex = -1;
                root.subtitleTransformActive = false;
                root.watermarkTransformActive = false;
                root.subtitleAudioRefreshPending = false;
                root.subtitleVisualRefreshPending = false;
            }
            // qmllint enable missing-property
            root.reloadSegments();
            root.schedulePreview();
        }

        function onManualSubtitleSaved() { root.schedulePreview(); }
        function onOriginalVolumeChanged() { root.syncVolumes(); }
        function onTtsVolumeChanged() { root.syncVolumes(); }
        function onBackgroundMusicVolumeChanged() { root.syncVolumes(); }

        function onManualExportCompleted(videoId, outputPath) {
            if (!root.exportCompletionArmed || String(videoId) !== AppController.selectedVideoId)
                return;
            root.exportCompletionArmed = false;
            root.showExportCompleted(outputPath);
        }

    }

    Connections {
        target: AppController.manualPreviewAudio

        function onPositionChanged() {
            // Karaoke follows samples actually presented by QAudioSink, not
            // the decoder clock that may lead it by one Windows audio buffer.
            AppController.subtitleOverlayRenderer.seek(
                comparePreview.sequenceMsForSource(
                    AppController.manualPreviewAudio.positionSeconds * 1000) / 1000
            );
        }
    }

    Keys.onPressed: function(event) {
        if (event.isAutoRepeat && event.key !== Qt.Key_J && event.key !== Qt.Key_L)
            return;
        if ((event.modifiers & Qt.ControlModifier) !== 0 && event.key === Qt.Key_Z) {
            AppController.undoEdit();
            event.accepted = true;
        } else if ((event.modifiers & Qt.ControlModifier) !== 0 && event.key === Qt.Key_Y) {
            AppController.redoEdit();
            event.accepted = true;
        } else if (event.key === Qt.Key_Delete) {
            if (root.editorHasSelection && !root.editorSourceSelected)
                AppController.removeClips(root.selectedEditorClipIds, false);
            event.accepted = true;
        } else if (event.key === Qt.Key_Space) {
            comparePreview.togglePlayback();
            event.accepted = true;
        } else if (event.key === Qt.Key_J) {
            comparePreview.shuttleBackward();
            event.accepted = true;
        } else if (event.key === Qt.Key_K) {
            comparePreview.pausePlayback();
            event.accepted = true;
        } else if (event.key === Qt.Key_L) {
            comparePreview.shuttleForward();
            event.accepted = true;
        } else if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal) {
            manualSubtitleTimeline.zoomAt(
                manualSubtitleTimeline.width / 2,
                manualSubtitleTimeline.zoomFactor * 1.2);
            event.accepted = true;
        } else if (event.key === Qt.Key_Minus) {
            manualSubtitleTimeline.zoomAt(
                manualSubtitleTimeline.width / 2,
                manualSubtitleTimeline.zoomFactor / 1.2);
            event.accepted = true;
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space8

        ManualEditorToolbar {
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            fileName: AppController.selectedFileName
            hasVideo: AppController.hasSelectedVideo
            hasOutput: AppController.hasSelectedOutput
            hasProject: AppController.hasOpenProject
            canUndo: AppController.canUndoEdit
            canRedo: AppController.canRedoEdit
            hasSelection: root.editorHasSelection
            sourceSelected: root.editorSourceSelected
            comparing: root.comparing
            zoomFactor: manualSubtitleTimeline.zoomFactor
            onUndoRequested: AppController.undoEdit()
            onRedoRequested: AppController.redoEdit()
            onZoomChanged: function(value) {
                manualSubtitleTimeline.zoomAt(manualSubtitleTimeline.width / 2, value);
            }
            onCompareToggled: root.comparing = !root.comparing
            onOutputRequested: AppController.openOutputFile()
            onExportRequested: {
                root.selectedStageIndex = 6;
                root.activatePanel("tasks", "right");
            }
            onProjectFolderRequested: AppController.openProjectFolder()
            onInputVideoRequested: AppController.openInputFile()
            onOutputFolderRequested: AppController.openOutputFolder()
            onVideoFolderRequested: AppController.openVideoFolder()
            onTechnicalLogRequested: {
                if (technicalLogLoader.status === Loader.Ready && root.technicalLogDialog)
                    root.technicalLogDialog.open();
                else
                    technicalLogLoader.active = true;
            }
            onProjectDeleteRequested: AppController.deleteCurrentProject()
            onResetWorkspaceRequested: root.resetWorkspaceLayout()
        }

        SourceMediaPanel {
            visible: !AppController.hasSelectedVideo
            Layout.fillWidth: true
            Layout.fillHeight: true
            compact: false
            onRequestUrlImport: root.requestUrlImport()
            onRequestDownloadProjectImport: root.requestDownloadProjectImport()
        }

        SplitView {
            id: manualEditorSplit
            visible: AppController.hasSelectedVideo
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Vertical

            handle: Rectangle {
                implicitHeight: 16
                color: SplitHandle.hovered || SplitHandle.pressed ? Theme.interactiveMuted : "transparent"

                Rectangle {
                    anchors.centerIn: parent
                    width: 52
                    height: 3
                    radius: 2
                    color: parent.SplitHandle.hovered || parent.SplitHandle.pressed
                        ? Theme.focus : Theme.outlineStrong
                }
            }

            SplitView {
                SplitView.fillWidth: true
                SplitView.fillHeight: true
                SplitView.minimumHeight: 220
                orientation: Qt.Horizontal

                handle: Rectangle {
                    implicitWidth: 16
                    color: SplitHandle.hovered || SplitHandle.pressed ? Theme.interactiveMuted : "transparent"

                    Rectangle {
                        anchors.centerIn: parent
                        width: 3
                        height: 52
                        radius: 2
                        color: parent.SplitHandle.hovered || parent.SplitHandle.pressed
                            ? Theme.focus : Theme.outlineStrong
                    }
                }

                EditorDockGroup {
                    id: leftDock
                    SplitView.fillHeight: true
                    SplitView.preferredWidth: root.leftDockWidth
                    SplitView.minimumWidth: 180
                    SplitView.maximumWidth: 480
                    panelIds: root.panelsFor("left")
                    activePanelId: root.activePanelFor("left")
                    onPanelActivated: function(panelId) { root.activatePanel(panelId, "left"); }
                    onWidthChanged: if (root.layoutReady) layoutSaveTimer.restart()
                }

                ManualComparePreview {
                    id: comparePreview
                    SplitView.fillWidth: true
                    SplitView.fillHeight: true
                    SplitView.minimumWidth: 400
                    comparing: root.comparing
                    activeMonitor: root.activeMonitor
                    onMonitorSelected: function(monitorId) {
                        root.activeMonitor = monitorId;
                        layoutSaveTimer.restart();
                    }
                    inputSource: AppController.selectedInputSource
                    resultSource: root.currentResultSource
                    resultBaseSource: AppController.editorPreviewBaseSource
                    thumbnailSource: AppController.videoThumbnailSource
                    previewBusy: AppController.editorPreviewBusy
                    previewProgress: AppController.editorPreviewProgress
                    subtitleInteractive: root.previewSubtitleIndex >= 0
                    subtitleEditEnabled: root.subtitleTransformActive
                        && root.selectedSubtitleIndex === root.previewSubtitleIndex
                    subtitleText: root.previewSubtitleFragment
                    subtitleKaraokeProgress: root.previewSubtitleKaraokeProgress
                    subtitleFontSize: root.activeSubtitleFontSize
                    subtitlePositionXPercent: root.activeSubtitlePositionX
                    subtitlePositionYPercent: root.activeSubtitlePositionY
                    subtitleBoxWidthPercent: root.activeSubtitleBoxWidth
                    subtitleOutline: root.activeSubtitleOutline
                    subtitleLayoutWidth: root.subtitleLayoutWidth
                    subtitleLayoutHeight: root.subtitleLayoutHeight
                    subtitleReferenceWidth: root.subtitleOutputWidth
                    subtitleReferenceHeight: root.subtitleOutputHeight
                    suppressResultAudio: root.subtitleAudioRefreshPending
                    subtitleLivePreviewEnabled: true
                    subtitleSprite: AppController.subtitleOverlayRenderer.frame
                    watermarkText: AppController.watermarkText
                    watermarkKind: AppController.watermarkKind
                    watermarkImageSource: AppController.watermarkImageSource
                    watermarkVideoSource: AppController.watermarkVideoSource
                    watermarkFontFamily: AppController.watermarkFontFamily
                    watermarkTextColor: AppController.watermarkTextColor
                    watermarkBold: AppController.watermarkBold
                    watermarkItalic: AppController.watermarkItalic
                    watermarkOpacityPercent: AppController.watermarkOpacityPercent
                    watermarkOutlinePercent: AppController.watermarkOutlinePercent
                    watermarkScalePercent: AppController.watermarkScalePercent
                    watermarkInteractive: AppController.watermarkKind === "image"
                        ? AppController.watermarkImagePath.length > 0
                        : AppController.watermarkKind === "video"
                            ? AppController.watermarkVideoPath.length > 0
                            : AppController.watermarkText.length > 0
                    watermarkEditEnabled: root.watermarkTransformActive
                    editorOverlays: AppController.manualPreviewComposition.frame.overlays
                    selectedEditorClipIds: root.selectedEditorClipIds
                    sourceEditDecisions: root.editorModel.document.sequence
                        ? (root.editorModel.document.sequence.edit_decisions || []) : []
                    sequenceDurationSeconds: root.editorModel.durationMs / 1000
                    onPositionSecondsChanged: {
                        AppController.manualPreviewComposition.setTime(positionSeconds);
                    }
                    onEditorClipSelected: function(clipId) {
                        root.selectEditorClip(clipId);
                    }
                    onSubtitleActivated: root.selectSubtitle(root.previewSubtitleIndex, false)
                    onSubtitleEditingDismissed: root.dismissSubtitleEditor()
                    onWatermarkActivated: root.selectWatermark()
                    onWatermarkEditingDismissed: root.dismissWatermarkEditor()
                    onWatermarkScalePreviewChanged: function(value) {
                        AppController.watermarkScalePercent = value;
                    }
                    onWatermarkScaleCommitted: function(beforeValue, afterValue) {
                        AppController.watermarkScalePercent = afterValue;
                        AppController.saveSelectedVideoSettings();
                        AppController.recordManualWatermarkScaleChange(beforeValue, afterValue);
                    }
                    onSubtitleLayoutPreviewChanged: function(fontSize, positionX, positionY) {
                        if (!AppController.subtitleLayoutOverride)
                            AppController.adoptSubtitlePreviewLayout();
                        root.subtitleVisualRefreshPending = true;
                        AppController.subtitleFontSize = fontSize;
                        AppController.subtitlePositionXPercent = positionX;
                        AppController.subtitlePositionYPercent = positionY;
                    }
                    onSubtitleLayoutCommitted: function(fontSize, positionX, positionY) {
                        if (!AppController.subtitleLayoutOverride)
                            AppController.adoptSubtitlePreviewLayout();
                        root.subtitleVisualRefreshPending = true;
                        AppController.subtitleFontSize = fontSize;
                        AppController.subtitlePositionXPercent = positionX;
                        AppController.subtitlePositionYPercent = positionY;
                        AppController.saveSelectedVideoSettings();
                        root.schedulePreview();
                    }
                }

                EditorDockGroup {
                    id: rightDock
                    SplitView.fillHeight: true
                    SplitView.preferredWidth: root.width < 1500 ? 296
                        : Math.max(300, Math.min(480,
                            Number(AppController.manualEditorLayout.inspectorWidth || 340)))
                    SplitView.minimumWidth: 260
                    SplitView.maximumWidth: 480
                    panelIds: root.panelsFor("right")
                    activePanelId: root.activePanelFor("right")
                    onPanelActivated: function(panelId) { root.activatePanel(panelId, "right"); }
                    onWidthChanged: if (root.layoutReady) layoutSaveTimer.restart()
                }
            }

            SubtitleTimeline {
                id: manualSubtitleTimeline
                visible: AppController.hasSelectedVideo
                SplitView.fillWidth: true
                SplitView.preferredHeight: root.height < 780 ? 210
                    : Math.max(220, Math.min(520,
                        Number(AppController.manualEditorLayout.timelineHeight || 280)))
                SplitView.minimumHeight: 200
                SplitView.maximumHeight: 520
                onHeightChanged: {
                    if (root.layoutReady)
                        layoutSaveTimer.restart();
                }
                segments: root.segments
                editorTracks: root.editorModel.tracks
                editorClips: root.editorModel.clips
                sourceTrimEnabled: Boolean(root.editorModel.document.sequence)
                    && (root.editorModel.document.sequence.edit_decisions || []).length === 1
                    && root.editorModel.clips.filter(function(clip) {
                        return String(clip.track_id || "") === "source-video"
                            && Boolean(clip.enabled);
                    }).length === 1
                selectedClipIds: root.editorModel.selectedClipIds
                selectedIndex: root.selectedSubtitleIndex
                duration: Math.max(0.1, comparePreview.durationSeconds)
                position: comparePreview.positionSeconds
                thumbnailSource: AppController.videoThumbnailSource
                managedScrubbing: true
                snappingEnabled: root.timelineSnappingEnabled
                onScrubStarted: function(seconds) { comparePreview.beginScrub(seconds); }
                onScrubMoved: function(seconds) { comparePreview.updateScrub(seconds); }
                onScrubFinished: function(seconds) { comparePreview.endScrub(seconds); }
                onSegmentSelected: function(index) { root.selectSubtitle(index, true); }
                onSegmentFocused: function(index) { root.selectSubtitle(index, true); }
                onClipSelected: function(clipId, additive) {
                    AppController.manualEditorDocumentModel.selectClip(clipId, additive);
                    if (!additive)
                        root.selectEditorClip(clipId);
                    root.forceActiveFocus();
                }
                onTrackSelected: function(trackId) {
                    AppController.manualEditorDocumentModel.selectTrack(trackId);
                    const stageByTrack = {
                        "source-video": 0, "subtitles": 2, "overlays": 3,
                        "voice": 4, "source-audio": 5, "music": 5
                    };
                    if (stageByTrack[trackId] !== undefined)
                        root.selectedStageIndex = stageByTrack[trackId];
                    root.forceActiveFocus();
                }
                onTrackStateRequested: function(trackId, propertyName, value) {
                    AppController.setTrackState(trackId, propertyName, value);
                }
                onClipMoveCommitted: function(clipId, startMs, trackId) {
                    AppController.moveClip(clipId, startMs, trackId);
                }
                onClipTrimCommitted: function(clipId, edge, timeMs) {
                    const clip = root.editorModel.clips.find(function(item) {
                        return String(item.clip_id || "") === clipId;
                    });
                    if (clip && String(clip.track_id || "") === "source-video")
                        AppController.trimSourceBoundary(edge, timeMs);
                    else
                        AppController.trimClip(clipId, edge, timeMs);
                }
                onSeekRequested: function(seconds) {
                    comparePreview.seekTo(seconds);
                }
                onInteractionDismissed: root.dismissSubtitleEditor()
                onTimingCommitted: function(index, start, end) {
                    const accepted = root.commitSubtitleTiming(index, start, end);
                    manualSubtitleTimeline.resolveTimingCommit(index, accepted);
                }
            }
        }
    }

    ManualToolNavigator {
        parent: root.panelHost("tools")
        anchors.fill: parent
        visible: root.isPanelActive("tools")
        tools: root.toolModel.slice(0, 6)
        currentIndex: root.selectedStageIndex
        onToolSelected: function(index) {
            root.selectedStageIndex = index;
            root.warmTool(index);
            root.activatePanel("tasks", "right");
        }
    }

    ManualSelectionPanel {
        parent: root.panelHost("properties")
        anchors.fill: parent
        visible: root.isPanelActive("properties")
        clipData: root.selectedEditorClip
        subtitleSegment: root.selectedSubtitleIndex >= 0
            && root.selectedSubtitleIndex < root.segments.length
            ? root.segments[root.selectedSubtitleIndex] : ({})
        legacySequence: Boolean(root.editorModel.document.sequence)
            && (root.editorModel.document.sequence.edit_decisions || []).length > 1
        onOpenImageToolRequested: {
            root.selectedStageIndex = root.imageToolIndex;
            root.activatePanel("tasks", "right");
        }
        onSettingsCommitted: root.schedulePreview()
        onWatermarkSettingsEdited: stageInspector.scheduleSave()
    }

    ManualStageInspector {
        id: stageInspector
        parent: root.panelHost("tasks")
        anchors.fill: parent
        visible: root.isPanelActive("tasks")
        currentStage: root.selectedStageIndex
        toolModel: root.toolModel
        subtitleSegments: root.segments
        selectedSubtitleIndex: root.selectedSubtitleIndex
        selectedEditorClip: root.selectedEditorClip
        onSubtitleSelected: function(index) { root.selectSubtitle(index, true); }
        onSubtitleDialogSelectionRequested: function(index) {
            root.selectSubtitleInDialog(index);
        }
        onSubtitleEditorClosed: root.finishSubtitleDialogEditing()
        onSourceLinkRequested: root.requestUrlImport()
        onSettingsCommitted: root.schedulePreview()
        onExportRequested: root.exportCompletionArmed = true
        onEditorSeekRequested: function(seconds) { comparePreview.seekTo(seconds); }
        onToolSelected: function(index) {
            root.dismissSubtitleEditor();
            root.dismissWatermarkEditor();
            root.selectedStageIndex = index;
            root.warmTool(index);
        }
    }

    Loader {
        id: exportCompletedDialogLoader
        active: false
        asynchronous: false
        onLoaded: {
            if (status === Loader.Ready && root.exportCompletedDialog)
                root.exportCompletedDialog.showForOutput(root.pendingExportPath);
        }
        sourceComponent: Component {
            ExportCompletedDialog {
                onOpenVideoRequested: AppController.openOutputFile()
                onOpenFolderRequested: AppController.openOutputFolder()
                onClosed: exportCompletedDialogLoader.active = false
            }
        }
    }

    Loader {
        id: technicalLogLoader
        active: false
        asynchronous: false
        onLoaded: if (status === Loader.Ready && root.technicalLogDialog) root.technicalLogDialog.open()
        sourceComponent: Component {
            ActivityLogDialog {
                logText: AppController.logs
                detailText: qsTr("Log kỹ thuật")
                onClosed: technicalLogLoader.active = false
            }
        }
    }

}
