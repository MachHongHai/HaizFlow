import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.pipeline import process_video
from haizflow.pipeline.process_video import _checkpoint_valid
from haizflow.desktop.localization import QMessageBox
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.schemas.video import VideoConfig
from haizflow.services import video_store, project_store


class RestartCheckpointTests(unittest.TestCase):
    def test_original_subtitle_scan_is_skipped_when_source_picture_is_kept(self):
        video = SimpleNamespace(video_id="video-1", remove_original_subtitles=False)
        reporter = SimpleNamespace(update=mock.Mock())

        with (
            mock.patch.object(process_video, "detect_original_subtitle_region") as detect_region,
            mock.patch.object(process_video, "log_to_video") as log_to_video,
        ):
            region = process_video._original_subtitle_region_for_render(video, reporter, "workspace")

        self.assertIsNone(region)
        detect_region.assert_not_called()
        reporter.update.assert_called_once_with(
            87,
            "detecting_original_subtitles",
            "Keeping original video subtitles unchanged",
        )
        self.assertIn("preserving the source picture", log_to_video.call_args.args[1])

    def test_review_approval_resumes_from_edited_translation_without_retranslating(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "translated.json"
            transcript.write_text(
                '[{"start": 0, "end": 1, "text": "old"}]',
                encoding="utf-8",
            )
            video = SimpleNamespace(
                video_id="video-1",
                status="awaiting_review",
                files={"transcript_json": str(transcript)},
                checkpoints={"translation": "translation-signature", "voice": "stale"},
            )
            host = SimpleNamespace(
                _selected_video_id=video.video_id,
                _enqueue_video=mock.Mock(return_value=True),
                selectedVideoChanged=SimpleNamespace(emit=mock.Mock()),
            )
            controller = ProjectCommandsController(host)
            payload = '[{"start": 0, "end": 1, "text": "edited"}]'

            with (
                mock.patch.object(
                    process_video,
                    "get_video",
                    return_value=video,
                ),
                mock.patch(
                    "haizflow.desktop.project_commands_controller.video_store.get_video",
                    return_value=video,
                ),
                mock.patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update_video,
                mock.patch("haizflow.desktop.project_commands_controller.video_store.log_to_video"),
            ):
                approved = controller.approve_translation_review(payload)

            saved = json.loads(transcript.read_text(encoding="utf-8"))

        self.assertEqual(saved[0]["text"], "edited")
        self.assertTrue(approved)
        self.assertEqual(update_video.call_args.kwargs["resume_step"], "creating_subtitle")
        self.assertEqual(
            update_video.call_args.kwargs["checkpoints"],
            {"translation": "translation-signature"},
        )
        host._enqueue_video.assert_called_once_with(video.video_id)

    def test_completed_video_subtitle_edit_regenerates_only_downstream_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "translated.json"
            transcript.write_text(
                '[{"start": 0, "end": 1, "text": "old"}]',
                encoding="utf-8",
            )
            video = SimpleNamespace(
                video_id="video-done",
                status="done",
                files={"transcript_json": str(transcript)},
                checkpoints={"translation": "translation-signature", "voice": "old", "render": "old"},
            )
            host = SimpleNamespace(
                _selected_video_id=video.video_id,
                _enqueue_video=mock.Mock(return_value=True),
                selectedVideoChanged=SimpleNamespace(emit=mock.Mock()),
            )
            controller = ProjectCommandsController(host)

            with (
                mock.patch(
                    "haizflow.desktop.project_commands_controller.video_store.get_video",
                    return_value=video,
                ),
                mock.patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update_video,
                mock.patch("haizflow.desktop.project_commands_controller.video_store.log_to_video"),
            ):
                approved = controller.approve_translation_review(
                    '[{"start": 0, "end": 1, "text": "edited after auto"}]'
                )

            saved = json.loads(transcript.read_text(encoding="utf-8"))

        self.assertTrue(approved)
        self.assertEqual(saved[0]["text"], "edited after auto")
        self.assertEqual(update_video.call_args.kwargs["status"], "pending")
        self.assertEqual(update_video.call_args.kwargs["resume_step"], "creating_subtitle")
        self.assertEqual(update_video.call_args.kwargs["processing_elapsed_seconds"], 0.0)
        self.assertIsNone(update_video.call_args.kwargs["started_at"])
        self.assertEqual(
            update_video.call_args.kwargs["checkpoints"],
            {"translation": "translation-signature"},
        )
        host._enqueue_video.assert_called_once_with(video.video_id)

    def test_manual_timing_edit_preserves_voice_and_invalidates_only_the_mix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "translated.json"
            transcript.write_text(
                '[{"start": 0, "end": 1, "text": "same voice"}]',
                encoding="utf-8",
            )
            video = SimpleNamespace(
                video_id="manual-timing",
                project_type="manual",
                status="manual_ready",
                files={"transcript_json": str(transcript)},
                checkpoints={
                    "translation": "translation-signature",
                    "voice": "voice-signature",
                    "timeline": "timeline-signature",
                    "render": "render-signature",
                },
                manual_completed_stages=["translation", "subtitles", "voice", "timeline", "render"],
            )
            host = SimpleNamespace(
                _selected_video_id=video.video_id,
                refreshVideos=mock.Mock(),
                selectedVideoChanged=SimpleNamespace(emit=mock.Mock()),
            )
            controller = ProjectCommandsController(host)

            with (
                mock.patch(
                    "haizflow.desktop.project_commands_controller.video_store.get_video",
                    return_value=video,
                ),
                mock.patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update_video,
                mock.patch("haizflow.desktop.project_commands_controller.video_store.log_to_video"),
            ):
                approved = controller.approve_translation_review(
                    '[{"start": 0, "end": 1.8, "text": "same voice", '
                    '"timeline_edited": true, "fit_voice_to_timing": true}]'
                )

        self.assertTrue(approved)
        changes = update_video.call_args.kwargs
        self.assertEqual(changes["manual_completed_stages"], ["translation", "subtitles", "voice"])
        self.assertEqual(changes["manual_completed_stage"], "voice")
        self.assertEqual(
            changes["checkpoints"],
            {"translation": "translation-signature", "voice": "voice-signature"},
        )

    def test_manual_text_edit_invalidates_old_voice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "translated.json"
            transcript.write_text(
                '[{"start": 0, "end": 1, "text": "old voice"}]',
                encoding="utf-8",
            )
            video = SimpleNamespace(
                video_id="manual-text",
                project_type="manual",
                status="manual_ready",
                files={"transcript_json": str(transcript)},
                checkpoints={"translation": "translation-signature", "voice": "voice-signature"},
                manual_completed_stages=["translation", "subtitles", "voice"],
            )
            host = SimpleNamespace(
                _selected_video_id=video.video_id,
                refreshVideos=mock.Mock(),
                selectedVideoChanged=SimpleNamespace(emit=mock.Mock()),
            )
            controller = ProjectCommandsController(host)

            with (
                mock.patch(
                    "haizflow.desktop.project_commands_controller.video_store.get_video",
                    return_value=video,
                ),
                mock.patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update_video,
                mock.patch("haizflow.desktop.project_commands_controller.video_store.log_to_video"),
            ):
                approved = controller.approve_translation_review(
                    '[{"start": 0, "end": 1, "text": "new voice"}]'
                )

        self.assertTrue(approved)
        changes = update_video.call_args.kwargs
        self.assertEqual(changes["manual_completed_stages"], ["translation"])
        self.assertEqual(changes["checkpoints"], {"translation": "translation-signature"})

    def test_changed_voice_signature_discards_all_old_voice_parts_before_tts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript = root / "temp" / "vi_segments.json"
            transcript.parent.mkdir(parents=True)
            transcript.write_text(
                '[{"start": 0, "end": 1, "text": "hello"}]',
                encoding="utf-8",
            )
            (root / "input.mp4").write_bytes(b"source-video")
            old_part = root / "temp" / "voice_parts" / "voice_0001.mp3"
            old_part.parent.mkdir()
            old_part.write_bytes(b"old-voice" * 100)
            video = SimpleNamespace(
                video_id="video-1",
                files={
                    "video_input": str(root / "input.mp4"),
                    "final_video": str(root / "final.mp4"),
                    "srt_output": str(root / "temp" / "vi.srt"),
                    "voice_output": str(root / "temp" / "voice.wav"),
                    "transcript_json": str(transcript),
                },
                subtitle_style=SimpleNamespace(max_chars_per_line=24),
                tts_voice="new-voice",
                resume_step="creating_voice",
                runtime_recovery_step="",
                checkpoints={"voice": "stale-signature"},
            )
            reporter = SimpleNamespace(update=mock.Mock())
            stale_was_removed = []

            def stop_after_check(*_args, **_kwargs):
                stale_was_removed.append(not old_part.exists())
                raise RuntimeError("stop after stale voice check")

            with (
                mock.patch.object(process_video, "check_cancellation"),
                mock.patch.object(process_video, "generate_srt"),
                mock.patch.object(process_video, "_mark_checkpoint"),
                mock.patch.object(
                    process_video,
                    "generate_voice_parts",
                    side_effect=stop_after_check,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "stop after stale voice check"):
                    process_video._finish_after_translation(
                        video,
                        reporter,
                        str(root),
                        str(root / "temp" / "audio.wav"),
                    )

        self.assertEqual(stale_was_removed, [True])

    def test_matching_partial_voice_signature_keeps_verified_parts_on_resume(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript = root / "temp" / "vi_segments.json"
            transcript.parent.mkdir(parents=True)
            transcript.write_text(
                '[{"start": 0, "end": 1, "text": "hello"}]',
                encoding="utf-8",
            )
            (root / "input.mp4").write_bytes(b"source-video")
            existing_part = root / "temp" / "voice_parts" / "voice_0001.mp3"
            existing_part.parent.mkdir()
            existing_part.write_bytes(b"existing-voice" * 100)
            transcript_state = process_video._file_state(str(transcript))
            voice_signature = process_video._signature(
                transcript_state,
                "edge",
                "edge",
                "vi",
                "same-voice",
                "single",
                process_video._file_state(""),
                "",
                "omnivoice-dedicated-short-anchor-or-source-speaker-r5",
            )
            video = SimpleNamespace(
                video_id="video-1",
                files={
                    "video_input": str(root / "input.mp4"),
                    "final_video": str(root / "final.mp4"),
                    "srt_output": str(root / "temp" / "vi.srt"),
                    "voice_output": str(root / "temp" / "voice.wav"),
                    "transcript_json": str(transcript),
                },
                subtitle_style=SimpleNamespace(max_chars_per_line=24),
                tts_voice="same-voice",
                resume_step="creating_voice",
                runtime_recovery_step="",
                checkpoints={"voice_partial": voice_signature},
            )
            reporter = SimpleNamespace(update=mock.Mock())
            retained = []

            def stop_after_check(*_args, **_kwargs):
                retained.append(existing_part.exists())
                raise RuntimeError("stop after partial voice check")

            with (
                mock.patch.object(process_video, "check_cancellation"),
                mock.patch.object(process_video, "generate_srt"),
                mock.patch.object(process_video, "_mark_checkpoint"),
                mock.patch.object(
                    process_video,
                    "generate_voice_parts",
                    side_effect=stop_after_check,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "stop after partial voice check"):
                    process_video._finish_after_translation(
                        video,
                        reporter,
                        str(root),
                        str(root / "temp" / "audio.wav"),
                    )

        self.assertEqual(retained, [True])

    def test_checkpoint_is_only_valid_for_a_paused_video_being_resumed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "translation.json"
            artifact.write_text("[]", encoding="utf-8")
            video = SimpleNamespace(checkpoints={"translation": "signature"}, resume_step="")

            self.assertFalse(_checkpoint_valid(video, "translation", "signature", [str(artifact)]))

            video.resume_step = "translating"
            self.assertTrue(_checkpoint_valid(video, "translation", "signature", [str(artifact)]))

    def test_changed_translation_signature_does_not_resume_a_reviewed_transcript(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.mp4"
            transcript = root / "translated.json"
            source.write_bytes(b"source")
            transcript.write_text("[]", encoding="utf-8")
            video = SimpleNamespace(
                video_id="video-1",
                mode="review",
                review_approved=True,
                translator_provider="hymt2",
                files={
                    "video_input": str(source),
                    "final_video": str(root / "final.mp4"),
                    "srt_output": str(root / "subtitle.srt"),
                    "voice_output": str(root / "voice.wav"),
                    "transcript_json": str(transcript),
                },
                target_language="en",
                enable_audio_separation=False,
                status="processing",
                step="translating",
                resume_step="rendering",
                runtime_recovery_step="",
                checkpoints={"translation": "stale-signature"},
                gpu_recovery_attempted=False,
            )
            reporter = SimpleNamespace(update=mock.Mock())
            profile = SimpleNamespace(warm_hymt2_on_startup=False, cuda_available=False)

            with (
                mock.patch.object(process_video, "get_video", return_value=video),
                mock.patch.object(process_video, "update_video") as update_video,
                mock.patch.object(process_video, "log_to_video"),
                mock.patch.object(process_video, "runtime_profile", return_value=profile),
                mock.patch.object(process_video, "validate_video_integrity"),
                mock.patch.object(
                    process_video, "extract_audio", side_effect=RuntimeError("stop after resume decision")
                ) as extract_audio,
            ):
                process_video.process_video_sync(video.video_id, _reporter=reporter)

            extract_audio.assert_called_once()
            update_video.assert_any_call(video.video_id, review_approved=False)


class ProjectCommandStateTests(unittest.TestCase):
    def test_resume_keeps_paused_status_until_enqueue_clears_registry_flags(self):
        video = SimpleNamespace(video_id="video-paused", status="paused")
        queue = SimpleNamespace(contains=mock.Mock(return_value=False))
        host = SimpleNamespace(
            _selected_video_id=video.video_id,
            _processing_queue=queue,
            _enqueue_video=mock.Mock(return_value=True),
            selectedVideoChanged=SimpleNamespace(emit=mock.Mock()),
        )
        controller = ProjectCommandsController(host)

        with (
            mock.patch(
                "haizflow.desktop.project_commands_controller.video_store.get_video",
                return_value=video,
            ),
            mock.patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update_video,
            mock.patch("haizflow.desktop.project_commands_controller.video_store.log_to_video"),
        ):
            controller.resume_selected_video()

        update_video.assert_not_called()
        host._enqueue_video.assert_called_once_with(video.video_id)
        host.selectedVideoChanged.emit.assert_called_once()

    def test_restart_accepts_a_fully_paused_video_and_restarts_from_scratch(self):
        video = SimpleNamespace(video_id="video-paused", status="paused")
        restarted = SimpleNamespace(video_id=video.video_id)
        host = SimpleNamespace(
            _selected_video_id=video.video_id,
            _settings_owner_video_id=video.video_id,
            _processing_queue=SimpleNamespace(contains=mock.Mock(return_value=False)),
            _device_switching=False,
            _apply_setup_to_video=mock.Mock(),
            _enqueue_video=mock.Mock(return_value=True),
            selectedVideoChanged=SimpleNamespace(emit=mock.Mock()),
        )
        controller = ProjectCommandsController(host)

        with (
            mock.patch(
                "haizflow.desktop.project_commands_controller.video_store.get_video",
                return_value=video,
            ),
            mock.patch(
                "haizflow.desktop.project_commands_controller.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            mock.patch(
                "haizflow.desktop.project_commands_controller.video_store.prepare_video_restart",
                return_value=restarted,
            ) as prepare_restart,
            mock.patch("haizflow.desktop.project_commands_controller.video_store.log_to_video"),
            mock.patch("haizflow.desktop.project_commands_controller.runtime_profile") as profile,
        ):
            profile.return_value.summary = "test runtime"
            controller.restart_selected_video()

        host._apply_setup_to_video.assert_called_once_with(video, review_approved=False)
        prepare_restart.assert_called_once_with(video.video_id)
        host._enqueue_video.assert_called_once_with(video.video_id)

    def test_debounced_settings_save_cannot_cross_video_selection(self):
        host = SimpleNamespace(
            _selected_video_id="video-b",
            _settings_owner_video_id="video-b",
            _processing_queue=SimpleNamespace(contains=mock.Mock(return_value=False)),
            _apply_setup_to_video=mock.Mock(),
        )
        controller = ProjectCommandsController(host)

        with mock.patch("haizflow.desktop.project_commands_controller.video_store.get_video") as get_video:
            saved = controller.persist_selected_video_settings("video-a")

        self.assertFalse(saved)
        get_video.assert_not_called()
        host._apply_setup_to_video.assert_not_called()


class InterruptedVideoRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_index = project_store.PROJECT_INDEX_PATH
        self.original_videos = video_store.LEGACY_VIDEO_WORKSPACES_DIR
        project_store.PROJECT_INDEX_PATH = str(self.root / "runtime" / "projects.json")
        video_store.LEGACY_VIDEO_WORKSPACES_DIR = str(self.root / "legacy-videos")

    def tearDown(self):
        project_store.PROJECT_INDEX_PATH = self.original_index
        video_store.LEGACY_VIDEO_WORKSPACES_DIR = self.original_videos
        self.temp.cleanup()

    def _create_video(self, status: str, step: str):
        project_name = f"Recovery-{uuid.uuid4().hex}"
        project_directory = self.root / "projects"
        project_store.ensure_project(project_name, str(project_directory), "single")
        video = video_store.create_video(
            uuid.uuid4().hex,
            "source.mp4",
            VideoConfig(project_name=project_name, project_directory=str(project_directory)),
        )
        return video_store.update_video(video.video_id, status=status, step=step, error="stale error")

    def test_stale_processing_video_becomes_resumable_after_restart(self):
        interrupted = self._create_video("processing", "rendering")
        completed = self._create_video("done", "done")

        recovered = video_store.recover_interrupted_videos()

        self.assertEqual(recovered, [interrupted.video_id])
        restored = video_store.get_video(interrupted.video_id)
        self.assertEqual(restored.status, "paused")
        self.assertEqual(restored.step, "paused")
        self.assertEqual(restored.resume_step, "rendering")
        self.assertIsNone(restored.error)
        self.assertIn("interrupted exit", restored.step_detail)
        self.assertEqual(video_store.get_video(completed.video_id).status, "done")
        self.assertEqual(video_store.recover_interrupted_videos(), [])

    def test_interrupted_recovery_does_not_count_time_while_the_app_was_closed(self):
        interrupted = self._create_video("processing", "creating_voice")
        metadata_path = Path(video_store.get_video_json_path(interrupted.video_id))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["processing_elapsed_seconds"] = 45.0
        metadata["started_at"] = "2026-08-13T01:00:00Z"
        metadata["updated_at"] = "2026-08-13T01:00:30Z"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        video_store.recover_interrupted_videos()

        restored = video_store.get_video(interrupted.video_id)
        self.assertEqual(restored.processing_elapsed_seconds, 75.0)
        self.assertIsNone(restored.started_at)


if __name__ == "__main__":
    unittest.main()
