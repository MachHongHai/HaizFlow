"""Mocked recovery and low-memory handoffs; no real models or user projects."""

import json
import contextlib
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import numpy as np

from haizflow.core import memory
from haizflow.pipeline import process_video, omnivoice_tts as voice, manual_tools


@pytest.mark.parametrize("device,recovery,expected", [
    ("gpu", "", ("large-v3-turbo", "full", "omnivoice-gpu")),
    ("cpu", "creating_voice", ("small-cpu", "q4", "omnivoice")),
    ("cpu", "translating", ("small-cpu", "q4", "omnivoice")),
    ("cpu", "", ("large-v3-turbo", "full", "omnivoice-gpu")),
    ("gpu", "creating_voice", ("large-v3-turbo", "full", "omnivoice-gpu")),
])
def test_execution_choices_change_only_for_active_cpu_recovery(device, recovery, expected):
    video = SimpleNamespace(speech_recognition_model="large-v3-turbo", translation_model="full",
                            tts_provider="omnivoice-gpu", runtime_recovery_step=recovery)
    original = vars(video).copy()
    with patch.object(process_video, "processing_device_preference", return_value=device):
        assert tuple(process_video._execution_models(video).values()) == expected
    assert vars(video) == original


def test_cpu_recovery_preserves_explicit_cpu_choices_and_remote_translation():
    video = SimpleNamespace(speech_recognition_model="small-cpu", translation_model="gemini-2.5-flash",
                            tts_provider="omnivoice", runtime_recovery_step="rendering")
    with patch.object(process_video, "processing_device_preference", return_value="cpu"):
        assert process_video._execution_models(video) == {
            "speech_recognition_model": "small-cpu", "translation_model": "gemini-2.5-flash",
            "tts_provider": "omnivoice",
        }


def test_recovery_recognition_reuses_checkpoint_without_recomputing(tmp_path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"source")
    output = tmp_path / "asr.json"
    segments = [{"start": 0, "end": 1, "text": "Hello", "language": "en"}]
    video = SimpleNamespace(video_id="fixture", files={"video_input": str(source)}, source_language="auto",
                            speech_recognition_model="small-gpu", enable_audio_separation=False,
                            resume_step="", runtime_recovery_step="rendering", checkpoints={})

    def recognize(*args, **kwargs):
        assert kwargs["model_name"] == "small-cpu"
        output.write_text(json.dumps(segments), encoding="utf-8")
        return segments, "en"

    with (patch.object(process_video, "processing_device_preference", return_value="cpu"),
          patch.object(process_video, "transcribe", side_effect=recognize) as execute,
          patch.object(process_video, "update_video")):
        first = process_video._recognize_for_translation(video, Mock(), "audio.wav", str(output))
        second = process_video._recognize_for_translation(video, Mock(), "audio.wav", str(output))
    assert first == second
    assert execute.call_count == 1
    assert video.speech_recognition_model == "small-gpu"


@pytest.mark.parametrize("completed", [False, True])
def test_voice_recovery_routes_cpu_and_keeps_original_checkpoint_identity(tmp_path, completed):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"source")
    temp = tmp_path / "temp"
    temp.mkdir()
    transcript = temp / "segments.json"
    transcript.write_text('[{"start":0,"end":1,"text":"Hello"}]', encoding="utf-8")
    part = temp / "voice_parts" / "voice_0001.mp3"
    part.parent.mkdir()
    part.write_bytes(b"verified-voice")
    signature = process_video._signature(process_video._file_state(str(transcript)), "omnivoice-gpu",
        "omnivoice", "vi", "same-voice", "single", None, "",
        "omnivoice-dedicated-short-anchor-or-source-speaker-r5")
    video = SimpleNamespace(video_id="fixture", files={"video_input": str(source),
        "final_video": str(tmp_path / "final.mp4"), "srt_output": str(temp / "subtitles.srt"),
        "voice_output": str(temp / "voice.wav"), "transcript_json": str(transcript)},
        subtitle_style=SimpleNamespace(max_chars_per_line=24), tts_voice="same-voice",
        tts_provider="omnivoice-gpu", target_language="vi", resume_step="",
        runtime_recovery_step="creating_voice", checkpoints={"voice" if completed else "voice_partial": signature})

    def generate(*args, **kwargs):
        assert kwargs["provider"] == "omnivoice"
        assert part.read_bytes() == b"verified-voice"

    with (patch.object(process_video, "processing_device_preference", return_value="cpu"),
          patch.object(process_video, "check_cancellation"), patch.object(process_video, "generate_srt"),
          patch.object(process_video, "shutdown_hymt2_worker"),
          patch.object(process_video, "_release_recognition_runtime"),
          patch.object(process_video, "log_to_video"), patch.object(process_video, "_mark_checkpoint") as mark,
          patch.object(process_video, "_complete_manual_stage"),
          patch.object(voice, "release_model_memory"),
          patch.object(process_video, "generate_voice_parts", side_effect=generate) as execute):
        process_video._finish_after_translation(video, Mock(), str(tmp_path), "audio.wav", stop_after="voice")
    assert execute.call_count == int(not completed)
    if not completed:
        assert all(call.args[2] == signature for call in mark.call_args_list if call.args[1].startswith("voice"))
    assert video.tts_provider == "omnivoice-gpu"
    assert part.read_bytes() == b"verified-voice"


