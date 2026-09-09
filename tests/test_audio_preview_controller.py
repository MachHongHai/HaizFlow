import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from haizflow.desktop.audio_preview_controller import AudioPreviewController
from haizflow.desktop.catalog import EDGE_TTS_VOICES_BY_LANGUAGE, OMNIVOICE_TTS_VOICES


def _host(**overrides):
    values = {
        "_selected_video_id": "",
        "_enable_audio_separation": False,
        "_video_path": "",
        "_background_music_path": "",
        "_tts_voice": "omnivoice:female",
        "_tts_provider": "omnivoice",
        "_target_language": "vi",
        "_audio_preview_source": "",
        "_audio_preview_original_source": "",
        "_audio_preview_background_music_source": "",
        "_audio_preview_state": "idle",
        "_status_message": "",
        "statusMessageChanged": SimpleNamespace(emit=Mock()),
        "audioPreviewChanged": SimpleNamespace(emit=Mock()),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AudioPreviewControllerTests(unittest.TestCase):
    def test_every_vietnamese_voice_has_the_locked_packaged_sample(self):
        preview = AudioPreviewController(_host())
        missing = [
            voice
            for voice, _label, _category in OMNIVOICE_TTS_VOICES
            if not preview.has_voice_sample("omnivoice", voice, "vi")
        ]
        missing.extend(
            voice
            for voice, _label in EDGE_TTS_VOICES_BY_LANGUAGE["vi"]
            if not preview.has_voice_sample("edge", voice, "vi")
        )
        self.assertEqual(missing, [])

        manifest_path = AudioPreviewController._PACKAGED_SAMPLE_DIR / "samples.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["samples"]), 34)
        self.assertEqual(
            manifest["sentences"]["vi"],
            "Ứng dụng được phát triển bởi Mạch Hồng Hải, một sinh viên Đại học Kinh tế "
            "Thành phố Hồ Chí Minh, nếu bạn thích ứng dụng này, hãy vào phần liên hệ và gửi "
            "tặng một sao cho repository Github ứng dụng này. Cảm ơn bạn rất nhiều vì đã sử "
            "dụng ứng dụng của tôi, chúc bạn một ngày mới tốt lành.",
        )

    def test_invalidate_clears_all_previous_player_sources(self):
        host = _host(
            _audio_preview_source="file:///voice.mp3",
            _audio_preview_original_source="file:///source.m4a",
            _audio_preview_background_music_source="file:///music.m4a",
            _audio_preview_state="ready",
        )

        AudioPreviewController(host).invalidate()

        self.assertEqual(host._audio_preview_source, "")
        self.assertEqual(host._audio_preview_original_source, "")
        self.assertEqual(host._audio_preview_background_music_source, "")
        self.assertEqual(host._audio_preview_state, "idle")
        host.audioPreviewChanged.emit.assert_called_once()

    def test_packaged_sample_is_resolved_without_loading_a_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "omnivoice" / "omnivoice_female" / "vi.mp3"
            sample.parent.mkdir(parents=True)
            sample.write_bytes(b"existing voice sample")

            with patch.object(AudioPreviewController, "_PACKAGED_SAMPLE_DIR", Path(temp_dir)):
                path = AudioPreviewController(_host()).voice_sample_path("omnivoice", "omnivoice:female", "vi")

        self.assertEqual(path, str(sample))

    def test_voice_only_preview_publishes_an_existing_sample_immediately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "sample.mp3"
            sample.write_bytes(b"existing voice sample")
            host = _host()
            preview = AudioPreviewController(host)

            with patch.object(preview, "voice_sample_path", return_value=str(sample)):
                self.assertTrue(preview.start(voice_only=True))

        self.assertEqual(host._audio_preview_source, sample.resolve().as_uri())
        self.assertEqual(host._audio_preview_original_source, "")
        self.assertEqual(host._audio_preview_state, "ready")
        host.audioPreviewChanged.emit.assert_called_once()

    def test_voice_only_preview_never_synthesizes_a_missing_sample(self):
        host = _host()
        preview = AudioPreviewController(host)

        with patch.object(preview, "voice_sample_path", return_value=""):
            self.assertFalse(preview.start(voice_only=True))

        self.assertEqual(host._audio_preview_state, "failed")
        self.assertIn("No prerecorded sample", host._status_message)

    def test_project_voice_part_is_not_used_as_a_voice_library_sample(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            parts = Path(temp_dir) / "temp" / "voice_parts"
            parts.mkdir(parents=True)
            sample = parts / "voice_0001.mp3"
            sample.write_bytes(b"existing voice part")
            video = SimpleNamespace(
                video_id="video-1",
                tts_provider="omnivoice",
                tts_voice="omnivoice:male",
                checkpoints={"voice": "verified"},
                files={},
            )
            preview = AudioPreviewController(_host())

            with (
                patch.object(AudioPreviewController, "_PACKAGED_SAMPLE_DIR", Path(temp_dir) / "packaged"),
                patch("haizflow.desktop.audio_preview_controller.video_store.get_video", return_value=video),
                patch(
                    "haizflow.desktop.audio_preview_controller.video_store.get_video_dir",
                    return_value=temp_dir,
                ),
            ):
                resolved = preview.voice_sample_path(
                    "omnivoice", "omnivoice:male", "vi", selected_video_id="video-1"
                )

        self.assertEqual(resolved, "")

    def test_unverified_leftover_voice_part_is_not_used(self):
        video = SimpleNamespace(
            video_id="video-1",
            tts_provider="omnivoice",
            tts_voice="omnivoice:male",
            checkpoints={},
            files={},
        )
        preview = AudioPreviewController(_host())

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(AudioPreviewController, "_PACKAGED_SAMPLE_DIR", Path(temp_dir) / "packaged"),
                patch("haizflow.desktop.audio_preview_controller.video_store.get_video", return_value=video),
            ):
                resolved = preview.voice_sample_path("omnivoice", "omnivoice:male", "vi")

        self.assertEqual(resolved, "")

    def test_clone_preview_uses_the_authorised_reference_recording(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reference = Path(temp_dir) / "reference.wav"
            reference.write_bytes(b"authorised recording")
            video = SimpleNamespace(video_id="video-1", files={"voice_reference": str(reference)})
            preview = AudioPreviewController(_host())

            with patch(
                "haizflow.desktop.audio_preview_controller.video_store.get_video",
                return_value=video,
            ):
                resolved = preview.voice_sample_path("omnivoice", "omnivoice:clone", "vi", selected_video_id="video-1")

        self.assertEqual(resolved, str(reference))

    def test_mix_preview_reuses_existing_tracks_without_encoding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "video.mp4"
            music = root / "music.mp3"
            voice = root / "voice.mp3"
            for path in (source, music, voice):
                path.write_bytes(b"existing media")
            video = SimpleNamespace(video_id="video-1", files={"video_input": str(source)})
            host = _host(
                _selected_video_id="video-1",
                _video_path=str(source),
                _background_music_path=str(music),
            )
            preview = AudioPreviewController(host)

            with (
                patch(
                    "haizflow.desktop.audio_preview_controller.video_store.get_video",
                    return_value=video,
                ),
                patch.object(preview, "voice_sample_path", return_value=str(voice)),
            ):
                self.assertTrue(preview.start())

        self.assertEqual(host._audio_preview_source, voice.resolve().as_uri())
        self.assertEqual(host._audio_preview_original_source, source.resolve().as_uri())
        self.assertEqual(host._audio_preview_background_music_source, music.resolve().as_uri())
        self.assertEqual(host._audio_preview_state, "ready")

    def test_mix_preview_prefers_verified_voice_from_selected_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parts = root / "temp" / "voice_parts"
            parts.mkdir(parents=True)
            voice = parts / "voice_0001.mp3"
            voice.write_bytes(b"current project voice")
            video = SimpleNamespace(
                video_id="video-1",
                tts_provider="omnivoice",
                tts_voice="omnivoice:male",
                checkpoints={"voice": "verified"},
                files={},
            )
            host = _host(
                _selected_video_id="video-1",
                _tts_voice="omnivoice:male",
            )
            preview = AudioPreviewController(host)

            with (
                patch("haizflow.desktop.audio_preview_controller.video_store.get_video", return_value=video),
                patch("haizflow.desktop.audio_preview_controller.video_store.get_video_dir", return_value=root),
            ):
                self.assertTrue(preview.start())

        self.assertEqual(host._audio_preview_source, voice.resolve().as_uri())

    def test_separation_preview_never_falls_back_to_complete_source_audio(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "video.mp4"
            music = root / "music.mp3"
            source.write_bytes(b"source video")
            music.write_bytes(b"background music")
            video = SimpleNamespace(
                video_id="video-1",
                files={"video_input": str(source), "background_audio": str(root / "missing.wav")},
            )
            host = _host(
                _selected_video_id="video-1",
                _enable_audio_separation=True,
                _video_path=str(source),
                _background_music_path=str(music),
            )
            preview = AudioPreviewController(host)

            with (
                patch(
                    "haizflow.desktop.audio_preview_controller.video_store.get_video",
                    return_value=video,
                ),
                patch.object(preview, "voice_sample_path", return_value=""),
            ):
                self.assertTrue(preview.start())

        self.assertEqual(host._audio_preview_original_source, "")
        self.assertEqual(host._audio_preview_background_music_source, music.resolve().as_uri())


if __name__ == "__main__":
    unittest.main()
