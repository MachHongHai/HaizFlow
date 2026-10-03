import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 900
    height: 650

    Component {
        id: pickerComponent
        VoicePicker {
            width: 420
            height: 42
            previewEnabled: false
            model: [{voice: "omnivoice:male", label: qsTr("Nam tự nhiên"), category: "natural"}]
        }
    }

    TestCase {
        name: "VoicePickerSpecialOptionsTests"
        when: windowShown
        SignalSpy { id: cloneSpy; signalName: "cloneRequested" }

        function test_specialOptionsDoNotAddCategories() {
            const picker = createTemporaryObject(pickerComponent, root);
            verify(!!picker, "Component exists");
            picker.allowVoiceClone = true;
            picker.allowMultipleSpeakers = true;
            compare(picker.specialOptions().length, 2);
            compare(picker.categories().length, 1);
            picker.currentValue = "omnivoice:multiple";
            compare(picker.activeCategory, "natural");
            compare(picker.voicesIn("natural").length, 1);
        }

        function test_missingCloneOpensRecorderWithoutSelectingPreset() {
            const picker = createTemporaryObject(pickerComponent, root);
            verify(!!picker, "Component exists");
            cloneSpy.target = picker;
            cloneSpy.clear();
            picker.allowVoiceClone = true;
            picker.chooseOption(picker.specialOptions()[0]);
            compare(cloneSpy.count, 1);
            compare(picker.currentValue, "");
        }

        function test_availableCloneAlsoOpensRecorder() {
            const picker = createTemporaryObject(pickerComponent, root);
            verify(!!picker, "Component exists");
            cloneSpy.target = picker;
            cloneSpy.clear();
            picker.allowVoiceClone = true;
            picker.model = [{voice: "omnivoice:clone", category: "clone", available: true}];
            picker.chooseOption(picker.specialOptions()[0]);
            compare(cloneSpy.count, 1);
            compare(picker.currentValue, "");
            compare(picker.categories().length, 0);
        }

        function test_cloneCannotRequestLibraryPreview() {
            const picker = createTemporaryObject(pickerComponent, root);
            verify(!!picker, "Component exists");
            picker.previewEnabled = true;
            picker.togglePreview("omnivoice:clone");
            compare(picker.requestedVoice, "");
        }
    }
}
