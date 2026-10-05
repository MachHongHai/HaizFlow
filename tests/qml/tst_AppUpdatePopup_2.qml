pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 640
    height: 600
    Component {
        id: controllerComponent
        QtObject {
            property string appUpdateState: "ready"
            property bool hasAppUpdate: true
            property string latestAppVersion: "0.2.0"
            property string currentAppVersion: "0.1.0"
            property int appUpdateDownloadProgress: 90
            property string appUpdateError: ""
            property bool appUpdateBlocked: false
            property int installCalls: 0
            function confirmAppUpdate(version, state) {
                if (version !== latestAppVersion || state !== appUpdateState || appUpdateBlocked) return false;
                installCalls++; appUpdateState = "restarting"; return true;
            }
            function checkForAppUpdates() { appUpdateState = "checking"; }
        }
    }
    Component { id: popupComponent; AppUpdatePopup { width: 380; x: 20; y: 20 } }
    TestCase {
        name: "DeltaUpdatePopupTests"
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
        function test_restart_is_explicit_and_blocked_by_jobs() {
            const popup = makePopup();
            const install = findChild(popup, "appUpdateInstallButton");
            verify(!!install, "Object exists");
            compare(install.text, qsTr("Khởi động lại"));
            popup.controller.appUpdateBlocked = true;
            tryCompare(install, "enabled", false);
            mouseClick(install);
            tryCompare(popup.controller, "installCalls", 0);
            popup.controller.appUpdateBlocked = false;
            tryCompare(install, "enabled", true);
            mouseClick(install);
            tryCompare(popup.controller, "installCalls", 0);
            const confirmation = findChild(popup, "appUpdateConfirmationDialog");
            verify(!!confirmation, "Object exists");
            tryCompare(confirmation, "opened", true);
            confirmation.confirmed();
            confirmation.accept();
            tryCompare(popup.controller, "installCalls", 1);
            tryCompare(popup, "state", "restarting");
        }
        function test_preparing_prevents_repeat_and_defer_preserves_state() {
            const popup = makePopup();
            const install = findChild(popup, "appUpdateInstallButton");
            verify(!!install, "Object exists");
            popup.controller.appUpdateState = "preparing";
            tryCompare(popup, "updating", true);
            tryCompare(install, "enabled", false);
            popup.controller.appUpdateState = "ready";
            popup.close();
            tryCompare(popup, "visible", false);
            compare(popup.controller.appUpdateState, "ready");
            compare(popup.controller.appUpdateDownloadProgress, 90);
        }
        function test_failed_and_rollback_keep_error_text() {
            const popup = makePopup();
            popup.controller.appUpdateState = "failed";
            popup.controller.appUpdateError = qsTr("Không đủ dung lượng đĩa");
            compare(popup.updateError(popup.controller.appUpdateError), qsTr("Không đủ dung lượng đĩa"));
            popup.controller.appUpdateState = "rolled_back";
            compare(popup.updating, false);
            compare(popup.state, "rolled_back");
        }
    }
}
