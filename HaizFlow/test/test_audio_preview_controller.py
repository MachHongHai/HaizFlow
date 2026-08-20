import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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

    def test_separation_preview_never_falls_back_to_the_complete_source_track(self):
        signal = SimpleNamespace(emit=Mock())
        host = SimpleNamespace(
            _selected_video_id="video-1",
            _enable_audio_separation=True,
            _video_path="",
            _background_music_path="",
            _original_volume=60,
            _background_music_volume=30,
            _tts_volume=100,
            _tts_voice="omnivoice:female",
            _tts_provider="omnivoice",
            _target_language="vi",
            _audio_preview_state="idle",
            _status_message="",
            statusMessageChanged=signal,
            audioPreviewChanged=signal,
        )
        video = SimpleNamespace(
            video_id="video-1",
            files={
                "video_input": str(Path("D:/project/input.mp4")),
                "background_audio": str(Path("D:/project/missing-no-vocals.wav")),
            },
        )
        fake_thread = Mock()

        with (
            patch(
                "haizflow.desktop.audio_preview_controller.video_store.get_video",
                return_value=video,
            ),
            patch(
                "haizflow.desktop.audio_preview_controller.video_store.get_video_dir",
                return_value="D:/project",
            ),
            patch(
                "haizflow.desktop.audio_preview_controller.os.path.isfile",
                side_effect=lambda value: str(value).endswith("input.mp4"),
            ),
            patch(
                "haizflow.desktop.audio_preview_controller.threading.Thread",
                return_value=fake_thread,
            ) as thread_type,
        ):
            self.assertTrue(AudioPreviewController(host).start())

        snapshot = thread_type.call_args.kwargs["args"][0]
        self.assertEqual(snapshot["source_path"], "")
        fake_thread.start.assert_called_once_with()

    def test_busy_local_preview_keeps_only_the_latest_request(self):
        signal = SimpleNamespace(emit=Mock())
        host = SimpleNamespace(
            _selected_video_id="video-1",
            _enable_audio_separation=False,
            _video_path="",
            _background_music_path="",
            _original_volume=60,
            _background_music_volume=30,
            _tts_volume=100,
            _tts_voice="omnivoice:female",
            _tts_provider="omnivoice",
            _target_language="vi",
            _audio_preview_state="idle",
            _status_message="",
            statusMessageChanged=signal,
            audioPreviewChanged=signal,
        )
        video = SimpleNamespace(
            video_id="video-1",
            files={"video_input": "D:/project/input.mp4"},
        )
        preview = AudioPreviewController(host)
        preview._thread = SimpleNamespace(is_alive=lambda: True)

        with (
            patch(
                "haizflow.desktop.audio_preview_controller.video_store.get_video",
                return_value=video,
            ),
            patch(
                "haizflow.desktop.audio_preview_controller.video_store.get_video_dir",
                return_value="D:/project",
            ),
            patch(
                "haizflow.desktop.audio_preview_controller.os.path.isfile",
                return_value=True,
            ),
        ):
            self.assertTrue(preview.start(voice="omnivoice:male"))
            self.assertTrue(preview.start(voice="omnivoice:bright"))

        self.assertEqual(preview._pending_snapshot["voice"], "omnivoice:bright")

    def test_preview_snapshot_includes_authorised_clone_reference(self):
        signal = SimpleNamespace(emit=Mock())
        host = SimpleNamespace(
            _selected_video_id="video-1",
            _enable_audio_separation=False,
            _video_path="",
            _background_music_path="",
            _original_volume=60,
            _background_music_volume=30,
            _tts_volume=100,
            _tts_voice="omnivoice:clone",
            _tts_provider="omnivoice",
            _target_language="vi",
            _audio_preview_state="idle",
            _status_message="",
            statusMessageChanged=signal,
            audioPreviewChanged=signal,
        )
        video = SimpleNamespace(
            video_id="video-1",
            files={
                "video_input": "D:/project/input.mp4",
                "voice_reference": "D:/project/reference.wav",
                "voice_reference_transcript": "Xin chào.",
            },
        )
        fake_thread = Mock()

        with (
            patch(
                "haizflow.desktop.audio_preview_controller.video_store.get_video",
                return_value=video,
            ),
            patch(
                "haizflow.desktop.audio_preview_controller.video_store.get_video_dir",
                return_value="D:/project",
            ),
            patch(
                "haizflow.desktop.audio_preview_controller.os.path.isfile",
                return_value=True,
            ),
            patch(
                "haizflow.desktop.audio_preview_controller.threading.Thread",
                return_value=fake_thread,
            ) as thread_type,
        ):
            self.assertTrue(AudioPreviewController(host).start())

        snapshot = thread_type.call_args.kwargs["args"][0]
        self.assertEqual(snapshot["reference_path"], "D:/project/reference.wav")
        self.assertEqual(snapshot["reference_text"], "Xin chào.")


if __name__ == "__main__":
    unittest.main()
