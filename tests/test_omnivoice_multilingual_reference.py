"""Lightweight regression: no Torch imports, model loading, network or user-data writes."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from haizflow.pipeline import omnivoice_tts as voice
from haizflow.pipeline import tts_quality
from test_omnivoice_batching import fake_speech_wave, fake_torch


@pytest.mark.parametrize("language", ["ja", "ko", "es"])
@pytest.mark.parametrize("voice_id", ["omnivoice:female_gentle", "omnivoice:male", "omnivoice:deep"])
def test_new_languages_use_the_exact_packaged_voice_identity_and_english_transcript(language, voice_id):
    path, text = voice._preset_reference(voice_id, language)
    original_path, original_text = voice._preset_reference(voice_id, "en")
    assert path == original_path and text == original_text
    assert Path(path).is_file() and Path(path).stat().st_size > 512
    assert voice_id.replace(":", "_") in path


def test_same_language_sample_is_preferred_when_available(tmp_path, monkeypatch):
    # Isolate the package assets through __file__, not the user's model/data root.
    monkeypatch.setattr(voice, "__file__", str(tmp_path / "pipeline/omnivoice_tts.py"))
    root = tmp_path / "desktop/assets/voice_samples"
    folder = root / "omnivoice/omnivoice_female_gentle"
    folder.mkdir(parents=True)
    (root / "samples.json").write_text(
        json.dumps({"sentences": {"en": "English reference.", "ja": "日本語の参照です。"}}), encoding="utf-8"
    )
    (folder / "en.mp3").write_bytes(b"x" * 600)
    (folder / "ja.mp3").write_bytes(b"x" * 600)
    assert voice._preset_reference("omnivoice:female_gentle", "ja") == (str(folder / "ja.mp3"), "日本語の参照です。")
    (folder / "ja.mp3").write_bytes(b"broken")
    assert voice._preset_reference("omnivoice:female_gentle", "ja") == (str(folder / "en.mp3"), "English reference.")
    assert voice._preset_reference("omnivoice:does-not-exist", "ja") == ("", "")


@pytest.mark.parametrize("language", ["vi", "en", "zh"])
def test_existing_language_reference_does_not_change(language):
    path, text = voice._preset_reference("omnivoice:female_gentle", language)
    assert Path(path).name == language + ".mp3" and text


def test_only_new_languages_change_their_omnivoice_audio_cache_policy(monkeypatch):
    languages = ("vi", "en", "zh", "ja", "ko", "es")
    before = {lang: tts_quality.voice_text_policy_versions("A stable sentence.", lang) for lang in languages}
    monkeypatch.setattr(tts_quality, "MULTILINGUAL_REFERENCE_VERSION", "test-new-reference-policy")
    after = {lang: tts_quality.voice_text_policy_versions("A stable sentence.", lang) for lang in languages}
    for lang in languages:
        assert (before[lang] != after[lang]) == (lang in {"ja", "ko", "es"})


def test_missing_reference_is_actionable_and_never_launches_unconditioned_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "_prepare_isolated_runtime", Mock())
    monkeypatch.setattr(voice, "verify_omnivoice_model", lambda root: tmp_path)
    monkeypatch.setattr(voice, "_sdk_root", lambda: tmp_path)
    monkeypatch.setattr(voice, "TMP_DIR", str(tmp_path))
    monkeypatch.setattr(voice, "log_to_video", Mock())
    monkeypatch.setattr(voice, "_preset_reference", lambda *args: ("", ""))
    with pytest.raises(RuntimeError, match="OmniVoice thiếu mẫu giọng"):
        voice.synthesize_batch_to_mp3(
            [{"text": "逃げただと？", "voice": "omnivoice:female_gentle", "output_path": str(tmp_path / "voice.mp3")}],
            "isolated-fixture",
            language_id="ja",
            speaker_mode="multiple",
            device="cpu",
        )
    assert not (tmp_path / "voice.mp3").exists()


@pytest.mark.parametrize("language,text", [("ja", "逃げただと？"), ("ko", "도망쳤다고?"), ("es", "¿Has huido?")])
@pytest.mark.parametrize("mode", ["single", "multiple"])
def test_worker_clones_reference_keeps_target_text_language_and_zero_fade(tmp_path, language, text, mode):
    torch, calls, references, written = fake_torch(), [], [], []
    prompt = SimpleNamespace(ref_rms=0.0)

    def encode(**kwargs):
        references.append(kwargs)
        return prompt

    def generate(**kwargs):
        calls.append(kwargs)
        return [fake_speech_wave()]

    model = SimpleNamespace(generate=generate, sampling_rate=24000, create_voice_clone_prompt=encode)
    runtime = {
        "modules": (np, SimpleNamespace(write=lambda *args, **kwargs: written.append(args)), torch, Mock()),
        "model": model,
        "model_key": ("model", "cpu"),
    }
    reference_path, reference_text = voice._preset_reference("omnivoice:female_gentle", language)
    request = {
        "model_root": "model",
        "site_packages": str(tmp_path),
        "device": "cpu",
        "language": language,
        "speaker_mode": mode,
        "status_path": str(tmp_path / "status.json"),
        "narrator_anchor_text": "Native anchor.",
        "preset_reference_path": reference_path,
        "preset_reference_text": reference_text,
        "items": [
            {
                "voice": "omnivoice:female_gentle",
                "text": text,
                "wav_path": str(tmp_path / "out.wav"),
                "preset_reference_path": reference_path,
                "preset_reference_text": reference_text,
            }
        ],
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    assert voice._worker_main(str(path), runtime) == 0
    assert len(calls) == len(references) == len(written) == 1
    assert calls[0]["voice_clone_prompt"] is prompt and calls[0]["instruct"] is None
    assert calls[0]["text"] == text and calls[0]["language"] == language
    assert calls[0]["fade_duration"] == 0 and calls[0]["normalize_text"] is False
    assert not {"duration", "speed", "pad_duration"} & calls[0].keys()
    assert references[0] == {"ref_audio": reference_path, "ref_text": reference_text}


def test_failed_retry_names_exact_sentence_without_publishing_artifact(tmp_path):
    calls, writes = [], []
    torch = fake_torch()

    def generate(**kwargs):
        calls.append(kwargs)
        return [np.ones(24000, dtype=np.float32)]

    model = SimpleNamespace(generate=generate, sampling_rate=24000, create_voice_clone_prompt=lambda **kwargs: object())
    runtime = {
        "modules": (np, SimpleNamespace(write=lambda *args, **kwargs: writes.append(args)), torch, Mock()),
        "model": model,
        "model_key": ("model", "cpu"),
    }
    request = {
        "model_root": "model",
        "site_packages": str(tmp_path),
        "device": "cpu",
        "language": "ja",
        "speaker_mode": "multiple",
        "status_path": str(tmp_path / "status.json"),
        "items": [
            {
                "voice": "omnivoice:female_gentle",
                "text": "逃げただと？",
                "wav_path": str(tmp_path / "bad.wav"),
                "preset_reference_path": "reference.mp3",
                "preset_reference_text": "Reference.",
            }
        ],
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    with pytest.raises(tts_quality.SpeechQualityError, match="segment 1/1, language=ja, voice=omnivoice:female_gentle"):
        voice._worker_main(str(path), runtime)
    assert len(calls) == 2 and not writes
    assert not (tmp_path / "bad.wav").exists()


def test_waveform_filter_still_rejects_tones_and_dc_but_accepts_valid_speech():
    rate = 24000
    t = np.arange(rate) / rate
    for bad in (np.ones(rate), 0.2 * np.sin(2 * np.pi * 1500 * t)):
        with pytest.raises(tts_quality.SpeechQualityError):
            tts_quality.validate_speech_waveform(bad, rate)
    tts_quality.validate_speech_waveform(fake_speech_wave(), rate)
