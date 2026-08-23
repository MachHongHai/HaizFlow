pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "."

FloatingToolDialog {
    id: root
    objectName: "translationReviewDialog"
    // Keep the project/video selection stable while an auto-saved draft is open.
    // The editor is still movable and maximizable, but navigation behind it is blocked.
    modal: true
    expandedWidth: 1180
    expandedHeight: 800
    toolTitle: I18n.t("Review subtitles")
    toolSubtitle: qsTr("%1 %2").arg(segments.length).arg(I18n.t("segments"))

    property var segments: []
    property var undoStack: []
    property var redoStack: []
    property string openedSnapshot: "[]"
    property bool approvalInProgress: false
    property bool previewStarted: false
    property int selectedIndex: -1
    property real pixelsPerSecond: 90
    readonly property var selectedSegment: selectedIndex >= 0 && selectedIndex < segments.length
                                                   ? segments[selectedIndex] : null
    readonly property real contentDuration: {
        let result = Math.max(1, Number(videoPlayer.duration || 0) / 1000)
        for (let i = 0; i < segments.length; ++i)
            result = Math.max(result, Number(segments[i].end || 0))
        return result
    }
    readonly property real playheadSeconds: Number(videoPlayer.position || 0) / 1000
    readonly property var previewSegment: segmentAt(playheadSeconds) || selectedSegment

    function cloneSegments(value) { return JSON.parse(JSON.stringify(value || [])) }

    function segmentAt(secondsValue) {
        const position = Number(secondsValue || 0)
        for (let index = 0; index < segments.length; ++index) {
            if (position >= Number(segments[index].start || 0)
                    && position < Number(segments[index].end || 0))
                return segments[index]
        }
        return null
    }

    function markChanged() {
        if (visible && !approvalInProgress)
            draftSaveTimer.restart()
    }

    function formatTime(secondsValue) {
        const totalMs = Math.max(0, Math.round((Number(secondsValue) || 0) * 1000))
        const minutes = Math.floor(totalMs / 60000)
        const seconds = Math.floor((totalMs % 60000) / 1000)
        const millis = totalMs % 1000
        return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0")
            + "." + String(millis).padStart(3, "0")
    }

    function remember() {
        const history = undoStack.slice()
        history.push(cloneSegments(segments))
        if (history.length > 40)
            history.shift()
        undoStack = history
        redoStack = []
    }

    function replaceSegment(index, replacement) {
        if (index < 0 || index >= segments.length)
            return
        const next = cloneSegments(segments)
        replacement.start = Math.max(0, Number(replacement.start || 0))
        replacement.end = Math.max(replacement.start + 0.05, Number(replacement.end || 0))
        next[index] = replacement
        next.sort(function(a, b) { return Number(a.start || 0) - Number(b.start || 0) })
        segments = next
        selectedIndex = next.indexOf(replacement)
        loadSelectedText()
        markChanged()
    }

    function editSelected(field, value) {
        if (!selectedSegment)
            return
        remember()
        const updated = cloneSegments(selectedSegment)
        updated[field] = value
        replaceSegment(selectedIndex, updated)
    }

    function moveSegment(index, newStart) {
        if (index < 0 || index >= segments.length)
            return
        remember()
        const updated = cloneSegments(segments[index])
        const duration = Math.max(0.05, Number(updated.end) - Number(updated.start))
        updated.start = Math.max(0, Number(newStart))
        updated.end = updated.start + duration
        replaceSegment(index, updated)
    }

    function splitSelected() {
        if (!selectedSegment)
            return
        const splitAt = playheadSeconds
        const start = Number(selectedSegment.start || 0)
        const end = Number(selectedSegment.end || 0)
        if (splitAt <= start + 0.08 || splitAt >= end - 0.08)
            return
        remember()
        const words = String(selectedSegment.text || "").trim().split(/\s+/)
        const midpoint = Math.max(1, Math.ceil(words.length / 2))
        const first = cloneSegments(selectedSegment)
        const second = cloneSegments(selectedSegment)
        first.end = splitAt
        second.start = splitAt
        first.text = words.slice(0, midpoint).join(" ")
        second.text = words.slice(midpoint).join(" ") || first.text
        const next = cloneSegments(segments)
        next.splice(selectedIndex, 1, first, second)
        segments = next
        loadSelectedText()
        markChanged()
    }

    function deleteSelected() {
        if (!selectedSegment)
            return
        remember()
        const next = cloneSegments(segments)
        next.splice(selectedIndex, 1)
        segments = next
        selectedIndex = Math.min(selectedIndex, next.length - 1)
        loadSelectedText()
        markChanged()
    }

    function undo() {
        if (undoStack.length === 0)
            return
        const history = undoStack.slice()
        const future = redoStack.slice()
        future.push(cloneSegments(segments))
        segments = history.pop()
        undoStack = history
        redoStack = future
        selectedIndex = Math.min(selectedIndex, segments.length - 1)
        loadSelectedText()
        markChanged()
    }

    function redo() {
        if (redoStack.length === 0)
            return
        const future = redoStack.slice()
        const history = undoStack.slice()
        history.push(cloneSegments(segments))
        segments = future.pop()
        undoStack = history
        redoStack = future
        selectedIndex = Math.min(selectedIndex, segments.length - 1)
        loadSelectedText()
        markChanged()
    }

    function commitPendingText() {
        if (selectedSegment && subtitleText.text !== String(selectedSegment.text || ""))
            editSelected("text", subtitleText.text)
    }

    function loadSelectedText() {
        subtitleText.text = selectedSegment ? String(selectedSegment.text || "") : ""
    }

    function selectSegment(index) {
        if (index === selectedIndex)
            return
        commitPendingText()
        selectedIndex = index
        loadSelectedText()
    }

    function saveDraftOnClose() {
        commitPendingText()
        if (approvalInProgress || segments.length === 0)
            return
        const currentSnapshot = JSON.stringify(segments)
        if (currentSnapshot !== openedSnapshot) {
            AppController.saveTranslationReviewDraft(currentSnapshot)
            openedSnapshot = currentSnapshot
        }
    }

    function seekTo(secondsValue) {
        videoPlayer.setPosition(Math.max(0, Number(secondsValue || 0) * 1000))
    }

    onOpened: {
        segments = cloneSegments(AppController.reviewSegments)
        undoStack = []
        redoStack = []
        approvalInProgress = false
        openedSnapshot = JSON.stringify(segments)
        selectedIndex = segments.length > 0 ? 0 : -1
        loadSelectedText()
        previewStarted = false
        videoPlayer.source = AppController.selectedInputSource
        videoPlayer.setPosition(0)
    }
    onClosed: {
        videoPlayer.pause()
        saveDraftOnClose()
    }

    Shortcut {
        sequence: StandardKey.Undo
        enabled: root.visible && root.undoStack.length > 0
        onActivated: root.undo()
    }

    Shortcut {
        sequence: StandardKey.Redo
        enabled: root.visible && root.redoStack.length > 0
        onActivated: root.redo()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space12
        spacing: Theme.space8

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.space8

            Rectangle {
                Layout.preferredWidth: Math.min(560, root.width * 0.52)
                Layout.fillHeight: true
                color: Theme.video
                radius: Theme.radiusSmall
                border.width: 1
                border.color: Theme.outline
                clip: true

                Image {
                    anchors.fill: parent
                    anchors.margins: 1
                    source: AppController.videoThumbnailSource
                    sourceSize.width: 960
                    sourceSize.height: 540
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    visible: !root.previewStarted && status === Image.Ready
                    z: 1
                }

                VideoOutput {
                    id: reviewVideoOutput
                    anchors.fill: parent
                    anchors.margins: 1
                    fillMode: VideoOutput.PreserveAspectFit
                }

                Text {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: Theme.space20
                    anchors.rightMargin: Theme.space20
                    anchors.bottomMargin: 72
                    visible: root.previewSegment !== null
                    text: root.previewSegment ? String(root.previewSegment.text || "") : ""
                    color: Theme.textOnDark
                    font.pixelSize: Math.max(22, Math.min(38, parent.width / 16))
                    font.weight: Font.Bold
                    style: Text.Outline
                    styleColor: "#CC000000"
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    textFormat: Text.PlainText
                    z: 3
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 54
                    color: Theme.scrim
                    z: 4
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.space8
                        spacing: Theme.space8
                        IconButton {
                            glyph: videoPlayer.playbackState === MediaPlayer.PlayingState ? "\uE769" : "\uE768"
                            toolTipText: videoPlayer.playbackState === MediaPlayer.PlayingState ? I18n.t("Pause") : I18n.t("Play")
                            onClicked: videoPlayer.playbackState === MediaPlayer.PlayingState ? videoPlayer.pause() : videoPlayer.play()
                        }
                        Text {
                            Layout.preferredWidth: 78
                            text: root.formatTime(root.playheadSeconds)
                            color: Theme.textOnDark
                            font.pixelSize: Theme.caption
                            font.family: "Consolas"
                        }
                        Slider {
                            Layout.fillWidth: true
                            from: 0
                            to: Math.max(1, root.contentDuration)
                            value: root.playheadSeconds
                            onMoved: root.seekTo(value)
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.surfaceElevated
                radius: Theme.radiusSmall
                border.width: 1
                border.color: Theme.outline
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space12
                    spacing: Theme.space8
                    Text {
                        text: root.selectedSegment ? I18n.t("Segment") + " " + String(root.selectedIndex + 1)
                                                   : I18n.t("No subtitle selected")
                        color: Theme.text
                        font.pixelSize: Theme.h3
                        font.weight: Font.DemiBold
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        enabled: root.selectedSegment !== null
                        spacing: Theme.space8
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { text: I18n.t("Start"); color: Theme.textMuted; font.pixelSize: Theme.caption }
                            SpinBox {
                                Layout.fillWidth: true
                                from: 0; to: 86400000; stepSize: 10
                                value: root.selectedSegment ? Math.round(Number(root.selectedSegment.start) * 1000) : 0
                                textFromValue: function(value) { return root.formatTime(value / 1000) }
                                valueFromText: function(text) { return Math.round(parseFloat(text) * 1000) || 0 }
                                onValueModified: root.editSelected("start", value / 1000)
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { text: I18n.t("End"); color: Theme.textMuted; font.pixelSize: Theme.caption }
                            SpinBox {
                                Layout.fillWidth: true
                                from: 50; to: 86400000; stepSize: 10
                                value: root.selectedSegment ? Math.round(Number(root.selectedSegment.end) * 1000) : 50
                                textFromValue: function(value) { return root.formatTime(value / 1000) }
                                valueFromText: function(text) { return Math.round(parseFloat(text) * 1000) || 50 }
                                onValueModified: root.editSelected("end", value / 1000)
                            }
                        }
                    }
                    TextArea {
                        id: subtitleText
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        enabled: root.selectedSegment !== null
                        text: ""
                        placeholderText: I18n.t("Subtitle text")
                        wrapMode: TextEdit.Wrap
                        selectByMouse: true
                        color: Theme.text
                        font.pixelSize: Theme.bodyLarge
                        background: Rectangle {
                            color: Theme.input
                            radius: Theme.radiusSmall
                            border.width: subtitleText.activeFocus ? 2 : 1
                            border.color: subtitleText.activeFocus ? Theme.focus : Theme.outline
                        }
                        onEditingFinished: {
                            if (root.selectedSegment && text !== String(root.selectedSegment.text || ""))
                                root.editSelected("text", text)
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        AppButton { text: I18n.t("Split at playhead"); compact: true; enabled: root.selectedSegment !== null; onClicked: root.splitSelected() }
                        AppButton { text: I18n.t("Delete segment"); compact: true; tone: "danger"; enabled: root.selectedSegment !== null; onClicked: root.deleteSelected() }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 272
            color: Theme.codeSurface
            radius: Theme.radiusSmall
            border.width: 1
            border.color: Theme.outline
            clip: true
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.space8
                spacing: Theme.space4
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: I18n.t("Video timeline"); color: Theme.text; font.pixelSize: Theme.body; font.weight: Font.DemiBold }
                    Item { Layout.fillWidth: true }
                    Text { text: I18n.t("Zoom"); color: Theme.textMuted; font.pixelSize: Theme.caption }
                    Slider { Layout.preferredWidth: 150; from: 45; to: 220; value: root.pixelsPerSecond; onMoved: root.pixelsPerSecond = value }
                }
                Flickable {
                    id: timelineFlick
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: Math.max(width, root.contentDuration * root.pixelsPerSecond + 80)
                    contentHeight: height
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    Item {
                        width: timelineFlick.contentWidth
                        height: timelineFlick.height
                        MouseArea {
                            anchors.fill: parent
                            onClicked: function(mouse) { root.seekTo((mouse.x - 68) / root.pixelsPerSecond) }
                        }
                        Row {
                            x: 68; y: 4; spacing: 0
                            Repeater {
                                model: Math.ceil(root.contentDuration) + 1
                                delegate: Item {
                                    required property int index
                                    width: root.pixelsPerSecond
                                    height: 28
                                    Rectangle { x: 0; y: 18; width: 1; height: 10; color: Theme.textSubtle }
                                    Text { x: 4; text: parent.index + "s"; color: Theme.textSubtle; font.pixelSize: Theme.label }
                                }
                            }
                        }
                        Text { x: 4; y: 49; text: I18n.t("Video"); color: Theme.textMuted; font.pixelSize: Theme.label }
                        Rectangle {
                            x: 68; y: 36; width: parent.width - 68; height: 52
                            color: Theme.video; border.width: 1; border.color: Theme.divider; clip: true
                            Row {
                                anchors.fill: parent
                                Repeater {
                                    model: Math.max(1, Math.ceil((timelineFlick.contentWidth - 68) / 120))
                                    delegate: Image {
                                        required property int index
                                        width: 120; height: 52
                                        source: AppController.videoThumbnailSource
                                        sourceSize.width: 240; sourceSize.height: 104
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true
                                        opacity: 0.72
                                    }
                                }
                            }
                        }
                        Text { x: 4; y: 126; text: I18n.t("Subtitles"); color: Theme.textMuted; font.pixelSize: Theme.label }
                        Rectangle { x: 68; y: 96; width: parent.width - 68; height: 100; color: Theme.surface; border.width: 1; border.color: Theme.divider }
                        Repeater {
                            model: root.segments
                            delegate: Rectangle {
                                id: clip
                                required property int index
                                required property var modelData
                                x: 68 + Number(modelData.start || 0) * root.pixelsPerSecond
                                y: 104
                                width: Math.max(24, (Number(modelData.end || 0) - Number(modelData.start || 0)) * root.pixelsPerSecond)
                                height: 78
                                radius: Theme.radiusTiny
                                color: index === root.selectedIndex ? Theme.interactiveMuted : Theme.blueMuted
                                border.width: index === root.selectedIndex ? 2 : 1
                                border.color: index === root.selectedIndex ? Theme.focus : Theme.blueOutline
                                z: 2
                                Text {
                                    anchors.fill: parent
                                    anchors.margins: 7
                                    text: String(clip.modelData.text || "")
                                    color: Theme.text
                                    font.pixelSize: Theme.caption
                                    wrapMode: Text.Wrap
                                    elide: Text.ElideRight
                                    maximumLineCount: 3
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.SizeAllCursor
                                    drag.target: clip
                                    drag.axis: Drag.XAxis
                                drag.minimumX: 68
                                    drag.maximumX: timelineFlick.contentWidth - clip.width
                                    onPressed: root.selectSegment(clip.index)
                                    onDoubleClicked: root.seekTo(Number(clip.modelData.start || 0))
                                    onReleased: root.moveSegment(clip.index, (clip.x - 68) / root.pixelsPerSecond)
                                }
                            }
                        }
                        Rectangle { x: 68 + root.playheadSeconds * root.pixelsPerSecond; y: 22; width: 2; height: 180; color: Theme.danger; z: 4 }
                    }
                    ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            AppButton { text: I18n.t("Undo"); compact: true; enabled: root.undoStack.length > 0; onClicked: root.undo() }
            AppButton { text: I18n.t("Redo"); compact: true; enabled: root.redoStack.length > 0; onClicked: root.redo() }
            Item { Layout.fillWidth: true }
            AppButton {
                text: AppController.selectedStatus === "done"
                    ? I18n.t("Save and regenerate voice")
                    : I18n.t("Approve and continue")
                tone: "primary"
                enabled: root.segments.length > 0
                onClicked: {
                    root.commitPendingText()
                    if (AppController.approveTranslationReview(JSON.stringify(root.segments))) {
                        root.approvalInProgress = true
                        root.close()
                    }
                }
            }
        }
    }

    MediaPlayer {
        id: videoPlayer
        videoOutput: reviewVideoOutput
        audioOutput: AudioOutput { volume: 0.75 }
        onPlaybackStateChanged: {
            if (playbackState === MediaPlayer.PlayingState)
                root.previewStarted = true
        }
    }

    Timer {
        id: draftSaveTimer
        interval: 500
        repeat: false
        onTriggered: root.saveDraftOnClose()
    }
}
