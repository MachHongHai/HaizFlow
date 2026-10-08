import json
import hashlib
import sys
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, Mock

from PySide6.QtCore import QObject, Signal

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.app_update_controller import AppUpdateController, installer_asset, version_key


class Host(QObject):
    appUpdateAvailable = Signal()
    appAlertRequested = Signal(str, str, str)


class Response(BytesIO):
    def geturl(self):
        return "https://release-assets.githubusercontent.com/installer.exe"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class AppUpdateControllerTests(unittest.TestCase):
    def test_current_release_clears_badge_and_cannot_launch_repeat_update(self):
        controller = AppUpdateController(Host())
        controller._latest_version = "0.1.5"
        controller._state = "available"
        with patch("haizflow.desktop.app_update_controller.__version__", "0.1.5"):
            controller._apply_event({"kind": "result", "available": True, "version": "0.1.5",
                                     "notes": "", "url": ""})
            self.assertEqual(controller.state, "current")
            self.assertFalse(controller.available)
            with patch("haizflow.desktop.app_update_controller.subprocess.Popen") as launch:
                self.assertFalse(controller.install())
                launch.assert_not_called()

    def test_task_changes_refresh_update_blocked_binding_without_update_events(self):
        host = Host()
        controller = AppUpdateController(host)
        changes = []
        controller.changed.connect(lambda: changes.append(controller.blocked))
        controller.drain_events()
        host.isProcessing = True
        controller.drain_events()
        controller.drain_events()
        host.isProcessing = False
        controller.drain_events()
        self.assertEqual(changes, [False, True, False])

    def test_confirmation_launches_independent_updater_with_versioned_request(self):
        from haizflow.update.state import Layout, provision

        controller = AppUpdateController(Host())
        controller._latest_version = "99.0.0"
        controller._state = "available"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provision(root)
            (root / "HaizFlow.exe").touch()
            (root / "updater").mkdir()
            (root / "updater/HaizFlowUpdater.exe").touch()
            controller._delta_layout = Layout(root)
            with (patch("haizflow.desktop.app_update_controller.sys.frozen", True, create=True),
                  patch("haizflow.desktop.app_update_controller.sys.platform", "win32"),
                  patch("haizflow.desktop.app_update_controller.subprocess.Popen") as launch):
                self.assertTrue(controller.confirm_install("99.0.0", "available"))
                request = json.loads((controller._delta_layout.ipc / (controller._delta_token + ".update.json")).read_text())
                self.assertEqual(request["target"], "99.0.0")
                self.assertEqual(launch.call_args.args[0], [str(root / "updater/HaizFlowUpdater.exe"),
                    "--install-root", str(root), "--request-token", request["token"]])
                self.assertFalse(list(controller._delta_layout.ipc.glob("*.activate.json")))
                self.assertEqual(controller.state, "downloading")
                self.assertFalse(controller.confirm_install("99.0.0", "available"))
                launch.assert_called_once()

    def test_confirmation_is_bound_to_version_and_action(self):
        controller = AppUpdateController(Host())
        controller._latest_version = "99.0.0"
        controller._state = "available"
        with patch.object(controller, "install", return_value=True) as install:
            self.assertFalse(controller.confirm_install("98.0.0", "available"))
            self.assertFalse(controller.confirm_install("99.0.0", "ready"))
            install.assert_not_called()
            self.assertTrue(controller.confirm_install("99.0.0", "available"))
            install.assert_called_once()
            controller._state = "downloading"
            self.assertFalse(controller.confirm_install("99.0.0", "available"))
            install.assert_called_once()

    def test_delta_download_is_blocked_when_video_or_resource_work_is_running(self):
        host = Host()
        controller = AppUpdateController(host)
        controller._delta_layout = Mock()
        controller._latest_version = "99.0.0"
        controller._state = "available"
        with patch("haizflow.desktop.app_update_controller.subprocess.Popen") as launch:
            for property_name in ("isProcessing", "resourcePackBusy", "editorPreviewBusy"):
                setattr(host, property_name, True)
                self.assertFalse(controller.confirm_install("99.0.0", "available"))
                setattr(host, property_name, False)
            launch.assert_not_called()

    def test_failed_activation_reports_error_without_closing_core(self):
        host = Host()
        notifications = []
        host.appUpdateAvailable.connect(lambda: notifications.append(True))
        controller = AppUpdateController(host)
        controller._delta_layout = Mock()
        controller._state = "ready"
        controller._latest_version = "99.0.0"
        controller._delta_token = "a" * 64
        with (patch("haizflow.update.filesystem.child", return_value=Path("unused.json")),
              patch("haizflow.update.filesystem.atomic_json", side_effect=PermissionError("Denied")),
              patch("PySide6.QtCore.QCoreApplication.quit") as quit_app):
            self.assertFalse(controller.confirm_install("99.0.0", "ready"))
            quit_app.assert_not_called()
        self.assertEqual(controller.state, "ready")
        self.assertEqual(controller.error, "Denied")
        self.assertEqual(notifications, [True])

    def test_ready_notification_emits_once_and_does_not_activate(self):
        host = Host()
        notifications = []
        host.appUpdateAvailable.connect(lambda: notifications.append(True))
        controller = AppUpdateController(host)
        controller._delta_layout = Mock()
        controller._delta_token = "a" * 64
        controller._state = "downloading"
        data = {"token": controller._delta_token, "state": "ready", "progress": 90}
        with (patch("haizflow.update.filesystem.child", return_value=Mock(exists=lambda: True)),
              patch("haizflow.update.filesystem.read_json", return_value=data),
              patch("haizflow.update.filesystem.atomic_json") as activate,
              patch("PySide6.QtCore.QCoreApplication.quit") as quit_app):
            controller.drain_events()
            controller.drain_events()
            controller.check_if_needed()
            activate.assert_not_called()
            quit_app.assert_not_called()
        self.assertEqual(controller.state, "ready")
        self.assertEqual(notifications, [True])

    def test_restart_confirmation_only_writes_permission_after_safe_confirmation(self):
        controller = AppUpdateController(Host())
        controller._delta_layout = Mock()
        controller._delta_token = "b" * 64
        controller._latest_version = "99.0.0"
        controller._state = "ready"
        with (patch("haizflow.update.filesystem.child", return_value=Path("activate.json")),
              patch("haizflow.update.filesystem.atomic_json") as activate,
              patch("PySide6.QtCore.QCoreApplication.quit") as quit_app):
            self.assertTrue(controller.confirm_install("99.0.0", "ready"))
            activate.assert_called_once_with(Path("activate.json"), {"token": "b" * 64, "activate": True})
            quit_app.assert_called_once()
            self.assertFalse(controller.confirm_install("99.0.0", "ready"))
            quit_app.assert_called_once()

    def test_version_key_compares_stable_tags(self):
        self.assertGreater(version_key("v1.2.0"), version_key("1.1.9"))
        self.assertGreater(version_key("1.2.0"), version_key("1.2.0-rc.1"))
        self.assertEqual(version_key("1.2.0+build.1"), version_key("1.2.0"))

    def test_release_result_is_applied_on_qt_thread(self):
        host = Host()
        controller = AppUpdateController(host)
        payload = {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/MachHongHai/HaizFlow/releases/tag/v99.0.0",
            "body": "Release notes",
        }
        with patch(
            "haizflow.desktop.app_update_controller.urllib.request.urlopen",
            return_value=Response(json.dumps(payload).encode("utf-8")),
        ):
            controller.check(manual=True)
            controller._thread.join(timeout=2)
            controller.drain_events()
        self.assertEqual(controller.state, "available")
        self.assertEqual(controller.latest_version, "99.0.0")

    def test_unexpected_release_url_is_rejected(self):
        host = Host()
        controller = AppUpdateController(host)
        payload = {
            "tag_name": "v99.0.0",
            "html_url": "https://example.invalid/download.exe",
        }
        with patch(
            "haizflow.desktop.app_update_controller.urllib.request.urlopen",
            return_value=Response(json.dumps(payload).encode("utf-8")),
        ):
            controller.check(manual=True)
            controller._thread.join(timeout=2)
            controller.drain_events()
        self.assertEqual(controller.state, "error")

    def test_no_published_release_is_not_reported_as_network_failure(self):
        host = Host()
        controller = AppUpdateController(host)
        notifications = []
        host.appUpdateAvailable.connect(lambda: notifications.append(True))
        with patch(
            "haizflow.desktop.app_update_controller.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("https://api.github.com/", 404, "Not Found", None, None),
        ):
            controller.check(manual=True)
            controller._thread.join(timeout=2)
            controller.drain_events()
        self.assertEqual(controller.state, "no_release")
        self.assertEqual(notifications, [True])

    def test_background_check_updates_badge_without_opening_popup(self):
        host = Host()
        controller = AppUpdateController(host)
        notifications = []
        host.appUpdateAvailable.connect(lambda: notifications.append(True))
        controller._events.put({"kind": "result", "available": True, "version": "99.0.0", "notes": "", "url": ""})
        controller.drain_events()
        self.assertTrue(controller.available)
        self.assertEqual(notifications, [])
        controller._state = "checking"
        self.assertTrue(controller.available)

    def test_only_expected_signed_installer_with_sha256_is_selected(self):
        asset = self.asset(b"installer")
        payload = {"tag_name": "v99.0.0", "assets": [dict(asset, name="HaizFlow-99.0.0-UNSIGNED-Setup.exe"), asset]}
        selected = installer_asset(payload, "99.0.0")
        self.assertEqual(selected["sha256"], asset["digest"][7:])
        for overrides in ({"digest": None}, {"browser_download_url": "https://evil.invalid/setup.exe"}, {"size": -1}):
            payload["assets"] = [dict(asset, **overrides)]
            self.assertEqual(installer_asset(payload, "99.0.0"), {})

    @staticmethod
    def asset(data):
        name = "HaizFlow-99.0.0-Setup.exe"
        return {"name": name, "browser_download_url": f"https://github.com/MachHongHai/HaizFlow/releases/download/v99.0.0/{name}",
                "size": len(data), "digest": "sha256:" + hashlib.sha256(data).hexdigest()}

    def test_verified_download_opens_installer_on_qt_thread(self):
        data = b"MZ installer bytes"
        host = Host()
        controller = AppUpdateController(host)
        controller._latest_version = "99.0.0"
        asset = installer_asset({"tag_name": "v99.0.0", "assets": [self.asset(data)]}, "99.0.0")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("haizflow.config.TMP_DIR", directory),
            patch("haizflow.desktop.app_update_controller.urllib.request.urlopen", return_value=Response(data)),
            patch("haizflow.desktop.app_update_controller.verify_installer_signature") as signature,
            patch("haizflow.desktop.app_update_controller.subprocess.Popen") as launch,
        ):
            controller._download_installer(asset)
            launch.assert_not_called()
            signature.assert_called_once()
            controller.drain_events()
            launch.assert_called_once()
            self.assertEqual(Path(launch.call_args.args[0][0]).read_bytes(), data)
            self.assertEqual(controller.state, "installing")

    def test_bad_checksum_never_launches_or_checks_signature(self):
        data = b"MZ installer bytes"
        controller = AppUpdateController(Host())
        asset = installer_asset({"tag_name": "v99.0.0", "assets": [self.asset(data)]}, "99.0.0")
        asset["sha256"] = "0" * 64
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("haizflow.config.TMP_DIR", directory),
            patch("haizflow.desktop.app_update_controller.urllib.request.urlopen", return_value=Response(data)),
            patch("haizflow.desktop.app_update_controller.verify_installer_signature") as signature,
            patch("haizflow.desktop.app_update_controller.subprocess.Popen") as launch,
        ):
            controller._download_installer(asset)
            controller.drain_events()
            signature.assert_not_called()
            launch.assert_not_called()
            self.assertFalse(list(Path(directory).rglob("*.part")))
            self.assertIn("mã kiểm tra", controller.error)

    def test_running_task_blocks_installer_even_after_download_finished(self):
        host = Host()
        host.isProcessing = True
        controller = AppUpdateController(host)
        controller._events.put({"kind": "installer_ready", "path": "unused.exe"})
        with patch("haizflow.desktop.app_update_controller.subprocess.Popen") as launch:
            controller.drain_events()
            launch.assert_not_called()
        self.assertIn("Tác vụ đang chạy", controller.error)

    def test_source_mode_does_not_launch_or_download_an_installer(self):
        controller = AppUpdateController(Host())
        controller._latest_version = "99.0.0"
        with patch("haizflow.desktop.app_update_controller.sys.frozen", False, create=True):
            self.assertFalse(controller.install())
        self.assertIn("đã cài đặt", controller.error)


if __name__ == "__main__":
    unittest.main()
