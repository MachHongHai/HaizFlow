import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hflow.core.edge_voices import EDGE_VOICES
from hflow.core.vieneu_voices import VIENEU_VOICES, sample_voice_id
from hflow.desktop.audio_preview_controller import AudioPreviewController
from hflow.desktop.catalog import OMNIVOICE_TTS_VOICES, POPULAR_TARGET_LANGUAGES
from hflow.utils.ffmpeg import _binary


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
    def test_batch_draft_clone_preview_uses_reference_not_selected_video(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "draft.wav"
            other = Path(directory) / "other.wav"
            source = Path(directory) / "source.mp4"
            for path in (reference, other, source):
                path.write_bytes(b"media")
            video = SimpleNamespace(project_type="batch",
                                    files={"voice_reference": str(other), "video_input": str(source)})
            host = _host(_selected_video_id="selected", _tts_voice="omnivoice:clone")
            preview = AudioPreviewController(host)
            with patch("hflow.desktop.audio_preview_controller.video_store.get_video", return_value=video), \
                    patch.object(preview, "_sample_from_video") as cached:
                self.assertTrue(preview.start(voice_reference_path=str(reference)))
            cached.assert_not_called()
            self.assertEqual(host._audio_preview_source, reference.as_uri())

    def test_every_target_language_voice_has_a_matching_packaged_sample(self):
        preview = AudioPreviewController(_host())
        languages = [code for code, _english, _native in POPULAR_TARGET_LANGUAGES]
        self.assertEqual(languages, ["vi", "en", "zh"])
        missing = []
        for language in languages:
            missing.extend(
                (language, voice)
                for voice, _label, _category in OMNIVOICE_TTS_VOICES
                if not preview.has_voice_sample("omnivoice", voice, language)
            )
        self.assertEqual(missing, [])

        manifest_path = AudioPreviewController._PACKAGED_SAMPLE_DIR / "samples.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len([item for item in manifest["samples"] if item["provider"] == "omnivoice"]),
                         len(languages) * len(OMNIVOICE_TTS_VOICES))
        self.assertEqual(len(manifest["samples"]),
                         len(languages) * len(OMNIVOICE_TTS_VOICES) + sum(map(len, EDGE_VOICES.values()))
                         + len(VIENEU_VOICES))
        self.assertEqual(set(manifest["sentences"]), set(languages))
        packaged_audio = list(AudioPreviewController._PACKAGED_SAMPLE_DIR.rglob("*.mp3"))
        self.assertEqual(len(packaged_audio), len(manifest["samples"]))
        self.assertEqual({path.stem for path in packaged_audio}, set(languages))
        self.assertEqual(
            manifest["sentences"]["vi"],
            "Ứng dụng được phát triển bởi Mạch Hồng Hải, một sinh viên Đại học Kinh tế "
            "Thành phố Hồ Chí Minh, nếu bạn thích ứng dụng này, hãy vào phần liên hệ và gửi "
            "tặng một sao cho repository Github ứng dụng này. Cảm ơn bạn rất nhiều vì đã sử "
            "dụng ứng dụng của tôi, chúc bạn một ngày mới tốt lành.",
        )

    def test_all_edge_voices_have_exact_offline_samples_and_decode_completely(self):
        host = _host()
        preview = AudioPreviewController(host)
        manifest = json.loads((preview._PACKAGED_SAMPLE_DIR / "samples.json").read_text(encoding="utf-8"))
        edge_entries = {(item["voice"], item["language"]): item
                        for item in manifest["samples"] if item["provider"] == "edge"}
        self.assertEqual(len(edge_entries), sum(map(len, EDGE_VOICES.values())))
        with patch("hflow.pipeline.edge_tts_backend.synthesize_to_mp3") as synthesize:
            for language, voices in EDGE_VOICES.items():
                for voice, *_labels in voices:
                    with self.subTest(voice=voice, language=language):
                        self.assertTrue(preview.has_voice_sample("edge", voice, language))
                        path = Path(preview.voice_sample_path("edge", voice, language))
                        self.assertEqual(path, preview._PACKAGED_SAMPLE_DIR / edge_entries[(voice, language)]["path"])
                        self.assertTrue(preview.start(provider="edge", voice=voice,
                                                      target_language=language, voice_only=True))
                        self.assertEqual(host._audio_preview_source, path.as_uri())
                        self.assertEqual(host._audio_preview_state, "ready")
                        for other_language in EDGE_VOICES.keys() - {language}:
                            self.assertFalse(preview.has_voice_sample("edge", voice, other_language))
                        decoded = subprocess.run(
                            [_binary("ffmpeg"), "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                            capture_output=True, timeout=20,
                        )
                        self.assertEqual(decoded.returncode, 0, decoded.stderr.decode(errors="replace"))
            synthesize.assert_not_called()

    def test_all_vieneu_voices_have_exact_offline_cpu_gpu_samples_and_decode_completely(self):
        host = _host()
        preview = AudioPreviewController(host)
        manifest = json.loads((preview._PACKAGED_SAMPLE_DIR / "samples.json").read_text(encoding="utf-8"))
        entries = {item["voice"]: item for item in manifest["samples"] if item["provider"] == "vieneu"}
        self.assertEqual(len(entries), len(VIENEU_VOICES))
        self.assertEqual(len({entry["sha256"] for entry in entries.values()}), len(VIENEU_VOICES))
        paths = set()
        with patch("hflow.pipeline.vieneu_tts.synthesize_to_mp3") as synthesize:
            for name, _gender, _region in VIENEU_VOICES:
                voice = "vieneu:" + name
                with self.subTest(voice=voice):
                    path = Path(preview.voice_sample_path("vieneu", voice, "vi"))
                    self.assertEqual(path, preview._PACKAGED_SAMPLE_DIR / entries[voice]["path"])
                    self.assertEqual(path.parent.name, sample_voice_id(voice))
                    self.assertEqual(path.stat().st_size, entries[voice]["bytes"])
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entries[voice]["sha256"])
                    paths.add(path)
                    for provider in ("vieneu", "vieneu-gpu"):
                        self.assertTrue(preview.has_voice_sample(provider, voice, "vi"))
                        self.assertEqual(preview.voice_sample_path(provider, voice, "vi"), str(path))
                        self.assertTrue(preview.start(provider=provider, voice=voice,
                                                      target_language="vi", voice_only=True))
                        self.assertEqual(host._audio_preview_source, path.as_uri())
                        self.assertEqual(host._audio_preview_state, "ready")
                        self.assertFalse(preview.has_voice_sample(provider, voice, "en"))
                        self.assertFalse(preview.has_voice_sample(provider, voice, "zh"))
                    decoded = subprocess.run(
                        [_binary("ffmpeg"), "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                        capture_output=True, timeout=20,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    self.assertEqual(decoded.returncode, 0, decoded.stderr.decode(errors="replace"))
            synthesize.assert_not_called()
        self.assertEqual(len(paths), len(VIENEU_VOICES))
        self.assertFalse(preview.has_voice_sample("vieneu", "vieneu:Missing", "vi"))

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

    def test_omnivoice_preset_preview_uses_english_sample_for_english_project(self):
        preview = AudioPreviewController(_host())
        self.assertTrue(preview.has_voice_sample("omnivoice", "omnivoice:bright", "en"))
        self.assertTrue(preview.voice_sample_path("omnivoice", "omnivoice:bright", "en").endswith("en.mp3"))

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
                patch("hflow.desktop.audio_preview_controller.video_store.get_video", return_value=video),
                patch(
                    "hflow.desktop.audio_preview_controller.video_store.get_video_dir",
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
                patch("hflow.desktop.audio_preview_controller.video_store.get_video", return_value=video),
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
                "hflow.desktop.audio_preview_controller.video_store.get_video",
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
                    "hflow.desktop.audio_preview_controller.video_store.get_video",
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
                patch("hflow.desktop.audio_preview_controller.video_store.get_video", return_value=video),
                patch("hflow.desktop.audio_preview_controller.video_store.get_video_dir", return_value=root),
            ):
                self.assertTrue(preview.start())

        self.assertEqual(host._audio_preview_source, voice.resolve().as_uri())

    def test_mix_preview_uses_aligned_voice_track_even_if_voice_setting_changed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            voice = root / "voice_final.wav"
            voice.write_bytes(b"completed aligned voice track")
            video = SimpleNamespace(
                video_id="video-1",
                tts_provider="omnivoice",
                tts_voice="omnivoice:male",
                checkpoints={"voice": "verified"},
                files={"voice_output": str(voice)},
            )
            host = _host(_selected_video_id="video-1", _tts_voice="omnivoice:female")
            preview = AudioPreviewController(host)
            with patch(
                "hflow.desktop.audio_preview_controller.video_store.get_video",
                return_value=video,
            ):
                self.assertTrue(preview.start())
            self.assertEqual(host._audio_preview_source, voice.resolve().as_uri())

    def test_completed_mix_fallback_does_not_play_source_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            voice = root / "voice_final.wav"
            source = root / "video.mp4"
            music = root / "music.mp3"
            for path in (voice, source, music):
                path.write_bytes(b"existing media")
            video = SimpleNamespace(
                video_id="video-1", checkpoints={"voice": "verified"},
                files={"voice_output": str(voice), "video_input": str(source)},
            )
            host = _host(
                _selected_video_id="video-1", _video_path=str(source),
                _background_music_path=str(music),
            )
            preview = AudioPreviewController(host)
            with (
                patch("hflow.desktop.audio_preview_controller.video_store.get_video", return_value=video),
                patch("hflow.desktop.audio_preview_controller.video_store.get_video_dir", return_value=root),
            ):
                self.assertTrue(preview.start())
            self.assertEqual(host._audio_preview_source, voice.resolve().as_uri())
            self.assertEqual(host._audio_preview_original_source, "")
            self.assertEqual(host._audio_preview_background_music_source, "")

    def test_auto_mix_preview_uses_packaged_voice_instead_of_video_voice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sample = root / "sample.mp3"
            existing_mix = root / "voice_final.wav"
            source = root / "video.mp4"
            for path in (sample, existing_mix, source):
                path.write_bytes(b"existing media")
            video = SimpleNamespace(
                video_id="video-1", project_type="single", checkpoints={"voice": "verified"},
                files={"voice_output": str(existing_mix), "video_input": str(source)},
            )
            host = _host(_selected_video_id="video-1", _video_path=str(source))
            preview = AudioPreviewController(host)
            with (
                patch("hflow.desktop.audio_preview_controller.video_store.get_video", return_value=video),
                patch.object(preview, "voice_sample_path", return_value=str(sample)),
            ):
                self.assertTrue(preview.start())
            self.assertEqual(host._audio_preview_source, sample.resolve().as_uri())
            self.assertEqual(host._audio_preview_original_source, source.resolve().as_uri())

    def test_auto_mix_preview_does_not_play_only_source_when_voice_sample_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "video.mp4"
            source.write_bytes(b"source audio")
            video = SimpleNamespace(
                video_id="video-1", project_type="single",
                files={"video_input": str(source)}, checkpoints={},
            )
            host = _host(_selected_video_id="video-1", _video_path=str(source))
            preview = AudioPreviewController(host)
            with (
                patch("hflow.desktop.audio_preview_controller.video_store.get_video", return_value=video),
                patch.object(preview, "voice_sample_path", return_value=""),
            ):
                self.assertFalse(preview.start())
            self.assertEqual(host._audio_preview_state, "failed")
            self.assertEqual(host._audio_preview_original_source, "")

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
                    "hflow.desktop.audio_preview_controller.video_store.get_video",
                    return_value=video,
                ),
                patch.object(preview, "voice_sample_path", return_value=""),
            ):
                self.assertTrue(preview.start())

        self.assertEqual(host._audio_preview_original_source, "")
        self.assertEqual(host._audio_preview_background_music_source, music.resolve().as_uri())


if __name__ == "__main__":
    unittest.main()
