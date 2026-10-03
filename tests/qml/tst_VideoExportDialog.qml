pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 900
    height: 800
    Component {
        id: controllerComponent
        QtObject {
            property bool videoExportBusy: false
            property int exportCalls: 0
            property string lastVideo: ""
            property string lastDestination: ""
            property bool lastOverwrite: false
            property bool succeeds: true
            function manualExportSettings() {
                return {videoId: "stable-video", filename: "Dự án.mp4", preset: "source", ready: true,
                    presets: [{value: "source", label: qsTr("Theo nguồn")}, {value: "720p", label: qsTr("HD 720p")}]};
            }
            function exportVideoTo(video, preset, destination, overwrite) {
                exportCalls++;
                lastVideo = video;
                lastDestination = destination;
                lastOverwrite = overwrite;
                return succeeds;
            }
        }
    }
    Component { id: dialogComponent; VideoExportDialog { preferredWidth: 600 } }
    TestCase {
        name: "VideoExportDialogTests"
        when: windowShown
        function makeDialog() {
            let controller = createTemporaryObject(controllerComponent, root);
            verify(!!controller, "Object exists");
            let app = createTemporaryObject(dialogComponent, root, {controller: controller});
            verify(!!app, "Component exists");
            app.openForSelection();
            tryCompare(app, "opened", true);
            return app;
        }
        function test_opening_does_not_export() {
            let app = makeDialog();
            compare(app.configuration.videoId, "stable-video");
            compare(app.controller.exportCalls, 0);
            compare(app.destination, qsTr(""));
        }
        function test_native_replacement_approval_needs_no_second_checkbox() {
            let app = makeDialog();
            let confirm = findChild(app, "confirmVideoExport");
            verify(!!confirm, "Object exists");
            compare(confirm.enabled, false);
            app.destination = "C:/Exports/Dự án.mp4";
            tryCompare(confirm, "enabled", true);
            app.destinationExists = true;
            tryCompare(confirm, "enabled", true);
            mouseClick(confirm);
            tryCompare(app.controller, "exportCalls", 1);
            tryCompare(app.controller, "lastOverwrite", true);
        }
        function test_confirm_exports_once_then_closes() {
            let app = makeDialog();
            app.destination = "C:/Exports/Dự án.mp4";
            let confirm = findChild(app, "confirmVideoExport");
            verify(!!confirm, "Object exists");
            tryCompare(confirm, "enabled", true);
            mouseClick(confirm);
            tryCompare(app.controller, "exportCalls", 1);
            tryCompare(app.controller, "lastVideo", "stable-video");
            tryCompare(app.controller, "lastDestination", app.destination);
            tryCompare(app, "visible", false);
        }
        function test_failure_keeps_confirmation_open() {
            let app = makeDialog();
            app.controller.succeeds = false;
            app.destination = "C:/Exports/Không ghi được.mp4";
            let confirm = findChild(app, "confirmVideoExport");
            verify(!!confirm, "Object exists");
            mouseClick(confirm);
            tryCompare(app.controller, "exportCalls", 1);
            tryCompare(app, "visible", true);
        }
        function test_busy_prevents_second_export() {
            let app = makeDialog();
            app.destination = "C:/Exports/video.mp4";
            app.controller.videoExportBusy = true;
            let confirm = findChild(app, "confirmVideoExport");
            verify(!!confirm, "Object exists");
            tryCompare(confirm, "enabled", false);
            mouseClick(confirm);
            tryCompare(app.controller, "exportCalls", 0);
        }
    }
}
