import tempfile
import unittest
import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from haizflow.desktop.audio_preview_controller import AudioPreviewController
from haizflow.services import desktop_videos, video_store


class ManagedMediaCleanupTests(unittest.TestCase):
    def test_voice_reference_analysis_uses_decoded_audio_for_duration_and_peaks(self):
        with tempfile.TemporaryDirectory() as temporary:
            sample = Path(temporary) / "sample.m4a"
            sample.write_bytes(b"media")
            pcm = array.array("h", ([0] * 4000) + ([12000] * 4000)).tobytes()
            completed = SimpleNamespace(returncode=0, stdout=pcm, stderr=b"")

            with patch.object(desktop_videos.subprocess, "run", return_value=completed):
                analysis = desktop_videos.analyze_voice_reference(str(sample), 32)

            self.assertEqual(analysis["durationMs"], 1000)
            self.assertEqual(len(analysis["peaks"]), 32)
            self.assertLess(max(analysis["peaks"][:16]), min(analysis["peaks"][16:]))

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

    def test_voice_clone_reference_needs_only_audio_and_replaces_legacy_transcript(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            source = root / "authorised-sample.wav"
            source.write_bytes(b"voice")
            video = SimpleNamespace(
                video_id="video-1",
                files={"voice_reference_transcript": "legacy transcript"},
            )

            with (
                patch.object(video_store, "get_video_dir", return_value=str(workspace)),
                patch.object(video_store, "save_video"),
                patch.object(video_store, "log_to_video"),
            ):
                destination = Path(desktop_videos.set_desktop_voice_reference(video, str(source)))
                recording_path = Path(desktop_videos.prepare_desktop_voice_recording(video))

            self.assertTrue(destination.is_file())
            self.assertNotIn("voice_reference_transcript", video.files)
            self.assertEqual(video.files["voice_reference"], str(destination))
            self.assertEqual(recording_path.parent, workspace / "temp" / "voice_cloning")
            self.assertTrue(recording_path.name.startswith("recording-"))
            self.assertEqual(recording_path.suffix, ".m4a")

    def test_voice_clone_reference_falls_back_when_windows_locks_previous_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            source = root / "sample.m4a"
            source.write_bytes(b"voice")
            video = SimpleNamespace(video_id="video-1", files={})
            real_copy = desktop_videos._copy_file_atomically

            def copy_with_locked_stable_name(source_path, destination_path):
                if Path(destination_path).name == "voice_reference.m4a":
                    raise PermissionError(5, "Access is denied", destination_path)
                real_copy(source_path, destination_path)

            with (
                patch.object(video_store, "get_video_dir", return_value=str(workspace)),
                patch.object(video_store, "save_video"),
                patch.object(video_store, "log_to_video"),
                patch.object(desktop_videos, "_copy_file_atomically", side_effect=copy_with_locked_stable_name),
            ):
                destination = Path(desktop_videos.set_desktop_voice_reference(video, str(source)))

            self.assertTrue(destination.is_file())
            self.assertTrue(destination.name.startswith("voice_reference-"))
            self.assertEqual(video.files["voice_reference"], str(destination))


if __name__ == "__main__":
    unittest.main()
