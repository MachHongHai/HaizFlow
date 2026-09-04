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
    property var segments: []
    property string previewVideoId: ""
    property bool applyingSubtitleEdit: false
    property bool subtitleTransformActive: false
    property bool subtitleAudioRefreshPending: false
    property bool subtitleVisualRefreshPending: false
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
    readonly property var previewSubtitleFrame: previewSubtitleIndex >= 0
        ? AppController.subtitlePreviewFrame(
            String(previewSubtitle.text || ""),
            Number(previewSubtitle.start || 0),
            Number(previewSubtitle.end || 0),
            comparePreview.positionSeconds,
            activeSubtitleFontSize,
            subtitleLayoutWidth,
            activeSubtitleOutline
        ) : ({"text": "", "karaokeProgress": 0})
    readonly property string previewSubtitleFragment: String(previewSubtitleFrame.text || "")
    readonly property real previewSubtitleKaraokeProgress: Number(
        previewSubtitleFrame.karaokeProgress || 0
    )
    // qmllint enable missing-property

    function cloneSegments(value) {
        return JSON.parse(JSON.stringify(value || []));
    }

    onSelectedStageIndexChanged: {
        if (selectedStageIndex !== subtitleToolIndex)
            subtitleTransformActive = false;
    }

    function nextStageIndex() {
        return selectedStageIndex;
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
        segments = cloneSegments(AppController.reviewSegments);
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

    function saveSegments(nextSegments) {
        if (nextSegments.length === 0)
            return false;
        applyingSubtitleEdit = true;
        const saved = AppController.approveTranslationReview(JSON.stringify(nextSegments));
        applyingSubtitleEdit = false;
        if (!saved)
            return false;
        segments = cloneSegments(nextSegments);
        schedulePreview();
        return true;
    }

    function commitSubtitleTiming(index, start, end) {
        if (index < 0 || index >= segments.length)
            return false;
        const next = cloneSegments(segments);
        const previousStart = Number(next[index].start || 0);
        const previousEnd = Number(next[index].end || 0);
        next[index].start = Number(start);
        next[index].end = Number(end);
        next[index].timeline_edited = true;
        if (Math.abs((previousEnd - previousStart) - (Number(end) - Number(start))) > 0.001)
            next[index].fit_voice_to_timing = true;
        if (saveSegments(next)) {
            selectedSubtitleIndex = index;
            return true;
        }
        return false;
    }

    function commitSubtitleText(index, text) {
        if (index < 0 || index >= segments.length)
            return;
        const normalized = String(text || "").trim();
        if (normalized.length === 0 || normalized === String(segments[index].text || ""))
            return;
        const next = cloneSegments(segments);
        next[index].text = normalized;
        subtitleAudioRefreshPending = true;
        subtitleVisualRefreshPending = true;
        if (saveSegments(next))
            selectedSubtitleIndex = index;
        else {
            subtitleAudioRefreshPending = false;
            subtitleVisualRefreshPending = false;
        }
    }

    Component.onCompleted: {
        previewVideoId = AppController.selectedVideoId;
        selectedStageIndex = nextStageIndex();
        reloadSegments();
        schedulePreview();
    }
    Component.onDestruction: AppController.releaseEditorPreview()

    Timer {
        id: previewTimer
        interval: 180
        repeat: false
        onTriggered: AppController.requestEditorPreview(JSON.stringify(root.segments), comparePreview.positionSeconds)
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
                root.subtitleAudioRefreshPending = false;
                root.subtitleVisualRefreshPending = false;
            }
            // qmllint enable missing-property
            root.reloadSegments();
            root.schedulePreview();
        }

        function onEditorPreviewChanged() {
            if (root.subtitleAudioRefreshPending
                    && !AppController.editorPreviewBusy
                    && String(AppController.editorPreviewStage || "") === "ready")
                root.subtitleAudioRefreshPending = false;
            if (root.subtitleVisualRefreshPending
                    && !AppController.editorPreviewBusy
                    && String(AppController.editorPreviewStage || "") === "ready") {
                root.subtitleVisualRefreshPending = false;
                root.subtitleTransformActive = false;
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space8

        ManualWorkflowBar {
            Layout.fillWidth: true
            selectedTool: root.selectedStageIndex
            toolModel: root.toolModel
            hasVideo: AppController.hasSelectedVideo
            onToolSelected: function(index) { root.selectedStageIndex = index }
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
                implicitHeight: 8
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
                    implicitWidth: 8
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
                        && root.selectedStageIndex !== root.imageToolIndex
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
                    subtitleLivePreviewEnabled: root.subtitleVisualRefreshPending
                    onSubtitleActivated: {
                        if (root.previewSubtitleIndex < 0)
                            return;
                        root.selectedSubtitleIndex = root.previewSubtitleIndex;
                        root.subtitleTransformActive = true;
                    }
                    onSubtitleEditingDismissed: root.subtitleTransformActive = false
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
                        root.subtitleTransformActive = false;
                        root.schedulePreview();
                    }
                }

                ManualStageInspector {
                    SplitView.fillHeight: true
                    SplitView.preferredWidth: Math.max(286, Math.min(330, root.width * 0.18))
                    SplitView.minimumWidth: 280
                    currentStage: root.selectedStageIndex
                    toolModel: root.toolModel
                    subtitleSegments: root.segments
                    selectedSubtitleIndex: root.selectedSubtitleIndex
                    onSubtitleSelected: function(index) {
                        root.selectedSubtitleIndex = index;
                        root.selectedStageIndex = root.subtitleToolIndex;
                        root.subtitleTransformActive = index >= 0;
                        if (index >= 0 && index < root.segments.length)
                            comparePreview.seekTo(Number(root.segments[index].start || 0));
                    }
                    onSubtitleTextCommitted: function(index, text) {
                        root.commitSubtitleText(index, text);
                    }
                    onToolRequested: function(index) { root.selectedStageIndex = index }
                    onSourceLinkRequested: root.requestUrlImport()
                    onSettingsCommitted: root.schedulePreview()
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
                onSegmentSelected: function(index) {
                    root.selectedSubtitleIndex = index;
                    root.selectedStageIndex = root.subtitleToolIndex;
                    root.subtitleTransformActive = index >= 0;
                    if (index >= 0 && index < root.segments.length)
                        comparePreview.seekTo(Number(root.segments[index].start || 0));
                }
                onSeekRequested: function(seconds) {
                    comparePreview.seekTo(seconds);
                }
                onInteractionDismissed: root.subtitleTransformActive = false
                onTimingCommitted: function(index, start, end) {
                    const accepted = root.commitSubtitleTiming(index, start, end);
                    manualSubtitleTimeline.resolveTimingCommit(index, accepted);
                }
            }
        }
    }
}
