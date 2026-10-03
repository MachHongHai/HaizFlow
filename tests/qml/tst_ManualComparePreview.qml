import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 1100
    height: 600
    QtObject {
        id: audio
        property real lastSeek: -1
        function seek(seconds) { lastSeek = seconds; }
        function synchronize(seconds, playing, muted) {}
    }
    QtObject {
        id: mockController
        property bool canEditSelectedVideo: true
        property var manualPreviewAudio: audio
        function browseVideo() {}
    }
    Component {
        id: previewComponent
        ManualComparePreview {
            width: 1000
            height: 540
            controller: mockController
            sequenceDurationSeconds: 100
            resultUsesSequenceTimeline: true
        }
    }
    TestCase {
        name: "ManualPreviewClockTests"
        when: windowShown
        function test_trimKeepsSourceAndSequenceClocksSeparate() {
            const preview = createTemporaryObject(previewComponent, root);
            verify(!!preview);
            preview.sourceEditDecisions = [{source_start_ms: 5000,
                source_end_ms: 105000, sequence_start_ms: 0}];
            compare(preview.sourceMsForSequence(1000), 6000);
            compare(preview.resultMsForSequence(1000), 1000);
            compare(preview.sequenceMsForResult(1000), 1000);
            preview.restorePosition(2);
            compare(audio.lastSeek, 2, "The composed audio is on the edited sequence clock");
            preview.resultUsesSequenceTimeline = false;
            compare(preview.resultMsForSequence(1000), 6000);
            compare(preview.sequenceMsForResult(6000), 1000);
        }
        function test_inlineThumbSurvivesStaleDecoderUpdate() {
            const preview = createTemporaryObject(previewComponent, root);
            verify(!!preview);
            const slider = findChild(preview, "manualPreviewSeekSlider");
            verify(!!slider);
            mousePress(slider, slider.width * .3, slider.height / 2);
            tryCompare(slider, "pressed", true);
            mouseMove(slider, slider.width * .8, slider.height / 2);
            preview.restorePosition(2);
            verify(slider.value > 70);
            mouseRelease(slider, slider.width * .8, slider.height / 2);
            tryCompare(slider, "pressed", false);
            verify(audio.lastSeek > 70, "Release must seek to the user's thumb position");
        }
    }
}
