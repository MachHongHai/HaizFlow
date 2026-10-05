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
            function confirmAppUpdate(version, state) {
                if (version !== latestAppVersion || state !== appUpdateState) return false;
                installCalls++; appUpdateState = "downloading"; return true;
            }
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
            compare(message.message, qsTr("Bạn đang dùng phiên bản mới nhất. Xem chi tiết tại:"));
            compare(message.textFormat, Text.RichText);
            verify(message.text.indexOf('<a href="https://haizflow.pages.dev/"') >= 0);
            verify(message.text.indexOf('color: ' + Theme.interactive) >= 0);
            verify(!findChild(popup, "appUpdateLandingLink"), "Landing page is an inline link, not a button");
            popup.controller.hasAppUpdate = true;
            popup.controller.appUpdateState = "available";
            tryCompare(message, "message", qsTr("Có phiên bản mới. Xem thay đổi tại:"));
        }
        function test_install_click_requires_confirmation_then_disables_repeat() {
            const popup = makePopup();
            popup.controller.hasAppUpdate = true;
            popup.controller.appUpdateState = "available";
            const install = findChild(popup, "appUpdateInstallButton");
            verify(!!install, "Object exists");
            tryCompare(install, "visible", true);
            mouseClick(install);
            tryCompare(popup.controller, "installCalls", 0);
            const confirmation = findChild(popup, "appUpdateConfirmationDialog");
            verify(!!confirmation, "Object exists");
            tryCompare(confirmation, "opened", true);
            confirmation.confirmed();
            confirmation.accept();
            tryCompare(popup.controller, "installCalls", 1);
            tryCompare(install, "enabled", false);
        }
        function test_cancel_confirmation_does_not_download() {
            const popup = makePopup();
            popup.controller.hasAppUpdate = true;
            popup.controller.appUpdateState = "available";
            const install = findChild(popup, "appUpdateInstallButton");
            verify(!!install, "Object exists");
            mouseClick(install);
            const confirmation = findChild(popup, "appUpdateConfirmationDialog");
            verify(!!confirmation, "Object exists");
            tryCompare(confirmation, "opened", true);
            confirmation.reject();
            tryCompare(popup.controller, "installCalls", 0);
            tryCompare(popup, "state", "available");
        }
        function test_active_jobs_prevent_install() {
            const popup = makePopup();
            popup.controller.hasAppUpdate = true;
            popup.controller.appUpdateBlocked = true;
            popup.controller.appUpdateState = "ready";
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
