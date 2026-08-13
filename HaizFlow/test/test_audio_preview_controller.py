import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from haizflow.desktop.audio_preview_controller import AudioPreviewController


class AudioPreviewControllerTests(unittest.TestCase):
    def test_preview_text_matches_target_language(self):
        vietnamese = AudioPreviewController._preview_text("vi")
        english = AudioPreviewController._preview_text("en")

        self.assertIn("Đây là bản nghe thử", vietnamese)
        self.assertNotEqual(vietnamese, english)
        self.assertIn("complete mix", english)

    def test_unknown_preview_language_falls_back_to_english(self):
        self.assertEqual(
            AudioPreviewController._preview_text("unknown"),
            AudioPreviewController._preview_text("en"),
        )

    def test_invalidate_clears_the_previous_rendered_preview(self):
        host = SimpleNamespace(
            _audio_preview_source="file:///voice.mp3",
            _audio_preview_original_source="file:///source.m4a",
            _audio_preview_background_music_source="file:///music.m4a",
            _audio_preview_state="ready",
            audioPreviewChanged=SimpleNamespace(emit=Mock()),
        )
        preview = AudioPreviewController(host)

        preview.invalidate()

        self.assertEqual(host._audio_preview_source, "")
        self.assertEqual(host._audio_preview_original_source, "")
        self.assertEqual(host._audio_preview_background_music_source, "")
        self.assertEqual(host._audio_preview_state, "idle")
        host.audioPreviewChanged.emit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
