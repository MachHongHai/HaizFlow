pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 640
    height: 480
    Component {
        id: controllerComponent
        QtObject {
            property string appUpdateState: "current"
            property bool hasAppUpdate: false
            property string latestAppVersion: "1.1.0"
            property string currentAppVersion: "1.0.0"
            property int appUpdateDownloadProgress: 0
            property string appUpdateError: ""
            property bool appUpdateBlocked: false
            property int installCalls: 0
            property int checkCalls: 0
            function installAppUpdate() { installCalls++; appUpdateState = "downloading"; }
            function checkForAppUpdates() { checkCalls++; appUpdateState = "checking"; }
        }
    }
    Component { id: popupComponent; AppUpdatePopup { width: 380; x: 20; y: 20 } }

    TestCase {
        name: "AppUpdatePopupTests"
        when: windowShown
        function makePopup() {
            const controller = createTemporaryObject(controllerComponent, root);
            verify(!!controller, "Object exists");
            const popup = createTemporaryObject(popupComponent, root, {controller: controller});
            verify(!!popup, "Component exists");
            popup.open();
            tryCompare(popup, "opened", true);
            return popup;
        }
        function test_current_and_available_messages() {
            const popup = makePopup();
            const message = findChild(popup, "appUpdateMessage");
            verify(!!message, "Object exists");
            compare(message.text, qsTr("Hiện tại chưa có phiên bản mới, chi tiết bản cập nhật gần nhất:"));
            popup.controller.hasAppUpdate = true;
            popup.controller.appUpdateState = "available";
            tryCompare(message, "text", qsTr("Đã có phiên bản mới, hãy cập nhật ngay, chi tiết bản cập nhật xem tại:"));
        }
        function test_install_click_starts_download_and_disables_repeat() {
            const popup = makePopup();
            popup.controller.hasAppUpdate = true;
            popup.controller.appUpdateState = "available";
            const install = findChild(popup, "appUpdateInstallButton");
            verify(!!install, "Object exists");
            tryCompare(install, "visible", true);
            mouseClick(install);
            tryCompare(popup.controller, "installCalls", 1);
            tryCompare(install, "enabled", false);
        }
        function test_active_jobs_prevent_install() {
            const popup = makePopup();
            popup.controller.hasAppUpdate = true;
            popup.controller.appUpdateBlocked = true;
            const install = findChild(popup, "appUpdateInstallButton");
            verify(!!install, "Object exists");
            tryCompare(install, "enabled", false);
            mouseClick(install);
            tryCompare(popup.controller, "installCalls", 0);
        }
        function test_retry_check() {
            const popup = makePopup();
            popup.controller.appUpdateState = "error";
            const check = findChild(popup, "appUpdateCheckButton");
            verify(!!check, "Object exists");
            mouseClick(check);
            tryCompare(popup.controller, "checkCalls", 1);
            tryCompare(check, "enabled", false);
        }
    }
}
