import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PySide6.QtCore import QUrl

from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.schemas.video import CropSettings, SubtitleStyle
from haizflow.services import manual_artifacts
from haizflow.utils.ffmpeg import _binary, get_video_duration


class _Signal:
    def __init__(self):
        self.changed = threading.Event()

    def emit(self):
        self.changed.set()


class EditorPreviewControllerTests(unittest.TestCase):
    def test_real_trim_keeps_treated_pixels_and_skips_source_sequence_encode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            preview = root / "editor-preview"
            old_base = preview / "base-original"
            old_base.mkdir(parents=True)
            treated = old_base / "preview.mp4"
            for path, color in ((source, "red"), (treated, "green")):
                subprocess.run([
                    _binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"color=c={color}:s=64x64:r=10:d=2", "-c:v", "mpeg4", str(path),
                ], check=True, capture_output=True)
            settings = {
                "video_id": "trim-real", "source_path": str(source),
                "source_identity": {"path": str(source), "size": source.stat().st_size},
                "editor_sequence": {"duration_ms": 1000, "edit_decisions": [{
                    "decision_id": "trim", "source_start_ms": 500,
                    "source_end_ms": 1500, "sequence_start_ms": 0,
                }]},
                "segments": [], "subtitle_style": {}, "crop": {},
                "output_format": "keep_ratio", "subtitle_layout_override": False,
                "remove_original_subtitles": True, "removal_mode": "patch",
                "watermark_text": "", "watermark_scale_percent": 100,
                "ocr_region": {}, "original_subtitle_intervals": [],
                "preview_encoding": "test", "image_generation": 1,
                "independent_manual_preview": True, "original_video_volume": 60,
                "background_music_volume": 30, "tts_volume": 100,
                "audio_inputs": {}, "request_fingerprint": "trim",
            }
            EditorPreviewController._write_completion_marker(
                old_base / "preview.complete.json", treated, 2,
                base_context={"effects": EditorPreviewController._source_effects_key(settings),
                              "source_start": 0, "duration": 2},
            )
            video = SimpleNamespace(video_id="trim-real", crop=CropSettings(), subtitle_style=SubtitleStyle())
            controller = EditorPreviewController(SimpleNamespace(editorPreviewChanged=_Signal()))
            controller._generation = 1
            controller._active_process_id = "trim-real-preview"
            calls = []

            def render_proxy(*args, **kwargs):
                path, destination, _marker = args[3:6]
                calls.append((path, kwargs["source_start_seconds"]))
                subprocess.run([
                    _binary("ffmpeg"), "-y", "-v", "error", "-ss",
                    str(kwargs["source_start_seconds"]), "-i", path,
                    "-t", str(args[7]), "-c:v", "mpeg4", str(destination),
                ], check=True, capture_output=True)
                return True

            with (
                mock.patch.object(controller, "_render_proxy_layer", side_effect=render_proxy),
                mock.patch.object(controller, "_materialize_preview_sequence") as materialize,
                mock.patch.object(controller, "_finish_success") as finish,
                mock.patch.object(controller, "_finish_error") as fail,
            ):
                controller._render_current(1, "trim-real-preview", video, settings, preview)
            fail.assert_not_called()
            materialize.assert_not_called()
            finish.assert_called_once()
            self.assertEqual(calls, [(str(treated), .5)])
            output = finish.call_args.args[1]
            self.assertAlmostEqual(get_video_duration(str(output)), 1, delta=.15)
            frame = subprocess.run([
                _binary("ffmpeg"), "-v", "error", "-i", str(output),
                "-frames:v", "1", "-vf", "scale=1:1", "-pix_fmt", "rgb24",
                "-f", "rawvideo", "pipe:1",
            ], check=True, capture_output=True).stdout
            self.assertGreater(frame[1], frame[0] + 40, "Trim must keep treated green pixels, not raw red source")

    def test_single_edge_trim_is_one_source_window_without_intermediate_encode(self):
        sequence = {"duration_ms": 6000, "edit_decisions": [
            {"source_start_ms": 2000, "source_end_ms": 8000, "sequence_start_ms": 0}]}
        self.assertEqual(EditorPreviewController._contiguous_source_window(sequence), (2.0, 6.0))
        sequence["duration_ms"] = 9000
        self.assertIsNone(EditorPreviewController._contiguous_source_window(sequence))

    def test_trim_reuses_only_matching_treated_base_and_not_stale_effects(self):
        settings = {"video_id": "video", "source_identity": {"size": 1}, "crop": {},
                    "output_format": "keep_ratio", "remove_original_subtitles": True,
                    "removal_mode": "patch", "watermark_text": "", "watermark_scale_percent": 100,
                    "ocr_region": {}, "preview_encoding": "test", "image_generation": 1}
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            base = directory / "base-original"
            base.mkdir()
            output = base / "preview.mp4"
            output.write_bytes(b"treated video")
            EditorPreviewController._write_completion_marker(base / "preview.complete.json", output, 10,
                base_context={"effects": EditorPreviewController._source_effects_key(settings), "source_start": 0, "duration": 10})
            self.assertEqual(EditorPreviewController._reusable_treated_base(directory, settings, 2, 6), (output, 2))
            self.assertIsNone(EditorPreviewController._reusable_treated_base(directory, {**settings, "image_generation": 2}, 2, 6))
            self.assertIsNone(EditorPreviewController._reusable_treated_base(directory, settings, 2, 12))

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

    def test_visual_only_changes_do_not_invalidate_preview_audio(self):
        settings = {
            "video_id": "video-1",
            "source_identity": {"path": "input.mp4", "size": 1},
            "segments": [{"start": 0, "end": 1, "text": "Xin chào"}],
            "tts_provider": "omnivoice",
            "tts_voice": "omnivoice:male",
            "target_language": "vi",
            "speaker_mode": "single",
            "original_video_volume": 60,
            "background_music_volume": 30,
            "tts_volume": 100,
            "audio_inputs": {},
            "duration": 10.0,
            "removal_mode": "patch",
            "subtitle_style": {"font_size": 48},
        }
        changed = dict(settings, removal_mode="blur", subtitle_style={"font_size": 60})

        self.assertEqual(
            EditorPreviewController._audio_cache_payload(settings),
            EditorPreviewController._audio_cache_payload(changed),
        )

    def test_manual_watermark_is_a_live_layer_not_a_base_proxy_dependency(self):
        settings = {
            "video_id": "video-1",
            "source_identity": {"path": "input.mp4", "size": 1},
            "crop": {},
            "output_format": "keep_ratio",
            "remove_original_subtitles": True,
            "removal_mode": "patch",
            "watermark_text": "HaizFlow",
            "watermark_scale_percent": 100,
            "ocr_region": {},
            "original_subtitle_intervals": [],
            "preview_encoding": "manual-base-pcm-libass-watermark-overlay-v2",
            "independent_manual_preview": True,
        }
        changed = dict(
            settings,
            watermark_text="Mạch Hồng Hải",
            watermark_scale_percent=240,
        )

        self.assertEqual(
            EditorPreviewController._base_visual_cache_payload(settings),
            EditorPreviewController._base_visual_cache_payload(changed),
        )

    def test_completing_manual_voice_invalidates_a_silent_preview_request(self):
        settings = {
            "video_id": "video-1",
            "source_identity": {"path": "input.mp4", "size": 1},
            "segments": [{"start": 0, "end": 1, "text": "Xin chào"}],
            "tts_provider": "omnivoice",
            "tts_voice": "omnivoice:male",
            "target_language": "vi",
            "speaker_mode": "single",
            "original_video_volume": 60,
            "background_music_volume": 30,
            "tts_volume": 100,
            "audio_inputs": {},
            "voice_state": {"checkpoint": "", "ready": False},
            "duration": 10.0,
        }
        completed = {
            **settings,
            "voice_state": {"checkpoint": "voice-signature", "ready": True},
        }

        self.assertNotEqual(
            EditorPreviewController._audio_cache_payload(settings),
            EditorPreviewController._audio_cache_payload(completed),
        )

    def test_manual_preview_keeps_published_voice_while_a_new_preset_is_pending(self):
        video = SimpleNamespace(
            video_id="manual-video",
            project_type="manual",
            tts_provider="omnivoice",
            tts_voice="omnivoice:male",
            speaker_mode="single",
            active_artifacts={
                "subtitle_document": "subtitle-current",
                "tts_manifest": "voice-current",
            },
        )
        record = {
            "artifact_id": "tts_manifest:voice-current",
            "signature": "voice-current",
            "config_fingerprint": manual_artifacts.signature(
                "omnivoice", "omnivoice:male", "single"
            ),
            "inputs": ["subtitle_document:subtitle-current"],
        }

        with mock.patch(
            "haizflow.desktop.editor_preview_controller.manual_artifacts.peek",
            return_value=record,
        ) as peek:
            self.assertEqual(EditorPreviewController._manual_voice_artifact(video), record)

        peek.assert_called_once_with("manual-video", "tts_manifest", "voice-current")

        pending_replacement = {**record, "config_fingerprint": "old-voice-settings"}
        with mock.patch(
            "haizflow.desktop.editor_preview_controller.manual_artifacts.peek",
            return_value=pending_replacement,
        ):
            self.assertEqual(
                EditorPreviewController._manual_voice_artifact(video),
                pending_replacement,
            )

    def test_manual_visual_preview_is_published_into_the_artifact_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rendered = root / "editor" / "visual" / "preview.mp4"
            base_rendered = root / "editor" / "base" / "preview.mp4"
            cached = root / "cache" / "preview.mp4"
            rendered.parent.mkdir(parents=True)
            base_rendered.parent.mkdir(parents=True)
            cached.parent.mkdir(parents=True)
            rendered.write_bytes(b"rendered-preview")
            base_rendered.write_bytes(b"subtitle-free-preview")
            cached.write_bytes(b"cached-preview")
            video = SimpleNamespace(
                video_id="manual-video",
                project_type="manual",
                active_artifacts={"subtitle_document": "subtitle-signature"},
            )
            host = SimpleNamespace(editorPreviewChanged=_Signal())
            controller = EditorPreviewController(host)
            controller._generation = 1
            controller._video_id = video.video_id
            controller._request_fingerprint = "request-with-audio"

            with (
                mock.patch.object(controller, "_remove_stale_files"),
                mock.patch.object(controller, "_remove_stale_audio_dirs"),
                mock.patch("haizflow.desktop.editor_preview_controller.manual_artifacts.pin"),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.video_store.get_video",
                    return_value=video,
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.manual_artifacts.register_existing",
                    return_value={"resolved_outputs": {"video": str(cached)}},
                ) as register,
            ):
                controller._finish_success(
                    1,
                    rendered,
                    0.0,
                    5.0,
                    request_fingerprint="request-with-audio",
                    visual_signature="visual-only",
                    base_playback_path=base_rendered,
                )

            # The artifact cache stores the visual-only proxy. Playback keeps
            # the caller's media path, which may be a synchronized A/V mux.
            self.assertEqual(Path(QUrl(controller.source).toLocalFile()), rendered)
            self.assertEqual(Path(QUrl(controller.base_source).toLocalFile()), base_rendered)
            self.assertEqual(controller.audio_source, "")
            register.assert_called_once()
            self.assertEqual(register.call_args.args[2], "visual-only")

    def test_preview_mux_uses_one_audio_video_file_and_reuses_its_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            visual = root / "visual.mp4"
            audio = root / "audio.wav"
            visual.write_bytes(b"video")
            audio.write_bytes(b"RIFF" + b"audio" * 20)
            controller = EditorPreviewController(SimpleNamespace(editorPreviewChanged=_Signal()))
            controller._generation = 1
            controller._active_process_id = "preview-mux"

            def spawn(command, **_kwargs):
                Path(command[-1]).write_bytes(b"muxed-media")
                return SimpleNamespace(returncode=0)

            with (
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.subprocess.Popen",
                    side_effect=spawn,
                ) as popen,
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.communicate_process",
                    return_value=("", ""),
                ),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.get_video_duration",
                    return_value=5.0,
                ),
            ):
                first = controller._mux_preview_media(
                    1, "preview-mux", visual, audio, root / "preview", 5.0
                )
                second = controller._mux_preview_media(
                    1, "preview-mux", visual, audio, root / "preview", 5.0
                )

            self.assertEqual(first, second)
            self.assertTrue(first.is_file())
            popen.assert_called_once()
            command = popen.call_args.args[0]
            self.assertIn("copy", command)
            self.assertIn("aac", command)
            self.assertEqual(command.count("-map"), 2)

    def test_manual_preview_audio_remains_available_while_another_tool_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            source.write_bytes(b"source")
            video = SimpleNamespace(
                video_id="manual-processing",
                project_type="manual",
                status="processing",
                enable_audio_separation=False,
                files={},
            )
            controller = EditorPreviewController(self._host(video, source))
            controller._generation = 1
            settings = {
                "segments": [],
                "tts_voice": "omnivoice:female",
                "tts_provider": "omnivoice",
                "target_language": "vi",
                "speaker_mode": "single",
                "source_path": str(source),
                "original_video_volume": 60,
                "background_music_volume": 0,
                "tts_volume": 100,
                "duration": 1.0,
                "audio_inputs": {"voice_reference": {}},
            }

            def fake_mix(_segments, _parts, _source, output, *_args, **_kwargs):
                Path(output).write_bytes(b"RIFF" + b"\x00" * 100)

            with (
                mock.patch.object(controller, "_manual_voice_artifact", return_value=None),
                mock.patch(
                    "haizflow.desktop.editor_preview_controller.build_audio_timeline",
                    side_effect=fake_mix,
                ),
            ):
                mixed = controller._prepare_preview_audio(
                    1,
                    "preview-processing",
                    video,
                    settings,
                    root / "audio",
                )

            self.assertIsNotNone(mixed)
            self.assertTrue(mixed.is_file())

    def test_obsolete_worker_cannot_restart_its_cancelled_process(self):
        host = SimpleNamespace(editorPreviewChanged=_Signal())
        controller = EditorPreviewController(host)
        controller._generation = 1
        controller._active_process_id = "preview-old"
        entered_probe = threading.Event()
        release_probe = threading.Event()

        def blocked_duration(_path):
            entered_probe.set()
            release_probe.wait(2.0)
            return 10.0

        worker = threading.Thread(
            target=controller._render,
            args=(
                1,
                "preview-old",
                SimpleNamespace(video_id="video-old"),
                {"source_path": "input.mp4"},
                Path("preview"),
            ),
        )
        with (
            mock.patch.object(controller, "_source_duration", side_effect=blocked_duration),
            mock.patch("haizflow.desktop.editor_preview_controller.start_video") as start,
        ):
            worker.start()
            self.assertTrue(entered_probe.wait(1.0))
            with controller._lock:
                controller._generation = 2
                controller._active_process_id = "preview-new"
            release_probe.set()
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        start.assert_not_called()

    def test_clear_cache_keeps_media_currently_open_in_preview(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_dir = Path(temp_dir)
            preview_root = video_dir / "temp" / "editor-preview"
            current_dir = preview_root / "visual-current"
            stale_dir = preview_root / "visual-stale"
            current_dir.mkdir(parents=True)
            stale_dir.mkdir(parents=True)
            current = current_dir / "preview.mp4"
            stale = stale_dir / "preview.mp4"
            current.write_bytes(b"current")
            stale.write_bytes(b"stale")
            controller = EditorPreviewController(SimpleNamespace(editorPreviewChanged=_Signal()))
            controller._video_id = "video-clear"
            controller._source = QUrl.fromLocalFile(str(current)).toString()

            with mock.patch(
                "haizflow.desktop.editor_preview_controller.video_store.get_video_dir",
                return_value=str(video_dir),
            ):
                removed = controller.clear_cache("video-clear")

            self.assertEqual(removed, len(b"stale"))
            self.assertTrue(current.is_file())
            self.assertFalse(stale.exists())

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
            workspace_temp = video_dir / "temp"
            original_parts = workspace_temp / "voice_parts"
            original_parts.mkdir(parents=True)
            (original_parts / "voice_0001.mp3").write_bytes(b"voice" * 100)
            transcript = workspace_temp / "segments.json"
            transcript.write_text(
                json.dumps([{"start": 0.0, "end": 1.0, "text": "Câu A"}]),
                encoding="utf-8",
            )
            video = SimpleNamespace(
                video_id="video-audio-cache",
                status="done",
                files={"transcript_json": str(transcript)},
                enable_audio_separation=False,
            )
            controller = EditorPreviewController(self._host(video, source))
            controller._generation = 1

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
                    "haizflow.desktop.editor_preview_controller.build_audio_timeline",
                    side_effect=fake_mix,
                ),
            ):
                first = controller._prepare_preview_audio(
                    1, "preview-1", video, base_settings, root / "audio-a"
                )
                changed = {**base_settings, "segments": [{"start": 0.0, "end": 1.0, "text": "Câu B"}]}
                with self.assertRaisesRegex(RuntimeError, "tạo lại giọng"):
                    controller._prepare_preview_audio(
                        1, "preview-2", video, changed, root / "audio-b"
                    )
                (original_parts / "voice_0001.mp3").unlink()
                undo = controller._prepare_preview_audio(
                    1, "preview-3", video, base_settings, root / "audio-a-undo"
                )

            self.assertEqual(first.read_bytes(), b"RIFF" + b"\x00" * 100)
            self.assertEqual(undo.read_bytes(), b"RIFF" + b"\x00" * 100)

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

    def test_changed_subtitle_keeps_the_synchronized_pair_until_voice_is_run(self):
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
            controller._source = "file:///previous-preview.mp4"
            controller._audio_source = "file:///previous-preview.wav"

            def fake_render(*args, **_kwargs):
                Path(args[3]).write_bytes(b"preview")

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
                    "haizflow.desktop.editor_preview_controller.build_audio_timeline",
                    side_effect=AssertionError("preview must not mix missing voice clips"),
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
                self._wait_until_idle(controller)

            self.assertEqual(controller.source, "file:///previous-preview.mp4")
            self.assertEqual(controller.audio_source, "file:///previous-preview.wav")
            self.assertIn("tạo lại giọng", controller.error)

    def test_cache_cleanup_keeps_only_chunks_referenced_by_retained_visuals(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            preview_dir = Path(temp_dir) / "editor-preview"
            preview_dir.mkdir()
            chunk_names = ["chunk-current", "chunk-undo", "chunk-stale"]
            for index, name in enumerate(chunk_names):
                chunk_dir = preview_dir / name
                chunk_dir.mkdir()
                (chunk_dir / "preview.mp4").write_bytes(b"chunk")
                os.utime(chunk_dir / "preview.mp4", (100 + index, 100 + index))

            visual_paths = []
            for index in range(5):
                visual_dir = preview_dir / f"visual-{index}"
                visual_dir.mkdir()
                visual_path = visual_dir / "preview.mp4"
                visual_path.write_bytes(b"visual")
                os.utime(visual_path, (200 + index, 200 + index))
                marker = {
                    "version": 1,
                    "duration": 10,
                    "size": visual_path.stat().st_size,
                    "chunk_directories": ["chunk-current"] if index == 4 else ["chunk-undo"],
                }
                (visual_dir / "preview.complete.json").write_text(
                    json.dumps(marker), encoding="utf-8"
                )
                visual_paths.append(visual_path)

            EditorPreviewController._remove_stale_files(visual_paths[-1])

            self.assertTrue((preview_dir / "chunk-current").is_dir())
            self.assertTrue((preview_dir / "chunk-undo").is_dir())
            self.assertFalse((preview_dir / "chunk-stale").exists())
            self.assertFalse((preview_dir / "visual-0").exists())


if __name__ == "__main__":
    unittest.main()
