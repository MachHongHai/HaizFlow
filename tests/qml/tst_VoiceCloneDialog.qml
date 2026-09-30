pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 720
    height: 560
    readonly property string sample: Qt.resolvedUrl("../../src/haizflow/desktop/assets/voice_samples/omnivoice/omnivoice_female/en.mp3").toString().replace(/^file:\/\/\//, "")
    Component {
        id: controllerComponent
        QtObject {
            property string selectedVideoId: "video-one"
            property string ttsProvider: "omnivoice-gpu"
            property string voiceCloneReferencePath: root.sample
            property bool active: false
            property int applyCalls: 0
            property bool applyResult: true
            signal selectedVideoChanged()
            function voiceCloneReferenceAnalysis(path, bars) { return {peaks: [0.2, 0.5], durationMs: 7000}; }
            function cancelVoiceCloneRecording() { active = false; }
            function startVoiceCloneRecording() { active = true; return true; }
            function finishVoiceCloneRecording() { active = false; voiceCloneReferencePath = root.sample; return true; }
            function voiceCloneRecordingState() { return {active: active, error: "", durationMs: 7000, peaks: [0.5]}; }
            function chooseVoiceCloneReference() { return root.sample; }
            function setVoiceCloneReference(path, transcript) { voiceCloneReferencePath = path; return true; }
            function applyVoiceCloneReference(owner, provider) { applyCalls++; return applyResult && owner === selectedVideoId; }
        }
    }
    Component { id: dialogComponent; VoiceCloneDialog { expandedWidth: 540; expandedHeight: 448 } }
    SignalSpy { id: referenceAcceptedSpy; signalName: "referenceAccepted" }

    TestCase {
        name: "VoiceCloneDialogTests"
        when: windowShown
        function makeDialog() {
            const controller = createTemporaryObject(controllerComponent, root);
            verify(!!controller, "Object exists");
            const dialog = createTemporaryObject(dialogComponent, root, {controller: controller});
            verify(!!dialog, "Component exists");
            dialog.openForSelectedVideo();
            tryCompare(dialog, "opened", true);
            return dialog;
        }
        function test_existing_sample_is_reviewable_and_applies_once() {
            const dialog = makeDialog();
            compare(dialog.screen, "record");
            referenceAcceptedSpy.target = dialog;
            referenceAcceptedSpy.clear();
            verify(dialog.acceptReference());
            verify(dialog.acceptReference());
            compare(referenceAcceptedSpy.count, 1);
            compare(dialog.controller.applyCalls, 1);
            compare(dialog.referenceCommitted, true);
        }
        function test_recording_then_apply_does_not_require_recording_again() {
            const dialog = makeDialog();
            dialog.beginRecording();
            compare(dialog.recording, true);
            dialog.finishRecording();
            compare(dialog.hasSample, true);
            verify(dialog.acceptReference());
            compare(dialog.controller.applyCalls, 1);
            compare(dialog.referenceCommitted, true);
        }
        function test_import_does_not_hide_apply_or_commit_implicitly() {
            const dialog = makeDialog();
            dialog.chooseReferenceFile();
            compare(dialog.screen, "record");
            compare(dialog.referenceCommitted, false);
            compare(dialog.controller.applyCalls, 0);
            verify(dialog.acceptReference());
            compare(dialog.controller.applyCalls, 1);
        }
        function test_close_without_apply_preserves_existing_selection() {
            const dialog = makeDialog();
            dialog.close();
            tryCompare(dialog, "visible", false);
            compare(dialog.controller.applyCalls, 0);
        }
        function test_failed_apply_stays_uncommitted() {
            const dialog = makeDialog();
            dialog.controller.applyResult = false;
            compare(dialog.acceptReference(), false);
            compare(dialog.referenceCommitted, false);
            verify(dialog.recordingError.length > 0);
        }
        function test_sample_cannot_be_applied_to_another_video() {
            const dialog = makeDialog();
            dialog.controller.selectedVideoId = "video-two";
            compare(dialog.acceptReference(), false);
            compare(dialog.controller.applyCalls, 0);
        }
    }
}
