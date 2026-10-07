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
            ocrInteractive: true
            ocrLayers: [{clip_id: "ocr-source-region", enabled: true,
                start_ms: 0, duration_ms: 100000,
                region: {x_percent: 20, y_percent: 50, width_percent: 60, height_percent: 20}}]
            property var testRegionDraft: null
            onOcrLayerSelected: function(clipId) { selectedOcrLayerId = clipId; ocrEditing = true; }
            onOcrLayerRegionEdited: function(clipId, region) { testRegionDraft = region; }
        }
    }
    SignalSpy { id: regionActivationSpy; signalName: "ocrLayerSelected" }
    SignalSpy { id: regionDraftSpy; signalName: "ocrLayerRegionEdited" }
    TestCase {
        name: "ManualPreviewClockTests"
        when: windowShown

        function test_clickCoverageActivatesWithoutOpeningImageToolFirst() {
            const preview = createTemporaryObject(previewComponent, root);
            verify(!!preview, "Component exists");
            const overlay = findChild(preview, "manualResultOcrRegionOverlay");
            verify(!!overlay, "Object exists");
            overlay.videoRect = Qt.rect(0, 0, 500, 300);
            // Exercise pointer routing separately from decoder readiness.
            overlay.interactive = true;
            regionActivationSpy.target = preview;
            regionActivationSpy.clear();
            mouseClick(overlay, 250, 180);
            tryCompare(regionActivationSpy, "count", 1);
            tryCompare(preview, "ocrEditing", true);
            tryCompare(preview, "testRegionDraft", null);
        }

        function test_dragCoverageStagesDraftWithoutChangingAppliedRegion() {
            const preview = createTemporaryObject(previewComponent, root);
            verify(!!preview, "Component exists");
            const overlay = findChild(preview, "manualResultOcrRegionOverlay");
            verify(!!overlay, "Object exists");
            overlay.videoRect = Qt.rect(0, 0, 500, 300);
            overlay.interactive = true;
            regionDraftSpy.target = preview;
            regionDraftSpy.clear();
            mousePress(overlay, 250, 180);
            tryCompare(preview, "ocrEditing", true);
            mouseMove(overlay, 300, 210);
            tryCompare(regionDraftSpy, "count", 0);
            mouseRelease(overlay, 300, 210);
            tryCompare(regionDraftSpy, "count", 1);
            tryCompare(preview.testRegionDraft, "x_percent", 30);
            tryCompare(preview.testRegionDraft, "y_percent", 60);
            tryCompare(preview.ocrLayers[0].region, "x_percent", 20);
            tryCompare(preview.ocrLayers[0].region, "y_percent", 50);
        }
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
