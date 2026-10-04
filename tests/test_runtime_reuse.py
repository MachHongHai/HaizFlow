"""Runtime ownership and rerun regressions without loading ML weights."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.desktop.smart_warmup_controller import SmartWarmupController
from haizflow.pipeline import process_video
from haizflow.services import external_tasks


class RuntimeReuseTests(unittest.TestCase):
    def test_imports_only_voice_worker_is_closed_without_a_resident_model_marker(self):
        with patch("haizflow.desktop.smart_warmup_controller.shared_external_engine_pool"):
            controller = SmartWarmupController(SimpleNamespace(_keep_models_warm=True), Mock())
        for reason in ("shutdown", "storage-move", "device-switch", "memory-pressure"):
            with self.subTest(reason=reason), patch("haizflow.pipeline.omnivoice_tts.clear_runtime") as clear:
                controller._release_now(reason)
                clear.assert_called_once()
        with patch("haizflow.pipeline.omnivoice_tts.clear_runtime") as clear:
            controller._release_now("foreground")
            clear.assert_not_called()

    def test_auto_process_always_prepares_fresh_workspace(self):
        video = SimpleNamespace(
            video_id="fixture", project_type="single", status="done", resume_step="", processing_elapsed_seconds=200
        )
        host = SimpleNamespace(
            _selected_video_id="fixture",
            _settings_owner_video_id="fixture",
            _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
            _apply_setup_to_video=Mock(),
            _enqueue_video=Mock(return_value=True),
            selectedVideoChanged=SimpleNamespace(emit=Mock()),
            refreshVideos=Mock(),
        )
        with (
            patch("haizflow.desktop.project_commands_controller.video_store.get_video", return_value=video),
            patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update,
            patch("haizflow.desktop.project_commands_controller.video_store.prepare_video_restart", return_value=video) as restart,
            patch("haizflow.pipeline.process_registry.prepare_video_resume") as clear_cancel,
        ):
            for status in ("done", "paused", "failed", "pending", "cancelled"):
                with self.subTest(status=status):
                    video.status = status
                    self.assertTrue(ProjectCommandsController(host).process_for_export("fixture"))
        self.assertEqual(restart.call_count, 5)
        self.assertEqual(clear_cancel.call_count, 5)
        update.assert_not_called()

    def test_warm_context_ignores_settings_unrelated_to_recognition(self):
        host = SimpleNamespace(_keep_models_warm=True)
        with patch("haizflow.desktop.smart_warmup_controller.shared_external_engine_pool"):
            controller = SmartWarmupController(host, Mock())
        controller.request(
            "recognition", {"device": "cpu", "model": "small", "language": "vi", "provider": "omnivoice"}
        )
        first = controller._requests[0].context
        controller.request("recognition", {"device": "cpu", "model": "small", "language": "en"})
        self.assertEqual(first, controller._requests[0].context)
        self.assertEqual(first, {"device": "cpu", "model": "small"})

    def test_handoff_revalidates_warm_owner_without_losing_pack_lock(self):
        host = SimpleNamespace(_keep_models_warm=True, _selected_video=Mock(return_value=None))
        resources = Mock()
        resources.required_packs.return_value = ["engine-fixture"]
        with patch("haizflow.desktop.smart_warmup_controller.shared_external_engine_pool"):
            controller = SmartWarmupController(host, resources)
        controller._resident.add("recognition")
        controller._resident_contexts["recognition"] = {"device": "cpu", "model": "small"}
        controller.resume_after_foreground()
        self.assertIn("recognition", controller._validation_required)
        self.assertTrue(controller.pack_in_use("engine-fixture"))

    def test_voice_language_switch_keeps_same_model_device(self):
        with patch("haizflow.desktop.smart_warmup_controller.shared_external_engine_pool"):
            controller = SmartWarmupController(SimpleNamespace(_keep_models_warm=True, _settings_processing_device="gpu"), Mock())
        controller.request("voice", {"provider": "omnivoice", "language": "vi"})
        first = controller._requests[0].context
        controller.request("voice", {"provider": "omnivoice-cpu", "language": "en"})
        self.assertEqual(first, controller._requests[0].context)
        controller.request("voice", {"provider": "omnivoice-gpu", "language": "en"})
        self.assertNotEqual(first, controller._requests[0].context)

    def test_speaker_resources_are_only_required_for_multiple_speaker_mode(self):
        from haizflow.services.resource_packs import ResourcePackManager

        manager = ResourcePackManager()
        single = manager.required_packs("voice", {"provider": "omnivoice-cpu", "speaker_mode": "single"})
        multiple = manager.required_packs("voice", {"provider": "omnivoice-cpu", "speaker_mode": "multiple"})
        self.assertNotIn("model-speaker-identification", single)
        self.assertIn("model-speaker-identification", multiple)
        self.assertIn("engine-speaker-bundled", multiple)
        self.assertNotIn("engine-vision-onnx", multiple)

    def test_first_foreground_capability_uses_valid_translation_checkpoint(self):
        video = SimpleNamespace(
            files={"video_input": "fixture.mp4", "transcript_json": "fixture.json"}, enable_audio_separation=True
        )
        with (
            patch.object(process_video, "_translation_signature", return_value="signature"),
            patch.object(process_video, "_checkpoint_valid", return_value=True),
        ):
            self.assertEqual(process_video.foreground_capability(video), "voice")
        with (
            patch.object(process_video, "_translation_signature", return_value="changed"),
            patch.object(process_video, "_checkpoint_valid", return_value=False),
        ):
            self.assertEqual(process_video.foreground_capability(video), "separation")
        self.assertEqual(process_video.foreground_capability(video, "voice"), "voice")

    def test_file_task_reuses_warmed_rpc_worker_instead_of_spawning_process(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = Mock()

            def execute(capability, context, request_path):
                self.assertEqual(capability, "recognition")
                request = json.loads(Path(request_path).read_text(encoding="utf-8"))
                self.assertEqual(request["context"], {"device": "gpu"})
                Path(request["response_path"]).write_text(
                    json.dumps({"protocol_version": 1, "ok": True, "result": {"segments": []}}), encoding="utf-8"
                )
                return True

            pool.run_file_task.side_effect = execute
            with (
                patch.object(external_tasks, "TMP_DIR", directory),
                patch.object(external_tasks, "installed_engine_command", return_value=["mock-engine"]),
                patch.object(external_tasks, "shared_external_engine_pool", return_value=pool),
                patch.object(external_tasks, "check_cancellation"),
                patch.object(external_tasks.subprocess, "Popen") as spawn,
            ):
                result = external_tasks.run_external_task(
                    "recognition", "transcribe", {}, "fixture", context={"device": "gpu"}, isolate_source=True
                )
            self.assertEqual(result, {"segments": []})
            spawn.assert_not_called()
