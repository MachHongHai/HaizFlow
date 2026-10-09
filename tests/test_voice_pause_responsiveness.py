"""Pause owns only the active voice request; completed cache remains reusable.

The child below is a real idle process, not an OmniVoice/model benchmark.
"""

import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.pipeline import omnivoice_tts as voice, process_registry as registry


def test_manual_pause_does_not_wait_for_a_modal_confirmation():
    video = SimpleNamespace(video_id="manual-voice", project_type="manual", step="manual_voice")
    host = SimpleNamespace(
        _selected_video_id=video.video_id, isSelectedBatchVideo=False,
        _processing_queue=SimpleNamespace(contains=lambda _: True,
            detach_pending=Mock(return_value=(video.video_id, []))),
        selectedVideoChanged=Mock(), refreshVideos=Mock(),
    )
    with (
        patch("haizflow.desktop.project_commands_controller.video_store.get_video", return_value=video),
        patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update,
        patch("haizflow.desktop.project_commands_controller.video_store.log_to_video"),
        patch("haizflow.desktop.project_commands_controller.QMessageBox.question") as question,
        patch("haizflow.desktop.project_commands_controller.pause_video") as pause,
    ):
        ProjectCommandsController(host).stop_video()
    question.assert_not_called()
    pause.assert_called_once_with(video.video_id)
    assert update.call_args.kwargs["status"] == "paused"
    assert update.call_args.kwargs["resume_step"] == "manual_voice"
    assert "files" not in update.call_args.kwargs
    assert "active_artifacts" not in update.call_args.kwargs


def test_pause_while_waiting_for_resident_worker_does_not_touch_its_owner(tmp_path):
    key = "voice-pause-waiter"
    registry.start_video(key)
    request = {"status_path": str(tmp_path / "status.json"), "device": "cpu"}
    failures = []
    entered = threading.Event()

    def run():
        entered.set()
        try:
            voice._run_persistent_worker_process(tmp_path / "request.json", request, key)
        except RuntimeError as exc:
            failures.append(str(exc))

    voice._PERSISTENT_OPERATION_LOCK.acquire()
    worker = threading.Thread(target=run)
    try:
        with patch.object(voice, "_persistent_worker_unlocked") as launch:
            worker.start()
            assert entered.wait(1)
            registry.pause_video(key)
            worker.join(1)
            assert not worker.is_alive()
            launch.assert_not_called()
            assert failures == ["Video cancelled by user."]
    finally:
        voice._PERSISTENT_OPERATION_LOCK.release()
        worker.join(2)
        registry.clean_video(key)


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
def test_pause_kills_active_inference_even_while_progress_is_busy(tmp_path, device):
    key = "voice-pause-active-" + device
    registry.start_video(key)
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", "import time; time.sleep(60)"],
        stdin=subprocess.PIPE, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    request = {"status_path": str(tmp_path / "status.json"), "device": device}
    (tmp_path / "status.json").write_text(json.dumps({"completed": 1, "total": 294}), encoding="utf-8")
    # Stand-in for an already atomically published voice clip: never deleted.
    completed = tmp_path / "voice_0001.mp3"
    completed.write_bytes(b"completed checkpoint")
    progress_entered, release_progress = threading.Event(), threading.Event()
    failures = []

    def callback(*_):
        progress_entered.set()
        release_progress.wait(5)

    def run():
        try:
            voice._run_persistent_worker_process(
                tmp_path / "request.json", request, "logical-video", callback, cancellation_id=key,
            )
        except RuntimeError as exc:
            failures.append(str(exc))

    worker = threading.Thread(target=run)
    try:
        with (
            patch.object(voice, "_preflight_cpu_request"),
            patch.object(voice, "_persistent_worker_unlocked", return_value=process),
            patch.object(voice, "_stop_persistent_worker_unlocked"),
            patch.object(voice, "log_to_video"),
        ):
            worker.start()
            assert progress_entered.wait(3)
            started = time.monotonic()
            registry.pause_video(key)
            assert process.poll() is not None
            assert time.monotonic() - started < 3
            release_progress.set()
            worker.join(2)
            assert not worker.is_alive()
            assert failures == ["Video cancelled by user."]
            assert registry.is_paused(key)
            assert completed.read_bytes() == b"completed checkpoint"
            assert process not in registry._active_processes.get(key, [])
            registry.prepare_video_resume(key)
            registry.check_cancellation(key)
    finally:
        release_progress.set()
        worker.join(3)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        process.stdin.close()
        registry.clean_video(key)


def test_one_shot_worker_checks_the_request_owner_before_launch(tmp_path):
    key = "voice-isolated-pause"
    registry.pause_video(key)
    try:
        with patch.object(voice.subprocess, "Popen") as launch:
            with pytest.raises(RuntimeError, match="Video cancelled by user"):
                voice._run_worker_process(tmp_path / "request.json", {}, "logical-video", cancellation_id=key)
            launch.assert_not_called()
    finally:
        registry.clean_video(key)


def test_a_paused_worker_exit_never_triggers_a_fresh_synthesis(tmp_path):
    key = "voice-paused-no-fallback"
    registry.start_video(key)

    def exit_after_pause(*_, **__):
        registry.pause_video(key)
        return 1, "Warm OmniVoice worker exited unexpectedly (1)."

    try:
        with (
            patch.object(voice, "_prepare_isolated_runtime"),
            patch.object(voice, "verify_omnivoice_model", return_value=tmp_path),
            patch.object(voice, "_sdk_root", return_value=tmp_path),
            patch.object(voice, "_run_persistent_worker_process", side_effect=exit_after_pause),
            patch.object(voice, "_run_worker_process") as fallback,
            patch.object(voice, "log_to_video"),
        ):
            with pytest.raises(RuntimeError, match="Video cancelled by user"):
                voice.synthesize_batch_to_mp3(
                    [{"text": "Completed words", "voice": "omnivoice:deep",
                      "output_path": str(tmp_path / "voice.mp3")}],
                    key, language_id="vi", device="gpu", keep_worker_warm=True,
                )
            fallback.assert_not_called()
    finally:
        registry.clean_video(key)
