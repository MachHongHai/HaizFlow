import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from haizflow.desktop.presenters import build_project_summaries
from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline.process_video import _complete_manual_stage
from haizflow.pipeline import process_video
from haizflow.schemas.video import VideoConfig


class ManualWorkflowTests(unittest.TestCase):
    def test_manual_is_a_first_class_video_project_type(self):
        config = VideoConfig(project_type="manual")

        self.assertEqual(config.project_type, "manual")

    def test_presenter_does_not_collapse_manual_projects_into_single(self):
        video = SimpleNamespace(
            video_id="manual-video",
            project_key="manual:key",
            project_name="Manual demo",
            project_directory="D:/projects",
            project_type="manual",
            original_filename="source.mp4",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            status="manual_ready",
            progress=64,
            files={},
            video_width=1080,
            video_height=1920,
        )

        summary = build_project_summaries([video])[0]

        self.assertEqual(summary["project_type"], "manual")
        self.assertEqual(summary["status"], "manual_ready")

    def test_lifecycle_runs_only_the_requested_manual_stage(self):
        video = SimpleNamespace(
            video_id="manual-video",
            status="manual_ready",
            project_type="manual",
            manual_target_stage="voice",
        )
        host = SimpleNamespace(
            _deleted_video_ids=set(),
            _initial_model_warmup_done=threading.Event(),
            _shutdown_started=False,
            _runtime_probe_error="",
            _model_setup_state="ready",
            _model_runtime_lock=threading.Lock(),
        )
        host._initial_model_warmup_done.set()
        lifecycle = ProcessingLifecycleController(host)

        with (
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.get_video", return_value=video),
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.update_video"),
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.log_to_video"),
            patch("haizflow.pipeline.process_video.process_video_sync") as process,
        ):
            lifecycle.execute_pipeline(video.video_id)

        process.assert_called_once_with(video.video_id, stop_after="voice")

    def test_manual_stage_completion_is_idle_and_durable(self):
        with (
            patch("haizflow.pipeline.process_video.get_video", return_value=None),
            patch("haizflow.pipeline.process_video.update_video") as update,
            patch("haizflow.pipeline.process_video.log_to_video"),
        ):
            _complete_manual_stage("manual-video", "subtitles", 64)

        update.assert_called_once_with(
            "manual-video",
            status="manual_ready",
            progress=64,
            step="manual_subtitles",
            step_detail="Manual stage ready: subtitles",
            estimated_remaining_seconds=None,
            resume_step="",
            runtime_recovery_step="",
            manual_target_stage="",
            manual_completed_stage="subtitles",
            manual_completed_stages=["translation", "subtitles"],
        )

    def test_rerunning_an_unchanged_earlier_stage_preserves_later_manual_result(self):
        video = SimpleNamespace(
            manual_completed_stage="timeline",
            manual_completed_stages=["translation", "subtitles", "voice", "timeline"],
            progress=87,
        )
        with (
            patch("haizflow.pipeline.process_video.get_video", return_value=video),
            patch("haizflow.pipeline.process_video.update_video") as update,
            patch("haizflow.pipeline.process_video.log_to_video"),
        ):
            _complete_manual_stage("manual-video", "translation", 62)

        changes = update.call_args.kwargs
        self.assertEqual(changes["manual_completed_stage"], "translation")
        self.assertEqual(
            changes["manual_completed_stages"],
            ["translation", "subtitles", "voice", "timeline"],
        )
        self.assertEqual(changes["progress"], 87)

    def test_changing_voice_invalidates_manual_voice_and_later_stages(self):
        saved = VideoConfig(project_type="manual", tts_voice="omnivoice:male")
        edited = saved.model_copy(update={"tts_voice": "omnivoice:female"})
        video = SimpleNamespace(
            **saved.model_dump(),
            video_id="manual-video",
            manual_completed_stage="timeline",
            manual_completed_stages=["translation", "subtitles", "voice", "timeline"],
        )
        video.subtitle_style = saved.subtitle_style
        video.crop = saved.crop
        host = SimpleNamespace(_build_config=lambda: edited)

        with patch("haizflow.desktop.qml_controller.video_store.update_video") as update:
            HaizFlowController._apply_setup_to_video(host, video)

        changes = update.call_args.kwargs
        self.assertEqual(changes["manual_completed_stage"], "subtitles")
        self.assertEqual(changes["manual_completed_stages"], ["translation", "subtitles"])
        self.assertEqual(changes["manual_target_stage"], "")

    def test_changing_visuals_preserves_voice_and_audio_modules(self):
        saved = VideoConfig(project_type="manual", original_subtitle_removal_mode="patch")
        edited = saved.model_copy(update={"original_subtitle_removal_mode": "blur"})
        video = SimpleNamespace(
            **saved.model_dump(),
            video_id="manual-video",
            manual_completed_stage="timeline",
            manual_completed_stages=["translation", "subtitles", "voice", "timeline"],
        )
        video.subtitle_style = saved.subtitle_style
        video.crop = saved.crop
        host = SimpleNamespace(_build_config=lambda: edited)

        with patch("haizflow.desktop.qml_controller.video_store.update_video") as update:
            HaizFlowController._apply_setup_to_video(host, video)

        changes = update.call_args.kwargs
        self.assertNotIn("manual_completed_stages", changes)
        self.assertNotIn("manual_completed_stage", changes)

    def test_manual_subtitle_layout_is_independent_from_original_subtitle_cleanup(self):
        manual_video = SimpleNamespace(
            project_type="manual",
            subtitle_layout_override=True,
            remove_original_subtitles=True,
        )
        automatic_video = SimpleNamespace(
            project_type="single",
            subtitle_layout_override=True,
            remove_original_subtitles=True,
        )

        self.assertTrue(process_video._manual_subtitle_layout_for_render(manual_video))
        self.assertFalse(process_video._manual_subtitle_layout_for_render(automatic_video))

    def test_voice_module_does_not_run_subtitle_formatting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcript = root / "temp" / "segments.json"
            transcript.parent.mkdir(parents=True)
            transcript.write_text('[{"start": 0, "end": 1, "text": "xin chào"}]', encoding="utf-8")
            source = root / "input.mp4"
            source.write_bytes(b"video")
            video = SimpleNamespace(
                video_id="manual-video",
                files={
                    "video_input": str(source),
                    "final_video": str(root / "final.mp4"),
                    "srt_output": str(root / "temp" / "subtitles.srt"),
                    "voice_output": str(root / "temp" / "voice.wav"),
                    "transcript_json": str(transcript),
                },
                subtitle_style=SimpleNamespace(max_chars_per_line=32),
                tts_voice="vi-VN-HoaiMyNeural",
                checkpoints={},
                resume_step="",
                runtime_recovery_step="",
            )
            reporter = SimpleNamespace(update=lambda *_args: None)

            with (
                patch.object(process_video, "check_cancellation"),
                patch.object(process_video, "generate_srt") as generate_srt,
                patch.object(process_video, "_mark_checkpoint"),
                patch.object(process_video, "generate_voice_parts", side_effect=RuntimeError("voice reached")),
            ):
                with self.assertRaisesRegex(RuntimeError, "voice reached"):
                    process_video._finish_after_translation(
                        video,
                        reporter,
                        str(root),
                        str(root / "temp" / "source.wav"),
                        stop_after="voice",
                    )

            generate_srt.assert_not_called()

    def test_manual_downstream_run_reuses_translation_without_resume_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "segments.json"
            transcript.write_text("[]", encoding="utf-8")
            video = SimpleNamespace(
                project_type="manual",
                manual_completed_stages=["translation"],
                resume_step="",
                checkpoints={"translation": "signature"},
            )

            self.assertTrue(
                process_video._checkpoint_valid(
                    video,
                    "translation",
                    "signature",
                    [str(transcript)],
                )
            )

    def test_tts_run_enters_voice_branch_without_loading_translation_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input" / "video.mp4"
            transcript_path = root / "temp" / "segments.json"
            input_path.parent.mkdir(parents=True)
            transcript_path.parent.mkdir(parents=True)
            input_path.write_bytes(b"video")
            transcript_path.write_text('[{"start": 0, "end": 1, "text": "xin chào"}]', encoding="utf-8")
            signature = process_video._signature(
                process_video._file_state(str(input_path)),
                process_video.TIMING_SOURCE,
                "hymt2-semantic-source-context-retry-v21",
                "vi",
                True,
                "small",
                "hymt2",
                process_video.HYMT2_MODEL_REVISION,
            )
            video = SimpleNamespace(
                video_id="manual-video",
                mode="A",
                translator_provider="hymt2",
                target_language="vi",
                enable_audio_separation=True,
                speech_recognition_model="small",
                project_type="manual",
                manual_completed_stages=["translation", "subtitles"],
                resume_step="",
                checkpoints={"translation": signature},
                files={
                    "video_input": str(input_path),
                    "transcript_json": str(transcript_path),
                },
            )
            reporter = SimpleNamespace(update=lambda *_args: None)

            with (
                patch.object(process_video, "start_video"),
                patch.object(process_video, "clean_video"),
                patch.object(process_video, "validate_video_integrity"),
                patch.object(process_video, "get_video", return_value=video),
                patch.object(process_video, "log_to_video"),
                patch.object(process_video, "translate_segments") as translate,
                patch.object(process_video, "_finish_after_translation") as finish,
            ):
                process_video.process_video_sync(
                    video.video_id,
                    _reporter=reporter,
                    stop_after="voice",
                )

            translate.assert_not_called()
            finish.assert_called_once_with(
                video,
                reporter,
                str(root),
                str(root / "temp" / "audio.wav"),
                stop_after="voice",
            )


if __name__ == "__main__":
    unittest.main()
