import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.smart_warmup_controller import SmartWarmupController


class _Queue:
    has_work = False


class _Host:
    _keep_models_warm = True
    _settings_processing_device = "cpu"
    _speech_recognition_model = "small"
    _processing_queue = _Queue()

    def _selected_video(self):
        return None


class _Resources:
    def missing_packs(self, _capability, _context):
        return []


class SmartWarmupTests(unittest.TestCase):
    def test_foreground_keeps_required_resident_and_releases_only_wrong_prediction(self):
        controller = SmartWarmupController(_Host(), _Resources())
        controller._resident.update({"recognition", "translation", "voice"})
        controller.release = Mock()

        controller.foreground_work_requested({"recognition", "translation"})

        controller.release.assert_called_once_with("foreground", {"voice"})

    def test_startup_prediction_prioritizes_recognition_before_translation(self):
        controller = SmartWarmupController(_Host(), _Resources())
        controller.request_startup_prediction()
        ordered = sorted(controller._requests)
        self.assertEqual([item.capability for item in ordered], ["recognition", "translation"])

    def test_disabled_warmup_does_not_start_a_worker(self):
        host = _Host()
        host._keep_models_warm = False
        controller = SmartWarmupController(host, _Resources())
        controller.start()
        self.assertFalse(controller._started)
        self.assertIsNone(controller._thread)

    def test_memory_pressure_releases_speculative_residents(self):
        controller = SmartWarmupController(_Host(), _Resources())
        controller._resident.add("recognition")
        controller._resident_since["recognition"] = 1.0
        controller._release_now = Mock()
        profile = type("Profile", (), {"total_ram_bytes": 16 * 1024**3})()
        with (
            patch("haizflow.desktop.smart_warmup_controller.runtime_profile", return_value=profile),
            patch("haizflow.desktop.smart_warmup_controller.available_memory_bytes", return_value=2 * 1024**3),
        ):
            controller._expire_idle_residents()
        controller._release_now.assert_called_once_with("memory-pressure")

    def test_pack_in_use_includes_resident_model_dependencies(self):
        resources = _Resources()
        resources.required_packs = Mock(return_value=["engine-cpu-py313", "model-speech-cpu"])
        controller = SmartWarmupController(_Host(), resources)
        controller._resident.add("recognition")
        controller._resident_contexts["recognition"] = {"device": "cpu"}
        self.assertTrue(controller.pack_in_use("model-speech-cpu"))


if __name__ == "__main__":
    unittest.main()
