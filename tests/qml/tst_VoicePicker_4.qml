pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/hflow/desktop/qml"

Item {
    id: root
    width: 800
    height: 600

    Component {
        id: pickerComponent
        VoicePicker {
            width: 420
            height: 42
            allowVoiceClone: true
            allowMultipleSpeakers: true
            previewEnabled: false
            model: [
                {voice: "vieneu:Hải Đăng", label: qsTr("Hải Đăng"), category: "natural"},
                {voice: "vieneu:clone", label: qsTr("Giọng của tôi"), category: "reference", available: false}
            ]
        }
    }

    SignalSpy {
        id: cloneRequestedSpy
        signalName: "cloneRequested"
    }

    TestCase {
        name: "VieNeuVoicePickerTests"
        when: windowShown

        function test_cloneUsesNativeBackendIdentifier() {
            const picker = createTemporaryObject(pickerComponent, root)
            verify(!!picker, "Component exists")
            picker.currentValue = "vieneu:clone"
            compare(picker.displayLabel(), qsTr("Giọng đã nhân bản"))
            compare(picker.specialOptions()[0].voice, "vieneu:clone")
            compare(picker.voicesIn("reference").length, 0)
        }

        function test_cloneRequestOpensRecorderWithoutChoosingPreset() {
            const picker = createTemporaryObject(pickerComponent, root)
            verify(!!picker, "Component exists")
            cloneRequestedSpy.target = picker
            cloneRequestedSpy.clear()
            picker.chooseOption(picker.specialOptions()[0])
            tryCompare(cloneRequestedSpy, "count", 1)
        }

        function test_cloneCanBeHiddenWithoutRemovingMultipleSpeakers() {
            const picker = createTemporaryObject(pickerComponent, root)
            verify(!!picker, "Component exists")
            picker.allowVoiceClone = false
            compare(picker.specialOptions().length, 1)
            compare(picker.specialOptions()[0].voice, "omnivoice:multiple")
            compare(picker.visibleOptions().length, 2)
        }

        function test_vieneuPopupClosesOnSecondClick() {
            const picker = createTemporaryObject(pickerComponent, root)
            verify(!!picker, "Component exists")
            const popup = findChild(picker, "voicePickerPopup")
            verify(!!popup, "Object exists")
            mouseClick(picker, 30, 20)
            tryCompare(popup, "opened", true)
            mouseClick(picker, 30, 20)
            tryCompare(popup, "opened", false)
        }
    }
}
