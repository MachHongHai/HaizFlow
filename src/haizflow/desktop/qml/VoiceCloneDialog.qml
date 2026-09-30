pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtMultimedia
import "."

FloatingToolDialog {
    id: root

    expandedWidth: screen === "record" ? 540 : 410
    expandedHeight: screen === "record" ? (recordingError.length > 0 ? 408 : 372) : 178
    toolTitle: qsTr("Nhân bản giọng của tôi")
    toolSubtitle: ""

    property string screen: "source"
    property string samplePath: ""
    property string recordingError: ""
    property int recordingElapsedMs: 0
    property int sampleDurationMs: 0
    property var waveformPeaks: []
    property var livePeaks: []
    property bool recording: false
    signal referenceAccepted(string path)
    readonly property bool samplePlaying: samplePlayer.playbackState === MediaPlayer.PlayingState
    readonly property bool samplePaused: samplePlayer.playbackState === MediaPlayer.PausedState
    readonly property bool hasSample: samplePath.length > 0
    readonly property int waveformBarCount: 48
    readonly property int playableDurationMs: samplePlayer.duration > 0 ? samplePlayer.duration : sampleDurationMs
    readonly property real playbackProgress: playableDurationMs > 0 ? Math.max(0, Math.min(1, samplePlayer.position / playableDurationMs)) : 0

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

    function chooseReferenceFile() {
        releaseSamplePlayer();
        const selected = AppController.chooseVoiceCloneReference();
        if (selected.length > 0 && AppController.setVoiceCloneReference(selected, "")) {
            referenceAccepted(String(AppController.voiceCloneReferencePath || ""));
            root.close();
        }
    }

    function beginRecording() {
        releaseSamplePlayer();
        recordingError = "";
        recordingElapsedMs = 0;
        livePeaks = [];
        if (!AppController.startVoiceCloneRecording()) {
            recordingError = String(AppController.voiceCloneRecordingState().error || "");
            return;
        }
        recording = true;
        recordingTimer.start();
    }

    function finishRecording() {
        if (!recording)
            return;
        recordingTimer.stop();
        recording = false;
        if (AppController.finishVoiceCloneRecording()) {
            loadSample(AppController.voiceCloneReferencePath);
            recordingError = "";
        } else {
            recordingError = String(AppController.voiceCloneRecordingState().error || qsTr("Không thể lưu mẫu ghi âm. Hãy ghi lại."));
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
        recordingTimer.stop();
        AppController.cancelVoiceCloneRecording();
        releaseSamplePlayer();
        recording = false;
        screen = "source";
        recordingElapsedMs = 0;
        recordingError = "";
        loadSample(AppController.voiceCloneReferencePath);
        open();
    }

    onClosed: {
        recordingTimer.stop();
        AppController.cancelVoiceCloneRecording();
        recording = false;
        releaseSamplePlayer();
        screen = "source";
    }

    MediaPlayer {
        id: samplePlayer
        audioOutput: AudioOutput { volume: 1.0 }
        onDurationChanged: {
            if (duration > 0)
                root.sampleDurationMs = duration;
        }
    }

    Timer {
        id: recordingTimer
        interval: 80
        repeat: true
        onTriggered: {
            const state = AppController.voiceCloneRecordingState();
            root.livePeaks = state.peaks || [];
            root.recordingElapsedMs = Number(state.durationMs || 0);
            if (!state.active || String(state.error || "").length > 0) {
                stop();
                root.recording = false;
                root.recordingError = String(state.error || qsTr("Ghi âm đã dừng. Hãy thử lại."));
            }
        }
    }

    Item {
        anchors.fill: parent

        RowLayout {
            anchors.centerIn: parent
            spacing: Theme.space8
            visible: root.screen === "source"

            StudioButton {
                Layout.preferredWidth: 142
                text: qsTr("Ghi âm")
                iconGlyph: "\uE720"
                variant: "primary"
                onClicked: root.screen = "record"
            }

            StudioButton {
                Layout.preferredWidth: 126
                text: qsTr("Chọn tệp")
                iconGlyph: "\uE8B7"
                onClicked: root.chooseReferenceFile()
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.space20
            spacing: Theme.space12
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
                        AppController.cancelVoiceCloneRecording();
                        root.screen = "source";
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Ghi mẫu giọng")
                        color: Theme.text
                        font.pixelSize: TypeScale.control
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Đọc rõ 5–15 giây bằng giọng tự nhiên.")
                        color: Theme.textMuted
                        font.pixelSize: TypeScale.metadata
                        textFormat: Text.PlainText
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 110
                radius: Theme.radius
                color: Theme.surfaceStrong
                border.width: 1
                border.color: Theme.outlineStrong

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space12
                    spacing: Theme.space8

                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 56

                        Row {
                            id: waveformRow
                            anchors.centerIn: parent
                            width: parent.width
                            height: parent.height
                            spacing: 3

                            Repeater {
                                model: root.waveformBarCount
                                Rectangle {
                                    required property int index
                                    readonly property real peak: root.recording
                                        ? (root.livePeaks.length > index ? Number(root.livePeaks[index]) : 0.04)
                                        : (root.waveformPeaks.length > index ? Number(root.waveformPeaks[index]) : 0.04)
                                    width: Math.max(2, (waveformRow.width - waveformRow.spacing * (root.waveformBarCount - 1)) / root.waveformBarCount)
                                    height: 4 + Math.max(0.04, Math.min(1, peak)) * 48
                                    radius: width / 2
                                    color: root.recording || ((index + 1) / root.waveformBarCount <= root.playbackProgress)
                                        ? Theme.interactive : Theme.textMuted
                                    opacity: root.recording || root.hasSample ? 1 : 0.45
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

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: root.recording ? qsTr("Đang ghi") : (root.hasSample ? qsTr("Nghe lại mẫu") : qsTr("Microphone"))
                            color: root.recording ? Theme.interactive : Theme.textMuted
                            font.pixelSize: TypeScale.metadata
                            textFormat: Text.PlainText
                        }
                        Text {
                            text: root.formatTime(root.recording ? root.recordingElapsedMs
                                : root.samplePlaying || root.samplePaused ? samplePlayer.position : root.playableDurationMs)
                            color: Theme.text
                            font.pixelSize: TypeScale.metadata
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                visible: root.recordingError.length > 0
                text: root.recordingError
                color: Theme.danger
                font.pixelSize: TypeScale.metadata
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    Layout.fillWidth: true
                    text: root.recording ? qsTr("Nhấn dừng để dùng mẫu này")
                        : root.hasSample ? qsTr("Mẫu đã lưu. Nhấn Áp dụng để chọn giọng nhân bản.")
                        : qsTr("Chỉ dùng giọng của bạn hoặc người đã đồng ý")
                    color: Theme.textMuted
                    font.pixelSize: TypeScale.metadata
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }

                StudioButton {
                    visible: root.hasSample && !root.recording
                    text: qsTr("Ghi lại")
                    variant: "ghost"
                    onClicked: root.beginRecording()
                }

                StudioButton {
                    text: root.recording ? qsTr("Dừng ghi")
                        : root.hasSample ? (root.samplePlaying ? qsTr("Tạm dừng") : qsTr("Nghe lại")) : qsTr("Bắt đầu ghi")
                    iconGlyph: root.recording ? "\uE71A" : root.hasSample ? "\uE768" : "\uE720"
                    variant: "primary"
                    onClicked: {
                        if (root.recording)
                            root.finishRecording();
                        else if (root.hasSample)
                            root.toggleSamplePlayback();
                        else
                            root.beginRecording();
                    }
                }
            }

            StudioButton {
                Layout.fillWidth: true
                visible: root.hasSample && !root.recording
                text: qsTr("Áp dụng giọng nhân bản")
                variant: "primary"
                onClicked: {
                    root.referenceAccepted(root.samplePath);
                    root.close();
                }
            }
        }
    }
}
