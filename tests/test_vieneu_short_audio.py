"""VieNeu native speech is not a syllable-duration estimate; no real model load."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf

from haizflow.pipeline import vieneu_tts as voice
from haizflow.pipeline.tts_quality import SpeechQualityError, validate_short_phrase_audio


def speech(seconds=.13):
    return np.random.default_rng(42).normal(0, .08, round(48000 * seconds)).astype(np.float32)


@pytest.fixture
def worker(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "verify_assets", lambda *_: tmp_path)
    monkeypatch.setattr(voice, "prepare_runtime", lambda *_: tmp_path)
    model = Mock()
    monkeypatch.setattr(voice, "_load_model", lambda *_: model)
    # GPU status telemetry must not import Torch or allocate a real model.
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        max_memory_allocated=lambda: 0, max_memory_reserved=lambda: 0)))

    def run(texts, device="cpu", clone=False):
        reference = tmp_path / "authorized-reference.wav"
        if clone:
            sf.write(reference, speech(.5), 48000)
        items = [dict(text=text, voice="vieneu:clone" if clone else "vieneu:Hải Đăng",
                      reference_path=str(reference) if clone else "", wav=str(tmp_path / f"{index}.wav"))
                 for index, text in enumerate(texts)]
        voice._worker(dict(root=str(tmp_path), device=device, status=str(tmp_path / "status.json"), items=items))
        return items, json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))

    return model, run


@pytest.mark.parametrize("device", ["cpu", "gpu"])
@pytest.mark.parametrize("text", ["Tốt.", "Tôi", "Dạ!", "Vâng.", "Không."])
def test_clean_130ms_audio_is_not_rejected_just_for_a_written_syllable(worker, text, device):
    model, run = worker
    wave = speech()
    # Reproduce exactly the policy false-positive from the reported traceback.
    with pytest.raises(SpeechQualityError, match=r"incomplete \(0.13s\)"):
        validate_short_phrase_audio(wave, text, "vi", 48000)
    model.infer.return_value = wave
    items, status = run([text], device=device)
    saved, rate = sf.read(items[0]["wav"])
    assert len(saved) == len(wave) and rate == 48000  # No padding or stretching.
    assert status["completed"] == 1 and status["stage"] == "completed"
    assert status.get("quality_retries", 0) == 0
    assert model.infer.call_count == 1
    assert model.infer.call_args.args == (text,)
    assert model.infer.call_args.kwargs["apply_watermark"] is False


@pytest.mark.parametrize("broken", ["empty", "silent", "nonfinite", "tone"])
def test_only_actual_audio_failure_gets_one_retry_and_other_sentences_are_not_repeated(worker, broken):
    model, run = worker
    bad = {"empty": np.zeros(0), "silent": np.zeros(48000), "nonfinite": np.full(48000, np.nan),
           "tone": .1 * np.sin(2 * np.pi * 1500 * np.arange(48000) / 48000)}[broken]
    model.infer.side_effect = [speech(.5), bad, speech(), speech(.5)]
    items, status = run(["Câu đầu tiên.", "Tốt.", "Câu tiếp theo."])
    assert [call.args[0] for call in model.infer.call_args_list] == [
        "Câu đầu tiên.", "Tốt.", "Tốt.", "Câu tiếp theo."]
    assert status["completed"] == 3 and status["stage"] == "completed"
    assert status["quality_retries"] == 1
    assert all(Path(item["wav"]).is_file() for item in items)
    assert model.infer.call_args_list[1] == model.infer.call_args_list[2]


def test_two_failed_attempts_stop_without_publishing_bad_audio_or_losing_prior_clips(worker, tmp_path):
    model, run = worker
    model.infer.side_effect = [speech(.5), np.zeros(48000), np.zeros(48000)]
    with pytest.raises(RuntimeError, match="câu 2/3 sau 2 lần thử"):
        run(["Câu đã xong.", "Tốt.", "Chưa tạo."])
    assert model.infer.call_count == 3
    assert (tmp_path / "0.wav").is_file()
    assert not (tmp_path / "1.wav").exists() and not (tmp_path / "2.wav").exists()
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["completed"] == 1 and status["stage"] != "completed"


def test_clone_retry_preserves_authorized_reference_and_original_words(worker):
    model, run = worker
    model.infer.side_effect = [np.zeros(48000), speech()]
    _, status = run(["Tốt."], clone=True)
    assert status["completed"] == 1
    first, second = model.infer.call_args_list
    assert first == second
    assert first.args == ("Tốt.",)
    assert "ref_audio" in first.kwargs and "voice" not in first.kwargs

