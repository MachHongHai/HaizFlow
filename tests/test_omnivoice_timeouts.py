"""Long inference must advance, not fit a whole video into one media timeout."""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.pipeline import omnivoice_tts as voice
from haizflow.pipeline import process_registry as registry


def resident_fixture(tmp_path, monkeypatch, *, device="cuda:0"):
    process = SimpleNamespace(stdin=Mock(), poll=lambda: None)
    monkeypatch.setattr(voice, "_persistent_worker_unlocked", lambda _device: process)
    monkeypatch.setattr(voice, "_PERSISTENT_WORKER_PROCESS", process)
    monkeypatch.setattr(voice, "_PERSISTENT_MODEL_KEY", None)
    monkeypatch.setattr(voice, "_preflight_cpu_request", Mock())
    monkeypatch.setattr(voice, "register_process", Mock())
    monkeypatch.setattr(voice, "unregister_process", Mock())
    monkeypatch.setattr(voice, "check_cancellation", Mock())
    monkeypatch.setattr(voice, "_schedule_idle_shutdown", Mock())
    stop = Mock()
    monkeypatch.setattr(voice, "_stop_persistent_worker_unlocked", stop)
    monkeypatch.setattr(voice, "log_to_video", Mock())
    monkeypatch.setattr(voice, "MEDIA_PROCESS_TIMEOUT_SECONDS", 10)
    clock = [0.0]
    monkeypatch.setattr(voice.time, "monotonic", lambda: clock[0])
    request = {"device": device, "model_root": "fixture", "items": [{}] * 8,
               "status_path": str(tmp_path / "status.json")}
    return request, clock, stop


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
def test_resident_synthesis_can_exceed_video_deadline_while_finishing_sentences(tmp_path, monkeypatch, device):
    request, clock, stop = resident_fixture(tmp_path, monkeypatch, device=device)
    monkeypatch.setattr(voice, "MEDIA_PROCESS_TIMEOUT_SECONDS", 7200)
    request["items"] = [{}] * 40
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"completed": 0, "stage": "synthesizing", "total": 40}))
    progress = []

    def advance(_seconds):
        clock[0] += 600
        completed = int(clock[0] / 600)
        if completed == 40:
            (tmp_path / "response.json").write_text(json.dumps({"return_code": 0}))
        else:
            status.write_text(json.dumps({"completed": completed, "stage": "synthesizing", "total": 40}))

    monkeypatch.setattr(voice.time, "sleep", advance)
    result = voice._run_persistent_worker_process(tmp_path / "request.json", request, "fixture",
                                                  lambda current, *_: progress.append(current))
    assert result == (0, "")
    assert clock[0] > voice.MEDIA_PROCESS_TIMEOUT_SECONDS
    assert clock[0] > 6 * 3600  # User's six-hour run, without hours of real waiting.
    assert progress == list(range(40))
    stop.assert_not_called()


@pytest.mark.parametrize("status", [None, [], {"completed": 0, "stage": "synthesizing"}])
def test_resident_stall_still_stops_when_status_is_missing_invalid_or_unchanged(tmp_path, monkeypatch, status):
    request, clock, stop = resident_fixture(tmp_path, monkeypatch)
    if status is not None:
        (tmp_path / "status.json").write_text(json.dumps(status))

    def advance(_seconds):
        clock[0] += 4
        assert clock[0] < 30
        if isinstance(status, dict):
            # Rewriting timing/heartbeat metadata is not completed inference.
            (tmp_path / "status.json").write_text(json.dumps({**status, "timing_seconds": {"synthesis": clock[0]}}))

    monkeypatch.setattr(voice.time, "sleep", advance)
    code, error = voice._run_persistent_worker_process(tmp_path / "request.json", request, "fixture")
    assert code == 1 and "stopped making progress for 10 seconds" in error
    assert "cuda:0" in error
    stop.assert_called_once()


