import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from haizflow.desktop.resource_progress import InstallProgress, localized_progress, progress_copy
from haizflow.services.model_bootstrap import ModelProgress

ROOT = Path(__file__).resolve().parents[1]


class ProgressTests(unittest.TestCase):
    def test_dependency_completion_never_means_operation_completion(self):
        tracker = InstallProgress((("engine-cpu-py313", 100), ("model-whisper-small", 200)))
        readings = []
        for unit, events in (
            ("engine-cpu-py313", [ModelProgress("verifying", "", "", 100, 100, "transfer"),
                ModelProgress("installing", "", "", 50, 100, "installing"),
                ModelProgress("ready", "", "", 100, 100)]),
            ("model-whisper-small", [ModelProgress("checking", "", "", 0, 200),
                ModelProgress("downloading", "", "", 1, 200, "transfer"),
                ModelProgress("verifying", "", "", 30, 200, "transfer"),
                ModelProgress("downloading", "", "", 20, 200, "transfer"),
                ModelProgress("downloading", "", "", 200, 200, "transfer"),
                ModelProgress("verifying", "", "", 200, 200, "finalizing"),
                ModelProgress("ready", "", "", 200, 200)]),
        ):
            for event in events:
                readings.append(tracker.update(unit, event))
        self.assertEqual(readings, sorted(readings))
        self.assertTrue(all(0 <= value < 100 for value in readings))
        self.assertEqual(readings[-1], 99)
        self.assertLess(readings[2], 34)
        self.assertGreater(readings[4], readings[2])

    def test_zero_size_and_retries_are_safe(self):
        tracker = InstallProgress((("model-test", 1),))
        first = tracker.update("model-test", ModelProgress("downloading", "", "", 8, 10))
        self.assertEqual(tracker.update("model-test", ModelProgress("checking", "", "", 0, 0)), first)

    def test_progress_copy_never_leaks_english_asset_description(self):
        event = ModelProgress("downloading", "Whisper large-v3-turbo speech recognition",
                              "Tệp 2/11 · Đang tải · Whisper large-v3-turbo speech recognition", 5, 10)
        copy = progress_copy("model-whisper-turbo", event)
        self.assertEqual(localized_progress(copy, "vi"), "Đang tải · Tệp 2/11 · Whisper Turbo")
        self.assertEqual(localized_progress(copy, "en"), "Downloading · File 2/11 · Whisper Turbo")
        engine = progress_copy("engine-cuda128-py313", ModelProgress("installing", "", "", 0, 0))
        self.assertEqual(localized_progress(engine, "en"), "Installing · NVIDIA CUDA 12.8 runtime")

    def test_media_adapter_import_does_not_load_pydub(self):
        filename = ROOT / "src/haizflow/utils/media_subprocess.py"
        spec = importlib.util.spec_from_file_location("media_adapter_without_pydub", filename)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"pydub": None}):
            spec.loader.exec_module(module)
        self.assertTrue(callable(module._MediaSubprocess().Popen))

    def test_engine_collects_lightning_runtime_metadata(self):
        script = (ROOT / "scripts/build-resource-engine.ps1").read_text(encoding="utf-8")
        collection = script.split('"--collect-data", $Module')[0].rsplit("foreach ($Module", 1)[1]
        for module in ("lightning", "lightning_fabric", "pytorch_lightning"):
            self.assertIn(f'"{module}"', collection)

    def test_progress_delegate_is_retained_and_fill_uses_transform(self):
        page = (ROOT / "src/haizflow/desktop/qml/ResourcePacksPage.qml").read_text(encoding="utf-8")
        self.assertIn('stableRows.setProperty(i, "modelData", rows[i])', page)
        bar = (ROOT / "src/haizflow/desktop/qml/AppProgressBar.qml").read_text(encoding="utf-8")
        self.assertNotIn("Behavior on width", bar)
        self.assertIn("Behavior on xScale", bar)
        self.assertIn("Theme.motionEnabled", bar)

    def test_installer_artwork_has_fixed_canvases_and_aspect_ratio(self):
        import tempfile
        from PIL import Image
        spec = importlib.util.spec_from_file_location("artwork", ROOT / "scripts/generate-installer-artwork.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            Image.new("RGBA", (200, 100), "red").save(root / "mark.png")
            module.generate(root / "mark.png", root / "output")
            with Image.open(root / "output/header.png") as header:
                self.assertEqual(header.size, (128, 128))
                bounds = [(x, y) for y in range(128) for x in range(128) if header.getpixel((x, y)) == (255, 0, 0)]
                self.assertEqual(max(x for x, _ in bounds) - min(x for x, _ in bounds) + 1, 72)
                self.assertEqual(max(y for _, y in bounds) - min(y for _, y in bounds) + 1, 36)


if __name__ == "__main__":
    unittest.main()
