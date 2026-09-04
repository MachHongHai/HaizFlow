import inspect
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from haizflow.pipeline import manual_tools
from haizflow.services import manual_artifacts


class ManualArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.video = SimpleNamespace(video_id="manual-video", active_artifacts={}, project_type="manual")

        def update_video(_video_id, **changes):
            for name, value in changes.items():
                setattr(self.video, name, value)
            return self.video

        self.patches = [
            patch.object(manual_artifacts.video_store, "get_video_dir", return_value=str(self.root)),
            patch.object(manual_artifacts.video_store, "get_video", return_value=self.video),
            patch.object(manual_artifacts.video_store, "update_video", side_effect=update_video),
            patch.object(manual_artifacts.video_store, "list_videos", return_value=[self.video]),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def publish_text(self, signature, text):
        staging = manual_artifacts.create_staging_directory(self.video.video_id, "translation")
        (staging / "segments.json").write_text(text, encoding="utf-8")
        return manual_artifacts.publish(
            self.video.video_id,
            "translation",
            signature,
            staging,
            {"segments": "segments.json"},
        )

    def test_publish_is_atomic_and_activates_exact_variant(self):
        record = self.publish_text("first", "[]")

        self.assertEqual(self.video.active_artifacts["translation"], "first")
        self.assertEqual(Path(record["resolved_outputs"]["segments"]).read_text(encoding="utf-8"), "[]")
        self.assertTrue(
            (
                manual_artifacts.artifact_directory("manual-video", "translation", "first")
                / "complete.json"
            ).is_file()
        )

    def test_corrupted_cache_is_rejected(self):
        record = self.publish_text("broken", "[]")
        Path(record["resolved_outputs"]["segments"]).write_text("[1]", encoding="utf-8")

        self.assertIsNone(manual_artifacts.resolve("manual-video", "translation", "broken"))
        stored = manual_artifacts.load_manifest("manual-video")["artifacts"]["translation:broken"]
        self.assertEqual(stored["status"], "invalid")

    def test_ui_peek_checks_structure_without_hashing_media(self):
        self.publish_text("quick", "[]")

        with patch.object(
            manual_artifacts,
            "_sha256",
            side_effect=AssertionError("UI cache inspection must not hash files"),
        ):
            record = manual_artifacts.peek("manual-video", "translation", "quick")

        self.assertIsNotNone(record)
        self.assertTrue(Path(record["resolved_outputs"]["segments"]).is_file())

    def test_failed_request_is_recorded_without_becoming_a_cache_hit(self):
        manual_artifacts.record_error(
            "manual-video",
            "translation",
            "failed-signature",
            "model failed",
        )

        stored = manual_artifacts.load_manifest("manual-video")["artifacts"]["translation:failed-signature"]
        self.assertEqual(stored["status"], "error")
        self.assertEqual(stored["outputs"], {})
        self.assertIsNone(manual_artifacts.resolve("manual-video", "translation", "failed-signature"))

    def test_republish_replaces_a_corrupted_directory_for_the_same_signature(self):
        record = self.publish_text("same", "[]")
        Path(record["resolved_outputs"]["segments"]).write_text("corrupt", encoding="utf-8")

        repaired = self.publish_text("same", "[{}]")

        self.assertEqual(
            Path(repaired["resolved_outputs"]["segments"]).read_text(encoding="utf-8"),
            "[{}]",
        )

    def test_switching_back_to_an_existing_variant_does_not_republish(self):
        self.publish_text("a", "[]")
        self.publish_text("b", "[{}]")

        manual_artifacts.activate("manual-video", "translation", "a")
        resolved = manual_artifacts.resolve("manual-video", "translation", "a")

        self.assertIsNotNone(resolved)
        self.assertEqual(self.video.active_artifacts["translation"], "a")

    def test_prune_never_deletes_active_artifact(self):
        self.publish_text("active", "[]")
        inactive = self.publish_text("inactive", "[{}]")
        manual_artifacts.activate("manual-video", "translation", "active")

        manual_artifacts.prune("manual-video", limit_bytes=1)

        self.assertIsNotNone(manual_artifacts.resolve("manual-video", "translation", "active"))
        self.assertFalse(Path(inactive["resolved_outputs"]["segments"]).exists())

    def test_prune_and_clear_preserve_live_nested_staging(self):
        manifest_stage = manual_artifacts.create_staging_directory("manual-video", "tts_manifest")
        parts = manifest_stage / "parts"
        parts.mkdir()
        (parts / "voice_0001.mp3").write_bytes(b"ID3" + b"voice" * 64)

        manual_artifacts.prune("manual-video", limit_bytes=1)
        manual_artifacts.clear("manual-video", include_active=False)

        self.assertTrue(manifest_stage.is_dir())
        self.assertTrue((parts / "voice_0001.mp3").is_file())
        manual_artifacts.release_staging_directory(manifest_stage)

    def test_child_artifact_can_be_published_without_becoming_active(self):
        clip_stage = manual_artifacts.create_staging_directory("manual-video", "tts_clip")
        (clip_stage / "voice.mp3").write_bytes(b"ID3" + b"voice" * 64)

        record = manual_artifacts.publish(
            "manual-video",
            "tts_clip",
            "clip-child",
            clip_stage,
            {"audio": "voice.mp3"},
            activate_artifact=False,
        )

        self.assertIsNotNone(record)
        self.assertNotIn("tts_clip", self.video.active_artifacts)
        self.assertIsNotNone(manual_artifacts.resolve("manual-video", "tts_clip", "clip-child"))

    def test_publish_does_not_run_cache_maintenance_per_artifact(self):
        with (
            patch.object(manual_artifacts, "prune") as project_prune,
            patch.object(manual_artifacts, "prune_global") as global_prune,
        ):
            self.publish_text("no-inline-maintenance", "[]")

        project_prune.assert_not_called()
        global_prune.assert_not_called()

    def test_clear_pins_the_dependency_closure_of_active_artifacts(self):
        clip_stage = manual_artifacts.create_staging_directory("manual-video", "tts_clip")
        (clip_stage / "voice.mp3").write_bytes(b"ID3" + b"voice" * 64)
        clip = manual_artifacts.publish(
            "manual-video", "tts_clip", "clip-a", clip_stage, {"audio": "voice.mp3"}
        )
        manifest_stage = manual_artifacts.create_staging_directory("manual-video", "tts_manifest")
        (manifest_stage / "manifest.json").write_text('{"clips":["clip-a"]}', encoding="utf-8")
        manual_artifacts.publish(
            "manual-video",
            "tts_manifest",
            "voice-a",
            manifest_stage,
            {"manifest": "manifest.json"},
            inputs=[clip["artifact_id"]],
        )
        # video.json only needs to expose the top-level active artifact.  Its
        # immutable children are discovered from the manifest graph.
        self.video.active_artifacts.pop("tts_clip", None)

        manual_artifacts.clear("manual-video", include_active=False)

        self.assertIsNotNone(manual_artifacts.resolve("manual-video", "tts_clip", "clip-a"))
        self.assertIsNotNone(manual_artifacts.resolve("manual-video", "tts_manifest", "voice-a"))

    def test_visible_legacy_subtitles_are_republished_as_active_editor_state(self):
        transcript = self.root / "translated.json"
        transcript.write_text('[{"start":0,"end":1,"text":"Xin chào"}]', encoding="utf-8")
        self.video.files = {"transcript_json": str(transcript)}
        self.video.subtitle_style = {}

        def fake_srt(_source, destination, *_args):
            Path(destination).write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n", encoding="utf-8")

        with patch.object(manual_tools, "generate_srt", side_effect=fake_srt):
            record = manual_tools.ensure_current_subtitle_document("manual-video")

        self.assertIsNotNone(record)
        self.assertIn("subtitle_document", self.video.active_artifacts)
        self.assertEqual(
            json.loads(Path(record["resolved_outputs"]["segments"]).read_text(encoding="utf-8")),
            json.loads(transcript.read_text(encoding="utf-8")),
        )

    def test_active_voice_survives_single_speaker_timing_edits_but_not_text_edits(self):
        self.video.tts_provider = "omnivoice"
        self.video.tts_voice = "omnivoice:male"
        self.video.speaker_mode = "single"

        def subtitle(signature, start, text):
            staging = manual_artifacts.create_staging_directory("manual-video", "subtitle_document")
            (staging / "segments.json").write_text(
                json.dumps([{"start": start, "end": start + 1, "text": text}]),
                encoding="utf-8",
            )
            (staging / "subtitles.srt").write_text("subtitle", encoding="utf-8")
            return manual_artifacts.publish(
                "manual-video",
                "subtitle_document",
                signature,
                staging,
                {"segments": "segments.json", "srt": "subtitles.srt"},
            )

        original = subtitle("subtitle-original", 0, "Xin chào")
        voice_stage = manual_artifacts.create_staging_directory("manual-video", "tts_manifest")
        (voice_stage / "manifest.json").write_text("{}", encoding="utf-8")
        voice = manual_artifacts.publish(
            "manual-video",
            "tts_manifest",
            "voice-current",
            voice_stage,
            {"manifest": "manifest.json"},
            inputs=[original["artifact_id"]],
            config_fingerprint=manual_artifacts.signature(
                "omnivoice", "omnivoice:male", "single"
            ),
        )

        subtitle("subtitle-timing", 3, "Xin chào")
        self.assertEqual(manual_tools.active_voice_record(self.video), voice)

        self.video.speaker_mode = "multiple"
        self.assertIsNone(manual_tools.active_voice_record(self.video))
        self.video.speaker_mode = "single"
        subtitle("subtitle-text", 3, "Nội dung mới")
        self.assertIsNone(manual_tools.active_voice_record(self.video))

    def test_timing_edit_keeps_voice_clips_and_invalidates_only_rendered_consumers(self):
        self.video.subtitle_style = {}
        self.video.files = {
            "voice_parts_dir": str(self.root / "parts"),
            "voice_output": str(self.root / "old-mix.wav"),
        }
        stage = manual_artifacts.create_staging_directory("manual-video", "subtitle_document")
        (stage / "segments.json").write_text(
            '[{"start":0,"end":1,"text":"Xin chào"}]', encoding="utf-8"
        )
        (stage / "subtitles.srt").write_text("subtitle", encoding="utf-8")
        manual_artifacts.publish(
            "manual-video",
            "subtitle_document",
            "subtitle-before",
            stage,
            {"segments": "segments.json", "srt": "subtitles.srt"},
        )
        self.video.active_artifacts.update(
            tts_manifest="voice-current",
            audio_mix="mix-current",
            visual_proxy="visual-current",
            export="export-current",
        )

        with patch.object(manual_tools, "generate_srt", side_effect=lambda _s, d, *_a: Path(d).write_text("srt")):
            manual_tools.publish_edited_subtitles(
                "manual-video", [{"start": 2, "end": 3, "text": "Xin chào"}]
            )

        self.assertEqual(self.video.active_artifacts.get("tts_manifest"), "voice-current")
        self.assertNotIn("audio_mix", self.video.active_artifacts)
        self.assertNotIn("visual_proxy", self.video.active_artifacts)
        self.assertNotIn("export", self.video.active_artifacts)
        self.assertIn("voice_parts_dir", self.video.files)
        self.assertNotIn("voice_output", self.video.files)

    def test_text_edit_detaches_voice_and_its_rendered_consumers(self):
        self.video.subtitle_style = {}
        self.video.files = {
            "voice_parts_dir": str(self.root / "parts"),
            "voice_output": str(self.root / "old-mix.wav"),
        }
        stage = manual_artifacts.create_staging_directory("manual-video", "subtitle_document")
        (stage / "segments.json").write_text(
            '[{"start":0,"end":1,"text":"Câu cũ"}]', encoding="utf-8"
        )
        (stage / "subtitles.srt").write_text("subtitle", encoding="utf-8")
        manual_artifacts.publish(
            "manual-video",
            "subtitle_document",
            "subtitle-before",
            stage,
            {"segments": "segments.json", "srt": "subtitles.srt"},
        )
        self.video.active_artifacts.update(
            tts_manifest="voice-current",
            audio_mix="mix-current",
            visual_proxy="visual-current",
            export="export-current",
        )

        with patch.object(manual_tools, "generate_srt", side_effect=lambda _s, d, *_a: Path(d).write_text("srt")):
            manual_tools.publish_edited_subtitles(
                "manual-video", [{"start": 0, "end": 1, "text": "Câu mới"}]
            )

        for kind in ("tts_manifest", "audio_mix", "visual_proxy", "export"):
            self.assertNotIn(kind, self.video.active_artifacts)
        self.assertNotIn("voice_parts_dir", self.video.files)
        self.assertNotIn("voice_output", self.video.files)

    def test_atomic_manifest_replace_retries_a_transient_windows_denial(self):
        destination = self.root / "manifest.json"
        real_replace = os.replace
        attempts = 0

        def flaky_replace(source, target):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError(5, "Access is denied", str(target))
            return real_replace(source, target)

        with (
            patch.object(manual_artifacts.os, "replace", side_effect=flaky_replace),
            patch.object(manual_artifacts.time, "sleep"),
        ):
            manual_artifacts._write_json_atomic(destination, {"ok": True})

        self.assertEqual(attempts, 2)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"ok": True})

    def test_concurrent_manifest_updates_do_not_overwrite_each_other(self):
        self.publish_text("base", "[]")
        threads = [
            threading.Thread(
                target=manual_artifacts.record_error,
                args=("manual-video", "tts_clip", f"failed-{index}", f"error-{index}"),
            )
            for index in range(12)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        artifacts = manual_artifacts.load_manifest("manual-video")["artifacts"]
        self.assertIn("translation:base", artifacts)
        for index in range(12):
            self.assertIn(f"tts_clip:failed-{index}", artifacts)

    def test_retranslation_preserves_independent_editor_settings_and_detaches_old_voice(self):
        self.video.active_artifacts = {
            "source_audio": "source-a",
            "separation": "separation-a",
            "ocr_region": "ocr-a",
            "subtitle_document": "subtitle-old",
            "tts_manifest": "voice-old",
            "audio_mix": "mix-old",
            "visual_proxy": "visual-old",
            "export": "export-old",
        }
        self.video.files = {
            "video_input": str(self.root / "input.mp4"),
            "background_music": str(self.root / "music.mp3"),
            "background_audio": str(self.root / "no-vocals.wav"),
            "ocr_region": str(self.root / "region.json"),
            "voice_output": str(self.root / "old-voice.wav"),
            "voice_parts_dir": str(self.root / "old-parts"),
            "final_video": str(self.root / "previous-export.mp4"),
        }
        self.video.subtitle_style = {"font_size": 46, "margin_v": 92}
        self.video.subtitle_layout_override = True
        self.video.remove_original_subtitles = True
        self.video.original_subtitle_removal_mode = "blur"
        self.video.crop = {"left_percent": 4, "right_percent": 4}
        self.video.output_format = "keep_ratio"
        self.video.watermark_text = "HAIZFLOW"
        self.video.original_video_volume = 36
        self.video.background_music_volume = 28
        self.video.tts_volume = 90
        expected_subtitle = {"artifact_id": "subtitle_document:new"}

        def publish_new_subtitles(*_args):
            self.video.active_artifacts["subtitle_document"] = "subtitle-new"
            return expected_subtitle

        with patch.object(manual_tools, "_publish_subtitles", side_effect=publish_new_subtitles):
            result = manual_tools._replace_subtitles_from_translation("manual-video", "translated.json")

        self.assertIs(result, expected_subtitle)
        self.assertEqual(
            self.video.active_artifacts,
            {
                "source_audio": "source-a",
                "separation": "separation-a",
                "ocr_region": "ocr-a",
                "subtitle_document": "subtitle-new",
            },
        )
        self.assertIn("background_music", self.video.files)
        self.assertIn("background_audio", self.video.files)
        self.assertIn("ocr_region", self.video.files)
        self.assertIn("final_video", self.video.files)
        self.assertNotIn("voice_output", self.video.files)
        self.assertNotIn("voice_parts_dir", self.video.files)
        self.assertEqual(self.video.subtitle_style, {"font_size": 46, "margin_v": 92})
        self.assertTrue(self.video.subtitle_layout_override)
        self.assertTrue(self.video.remove_original_subtitles)
        self.assertEqual(self.video.original_subtitle_removal_mode, "blur")
        self.assertEqual(self.video.crop, {"left_percent": 4, "right_percent": 4})
        self.assertEqual(self.video.output_format, "keep_ratio")
        self.assertEqual(self.video.watermark_text, "HAIZFLOW")
        self.assertEqual(self.video.original_video_volume, 36)
        self.assertEqual(self.video.background_music_volume, 28)
        self.assertEqual(self.video.tts_volume, 90)

    def test_switching_settings_back_restores_the_matching_branch_without_a_model(self):
        source_video = self.root / "input.mp4"
        source_video.write_bytes(b"video")
        self.video.files = {"video_input": str(source_video)}
        self.video.enable_audio_separation = False
        self.video.speech_recognition_model = "small"
        self.video.source_language = "auto"
        self.video.target_language = "vi"
        self.video.remove_original_subtitles = False
        self.video.tts_provider = "omnivoice"
        self.video.tts_voice = "omnivoice:female"
        self.video.speaker_mode = "single"
        self.video.subtitle_style = {}
        self.video.crop = {}
        self.video.output_format = "keep_ratio"
        self.video.watermark_text = ""
        self.video.subtitle_layout_override = False
        self.video.original_subtitle_removal_mode = "patch"
        self.video.original_video_volume = 60
        self.video.background_music_volume = 30
        self.video.tts_volume = 100

        source_signature = manual_tools.source_signature(self.video)
        source_stage = manual_artifacts.create_staging_directory("manual-video", "source_audio")
        (source_stage / "audio.wav").write_bytes(b"audio")
        manual_artifacts.publish(
            "manual-video", "source_audio", source_signature, source_stage, {"audio": "audio.wav"}
        )

        first_signature = manual_tools.recognition_signature(self.video)
        first_stage = manual_artifacts.create_staging_directory("manual-video", "recognition")
        (first_stage / "segments.json").write_text("[]", encoding="utf-8")
        manual_artifacts.publish(
            "manual-video", "recognition", first_signature, first_stage, {"segments": "segments.json"}
        )

        self.video.speech_recognition_model = "large-v3-turbo"
        second_signature = manual_tools.recognition_signature(self.video)
        second_stage = manual_artifacts.create_staging_directory("manual-video", "recognition")
        (second_stage / "segments.json").write_text("[]", encoding="utf-8")
        manual_artifacts.publish(
            "manual-video", "recognition", second_signature, second_stage, {"segments": "segments.json"}
        )
        self.assertEqual(self.video.active_artifacts["recognition"], second_signature)

        self.video.speech_recognition_model = "small"
        restored = manual_tools.restore_cached_variants("manual-video")

        self.assertIn("recognition", restored)
        self.assertEqual(self.video.active_artifacts["recognition"], first_signature)
        self.assertIn("source_segments", self.video.files)


class ManualToolDispatchTests(unittest.TestCase):
    def test_importing_manual_state_does_not_load_model_runtimes(self):
        script = """
import sys
import haizflow.pipeline.manual_tools
blocked = {
    'haizflow.pipeline.transcribe',
    'haizflow.services.translation',
    'haizflow.pipeline.subtitle_ocr',
}
assert not (blocked & set(sys.modules)), blocked & set(sys.modules)
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_active_subtitle_document_does_not_depend_on_current_translation_settings(self):
        video = SimpleNamespace(video_id="manual-video", active_artifacts={})
        subtitle = {
            "artifact_id": "subtitle_document:edited",
            "resolved_outputs": {"segments": "edited.json", "srt": "edited.srt"},
        }
        with (
            patch.object(manual_tools.manual_artifacts, "active", return_value=subtitle),
            patch.object(manual_tools, "translation_signature", side_effect=AssertionError("must not run")),
        ):
            self.assertIs(manual_tools._current_subtitle_record(video), subtitle)

    def test_manual_toolbar_merges_recognition_into_translation(self):
        self.assertEqual(
            manual_tools.MANUAL_TOOL_IDS,
            ("source", "translation", "subtitle", "image", "voice", "audio", "export"),
        )

    def test_each_runner_contains_only_its_owned_heavy_operation(self):
        separation = inspect.getsource(manual_tools._run_separation)
        recognition = inspect.getsource(manual_tools._run_recognition)
        translation = inspect.getsource(manual_tools._run_translation)
        voice = inspect.getsource(manual_tools._run_voice)
        audio = inspect.getsource(manual_tools._run_audio)
        audio_compositor = inspect.getsource(manual_tools._compose_manual_audio)
        export = inspect.getsource(manual_tools._run_export)

        self.assertIn("separate_audio(", separation)
        self.assertNotIn("transcribe(", separation)
        self.assertNotIn("translate_segments(", separation)
        self.assertNotIn("generate_voice_parts(", separation)
        self.assertNotIn("build_audio_timeline(", separation)

        self.assertIn("transcribe(", recognition)
        self.assertNotIn("translate_segments(", recognition)
        self.assertIn("translate_segments(", translation)
        self.assertNotIn("transcribe(", translation)
        self.assertIn("generate_voice_parts(", voice)
        self.assertNotIn("translate_segments(", voice)
        self.assertIn("_compose_manual_audio(", audio)
        self.assertIn("build_audio_timeline(", audio_compositor)
        self.assertNotIn("generate_voice_parts(", audio_compositor)
        self.assertNotIn("generate_voice_parts(", audio)
        self.assertIn("render_video(", export)
        self.assertNotIn("generate_voice_parts(", export)
        self.assertNotIn("translate_segments(", export)

    def test_audio_and_export_are_not_blocked_by_optional_layers(self):
        video = SimpleNamespace(
            video_id="manual-video",
            status="manual_ready",
            manual_target_tool="",
            active_artifacts={},
            files={"video_input": "input.mp4"},
            enable_audio_separation=False,
            remove_original_subtitles=True,
        )

        with (
            patch.object(manual_tools, "_video_input", return_value="input.mp4"),
            patch.object(manual_tools.manual_artifacts, "file_state", return_value={"size": 1}),
            patch.object(manual_tools, "_source_ready", return_value=False),
            patch.object(manual_tools, "_recognition_ready", return_value=False),
            patch.object(manual_tools, "_translation_ready", return_value=False),
            patch.object(manual_tools, "_subtitle_ready", return_value=False),
            patch.object(manual_tools, "_image_ready", return_value=False),
            patch.object(manual_tools, "_voice_ready", return_value=False),
            patch.object(manual_tools, "_audio_ready", return_value=False),
            patch.object(manual_tools, "_artifact_ready", return_value=False),
            patch.object(manual_tools, "audio_signature", return_value="audio-current"),
            patch.object(manual_tools, "export_signature", return_value="export-current"),
        ):
            states = {row["toolId"]: row for row in manual_tools.tool_states(video)}

        self.assertTrue(states["audio"]["canRun"])
        self.assertEqual(states["audio"]["state"], "ready")
        self.assertTrue(states["export"]["canRun"])
        self.assertEqual(states["export"]["state"], "ready")

    def test_dispatch_runs_only_the_selected_tool(self):
        video = SimpleNamespace(
            video_id="manual-video",
            project_type="manual",
            active_artifacts={},
            status="processing",
        )
        reporter = SimpleNamespace()
        runner = Mock()

        with (
            patch.object(manual_tools, "start_video"),
            patch.object(manual_tools, "clean_video"),
            patch.object(manual_tools.video_store, "get_video", return_value=video),
            patch.object(manual_tools.video_store, "update_video"),
            patch.object(manual_tools.video_store, "log_to_video"),
            patch("haizflow.pipeline.process_video.ProgressReporter", return_value=reporter),
            patch.dict(manual_tools._RUNNERS, {"translation": runner}),
        ):
            manual_tools.run_manual_tool_sync(video.video_id, "translation")

        runner.assert_called_once_with(video, reporter)

    def test_translation_runner_reuses_cached_recognition_without_other_models(self):
        video = SimpleNamespace(
            video_id="manual-video",
            target_language="vi",
            active_artifacts={"recognition": "recognition-signature"},
        )
        recognition = {
            "artifact_id": "recognition:recognition-signature",
            "resolved_outputs": {"segments": "source.json"},
        }
        translated = {
            "artifact_id": "translation:translation-signature",
            "resolved_outputs": {"segments": "translated.json"},
        }
        reporter = SimpleNamespace(update=lambda *_args: None)

        with (
            patch.object(manual_tools, "recognition_signature", return_value="recognition-signature"),
            patch.object(manual_tools, "translation_signature", return_value="translation-signature"),
            patch.object(manual_tools.manual_artifacts, "resolve", side_effect=[recognition, None]),
            patch.object(manual_tools.manual_artifacts, "create_staging_directory", return_value=Path("stage")),
            patch.object(manual_tools.manual_artifacts, "publish", return_value=translated),
            patch.object(manual_tools, "translate_segments"),
            patch.object(manual_tools, "_replace_subtitles_from_translation") as replace_subtitles,
            patch.object(manual_tools, "extract_audio") as extract,
            patch.object(manual_tools, "separate_audio") as separate,
            patch.object(manual_tools, "transcribe") as transcribe,
            patch.object(manual_tools.shutil, "rmtree"),
            patch.object(Path, "mkdir"),
        ):
            manual_tools._run_translation(video, reporter)

        extract.assert_not_called()
        separate.assert_not_called()
        transcribe.assert_not_called()
        replace_subtitles.assert_called_once_with("manual-video", "translated.json")

    def test_translation_runner_recognizes_when_cache_is_missing_but_never_runs_tts(self):
        video = SimpleNamespace(
            video_id="manual-video",
            target_language="vi",
            active_artifacts={},
        )
        recognition = {
            "artifact_id": "recognition:recognition-signature",
            "resolved_outputs": {"segments": "source.json"},
        }
        translated = {
            "artifact_id": "translation:translation-signature",
            "resolved_outputs": {"segments": "translated.json"},
        }
        reporter = SimpleNamespace(update=lambda *_args: None)

        with (
            patch.object(manual_tools, "recognition_signature", return_value="recognition-signature"),
            patch.object(manual_tools, "translation_signature", return_value="translation-signature"),
            patch.object(
                manual_tools.manual_artifacts,
                "resolve",
                side_effect=[None, recognition, None],
            ),
            patch.object(manual_tools, "_run_recognition") as recognize,
            patch.object(manual_tools.manual_artifacts, "create_staging_directory", return_value=Path("stage")),
            patch.object(manual_tools.manual_artifacts, "publish", return_value=translated),
            patch.object(manual_tools, "translate_segments"),
            patch.object(manual_tools, "_replace_subtitles_from_translation") as replace_subtitles,
            patch.object(manual_tools, "_run_voice") as create_voice,
            patch.object(manual_tools, "_run_separation") as separate,
            patch.object(manual_tools.shutil, "rmtree"),
            patch.object(Path, "mkdir"),
        ):
            manual_tools._run_translation(video, reporter)

        recognize.assert_called_once_with(video, reporter)
        create_voice.assert_not_called()
        separate.assert_not_called()
        replace_subtitles.assert_called_once_with("manual-video", "translated.json")

    def test_cancelled_voice_batch_publishes_only_completed_mp3_clips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            parts = Path(temp_dir)
            (parts / "voice_0001.mp3").write_bytes(b"ID3" + b"a" * 2048)
            (parts / "voice_0002.mp3").write_bytes(b"")
            video = SimpleNamespace(video_id="manual-video")
            subtitle = {"artifact_id": "subtitle_document:current"}

            with patch.object(manual_tools.manual_artifacts, "register_existing") as register:
                manual_tools._publish_completed_voice_clips(
                    video,
                    subtitle,
                    parts,
                    ["clip-one", "clip-two"],
                )

        register.assert_called_once()
        self.assertEqual(register.call_args.args[2], "clip-one")

    def test_voice_runner_builds_manifest_without_model_when_every_clip_is_cached(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cached_parts = []
            for index in range(2):
                part = root / f"cached-{index}.mp3"
                part.write_bytes(b"ID3" + bytes([index + 1]) * 4096)
                cached_parts.append(part)
            stage = root / ".partial-manifest"
            reporter = SimpleNamespace(update=Mock())
            video = SimpleNamespace(
                video_id="manual-video",
                tts_provider="omnivoice",
                target_language="vi",
                tts_voice="omnivoice:female",
                speaker_mode="single",
            )
            subtitle = {"artifact_id": "subtitle_document:current"}
            segments = [
                {"start": 0, "end": 1, "text": "Một"},
                {"start": 1, "end": 2, "text": "Hai"},
            ]

            def resolve(_video_id, kind, artifact_signature):
                if kind == "tts_manifest":
                    return None
                index = ["clip-one", "clip-two"].index(artifact_signature)
                return {"resolved_outputs": {"audio": str(cached_parts[index])}}

            def publish(*_args, **_kwargs):
                return {"resolved_outputs": {"manifest": str(stage / "manifest.json")}}

            with (
                patch.object(manual_tools, "_load_segments", return_value=segments),
                patch.object(manual_tools, "_current_subtitle_record", return_value=subtitle),
                patch.object(manual_tools, "_current_subtitle_path", return_value="subtitles.json"),
                patch.object(manual_tools, "_voice_clip_signatures", return_value=["clip-one", "clip-two"]),
                patch.object(manual_tools.manual_artifacts, "resolve", side_effect=resolve),
                patch.object(manual_tools.manual_artifacts, "create_staging_directory", return_value=stage),
                patch.object(manual_tools.manual_artifacts, "publish", side_effect=publish),
                patch.object(manual_tools.manual_artifacts, "register_existing"),
                patch.object(manual_tools, "generate_voice_parts") as generate,
                patch.object(manual_tools, "_update_files"),
                patch.object(manual_tools, "_is_valid_mp3", return_value=True),
            ):
                manual_tools._run_voice(video, reporter)

        generate.assert_not_called()
        self.assertEqual(reporter.update.call_args.args[2], "Đang khôi phục giọng đọc từ cache")


if __name__ == "__main__":
    unittest.main()
