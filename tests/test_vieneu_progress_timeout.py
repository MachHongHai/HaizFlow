"""Real lightweight child processes exercise VieNeu progress/pause/timeout wiring."""
import sys
from unittest.mock import Mock

import pytest

from haizflow import config
from haizflow.pipeline import omnivoice_tts, vieneu_tts
from haizflow.pipeline import process_registry as registry

CHILD = r'''
import json, os, sys, time
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
path = Path(request["status"])
status = dict(completed=0, total=len(request["items"]), stage="synthesizing",
              device=request["device"], policy=sys.argv[2])
def write(value):
    temporary = path.with_suffix(".new")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temporary, path)
write([] if sys.argv[3] == "malformed" else status)
if sys.argv[3] != "progress":
    time.sleep(60)
else:
    for item in request["items"]:
        time.sleep(.35)
        Path(item["wav"]).write_bytes(b"RIFF" + bytes(256))
        status["completed"] += 1
        write(status)
    status["stage"] = "completed"
    write(status)
'''


@pytest.fixture
def run_synthesis(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TMP_DIR", str(tmp_path))
    # The old whole-request deadline would kill the progressing child after
    # 400ms. Its real clip completions instead keep the 600ms watchdog alive.
    monkeypatch.setattr(config, "MEDIA_PROCESS_TIMEOUT_SECONDS", .4)
    monkeypatch.setattr(vieneu_tts, "verify_assets", lambda *_: tmp_path)
    monkeypatch.setattr(vieneu_tts, "prepare_runtime", lambda *_: tmp_path)
    monkeypatch.setattr(omnivoice_tts, "_synthesis_stall_timeout", lambda _request: .6)
    monkeypatch.setattr("haizflow.services.video_store.log_to_video", Mock())

    def encode(wav, output, _id):
        assert wav.is_file()
        output.write_bytes(b"verified mp3 checkpoint")

    monkeypatch.setattr(omnivoice_tts, "_encode_mp3", encode)
    key = "vieneu-progress-" + tmp_path.name
    registry.start_video(key)
    outputs = [tmp_path / f"voice-{index}.mp3" for index in range(3)]

    def run(mode="progress", device="cpu", callback=None):
        monkeypatch.setattr(vieneu_tts, "worker_command", lambda path, _device: [
            sys.executable, "-u", "-c", CHILD, str(path), vieneu_tts.CACHE_VERSION, mode])
        vieneu_tts.synthesize_batch_to_mp3(
            [dict(text="Tôi.", voice="vieneu:Hải Đăng", output_path=str(path)) for path in outputs],
            key, device=device, progress_callback=callback)

    yield run, outputs, key
    registry.clean_video(key)


@pytest.mark.parametrize("device", ["cpu", "gpu"])
def test_progressing_vieneu_child_outlives_whole_request_deadline(run_synthesis, device):
    run, outputs, key = run_synthesis
    run(device=device)
    assert all(path.read_bytes() == b"verified mp3 checkpoint" for path in outputs)
    assert not registry._active_processes.get(key)


@pytest.mark.parametrize("mode", ["stall", "malformed"])
def test_no_progress_or_malformed_status_still_kills_child_without_publishing(run_synthesis, mode):
    run, outputs, key = run_synthesis
    with pytest.raises(RuntimeError, match="VieNeu không có tiến triển"):
        run(mode)
    assert not any(path.exists() for path in outputs)
    assert not registry._active_processes.get(key)


def test_pause_during_vieneu_generation_retains_only_completed_checkpoint(run_synthesis):
    run, outputs, key = run_synthesis

    def pause(current, _total, _stage):
        if current == 1:
            registry.pause_video(key)

    with pytest.raises(RuntimeError, match="Video cancelled by user"):
        run(callback=pause)
    assert outputs[0].read_bytes() == b"verified mp3 checkpoint"
    assert not outputs[1].exists() and not outputs[2].exists()
    assert registry.is_paused(key)
    assert not registry._active_processes.get(key)

