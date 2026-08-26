import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PySide6.QtCore import QUrl

from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.schemas.video import CropSettings, SubtitleStyle


class _Signal:
    def __init__(self):
        self.changed = threading.Event()

    def emit(self):
        self.changed.set()


class EditorPreviewControllerTests(unittest.TestCase):
    @staticmethod
    def _wait_until_idle(controller):
        for _ in range(200):
            if not controller.busy:
                return
            threading.Event().wait(0.02)
        raise AssertionError("Editor preview worker did not finish")

    @staticmethod
    def _host(video, source: Path):
        """Build the small controller host used by preview unit tests."""
        return SimpleNamespace(
            _selected_video=lambda: video,
            _resolve_video_file=lambda *_args: str(source),
            editorPreviewChanged=_Signal(),
        )

    def test_full_timeline_proxy_is_rendered_off_thread(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video_dir = root / "video-workspace"
            video = SimpleNamespace(
                video_id="video-1",
                subtitle_style=SubtitleStyle(),
                crop=CropSettings(),
                output_format="keep_ratio",
                subtitle_layout_override=False,
                remove_original_subtitles=True,
                original_subtitle_removal_mode="patch",
                watermark_text="HaizFlow",
            )
            signal = _Signal()
            host = SimpleNamespace(
                _selected_video=lambda: video,
                _resolve_video_file=lambda *_args: str(source),
                editorPreviewChanged=signal,
            )
            controller = EditorPreviewController(host)
            captured = []
            render_done = threading.Event()

            def fake_render(*args, **kwargs):
                captured.append({"args": args, "kwargs": kwargs})
                Path(args[3]).write_bytes(b"preview")
                render_done.set()

            def fake_assemble(
                _generation,
                _process_id,
                _chunk_paths,
                output_path,
                completion_path,
                expected_duration,
            ):
                output_path.write_bytes(b"preview")
                controller._write_completion_marker(completion_path, output_path, expected_duration)
                return True

            payload = json.dumps([
                {"start": 4.0, "end": 7.0, "text": "first"},
                {"start": 7.0, "end": 9.0, "text": "second"},
            ])
            with (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                    return_value=str(video_dir),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_duration",
                    return_value=20.0,
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.render_video",
                    side_effect=fake_render,
                ),
                mock.patch("haizflow.desktop.editor_preview_controller.start_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.clean_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.cancel_video"),
                mock.patch.object(
                    controller,
                    "_assemble_preview_chunks",
                    side_effect=fake_assemble,
                ),
            ):
                self.assertTrue(controller.request(payload, 7.0))
                self.assertTrue(render_done.wait(3.0))
                for _ in range(30):
                    if not controller.busy:
                        break
                    threading.Event().wait(0.02)

            self.assertFalse(controller.busy)
            self.assertEqual(controller.start_seconds, 0.0)
            self.assertEqual(controller.duration_seconds, 20.0)
            self.assertTrue(controller.source.startswith("file:"))
            self.assertEqual(len(captured), 3)
            self.assertEqual(captured[0]["kwargs"]["source_start_seconds"], 0.0)
            self.assertEqual(captured[0]["kwargs"]["source_duration_seconds"], 20.0)
            self.assertEqual(captured[1]["kwargs"]["source_start_seconds"], 0.0)
            self.assertEqual(captured[1]["kwargs"]["source_duration_seconds"], 12.0)
            self.assertEqual(captured[2]["kwargs"]["source_start_seconds"], 12.0)
            self.assertEqual(captured[2]["kwargs"]["source_duration_seconds"], 8.0)
            self.assertTrue(all(call["kwargs"]["compatibility_preview"] for call in captured))
            self.assertTrue(all(call["args"][7] == "video-1" for call in captured))
            self.assertTrue(
                all(
                    call["kwargs"]["process_registry_id"].startswith("editor-preview-video-1-")
                    for call in captured
                )
            )
            subtitle_path = Path(captured[-1]["args"][2])
            # Temporary source files are removed after a successful proxy.
            self.assertFalse(subtitle_path.exists())
            self.assertRegex(
                Path(captured[-1]["args"][3]).name,
                r"preview-\d+\.rendering\.mp4",
            )
            self.assertNotEqual(
                Path(captured[-1]["args"][3]).parent,
                video_dir / "temp" / "editor-preview",
            )
            published_path = Path(QUrl(controller.source).toLocalFile())
            self.assertEqual(published_path.name, "preview.mp4")
            self.assertTrue(published_path.is_file())

    def test_empty_timeline_renders_a_clean_preview(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video_dir = root / "video-workspace"
            video = SimpleNamespace(
                video_id="video-empty",
                subtitle_style=SubtitleStyle(),
                crop=CropSettings(),
                output_format="keep_ratio",
                subtitle_layout_override=False,
                remove_original_subtitles=False,
                original_subtitle_removal_mode="patch",
                watermark_text="",
            )
            signal = _Signal()
            host = SimpleNamespace(
                _selected_video=lambda: video,
                _resolve_video_file=lambda *_args: str(source),
                editorPreviewChanged=signal,
            )
            controller = EditorPreviewController(host)
            captured = {}
            render_done = threading.Event()

            def fake_render(*args, **_kwargs):
                captured["subtitle"] = Path(args[2]).read_text(encoding="utf-8")
                Path(args[3]).write_bytes(b"preview")
                render_done.set()

            with (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                    return_value=str(video_dir),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_duration",
                    return_value=8.0,
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.render_video",
                    side_effect=fake_render,
                ),
                mock.patch("haizflow.desktop.editor_preview_controller.start_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.clean_video"),
            ):
                self.assertTrue(controller.request("[]", 2.0))
                self.assertTrue(render_done.wait(3.0))
                for _ in range(30):
                    if not controller.busy:
                        break
                    threading.Event().wait(0.02)

            self.assertIn("\u200b", captured["subtitle"])
            self.assertTrue(controller.source.startswith("file:"))

    def test_preview_voice_cache_reuses_an_undo_state_without_synthesis(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video_dir = root / "video-workspace"
            video = SimpleNamespace(
                video_id="video-audio-cache",
                status="done",
                files={},
                enable_audio_separation=False,
            )
            controller = EditorPreviewController(self._host(video, source))
            controller._generation = 1
            missing_per_request = []

            def fake_generate(_segments, voice_dir, *_args, **_kwargs):
                voice_path = Path(voice_dir) / "voice_0001.mp3"
                missing_per_request.append(not voice_path.exists())
                if not voice_path.exists():
                    voice_path.write_bytes(b"voice" * 100)

            def fake_mix(_segments, _parts, _source, output, *_args, **_kwargs):
                Path(output).write_bytes(b"RIFF" + b"\x00" * 100)

            base_settings = {
                "segments": [{"start": 0.0, "end": 1.0, "text": "Câu A"}],
                "tts_voice": "omnivoice:female",
                "tts_provider": "omnivoice",
                "target_language": "vi",
                "speaker_mode": "single",
                "source_path": str(source),
                "original_video_volume": 0,
                "background_music_volume": 0,
                "tts_volume": 100,
                "duration": 1.0,
                "audio_inputs": {"voice_reference": {}},
            }
            with (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                    return_value=str(video_dir),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.generate_voice_parts",
                    side_effect=fake_generate,
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.build_audio_timeline",
                    side_effect=fake_mix,
                ),
            ):
                controller._prepare_preview_audio(1, "preview-1", video, base_settings, root / "audio-a")
                changed = {**base_settings, "segments": [{"start": 0.0, "end": 1.0, "text": "Câu B"}]}
                controller._prepare_preview_audio(1, "preview-2", video, changed, root / "audio-b")
                controller._prepare_preview_audio(1, "preview-3", video, base_settings, root / "audio-a-undo")

            self.assertEqual(missing_per_request, [True, True, False])

    def test_caption_chunk_reuses_the_transformed_ocr_region_without_removing_it_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video_dir = root / "video-workspace"
            region_path = video_dir / "temp" / "original_subtitle_region.json"
            region_path.parent.mkdir(parents=True)
            region_path.write_text(
                json.dumps(
                    {
                        "region": {
                            "x_percent": 20,
                            "y_percent": 60,
                            "width_percent": 60,
                            "height_percent": 10,
                            "line_height_percent": 8,
                        }
                    }
                ),
                encoding="utf-8",
            )
            video = SimpleNamespace(
                video_id="video-ocr-preview",
                subtitle_style=SubtitleStyle(),
                crop=CropSettings(
                    left_percent=10,
                    right_percent=10,
                    top_percent=20,
                ),
                output_format="keep_ratio",
                subtitle_layout_override=False,
                remove_original_subtitles=True,
                original_subtitle_removal_mode="patch",
                watermark_text="",
                status="queued",
                files={},
            )
            controller = EditorPreviewController(self._host(video, source))
            calls = []

            def fake_render(*args, **kwargs):
                calls.append((args, kwargs))
                Path(args[3]).write_bytes(b"preview")

            with (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                    return_value=str(video_dir),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_duration",
                    return_value=8.0,
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_dimensions",
                    return_value=(1000, 1000),
                ),
                mock.patch("haizflow.desktop.editor_preview_controller.render_video", side_effect=fake_render),
                mock.patch("haizflow.desktop.editor_preview_controller.start_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.clean_video"),
            ):
                self.assertTrue(
                    controller.request(
                        json.dumps([{"start": 1, "end": 3, "text": "Translated"}]),
                        1.0,
                    )
                )
                self._wait_until_idle(controller)

            self.assertEqual(len(calls), 2)
            base_args, base_kwargs = calls[0]
            chunk_args, chunk_kwargs = calls[1]
            self.assertEqual(base_args[8]["y_percent"], 60)
            self.assertIsNone(base_kwargs["subtitle_region_override"])
            self.assertIsNone(chunk_args[8])
            mapped = chunk_kwargs["subtitle_region_override"]
            self.assertAlmostEqual(mapped["x_percent"], 12.5)
            self.assertAlmostEqual(mapped["y_percent"], 50.0)
            self.assertAlmostEqual(mapped["height_percent"], 12.5)

    def test_truncated_cached_proxy_is_rebuilt_before_qml_can_open_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video_dir = root / "video-workspace"
            video = SimpleNamespace(
                video_id="video-cache",
                subtitle_style=SubtitleStyle(),
                crop=CropSettings(),
                output_format="keep_ratio",
                subtitle_layout_override=False,
                remove_original_subtitles=True,
                original_subtitle_removal_mode="patch",
                watermark_text="",
            )
            host = SimpleNamespace(
                _selected_video=lambda: video,
                _resolve_video_file=lambda *_args: str(source),
                editorPreviewChanged=_Signal(),
            )
            controller = EditorPreviewController(host)
            render_count = 0

            def fake_duration(path):
                candidate = Path(path)
                if candidate.name == "preview.mp4" and candidate.is_file():
                    return 1.0 if candidate.read_bytes() == b"truncated" else 12.0
                return 12.0

            def fake_render(*args, **_kwargs):
                nonlocal render_count
                render_count += 1
                Path(args[3]).write_bytes(b"complete")

            def wait_until_idle():
                for _ in range(100):
                    if not controller.busy:
                        return
                    threading.Event().wait(0.02)
                self.fail("Editor preview worker did not finish")

            patches = (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                    return_value=str(video_dir),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_duration",
                    side_effect=fake_duration,
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.render_video",
                    side_effect=fake_render,
                ),
                mock.patch("haizflow.desktop.editor_preview_controller.start_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.clean_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.cancel_video"),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                self.assertTrue(controller.request('[{"start": 0, "end": 2, "text": "hello"}]', 0))
                wait_until_idle()
                published_path = Path(QUrl(controller.source).toLocalFile())
                published_path.write_bytes(b"truncated")

                self.assertTrue(controller.request('[{"start": 0, "end": 2, "text": "hello"}]', 8))
                wait_until_idle()

            # The published file is reassembled from intact chunks; no video
            # frames need to be encoded again.
            self.assertEqual(render_count, 2)
            self.assertEqual(published_path.read_bytes(), b"complete")

    def test_duplicate_request_keeps_the_active_preview_worker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video_dir = root / "video-workspace"
            video = SimpleNamespace(
                video_id="video-1",
                subtitle_style=SubtitleStyle(),
                crop=CropSettings(),
                output_format="keep_ratio",
                subtitle_layout_override=False,
                remove_original_subtitles=True,
                original_subtitle_removal_mode="patch",
                watermark_text="",
                tts_provider="edge",
                tts_voice="en-US-GuyNeural",
                target_language="en",
                speaker_mode="single",
                original_video_volume=60,
                background_music_volume=30,
                tts_volume=100,
                status="queued",
                files={},
            )
            host = self._host(video, source)
            controller = EditorPreviewController(host)
            entered = threading.Event()
            release = threading.Event()
            calls = 0

            def render(*args, **kwargs):
                nonlocal calls
                calls += 1
                entered.set()
                release.wait(2)
                Path(args[3]).write_bytes(b"preview")
                return 0, ""

            with (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                    return_value=str(video_dir),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_duration",
                    return_value=10.0,
                ),
                mock.patch("haizflow.desktop.editor_preview_controller.render_video", side_effect=render),
                mock.patch("haizflow.desktop.editor_preview_controller.start_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.clean_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.cancel_video") as cancel,
            ):
                payload = json.dumps([{"start": 0, "end": 1, "text": "Hello"}])
                self.assertTrue(controller.request(payload, 0))
                self.assertTrue(entered.wait(1))
                self.assertTrue(controller.request(payload, 0.7))
                self.assertEqual(calls, 1)
                cancel.assert_not_called()
                release.set()
                self._wait_until_idle(controller)
            published_path = Path(QUrl(controller.source).toLocalFile())
            self.assertEqual(published_path.read_bytes(), b"preview")

    def test_audio_only_setting_change_reuses_the_visual_proxy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video_dir = root / "video-workspace"
            video = SimpleNamespace(
                video_id="video-audio-setting",
                subtitle_style=SubtitleStyle(),
                crop=CropSettings(),
                output_format="keep_ratio",
                subtitle_layout_override=False,
                remove_original_subtitles=True,
                original_subtitle_removal_mode="patch",
                watermark_text="",
                tts_provider="edge",
                tts_voice="vi-VN-NamMinhNeural",
                target_language="vi",
                speaker_mode="single",
                original_video_volume=60,
                background_music_volume=30,
                tts_volume=100,
                status="queued",
                files={},
            )
            controller = EditorPreviewController(self._host(video, source))
            render_count = 0

            def render(*args, **_kwargs):
                nonlocal render_count
                render_count += 1
                Path(args[3]).write_bytes(b"preview")

            with (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                    return_value=str(video_dir),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_duration",
                    return_value=10.0,
                ),
                mock.patch("haizflow.desktop.editor_preview_controller.render_video", side_effect=render),
                mock.patch("haizflow.desktop.editor_preview_controller.start_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.clean_video"),
            ):
                payload = json.dumps([{"start": 0, "end": 1, "text": "Hello"}])
                self.assertTrue(controller.request(payload, 0))
                self._wait_until_idle(controller)
                self.assertEqual(render_count, 2)
                video.tts_voice = "vi-VN-HoaiMyNeural"
                self.assertTrue(controller.request(payload, 0))
                self._wait_until_idle(controller)
                self.assertEqual(render_count, 2)

                edited_payload = json.dumps([{"start": 0, "end": 1, "text": "Edited"}])
                self.assertTrue(controller.request(edited_payload, 0))
                self._wait_until_idle(controller)

            # The subtitle layer is rebuilt, while the expensive base proxy is reused.
            self.assertEqual(render_count, 3)

    def test_subtitle_edit_invalidates_only_the_overlapping_visual_chunk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video_dir = root / "video-workspace"
            video = SimpleNamespace(
                video_id="video-chunk-cache",
                subtitle_style=SubtitleStyle(),
                crop=CropSettings(),
                output_format="keep_ratio",
                subtitle_layout_override=False,
                remove_original_subtitles=True,
                original_subtitle_removal_mode="patch",
                watermark_text="",
                tts_provider="edge",
                tts_voice="vi-VN-NamMinhNeural",
                target_language="vi",
                speaker_mode="single",
                original_video_volume=60,
                background_music_volume=30,
                tts_volume=100,
                status="queued",
                files={},
            )
            controller = EditorPreviewController(self._host(video, source))
            render_starts = []

            def render(*args, **kwargs):
                render_starts.append(float(kwargs["source_start_seconds"]))
                Path(args[3]).write_bytes(b"preview")

            def assemble(
                _generation,
                _process_id,
                _chunk_paths,
                output_path,
                completion_path,
                expected_duration,
            ):
                output_path.write_bytes(b"assembled")
                controller._write_completion_marker(completion_path, output_path, expected_duration)
                return True

            with (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                    return_value=str(video_dir),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_duration",
                    return_value=30.0,
                ),
                mock.patch("haizflow.desktop.editor_preview_controller.render_video", side_effect=render),
                mock.patch("haizflow.desktop.editor_preview_controller.start_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.clean_video"),
                mock.patch.object(
                    controller,
                    "_assemble_preview_chunks",
                    side_effect=assemble,
                ),
            ):
                payload = json.dumps(
                    [
                        {"start": 1, "end": 3, "text": "First"},
                        {"start": 15, "end": 17, "text": "Second"},
                        {"start": 25, "end": 27, "text": "Third"},
                    ]
                )
                self.assertTrue(controller.request(payload, 0))
                self._wait_until_idle(controller)
                self.assertEqual(render_starts, [0.0, 0.0, 12.0, 24.0])

                edited = json.dumps(
                    [
                        {"start": 1, "end": 3, "text": "Edited first"},
                        {"start": 15, "end": 17, "text": "Second"},
                        {"start": 25, "end": 27, "text": "Third"},
                    ]
                )
                self.assertTrue(controller.request(edited, 1.5))
                self._wait_until_idle(controller)

            # The base and the two untouched chunks are reused. Only the
            # 0-12 second chunk intersecting the edit is encoded again.
            self.assertEqual(render_starts, [0.0, 0.0, 12.0, 24.0, 0.0])

    def test_changed_subtitle_publishes_a_versioned_audio_mix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video_dir = root / "video-workspace"
            temp_path = video_dir / "temp"
            parts_path = temp_path / "voice_parts"
            parts_path.mkdir(parents=True)
            transcript = temp_path / "vi_segments.json"
            transcript.write_text(
                json.dumps([{"start": 0.0, "end": 2.0, "text": "old text"}]),
                encoding="utf-8",
            )
            current_mix = temp_path / "voice_final.wav"
            current_mix.write_bytes(b"old-wave")
            video = SimpleNamespace(
                video_id="video-audio",
                status="done",
                subtitle_style=SubtitleStyle(),
                crop=CropSettings(),
                output_format="keep_ratio",
                subtitle_layout_override=False,
                remove_original_subtitles=False,
                original_subtitle_removal_mode="patch",
                watermark_text="",
                tts_provider="edge",
                tts_voice="vi-VN-NamMinhNeural",
                target_language="vi",
                speaker_mode="single",
                original_video_volume=60,
                background_music_volume=30,
                tts_volume=100,
                enable_audio_separation=False,
                files={
                    "transcript_json": str(transcript),
                    "voice_output": str(current_mix),
                },
            )
            host = SimpleNamespace(
                _selected_video=lambda: video,
                _resolve_video_file=lambda *_args: str(source),
                editorPreviewChanged=_Signal(),
            )
            controller = EditorPreviewController(host)
            voice_started = threading.Event()
            release_voice = threading.Event()

            def fake_render(*args, **_kwargs):
                Path(args[3]).write_bytes(b"preview")

            def fake_voice_parts(segments_path, parts_dir, *_args, progress_callback=None, **_kwargs):
                voice_started.set()
                release_voice.wait(2)
                payload = json.loads(Path(segments_path).read_text(encoding="utf-8"))
                for index, _segment in enumerate(payload, 1):
                    (Path(parts_dir) / f"voice_{index:04d}.mp3").write_bytes(b"mp3")
                if progress_callback:
                    progress_callback(len(payload), len(payload))

            def fake_audio_timeline(_segments, _parts, _video, output, *_args, **_kwargs):
                Path(output).write_bytes(b"new-wave")

            with (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                    return_value=str(video_dir),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_duration",
                    return_value=6.0,
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.render_video",
                    side_effect=fake_render,
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.generate_voice_parts",
                    side_effect=fake_voice_parts,
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.build_audio_timeline",
                    side_effect=fake_audio_timeline,
                ),
                mock.patch("haizflow.desktop.editor_preview_controller.start_video"),
                mock.patch("haizflow.desktop.editor_preview_controller.clean_video"),
            ):
                self.assertTrue(
                    controller.request(
                        json.dumps([{"start": 0.0, "end": 2.0, "text": "new text"}]),
                        0.0,
                    )
                )
                self.assertTrue(voice_started.wait(1))
                # Keep the old version on screen until both the new visual
                # proxy and its regenerated voice are ready to swap together.
                self.assertEqual(controller.source, "")
                self.assertEqual(controller.audio_source, "")
                release_voice.set()
                self._wait_until_idle(controller)

            audio_path = Path(QUrl(controller.audio_source).toLocalFile())
            self.assertTrue(audio_path.is_file())
            self.assertEqual(audio_path.read_bytes(), b"new-wave")
            self.assertNotEqual(audio_path, current_mix)


if __name__ == "__main__":
    unittest.main()
