import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.services import desktop_settings


class DesktopSettingsTests(unittest.TestCase):
    def test_partial_update_preserves_warm_and_cache_preferences(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "desktop-settings.json"
            path.write_text(
                json.dumps(
                    {
                        **desktop_settings.DEFAULT_SETTINGS,
                        "keep_models_warm": False,
                        "manual_project_cache_gib": 7,
                        "manual_global_cache_gib": 28,
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(desktop_settings, "SETTINGS_PATH", path):
                saved = desktop_settings.save_settings({"processing_device": "gpu"})
                loaded = desktop_settings.load_settings()

        self.assertEqual(saved["processing_device"], "gpu")
        self.assertFalse(loaded["keep_models_warm"])
        self.assertEqual(loaded["manual_project_cache_gib"], 7)
        self.assertEqual(loaded["manual_global_cache_gib"], 28)

    def test_invalid_cache_limits_are_safely_bounded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "desktop-settings.json"
            with patch.object(desktop_settings, "SETTINGS_PATH", path):
                saved = desktop_settings.save_settings(
                    {"manual_project_cache_gib": "bad", "manual_global_cache_gib": -20}
                )
        self.assertEqual(saved["manual_project_cache_gib"], 4)
        self.assertEqual(saved["manual_global_cache_gib"], 4)

    def test_obsolete_font_picker_preferences_are_not_saved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "desktop-settings.json"
            with patch.object(desktop_settings, "SETTINGS_PATH", path):
                desktop_settings.save_settings(
                    {
                        "editor_recent_fonts": ["Segoe UI", "Bangers"],
                        "editor_favorite_fonts": ["Bangers", "Arial"],
                    }
                )
                desktop_settings.save_settings({"language": "vi"})
                loaded = desktop_settings.load_settings()

        self.assertNotIn("editor_recent_fonts", loaded)
        self.assertNotIn("editor_favorite_fonts", loaded)
        self.assertEqual(loaded["language"], "vi")


if __name__ == "__main__":
    unittest.main()
