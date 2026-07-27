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
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.schemas.video import VideoConfig
from haizflow.services import video_store, project_store


class RestartCheckpointTests(unittest.TestCase):
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
                mock.patch(
                    "haizflow.desktop.project_commands_controller.video_store.update_video"
                ) as update_video,
                mock.patch(
                    "haizflow.desktop.project_commands_controller.video_store.log_to_video"
                ),
            ):
                controller.approve_translation_review(payload)

            saved = json.loads(transcript.read_text(encoding="utf-8"))

        self.assertEqual(saved[0]["text"], "edited")
        self.assertEqual(update_video.call_args.kwargs["resume_step"], "creating_subtitle")
        self.assertEqual(
            update_video.call_args.kwargs["checkpoints"],
            {"translation": "translation-signature"},
        )
        host._enqueue_video.assert_called_once_with(video.video_id)

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
                mock.patch.object(process_video, "extract_audio", side_effect=RuntimeError("stop after resume decision")) as extract_audio,
            ):
                process_video.process_video_sync(video.video_id, _reporter=reporter)

            extract_audio.assert_called_once()
            update_video.assert_any_call(video.video_id, review_approved=False)


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


if __name__ == "__main__":
    unittest.main()
