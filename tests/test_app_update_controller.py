import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.app_update_controller import AppUpdateController, version_key


class Host(QObject):
    appUpdateAvailable = Signal()
    appAlertRequested = Signal(str, str, str)


class Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class AppUpdateControllerTests(unittest.TestCase):
    def test_version_key_compares_stable_tags(self):
        self.assertGreater(version_key("v1.2.0"), version_key("1.1.9"))
        self.assertGreater(version_key("1.2.0"), version_key("1.2.0-rc.1"))

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


if __name__ == "__main__":
    unittest.main()
