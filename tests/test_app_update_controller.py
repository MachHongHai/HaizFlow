import json
import hashlib
import sys
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

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
