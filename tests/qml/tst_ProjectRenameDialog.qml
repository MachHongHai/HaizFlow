pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 800
    height: 600
    Component {
        id: controllerComponent
        QtObject {
            property int renameCalls: 0
            property string lastKey: ""
            property string lastName: ""
            property bool succeeds: true
            function renameProject(key, name) {
                renameCalls++;
                lastKey = key;
                lastName = name;
                return succeeds;
            }
        }
    }
    Component { id: dialogComponent; ProjectRenameDialog { preferredWidth: 480 } }
    TestCase {
        name: "ProjectRenameDialogTests"
        when: windowShown
        function makeDialog() {
            let controller = createTemporaryObject(controllerComponent, root);
            verify(!!controller, "Object exists");
            let app = createTemporaryObject(dialogComponent, root, {controller: controller});
            verify(!!app, "Component exists");
            app.openForProject("project:stable-id", qsTr("Tên cũ"));
            tryCompare(app, "opened", true);
            return app;
        }
        function test_name_inputs_data() {
            return [{tag: "letters", name: qsTr("Dự án mới")}, {tag: "numbers", name: qsTr("12345")},
                {tag: "special", name: qsTr("Tên & Co. (2026)")}];
        }
        function test_name_inputs(data) {
            let app = makeDialog();
            let field = findChild(app, "renameProjectName");
            verify(!!field, "Object exists");
            field.focus = true;
            field.text = data.name;
            compare(field.text, data.name);
            app.submit();
            compare(app.controller.lastKey, "project:stable-id");
            compare(app.controller.lastName, data.name);
        }
        function test_empty_name_does_not_submit() {
            let app = makeDialog();
            let field = findChild(app, "renameProjectName");
            verify(!!field, "Object exists");
            field.focus = true;
            field.text = qsTr("   ");
            app.submit();
            compare(app.controller.renameCalls, 0);
            compare(app.visible, true);
        }
        function test_backend_failure_keeps_name_for_retry() {
            let app = makeDialog();
            let field = findChild(app, "renameProjectName");
            verify(!!field, "Object exists");
            app.controller.succeeds = false;
            field.focus = true;
            field.text = qsTr("Tên mới");
            app.submit();
            compare(app.controller.renameCalls, 1);
            compare(app.visible, true);
            compare(field.text, qsTr("Tên mới"));
        }
    }
}
