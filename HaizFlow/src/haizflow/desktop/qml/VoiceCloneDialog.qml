pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "."

FloatingToolDialog {
    id: root

    expandedWidth: screen === "record" ? 480 : 410
    expandedHeight: screen === "record" ? (recordingError.length > 0 ? 304 : 264) : 178
    toolTitle: qsTr("Nhân bản giọng của tôi")
    toolSubtitle: ""

    property string screen: "source"
    property string samplePath: ""
    property string pendingRecordingPath: ""
    property string recordingError: ""
    property int recordingElapsedSeconds: 0
    property int sampleDurationMs: 0
    property var waveformPeaks: []
    property bool discardRecordingWhenStopped: false
    readonly property bool recording: recorder.recorderState === MediaRecorder.RecordingState
    readonly property bool samplePlaying: samplePlayer.playbackState === MediaPlayer.PlayingState
    readonly property bool samplePaused: samplePlayer.playbackState === MediaPlayer.PausedState
    readonly property bool hasSample: samplePath.length > 0
    readonly property int waveformBarCount: 48
    readonly property int playableDurationMs: samplePlayer.duration > 0 ? samplePlayer.duration : sampleDurationMs
    readonly property real playbackProgress: playableDurationMs > 0 ? Math.max(0, Math.min(1, samplePlayer.position / playableDurationMs)) : 0

    function localPath(location) {
        const decoded = decodeURIComponent(String(location || "").replace(/^file:\/\//, ""));
        return /^\/[A-Za-z]:\//.test(decoded) ? decoded.slice(1) : decoded;
    }

    function localFileUrl(path) {
        return path.length > 0 ? "file:///" + path.replace(/\\/g, "/") : "";
    }

    function formatTime(milliseconds) {
        const seconds = Math.max(0, Math.floor(milliseconds / 1000));
        return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
    }

    function releaseSamplePlayer() {
        samplePlayer.stop();
        samplePlayer.source = "";
    }

    function loadSample(path) {
        samplePath = String(path || "");
        waveformPeaks = [];
        sampleDurationMs = 0;
        if (samplePath.length === 0)
            return;
        const analysis = AppController.voiceCloneReferenceAnalysis(samplePath, waveformBarCount);
        waveformPeaks = analysis.peaks || [];
        sampleDurationMs = Math.max(0, Number(analysis.durationMs || 0));
        samplePlayer.source = localFileUrl(samplePath);
    }

    function discardPendingRecording() {
        finalizeTimer.stop();
        if (recording) {
            discardRecordingWhenStopped = true;
            recorder.stop();
            return;
        }
        if (pendingRecordingPath.length > 0)
            AppController.discardVoiceCloneRecording(pendingRecordingPath);
        pendingRecordingPath = "";
    }

    function chooseReferenceFile() {
        releaseSamplePlayer();
        const selected = AppController.chooseVoiceCloneReference();
        if (selected.length > 0 && AppController.setVoiceCloneReference(selected, ""))
            root.close();
    }

    function beginRecording() {
        releaseSamplePlayer();
        discardPendingRecording();
        recordingError = "";
        recordingElapsedSeconds = 0;
        sampleDurationMs = 0;
        samplePath = "";
        waveformPeaks = [];
        const location = AppController.prepareVoiceCloneRecording();
        if (!location || location.toString().length === 0)
            return;
        pendingRecordingPath = localPath(location);
        recorder.outputLocation = location;
        recorder.record();
    }

    function finishRecording() {
        if (recording)
            recorder.stop();
    }

    function commitRecordedSample() {
        if (pendingRecordingPath.length === 0)
            return;
        releaseSamplePlayer();
        const actualPath = localPath(recorder.actualLocation);
        const recordedPath = actualPath.length > 0 ? actualPath : pendingRecordingPath;
        if (AppController.saveRecordedVoiceCloneReference(recordedPath)) {
            pendingRecordingPath = "";
            loadSample(AppController.voiceCloneReferencePath);
            recordingError = "";
        }
    }

    function toggleSamplePlayback() {
        if (!hasSample)
            return;
        if (samplePlaying) {
            samplePlayer.pause();
            return;
        }
        if (!samplePaused || samplePlayer.source.toString().length === 0)
            samplePlayer.source = localFileUrl(samplePath);
        samplePlayer.play();
    }

    function openForSelectedVideo() {
        discardPendingRecording();
        releaseSamplePlayer();
        screen = "source";
        recordingElapsedSeconds = 0;
        recordingError = "";
        loadSample(AppController.voiceCloneReferencePath);
        open();
    }

    onClosed: {
        releaseSamplePlayer();
        discardPendingRecording();
        screen = "source";
    }

    CaptureSession {
        audioInput: AudioInput {}
        recorder: MediaRecorder {
            id: recorder
            audioBitRate: 128000

            onRecorderStateChanged: {
                if (recorder.recorderState === MediaRecorder.RecordingState) {
                    recordingTimer.start();
                    return;
                }
                recordingTimer.stop();
                if (root.discardRecordingWhenStopped) {
                    root.discardRecordingWhenStopped = false;
                    root.discardPendingRecording();
                    return;
                }
                if (root.pendingRecordingPath.length === 0)
                    return;
                root.sampleDurationMs = Math.max(root.sampleDurationMs, recorder.duration);
                // QtMultimedia releases the Windows recording handle asynchronously.
                finalizeTimer.restart();
            }

            onDurationChanged: root.sampleDurationMs = duration

            onErrorOccurred: function (error, errorString) {
                if (error !== MediaRecorder.NoError)
                    root.recordingError = errorString || qsTr("Không thể bắt đầu ghi âm bằng microphone");
            }
        }
    }

    MediaPlayer {
        id: samplePlayer
        audioOutput: AudioOutput {
            volume: 1.0
        }
        onDurationChanged: {
            if (duration > 0)
                root.sampleDurationMs = duration;
        }
    }

    Timer {
        id: recordingTimer
        interval: 1000
        repeat: true
        onTriggered: root.recordingElapsedSeconds += 1
    }

    Timer {
        id: finalizeTimer
        interval: 180
        repeat: false
        onTriggered: root.commitRecordedSample()
    }

    Item {
        anchors.fill: parent

        RowLayout {
            anchors.centerIn: parent
            spacing: Theme.space8
            visible: root.screen === "source"

            AppButton {
                Layout.preferredWidth: 142
                text: qsTr("Ghi âm")
                iconGlyph: "\uE720"
                compact: true
                tone: "primary"
                onClicked: root.screen = "record"
            }

            AppButton {
                Layout.preferredWidth: 126
                text: qsTr("Chọn tệp")
                iconGlyph: "\uE8B7"
                compact: true
                onClicked: root.chooseReferenceFile()
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.space16
            spacing: Theme.space8
            visible: root.screen === "record"

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                IconButton {
                    glyph: "\uE72B"
                    controlSize: 32
                    toolTipText: qsTr("Quay lại")
                    enabled: !root.recording
                    onClicked: {
                        root.releaseSamplePlayer();
                        root.screen = "source";
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Ghi mẫu giọng")
                    color: Theme.text
                    font.pixelSize: Theme.body
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                radius: height / 2
                color: root.recording ? Theme.interactive : Theme.surfaceStrong
                border.width: root.recording ? 0 : 1
                border.color: Theme.outlineStrong
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: Theme.space8

                    Button {
                        id: recordingControl
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        focusPolicy: Qt.TabFocus
                        Accessible.name: root.recording ? qsTr("Dừng ghi âm") : (root.hasSample ? (root.samplePlaying ? qsTr("Tạm dừng") : qsTr("Nghe lại")) : qsTr("Ghi âm"))
                        onClicked: {
                            if (root.recording)
                                root.finishRecording();
                            else if (root.hasSample)
                                root.toggleSamplePlayback();
                            else
                                root.beginRecording();
                        }

                        contentItem: AppIcon {
                            glyph: root.recording ? "\uE71A" : (root.samplePlaying ? "\uE769" : (root.hasSample ? "\uE768" : "\uE720"))
                            iconColor: root.recording ? Theme.interactive : Theme.surface
                            iconSize: 16
                        }

                        background: Rectangle {
                            radius: width / 2
                            color: recordingControl.down ? Theme.textMuted : Theme.text
                            border.width: recordingControl.activeFocus ? 2 : 0
                            border.color: Theme.focus
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 30

                        Row {
                            id: waveformRow
                            anchors.centerIn: parent
                            width: parent.width
                            height: parent.height
                            spacing: 2

                            Repeater {
                                model: root.waveformBarCount

                                Rectangle {
                                    required property int index
                                    readonly property real peak: root.recording ? 0.08 : (root.waveformPeaks.length > index ? Number(root.waveformPeaks[index]) : 0.08)
                                    width: Math.max(2, (waveformRow.width - waveformRow.spacing * (root.waveformBarCount - 1)) / root.waveformBarCount)
                                    height: 4 + Math.max(0.08, Math.min(1, peak)) * 24
                                    radius: width / 2
                                    color: root.recording || ((index + 1) / root.waveformBarCount <= root.playbackProgress) ? (root.recording ? Theme.text : Theme.interactive) : Theme.textMuted
                                    opacity: root.recording ? 0.52 : 0.82
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: root.hasSample && !root.recording && root.playableDurationMs > 0
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onPressed: function (mouse) {
                                samplePlayer.setPosition(Math.round(root.playableDurationMs * mouse.x / Math.max(1, width)));
                            }
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 54
                        Layout.preferredHeight: 32
                        radius: height / 2
                        color: root.recording ? Theme.text : Theme.surfaceElevated

                        Text {
                            anchors.centerIn: parent
                            text: root.recording ? root.formatTime(root.recordingElapsedSeconds * 1000) : root.formatTime(root.samplePlaying || root.samplePaused ? samplePlayer.position : root.playableDurationMs)
                            color: root.recording ? Theme.interactivePressed : Theme.text
                            font.pixelSize: Theme.caption
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                visible: root.recordingError.length > 0
                text: root.recordingError
                color: Theme.danger
                font.pixelSize: Theme.caption
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
                textFormat: Text.PlainText
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    Layout.fillWidth: true
                    text: root.recording ? qsTr("Đang ghi âm mẫu giọng") : (root.hasSample ? qsTr("Mẫu giọng đã sẵn sàng") : qsTr("Sẵn sàng ghi âm"))
                    color: root.recording ? Theme.interactive : Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }

                AppButton {
                    visible: root.hasSample && !root.recording
                    text: qsTr("Ghi lại")
                    compact: true
                    tone: "ghost"
                    onClicked: root.beginRecording()
                }
            }
        }
    }
}
