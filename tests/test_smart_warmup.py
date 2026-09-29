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

    def test_constrained_foreground_waits_for_speculative_release(self):
        controller = SmartWarmupController(_Host(), _Resources())
        controller._resident.add("recognition")
        controller.request("voice")
        controller._release_now = Mock()

        controller.quiesce_for_foreground()

        self.assertTrue(controller._suspended)
        self.assertEqual(controller._requests, [])
        controller._release_now.assert_called_once_with("foreground")
        controller.resume_after_foreground()
        self.assertFalse(controller._suspended)

    def test_startup_prediction_only_queues_first_model(self):
        controller = SmartWarmupController(_Host(), _Resources())
        profile = type("Profile", (), {
            "total_ram_gib": 32, "cuda_available": True, "total_vram_gib": 16,
        })()
        with patch("haizflow.desktop.smart_warmup_controller.runtime_profile", return_value=profile):
            controller.request_startup_prediction()
        ordered = sorted(controller._requests)
        self.assertEqual([item.capability for item in ordered], ["recognition"])

    def test_constrained_machine_queues_one_model_subject_to_live_memory_budget(self):
        controller = SmartWarmupController(_Host(), _Resources())
        profile = type("Profile", (), {
            "total_ram_gib": 16, "cuda_available": True, "total_vram_gib": 8,
        })()
        with patch("haizflow.desktop.smart_warmup_controller.runtime_profile", return_value=profile):
            controller.request_startup_prediction()
            controller.request_project_prediction()
        self.assertEqual([item.capability for item in controller._requests], ["recognition"])
        with (
            patch("haizflow.desktop.smart_warmup_controller.runtime_profile", return_value=profile),
            patch("haizflow.desktop.smart_warmup_controller.available_memory_bytes", return_value=2 * 1024**3),
        ):
            self.assertFalse(controller._has_warmup_budget("recognition", {"model": "small"}))

    def test_translation_warmup_uses_project_model_choice(self):
        controller = SmartWarmupController(_Host(), _Resources())
        with patch("haizflow.services.translation.warm_hymt2_worker") as warm:
            controller._warm("translation", {"translation_model": "q4"})
        warm.assert_called_once_with(model_preference="q4")

    def test_eight_gigabyte_gpu_never_speculatively_loads_full_translation(self):
        controller = SmartWarmupController(_Host(), _Resources())
        profile = type("Profile", (), {
            "total_ram_gib": 16, "cuda_available": True, "total_vram_gib": 8,
        })()
        with (
            patch("haizflow.desktop.smart_warmup_controller.runtime_profile", return_value=profile),
            patch("haizflow.desktop.smart_warmup_controller.available_memory_bytes", return_value=9 * 1024**3),
        ):
            self.assertTrue(controller._has_warmup_budget("recognition", {"model": "small"}))
            self.assertFalse(controller._has_warmup_budget("translation", {"translation_model": "full"}))

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
        resources.required_packs = Mock(return_value=["engine-cpu-py313", "model-whisper-small"])
        controller = SmartWarmupController(_Host(), resources)
        controller._resident.add("recognition")
        controller._resident_contexts["recognition"] = {"device": "cpu"}
        self.assertTrue(controller.pack_in_use("model-whisper-small"))


if __name__ == "__main__":
    unittest.main()