def test_isolated_worker_uses_progress_watchdog_not_whole_video_deadline(tmp_path, monkeypatch):
    process = SimpleNamespace(returncode=0, kill=Mock())
    monkeypatch.setattr(voice.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(voice, "_preflight_cpu_request", Mock())
    monkeypatch.setattr(voice, "check_cancellation", Mock())
    monkeypatch.setattr(voice, "_worker_command", lambda _path: ["fixture-worker"])
    # No real model/process/thread; the persistent tests above exercise the
    # shared inactivity policy with a deterministic multi-hour-equivalent clock.
    monkeypatch.setattr(voice.threading, "Thread", Mock())
    communicate = Mock(return_value=("", ""))
    monkeypatch.setattr(voice, "communicate_process", communicate)
    request = {"device": "cuda:0", "status_path": str(tmp_path / "status.json")}
    assert voice._run_worker_process(tmp_path / "request.json", request, "fixture") == (0, "")
    assert communicate.call_args.kwargs["timeout_seconds"] is None


def test_real_isolated_stalled_child_is_killed_without_unbounded_wait(tmp_path, monkeypatch):
    key = "isolated-voice-stall"
    registry.start_video(key)
    monkeypatch.setattr(voice, "_preflight_cpu_request", Mock())
    monkeypatch.setattr(voice, "_worker_command", lambda _path: [sys.executable, "-u", "-c",
                                                               "import time; time.sleep(60)"])
    monkeypatch.setattr(voice, "_synthesis_stall_timeout", lambda _request: .1)
    monkeypatch.setattr(voice, "_log_monitor_event", Mock())
    started = time.monotonic()
    try:
        code, detail = voice._run_worker_process(tmp_path / "request.json",
            {"device": "cuda:0", "status_path": str(tmp_path / "missing.json")}, key)
        assert code != 0 and "stopped making progress for 0.1 seconds" in detail
        assert time.monotonic() - started < 10
        assert not registry._active_processes.get(key)
    finally:
        registry.clean_video(key)


@pytest.mark.parametrize("reported", [False, True])
def test_gpu_to_cpu_retry_preserves_finished_clips_and_original_progress(tmp_path, monkeypatch, reported):
    monkeypatch.setattr(voice, "_prepare_isolated_runtime", Mock())
    monkeypatch.setattr(voice, "verify_omnivoice_model", lambda _root: tmp_path)
    monkeypatch.setattr(voice, "_sdk_root", lambda: tmp_path)
    monkeypatch.setattr(voice, "TMP_DIR", str(tmp_path))
    monkeypatch.setattr(voice, "_cpu_voice_threads", lambda: 4)
    monkeypatch.setattr(voice, "_preset_reference", lambda *_: ("", ""))
    monkeypatch.setattr(voice, "_stop_persistent_worker_unlocked", Mock())
    monkeypatch.setattr(voice, "log_to_video", Mock())
    calls, encoded, progress = [], [], []
    outputs = [tmp_path / f"voice-{index}.mp3" for index in range(3)]

    def encode(_wav, output, _id):
        encoded.append(output)
        output.write_bytes(b"verified audio")

    def worker(path, request, _id, callback, **_kwargs):
        assert json.loads(path.read_text(encoding="utf-8"))["items"] == request["items"]
        calls.append((request["device"], [item["text"] for item in request["items"]],
                      request["inference_steps"], request["voice_seed"]))
        if request["device"] == "cuda:0":
            # First clip is closed and valid, even if the last parent poll did
            # not see its completion before the next sentence ran out of VRAM.
            Path(request["items"][0]["wav_path"]).write_bytes(b"RIFF" + bytes(256))
            if reported:
                callback(1, 3, "synthesizing")
            return 1, "CUDA out of memory"
        assert outputs[0].read_bytes() == b"verified audio"
        for index, item in enumerate(request["items"], 1):
            Path(item["wav_path"]).write_bytes(b"RIFF" + bytes(256))
            callback(index, len(request["items"]), "synthesizing")
        return 0, ""

    monkeypatch.setattr(voice, "_run_persistent_worker_process", worker)
    monkeypatch.setattr(voice, "_encode_mp3", encode)
    voice.synthesize_batch_to_mp3(
        [dict(text=str(index), voice="omnivoice:male", output_path=str(output))
         for index, output in enumerate(outputs)],
        "fixture", language_id="vi", device="gpu", keep_worker_warm=True,
        progress_callback=lambda current, total, stage: progress.append((current, total, stage)))
    assert [call[:2] for call in calls] == [("cuda:0", ["0", "1", "2"]), ("cpu", ["1", "2"])]
    assert calls[0][2:] == calls[1][2:]  # Do not lower quality or change identity.
    assert encoded == outputs  # No second encoding or generation of clip zero.
    assert all(total == 3 for _, total, _ in progress)
    assert [current for current, _, _ in progress] == sorted(current for current, _, _ in progress)
    assert (1, 3, "retrying_voice_on_cpu") in progress