def test_memory_settle_resamples_but_does_not_lower_reserves():
    low = memory.MemorySnapshot(available_bytes=int(0.87 * memory.GIB), process_commit_available_bytes=4 * memory.GIB)
    ready = memory.MemorySnapshot(available_bytes=2 * memory.GIB, process_commit_available_bytes=5 * memory.GIB)
    with (patch.object(memory, "memory_snapshot", side_effect=[low, ready]) as telemetry,
          patch.object(memory.time, "sleep"), patch.object(memory.time, "monotonic", return_value=0)):
        memory.require_cpu_memory("translation", settle_seconds=2)
    assert telemetry.call_count == 2
    with (patch.object(memory, "memory_snapshot", return_value=low), patch.object(memory.time, "sleep"),
          patch.object(memory.time, "monotonic", side_effect=[0, 0, 3])):
        with pytest.raises(RuntimeError, match="RAM trống 0.9 GiB"):
            memory.require_cpu_memory("translation", settle_seconds=2)


def test_unknown_telemetry_is_not_retried_or_admitted():
    with (patch.object(memory, "memory_snapshot", return_value=memory.MemorySnapshot()),
          patch.object(memory.time, "sleep") as wait):
        with pytest.raises(RuntimeError, match="Không đọc được"):
            memory.require_cpu_memory("translation", settle_seconds=2)
    wait.assert_not_called()


def test_manual_cpu_translation_releases_rpc_warm_owners_before_dispatch(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    video = SimpleNamespace(video_id="fixture", translation_model="q4", target_language="vi")
    order = []
    record = {"artifact_id": "asr", "resolved_outputs": {"segments": "recognized.json"}}
    def resolve(_id, kind, _signature):
        return record if kind == "recognition" else None
    with (patch.object(manual_tools, "recognition_signature", return_value="asr"),
          patch.object(manual_tools, "translation_signature", return_value="translation"),
          patch.object(manual_tools.manual_artifacts, "resolve", side_effect=resolve),
          patch.object(manual_tools.manual_artifacts, "create_staging_directory", return_value=staging),
          patch.object(manual_tools.manual_artifacts, "discard_staging_directory"),
          patch.object(manual_tools.manual_artifacts, "publish", return_value=record),
          patch.object(manual_tools, "_release_recognition_runtime", side_effect=lambda: order.append("asr-released")),
          patch.object(voice, "clear_runtime", side_effect=lambda: order.append("voice-released")),
          patch("haizflow.services.external_engine.shared_external_engine_pool") as pool,
          patch.object(manual_tools, "translate_segments", side_effect=lambda *a, **kw: order.append("dispatch")),
          patch.object(manual_tools, "_replace_subtitles_from_translation")):
        pool.return_value.release.side_effect = lambda capabilities: order.append(capabilities)
        manual_tools._run_translation(video, Mock())
    assert order == ["asr-released", "voice-released", {"voice", "translation"}, "dispatch"]


def test_decoder_activity_hook_is_removed_even_after_inference_error():
    model = Mock()
    activity = Mock()
    with pytest.raises(RuntimeError, match="inference failure"):
        with voice._inference_activity(model, activity):
            model.register_forward_hook.call_args.args[0](None, None, None)
            raise RuntimeError("inference failure")
    activity.assert_called_once_with()
    model.register_forward_hook.return_value.remove.assert_called_once_with()


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
def test_worker_reports_real_cpu_forwards_without_changing_audio_or_gpu_path(tmp_path, device):
    torch = SimpleNamespace(Tensor=type("Tensor", (), {}), float32="fp32", float16="fp16",
        set_num_threads=Mock(), set_num_interop_threads=Mock(), manual_seed=Mock(),
        inference_mode=contextlib.nullcontext,
        cuda=SimpleNamespace(is_available=lambda: True, manual_seed_all=Mock(), empty_cache=Mock(),
            mem_get_info=lambda: (0, 0), memory_reserved=lambda: 0, memory_allocated=lambda: 0),
        backends=SimpleNamespace(cuda=SimpleNamespace(matmul=SimpleNamespace()), cudnn=SimpleNamespace()))
    callbacks, statuses, audio = [], [], []
    handle = Mock()
    def register(callback):
        callbacks.append(callback)
        return handle
    def generate(**kwargs):
        for _ in range(4):
            for callback in callbacks:
                callback(None, None, None)
        return [np.ones(480, dtype=np.float32)]
    model = SimpleNamespace(generate=generate, sampling_rate=24000, register_forward_hook=Mock(side_effect=register))
    sf = SimpleNamespace(write=lambda _path, waveform, _rate, **kw: audio.append(waveform))
    runtime = {"modules": (np, sf, torch, Mock()), "model": model, "model_key": ("model", device)}
    request = {"site_packages": str(tmp_path), "model_root": "model", "device": device, "cpu_threads": 4,
        "language": "vi", "speaker_mode": "multiple", "items": [{"text": "Hello", "voice": "omnivoice:male",
        "wav_path": str(tmp_path / "voice.wav")}], "status_path": str(tmp_path / "status.json")}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    with (patch.object(voice, "_write_status_file", side_effect=lambda _p, payload: statuses.append(payload)),
          patch.object(voice, "_cpu_voice_threads", side_effect=AssertionError("post-load resampling"))):
        assert voice._worker_main(str(path), runtime) == 0
    assert len(audio) == 1 and np.array_equal(audio[0], np.ones(480, dtype=np.float32))
    assert statuses[-1]["completed"] == 1
    if device == "cpu":
        assert statuses[-1]["inference_forwards"] == 4
        assert any(row["inference_forwards"] > 0 and row["completed"] == 0 for row in statuses)
        handle.remove.assert_called_once_with()
    else:
        assert statuses[-1]["inference_forwards"] == 0
        model.register_forward_hook.assert_not_called()
