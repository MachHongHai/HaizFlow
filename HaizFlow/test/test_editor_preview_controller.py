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
            captured = {}
            render_done = threading.Event()

            def fake_render(*args, **kwargs):
                captured["args"] = args
                captured["kwargs"] = kwargs
                Path(args[3]).write_bytes(b"preview")
                render_done.set()

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
            self.assertEqual(captured["kwargs"]["source_start_seconds"], 0.0)
            self.assertEqual(captured["kwargs"]["source_duration_seconds"], 20.0)
            self.assertTrue(captured["kwargs"]["compatibility_preview"])
            self.assertEqual(captured["args"][7], "video-1")
            self.assertTrue(captured["kwargs"]["process_registry_id"].startswith("editor-preview-video-1-"))
            subtitle_path = Path(captured["args"][2])
            # Temporary source files are removed after a successful proxy.
            self.assertFalse(subtitle_path.exists())
            self.assertRegex(
                Path(captured["args"][3]).name,
                r"preview-\d+\.rendering\.mp4",
            )
            self.assertNotEqual(Path(captured["args"][3]).parent, video_dir / "temp" / "editor-preview")
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

            self.assertEqual(render_count, 2)
            self.assertEqual(published_path.read_bytes(), b"complete")

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

            def fake_render(*args, **_kwargs):
                Path(args[3]).write_bytes(b"preview")

            def fake_voice_parts(segments_path, parts_dir, *_args, progress_callback=None, **_kwargs):
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
                self._wait_until_idle(controller)

            audio_path = Path(QUrl(controller.audio_source).toLocalFile())
            self.assertTrue(audio_path.is_file())
            self.assertEqual(audio_path.read_bytes(), b"new-wave")
            self.assertNotEqual(audio_path, current_mix)


if __name__ == "__main__":
    unittest.main()
