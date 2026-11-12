"""Real lightweight workers cover residency, cancellation and watchdogs without AI."""
import json
import sys
from unittest.mock import Mock

import pytest

from haizflow.pipeline import process_registry as registry, vieneu_tts, omnivoice_tts
from haizflow.services.resident_voice_worker import ResidentVoiceWorker

SERVER = r'''
import json, os, sys, time
from pathlib import Path
def write(path, value):
    path = Path(path)
    tmp = path.with_suffix('.new')
    tmp.write_text(json.dumps(value), encoding='utf-8')
    os.replace(tmp, path)
count = 0
for line in sys.stdin:
    request = json.loads(Path(line.strip()).read_text(encoding='utf-8'))
    count += 1
    status = dict(completed=0, total=len(request['items']), stage='synthesizing',
                  policy=sys.argv[1], device=request['device'], pid=os.getpid(), request=count)
    write(request['status'], status)
    if sys.argv[2] == 'stall':
        time.sleep(60)
    for item in request['items']:
        time.sleep(.25)
        Path(item['wav']).write_bytes(b'RIFF' + bytes(256))
        status['completed'] += 1
        write(request['status'], status)
    status['stage'] = 'completed'
    write(request['status'], status)
    write(request['response_path'], {'return_code': 0})
'''


@pytest.fixture
def resident(tmp_path, monkeypatch):
    from haizflow import config

    worker = ResidentVoiceWorker('vieneu-test-' + tmp_path.name)
    monkeypatch.setattr(vieneu_tts, '_RESIDENT_WORKER', worker)
    monkeypatch.setattr(vieneu_tts, 'verify_assets', lambda *_: tmp_path)
    monkeypatch.setattr(vieneu_tts, 'prepare_runtime', lambda *_: tmp_path)
    monkeypatch.setattr(config, 'TMP_DIR', str(tmp_path))
    monkeypatch.setattr('haizflow.services.resident_voice_worker.can_retain_model', lambda: True)
    monkeypatch.setattr('haizflow.services.video_store.log_to_video', Mock())
    monkeypatch.setattr(omnivoice_tts, '_synthesis_stall_timeout', lambda _: .8)
    monkeypatch.setattr(omnivoice_tts, '_encode_mp3',
                        lambda _wav, output, _id: output.write_bytes(b'ID3' + bytes(600)))
    key = 'resident-video-' + tmp_path.name
    registry.start_video(key)

    def run(voice='vieneu:Trúc Ly', device='cpu', mode='ok', callback=None, count=1):
        monkeypatch.setattr(vieneu_tts, 'server_command', lambda _: [
            sys.executable, '-u', '-c', SERVER, vieneu_tts.CACHE_VERSION, mode])
        outputs = [tmp_path / f'{i}.mp3' for i in range(count)]
        vieneu_tts.synthesize_batch_to_mp3([
            dict(text='Xin chào.', voice=voice, output_path=str(path)) for path in outputs],
            key, device=device, keep_worker_warm=True, progress_callback=callback)
        return outputs

    yield worker, run, key
    worker.close()
    registry.clean_video(key)


def test_repeated_requests_keep_process_but_switching_device_restarts(resident):
    worker, run, key = resident
    seen = []
    run(callback=lambda *_: seen.append(worker._process.pid) if worker._process is not None else None)
    first = worker._process
    run(voice='vieneu:Hải Đăng')
    assert worker._process is first and first.poll() is None
    assert not registry._active_processes.get(key)
    run(device='gpu')
    assert first.poll() is not None
    assert worker._process is not first
    assert seen


def test_pause_keeps_only_completed_audio_and_retires_active_worker(resident, tmp_path):
    worker, run, key = resident

    def pause(current, _total, _stage):
        if current == 1:
            registry.pause_video(key)

    with pytest.raises(RuntimeError, match='Video cancelled by user'):
        run(callback=pause, count=3)
    assert (tmp_path / '0.mp3').is_file()
    assert not (tmp_path / '1.mp3').exists()
    assert worker._process is None
    assert not registry._active_processes.get(key)
    registry.prepare_video_resume(key)
    assert run()[0].is_file()


def test_pause_at_last_completion_does_not_keep_dead_resident(resident):
    worker, run, key = resident

    def pause(current, _total, _stage):
        if current == 1:
            registry.pause_video(key)

    with pytest.raises(RuntimeError, match='Video cancelled by user'):
        run(callback=pause)
    assert worker._process is None


def test_stall_kills_process_and_publishes_nothing(resident, tmp_path):
    worker, run, key = resident
    with pytest.raises(RuntimeError, match='không có tiến triển'):
        run(mode='stall')
    assert worker._process is None and not (tmp_path / '0.mp3').exists()
    assert not registry._active_processes.get(key)


def test_low_memory_does_not_keep_model_resident(resident, monkeypatch):
    worker, run, _key = resident
    monkeypatch.setattr('haizflow.services.resident_voice_worker.can_retain_model', lambda: False)
    run()
    assert worker._process is None


def test_idle_timeout_frees_worker_and_clear_releases_both_backends(resident):
    import time

    worker, run, _key = resident
    worker.idle_seconds = .15
    run()
    process = worker._process
    deadline = time.monotonic() + 3
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(.02)
    assert process.poll() is not None
    run()
    omnivoice_tts.clear_runtime()
    assert worker._process is None


def test_worker_reuses_exact_model_across_presets_without_keeping_old_reference(tmp_path, monkeypatch):
    import numpy as np

    model = Mock()
    model.infer.return_value = np.full(4800, .1, dtype=np.float32)
    loader = Mock(return_value=model)
    monkeypatch.setattr(vieneu_tts, 'verify_assets', lambda *_: tmp_path)
    monkeypatch.setattr(vieneu_tts, 'prepare_runtime', lambda *_: tmp_path)
    monkeypatch.setattr(vieneu_tts, '_load_model', loader)
    monkeypatch.setattr('haizflow.pipeline.tts_quality.validate_speech_waveform', Mock())
    state = {}
    for index, voice in enumerate(['vieneu:Trúc Ly', 'vieneu:Hải Đăng']):
        vieneu_tts._worker(dict(root=str(tmp_path), device='cpu', status=str(tmp_path / 'status.json'),
            items=[dict(text='Xin chào.', voice=voice, wav=str(tmp_path / f'{index}.wav'))]), state)
    assert loader.call_count == 1
    assert [call.kwargs['voice'] for call in model.infer.call_args_list] == ['Trúc Ly', 'Hải Đăng']
    status = json.loads((tmp_path / 'status.json').read_text())
    assert status['model_reused'] is True
    assert str(tmp_path) in sys.path
    sys.path.remove(str(tmp_path))


def test_retention_uses_live_free_memory_not_installed_capacity(monkeypatch):
    from haizflow.core.memory import GIB, MemorySnapshot
    from haizflow.services.resident_voice_worker import can_retain_model

    for available, commit, expected in [(4, 5, True), (1, 5, False), (4, 1, False), (None, None, False)]:
        snapshot = MemorySnapshot(usable_bytes=16 * GIB,
            available_bytes=available * GIB if available is not None else None,
            process_commit_available_bytes=commit * GIB if commit is not None else None)
        monkeypatch.setattr('haizflow.core.memory.memory_snapshot', lambda: snapshot)
        assert can_retain_model() is expected
