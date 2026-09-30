pragma ComponentBehavior: Bound
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
            width: 600
            height: 42
            x: 260
            y: 520
            previewEnabled: false
            currentValue: "omnivoice:female"
            model: [{voice: "omnivoice:female", label: qsTr("Nữ tự nhiên"), category: "natural"}]
        }
    }
    TestCase {
        name: "VoicePickerTests"
        when: windowShown

        function test_popupFitsAndStaysNearTrigger() {
            const picker = createTemporaryObject(pickerComponent, root);
            verify(!!picker, "Component exists");
            const popup = findChild(picker, "voicePickerPopup");
            verify(!!popup, "Object exists");
            mouseClick(picker, 30, 20);
            tryCompare(popup, "opened", true);
            tryVerify(function() {
                return popup.x >= 8 && popup.y >= 8
                    && popup.x + popup.width <= popup.parent.width - 8
                    && popup.y + popup.height <= popup.parent.height - 8;
            });
            tryCompare(popup, "width", 440);
            tryCompare(popup, "x", Math.min(picker.x, popup.parent.width - 448));
            popup.close();
            tryCompare(popup, "opened", false);
        }

        function test_cloneLabelDoesNotFallBackToPreset() {
            const picker = createTemporaryObject(pickerComponent, root);
            verify(!!picker, "Component exists");
            picker.currentValue = "omnivoice:clone";
            compare(picker.displayLabel(), qsTr("Giọng đã nhân bản"));
        }
    }
}
