import unittest

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


if __name__ == "__main__":
    unittest.main()
