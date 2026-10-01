pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 900
    height: 650

    Component {
        id: dialogComponent
        AppDialog {
            preferredWidth: 560
            preferredHeight: 410
            title: "Create voice"
            Item { Layout.fillHeight: true }
            VoicePicker {
                objectName: "nestedVoicePicker"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                allowVoiceClone: true
                previewEnabled: false
                currentValue: "omnivoice:clone"
                model: [
                    {voice: "omnivoice:female", label: "Natural", category: "natural"},
                    {voice: "omnivoice:clone", label: "Cloned voice", category: "clone"}
                ]
            }
        }
    }

    TestCase {
        name: "VoicePickerDialogPositionTests"
        when: windowShown

        function verifyPosition(picker, popup) {
            const point = picker.mapToItem(popup.parent, 0, 0);
            const expectedX = Math.max(8, Math.min(point.x, popup.parent.width - popup.width - 8));
            tryCompare(popup, "x", expectedX);
            tryVerify(function() {
                return popup.y >= 8 && popup.y + popup.height <= popup.parent.height - 8;
            });
            verify(popup.x > 100, "The popup is not stuck at the screen's left edge");
        }

        function test_nestedDialogAndReopenUseCurrentLayout() {
            const dialog = createTemporaryObject(dialogComponent, root);
            verify(!!dialog);
            dialog.open();
            tryCompare(dialog, "opened", true);
            const picker = findChild(dialog, "nestedVoicePicker");
            verify(!!picker);
            const popup = findChild(picker, "voicePickerPopup");
            verify(!!popup);
            mouseClick(picker, 30, 20);
            tryCompare(popup, "opened", true);
            compare(picker.activeCategory, "clone");
            verifyPosition(picker, popup);
            dialog.preferredWidth = 680;
            tryCompare(dialog, "width", 680);
            verifyPosition(picker, popup);
            popup.close();
            tryCompare(popup, "opened", false);
            dialog.x = 280;
            dialog.y = 70;
            mouseClick(picker, 30, 20);
            tryCompare(popup, "opened", true);
            verifyPosition(picker, popup);
            popup.close();
            dialog.close();
            tryCompare(dialog, "opened", false);
        }
    }
}
