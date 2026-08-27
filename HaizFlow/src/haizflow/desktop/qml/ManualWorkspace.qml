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
    property string observedCompletedStages: ""
    property string previewVideoId: ""
    property bool applyingSubtitleEdit: false
    readonly property var stageIds: ["translation", "visual", "voice", "audio"]
    // qmllint disable missing-property
    readonly property var completedStages: AppController.manualCompletedStages || []
    readonly property string runningStage: AppController.isSelectedVideoQueued
        ? AppController.manualTargetStage : ""
    readonly property url currentResultSource: String(AppController.editorPreviewSource || "").length > 0
        ? AppController.editorPreviewSource
        : AppController.hasSelectedOutput
            ? AppController.selectedOutputSource
            : AppController.selectedInputSource
    // qmllint enable missing-property

    function cloneSegments(value) {
        return JSON.parse(JSON.stringify(value || []));
    }

    function nextStageIndex() {
        return selectedStageIndex;
    }

    function reloadSegments() {
        if (applyingSubtitleEdit)
            return;
        segments = cloneSegments(AppController.reviewSegments);
        if (segments.length === 0)
            selectedSubtitleIndex = -1;
        else
            selectedSubtitleIndex = Math.max(0, Math.min(selectedSubtitleIndex, segments.length - 1));
    }

    function schedulePreview() {
        if (AppController.projectType !== "manual" || AppController.isSelectedVideoQueued)
            return;
        if (segments.length === 0)
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
            return;
        const next = cloneSegments(segments);
        next[index].start = Number(start);
        next[index].end = Number(end);
        if (saveSegments(next))
            selectedSubtitleIndex = index;
    }

    function commitSubtitleText(index, text) {
        if (index < 0 || index >= segments.length)
            return;
        const normalized = String(text || "").trim();
        if (normalized.length === 0 || normalized === String(segments[index].text || ""))
            return;
        const next = cloneSegments(segments);
        next[index].text = normalized;
        if (saveSegments(next))
            selectedSubtitleIndex = index;
    }

    Component.onCompleted: {
        previewVideoId = AppController.selectedVideoId;
        // qmllint disable missing-property
        observedCompletedStages = JSON.stringify(AppController.manualCompletedStages || []);
        // qmllint enable missing-property
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
                root.observedCompletedStages = JSON.stringify(AppController.manualCompletedStages || []);
                root.selectedStageIndex = 0;
                root.selectedSubtitleIndex = -1;
            } else if (root.observedCompletedStages !== JSON.stringify(AppController.manualCompletedStages || [])) {
                root.observedCompletedStages = JSON.stringify(AppController.manualCompletedStages || []);
                root.selectedStageIndex = root.nextStageIndex();
            }
            // qmllint enable missing-property
            root.reloadSegments();
            root.schedulePreview();
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space8

        ManualWorkflowBar {
            Layout.fillWidth: true
            selectedStage: root.selectedStageIndex
            completedStages: root.completedStages
            runningStage: root.runningStage
            hasVideo: AppController.hasSelectedVideo
            processing: AppController.isSelectedVideoProcessing
            queued: AppController.isSelectedVideoQueued
            canExport: root.completedStages.indexOf("voice") >= 0
            onStageSelected: function(index) { root.selectedStageIndex = index }
            onExportRequested: {
                AppController.persistSelectedVideoSettings()
                AppController.runManualStage("render")
            }
            onPauseRequested: AppController.stopVideo()
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
                SplitView.minimumHeight: 360
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
                    resultAudioSource: AppController.editorPreviewAudioSource
                    thumbnailSource: AppController.videoThumbnailSource
                    previewBusy: AppController.editorPreviewBusy
                    previewProgress: AppController.editorPreviewProgress
                }

                ManualStageInspector {
                    SplitView.fillHeight: true
                    SplitView.preferredWidth: Math.max(286, Math.min(330, root.width * 0.18))
                    SplitView.minimumWidth: 280
                    currentStage: root.selectedStageIndex
                    completedStages: root.completedStages
                    subtitleSegments: root.segments
                    selectedSubtitleIndex: root.selectedSubtitleIndex
                    onSubtitleSelected: function(index) {
                        root.selectedSubtitleIndex = index;
                        if (index >= 0 && index < root.segments.length)
                            comparePreview.seekTo(Number(root.segments[index].start || 0));
                    }
                    onSubtitleTextCommitted: function(index, text) {
                        root.commitSubtitleText(index, text);
                    }
                }
            }

            SubtitleTimeline {
                visible: root.segments.length > 0
                SplitView.fillWidth: true
                SplitView.preferredHeight: 230
                SplitView.minimumHeight: 170
                segments: root.segments
                selectedIndex: root.selectedSubtitleIndex
                duration: Math.max(0.1, comparePreview.durationSeconds)
                position: comparePreview.positionSeconds
                thumbnailSource: AppController.videoThumbnailSource
                onSegmentSelected: function(index) {
                    root.selectedSubtitleIndex = index;
                    if (index >= 0 && index < root.segments.length)
                        comparePreview.seekTo(Number(root.segments[index].start || 0));
                }
                onSeekRequested: function(seconds) {
                    comparePreview.seekTo(seconds);
                }
                onTimingCommitted: function(index, start, end) {
                    root.commitSubtitleTiming(index, start, end);
                }
            }
        }
    }
}
