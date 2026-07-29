import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from haizflow.desktop.audio_preview_controller import AudioPreviewController
from haizflow.services import desktop_videos, video_store


class ManagedMediaCleanupTests(unittest.TestCase):
    def test_replacing_or_clearing_background_music_removes_all_managed_variants(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            first_source = root / "first.mp3"
            second_source = root / "second.wav"
            first_source.write_bytes(b"first")
            second_source.write_bytes(b"second")
            video = SimpleNamespace(video_id="video-1", files={})

            with (
                patch.object(video_store, "get_video_dir", return_value=str(workspace)),
                patch.object(video_store, "save_video"),
                patch.object(video_store, "log_to_video"),
            ):
                first_path = Path(desktop_videos.set_desktop_background_music(video, str(first_source)))
                stale_path = workspace / "input" / "background_music.legacy"
                stale_path.write_bytes(b"stale")
                second_path = Path(desktop_videos.set_desktop_background_music(video, str(second_source)))

                self.assertTrue(second_path.is_file())
                self.assertFalse(first_path.exists())
                self.assertFalse(stale_path.exists())

                desktop_videos.set_desktop_background_music(video, "")

            self.assertFalse(second_path.exists())
            self.assertNotIn("background_music", video.files)

    def test_new_audio_preview_removes_previous_controller_owned_tracks(self):
        with tempfile.TemporaryDirectory() as temporary:
            preview_dir = Path(temporary)
            old_voice = preview_dir / "voice-old.mp3"
            old_source = preview_dir / "source-old.m4a"
            unrelated_file = preview_dir / "notes.txt"
            current_voice = preview_dir / "voice-current.mp3"
            for path in (old_voice, old_source, unrelated_file, current_voice):
                path.write_bytes(b"data")

            AudioPreviewController._remove_stale_preview_files(preview_dir, {current_voice})

            self.assertTrue(current_voice.exists())
            self.assertFalse(old_voice.exists())
            self.assertFalse(old_source.exists())
            self.assertTrue(unrelated_file.exists())


if __name__ == "__main__":
    unittest.main()
