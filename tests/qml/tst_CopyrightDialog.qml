pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 800
    height: 600
    Component { id: dialogComponent; CopyrightDialog {} }
    TestCase {
        name: "CopyrightDialogTests"
        when: windowShown
        function test_open_and_escape() {
            const dialog = createTemporaryObject(dialogComponent, root);
            verify(!!dialog, "Component exists");
            dialog.open();
            tryCompare(dialog, "opened", true);
            compare(dialog.title, qsTr("Bản quyền"));
            keyClick(Qt.Key_Escape);
            tryCompare(dialog, "visible", false);
        }
        function test_reopen_preserves_identity() {
            const dialog = createTemporaryObject(dialogComponent, root);
            verify(!!dialog, "Component exists");
            dialog.open();
            tryCompare(dialog, "opened", true);
            dialog.close();
            tryCompare(dialog, "visible", false);
            dialog.open();
            tryCompare(dialog, "opened", true);
            compare(dialog.subtitle, qsTr("HaizFlow"));
        }
    }
}
