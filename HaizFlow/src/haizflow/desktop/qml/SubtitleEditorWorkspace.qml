pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property var segments: []
    property var selectedSegment: null
    property int selectedIndex: -1
    property real duration: 0
    property real position: 0
    property string thumbnailSource: ""
    property bool previewReady: false
    property bool statusVisible: false
    property bool previewBusy: false
    property real previewProgress: 0
    property string previewStatusText: ""
    property bool playing: false
    property bool canUndo: false
    property bool canRedo: false
    property bool canCommit: false
    property string primaryText: ""
    property alias videoOutput: editorPreview.videoOutput

    signal playbackToggled()
    signal scrubStarted(real position)
    signal scrubbed(real position)
    signal scrubFinished(real position)
    signal fullscreenRequested()
    signal previousRequested()
    signal nextRequested()
    signal textCommitted(string value)
    signal segmentSelected(int index)
    signal seekRequested(real seconds)
    signal timingCommitted(int index, real start, real end)
    signal undoRequested()
    signal redoRequested()
    signal commitRequested()

    function commitPendingText() {
        editorInspector.commitPendingText()
    }

    function setEditorText(value) {
        editorInspector.setEditorText(value)
    }

    spacing: Theme.space8

    SplitView {
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
                color: parent.SplitHandle.hovered || parent.SplitHandle.pressed ? Theme.focus : Theme.outlineStrong
            }
        }

        SplitView {
            SplitView.fillWidth: true
            SplitView.fillHeight: true
            SplitView.minimumHeight: 280
            orientation: Qt.Horizontal

            handle: Rectangle {
                implicitWidth: 8
                color: SplitHandle.hovered || SplitHandle.pressed ? Theme.interactiveMuted : "transparent"

                Rectangle {
                    anchors.centerIn: parent
                    width: 3
                    height: 52
                    radius: 2
                    color: parent.SplitHandle.hovered || parent.SplitHandle.pressed ? Theme.focus : Theme.outlineStrong
                }
            }

            SubtitleEditorPreview {
                id: editorPreview
                SplitView.fillWidth: true
                SplitView.preferredWidth: root.width * 0.78
                SplitView.minimumWidth: 520
                SplitView.fillHeight: true
                thumbnailSource: root.thumbnailSource
                previewReady: root.previewReady
                statusVisible: root.statusVisible
                busy: root.previewBusy
                progress: root.previewProgress
                statusText: root.previewStatusText
                position: root.position
                duration: root.duration
                playing: root.playing
                onPlaybackToggled: root.playbackToggled()
                onScrubStarted: function(value) { root.scrubStarted(value) }
                onScrubbed: function(value) { root.scrubbed(value) }
                onScrubFinished: function(value) { root.scrubFinished(value) }
                onFullscreenRequested: root.fullscreenRequested()
            }

            SubtitleEditorInspector {
                id: editorInspector
                SplitView.preferredWidth: Math.max(280, Math.min(360, root.width * 0.22))
                SplitView.minimumWidth: 280
                SplitView.maximumWidth: 380
                SplitView.fillHeight: true
                segment: root.selectedSegment
                selectedIndex: root.selectedIndex
                segmentCount: root.segments.length
                onPreviousRequested: root.previousRequested()
                onNextRequested: root.nextRequested()
                onTextCommitted: function(value) { root.textCommitted(value) }
            }
        }

        SubtitleTimeline {
            SplitView.fillWidth: true
            SplitView.preferredHeight: 250
            SplitView.minimumHeight: 170
            segments: root.segments
            selectedIndex: root.selectedIndex
            duration: root.duration
            position: root.position
            thumbnailSource: root.thumbnailSource
            onSegmentSelected: function(index) { root.segmentSelected(index) }
            onSeekRequested: function(seconds) { root.seekRequested(seconds) }
            onTimingCommitted: function(index, start, end) { root.timingCommitted(index, start, end) }
        }
    }

    SubtitleEditorCommandBar {
        Layout.fillWidth: true
        canUndo: root.canUndo
        canRedo: root.canRedo
        canCommit: root.canCommit
        primaryText: root.primaryText
        onUndoRequested: root.undoRequested()
        onRedoRequested: root.redoRequested()
        onCommitRequested: root.commitRequested()
    }
}
