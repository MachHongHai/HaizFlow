pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    signal requestUrlImport()
    signal requestDownloadProjectImport()

    property int selectedStageIndex: 0
    property int selectedSubtitleIndex: -1
    readonly property var segments: AppController.manualSubtitleModel.segments
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
    readonly property int activeSubtitleFontSize: subtitleLayoutOverride
        ? AppController.subtitleFontSize
        : Number(previewRenderLayout.fontSize || AppController.subtitleFontSize)
    readonly property int activeSubtitlePositionX: subtitleLayoutOverride
        ? AppController.subtitlePositionXPercent
        : Number(previewRenderLayout.positionXPercent || AppController.subtitlePositionXPercent)
    readonly property int activeSubtitlePositionY: subtitleLayoutOverride
        ? AppController.subtitlePositionYPercent
        : Number(previewRenderLayout.positionYPercent || AppController.subtitlePositionYPercent)
    readonly property int activeSubtitleBoxWidth: subtitleLayoutOverride
        ? AppController.subtitleBoxWidthPercent
        : Number(previewRenderLayout.boxWidthPercent || AppController.subtitleBoxWidthPercent)
    readonly property int activeSubtitleOutline: subtitleLayoutOverride
        ? Math.max(
            Number(previewRenderLayout.outline || 2),
            Math.min(10, Math.max(3, Math.round(activeSubtitleFontSize * 0.09)))
        )
        : Number(previewRenderLayout.outline || Math.max(2, Math.round(activeSubtitleFontSize * 0.09)))
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
    readonly property int subtitleLayoutWidth: subtitleLayoutOverride
        ? Math.max(24, Math.round(subtitleOutputWidth * activeSubtitleBoxWidth / 100))
        : Math.max(24, Number(previewRenderLayout.layoutWidth || subtitleOutputWidth * activeSubtitleBoxWidth / 100))
    readonly property int subtitleLayoutHeight: subtitleLayoutOverride
        ? Math.max(20, Math.round(subtitleOutputHeight * AppController.subtitleBoxHeightPercent / 100))
        : Math.max(20, Number(previewRenderLayout.layoutHeight || subtitleOutputHeight * 0.07))
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
        positionXPercent: activeSubtitlePositionX, positionYPercent: activeSubtitlePositionY
    })
    onOverlayLayoutJsonChanged: overlayTimer.restart()
    onSegmentsChanged: overlayTimer.restart()
    Timer {
        id: overlayTimer
        interval: root.initialMediaLoad ? 300 : 160
        onTriggered: {
            AppController.subtitleOverlayRenderer.configure(JSON.stringify(root.segments), root.overlayLayoutJson, true);
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
    }
    Component.onDestruction: {
        // Close the explicit-save editor before detaching native preview
        // resources. Unsaved text remains a draft and is never committed by
        // route teardown.
        stageInspector.dismissTextEditor();
        AppController.endManualSubtitleEdit();
        AppController.releaseEditorPreview();
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
        onTriggered: root.initialMediaLoad = false
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
                AppController.manualPreviewAudio.positionSeconds
            );
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space8

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: AppController.selectedFileName
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                elide: Text.ElideMiddle
                textFormat: Text.PlainText
            }

            StudioButton {
                text: qsTr("Mở video xuất")
                iconName: "play"
                variant: "secondary"
                visible: AppController.hasSelectedVideo
                enabled: AppController.hasSelectedOutput
                toolTipText: enabled ? qsTr("Mở video vừa xuất")
                    : qsTr("Chưa có video xuất")
                onClicked: AppController.openOutputFile()
            }

            ProjectHeaderActions {
                projectFolderEnabled: AppController.hasOpenProject
                showInputVideo: true
                inputVideoEnabled: AppController.hasSelectedVideo
                showOutputFolder: true
                outputFolderEnabled: AppController.hasSelectedVideo
                showVideoFolder: true
                videoFolderEnabled: AppController.hasSelectedVideo
                showTechnicalLog: true
                technicalLogEnabled: AppController.hasSelectedVideo
                deleteEnabled: AppController.hasOpenProject
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
                onDeleteRequested: AppController.deleteCurrentProject()
            }
        }

        ManualWorkflowBar {
            Layout.fillWidth: true
            selectedTool: root.selectedStageIndex
            toolModel: root.toolModel
            hasVideo: AppController.hasSelectedVideo
            onToolSelected: function(index) {
                root.dismissSubtitleEditor();
                root.dismissWatermarkEditor();
                root.selectedStageIndex = index;
                root.warmTool(index);
            }
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
                SplitView.minimumHeight: 300
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

                ManualComparePreview {
                    id: comparePreview
                    SplitView.fillWidth: true
                    SplitView.fillHeight: true
                    SplitView.preferredWidth: root.width * 0.82
                    SplitView.minimumWidth: 640
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
                    watermarkScalePercent: AppController.watermarkScalePercent
                    watermarkInteractive: AppController.watermarkText.length > 0
                    watermarkEditEnabled: root.watermarkTransformActive
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

                ManualStageInspector {
                    id: stageInspector
                    SplitView.fillHeight: true
                    SplitView.preferredWidth: Math.max(286, Math.min(330, root.width * 0.18))
                    SplitView.minimumWidth: 280
                    currentStage: root.selectedStageIndex
                    toolModel: root.toolModel
                    subtitleSegments: root.segments
                    selectedSubtitleIndex: root.selectedSubtitleIndex
                    onSubtitleSelected: function(index) { root.selectSubtitle(index, true); }
                    onSubtitleDialogSelectionRequested: function(index) {
                        root.selectSubtitleInDialog(index);
                    }
                    onSubtitleEditorClosed: root.finishSubtitleDialogEditing()
                    onSourceLinkRequested: root.requestUrlImport()
                    onSettingsCommitted: root.schedulePreview()
                    onExportRequested: root.exportCompletionArmed = true
                }
            }

            SubtitleTimeline {
                id: manualSubtitleTimeline
                visible: root.segments.length > 0
                SplitView.fillWidth: true
                SplitView.preferredHeight: 260
                SplitView.minimumHeight: 248
                segments: root.segments
                selectedIndex: root.selectedSubtitleIndex
                duration: Math.max(0.1, comparePreview.durationSeconds)
                position: comparePreview.positionSeconds
                thumbnailSource: AppController.videoThumbnailSource
                managedScrubbing: true
                onScrubStarted: function(seconds) { comparePreview.beginScrub(seconds); }
                onScrubMoved: function(seconds) { comparePreview.updateScrub(seconds); }
                onScrubFinished: function(seconds) { comparePreview.endScrub(seconds); }
                onSegmentSelected: function(index) { root.selectSubtitle(index, true); }
                onSegmentFocused: function(index) { root.selectSubtitle(index, true); }
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
