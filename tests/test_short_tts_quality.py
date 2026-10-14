import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from hflow.pipeline import manual_tools, process_video
from hflow.pipeline import omnivoice_tts as voice
from hflow.pipeline.tts_quality import (
    active_speech_rms,
    match_quiet_speech_level,
    short_phrase_generation_options,
    short_phrase_units,
    spoken_text_for_omnivoice,
    uses_spoken_number_normalization,
    validate_short_phrase_audio,
    validate_speech_waveform,
)
from test_omnivoice_batching import fake_speech_wave, fake_torch


def test_short_phrase_policy_protects_final_phonemes_and_leaves_long_text_unchanged():
    options = short_phrase_generation_options("Đồ ngốc!", "Vietnamese")
    assert "duration" not in options
    assert "postprocess_output" not in options
    assert options["fade_duration"] == 0.0
    assert short_phrase_units("Đồ ngốc!", "vi") == 2
    assert short_phrase_units("快走！", "Chinese") == 2
    assert short_phrase_generation_options("Đây là một câu nói bình thường dài hơn.", "vi") == {}
    assert short_phrase_generation_options("Some ordinary sentence longer than four words.", "English") == {}
    assert short_phrase_generation_options("Привет", "ru") == {}
    assert short_phrase_generation_options("90000 dollars", "English") == {}
    assert short_phrase_generation_options("Internationalization demonstration", "English") == {}
    assert short_phrase_generation_options("internationalization", "vi") == {}


def test_padding_and_silence_cannot_hide_an_incomplete_short_phrase():
    with pytest.raises(RuntimeError, match="incomplete"):
        validate_short_phrase_audio(np.concatenate([np.zeros(24000), np.ones(4800), np.zeros(24000)]),
                                    "Đồ ngốc!", "Vietnamese", 24000)
    validate_short_phrase_audio(np.concatenate([np.zeros(2400), np.ones(16000), np.zeros(2400)]),
                                "Đồ ngốc!", "Vietnamese", 24000)


def test_short_policy_invalidates_only_short_local_clips_not_edge_or_long_cache():
    video = SimpleNamespace(speaker_mode="single", tts_voice="omnivoice:female", tts_provider="omnivoice-gpu",
                            target_language="vi", files={}, manual_tool_generations={})
    segments = [{"text": "Đồ ngốc!"}, {"text": "Đây là một câu dài vẫn được giữ nguyên trong cache."}]
    from hflow.pipeline import tts_quality
    first = manual_tools._voice_clip_signatures(video, segments)
    with patch.object(tts_quality, "SHORT_PHRASE_VERSION", "another-test-policy"):
        changed = manual_tools._voice_clip_signatures(video, segments)
    assert first[0] != changed[0] and first[1] == changed[1]
    video.tts_provider, video.tts_voice = "edge", "vi-VN-HoaiMyNeural"
    edge = manual_tools._voice_clip_signatures(video, segments)
    with patch.object(tts_quality, "SHORT_PHRASE_VERSION", "another-test-policy"):
        assert manual_tools._voice_clip_signatures(video, segments) == edge
    video.tts_provider, video.tts_voice = "omnivoice-gpu", "omnivoice:female"
    short_auto = process_video._voice_checkpoint_signature(video, "same-document", segments=segments[:1])
    long_auto = process_video._voice_checkpoint_signature(video, "same-document", segments=segments[1:])
    with patch.object(tts_quality, "SHORT_PHRASE_VERSION", "another-test-policy"):
        assert process_video._voice_checkpoint_signature(video, "same-document", segments=segments[:1]) != short_auto
        assert process_video._voice_checkpoint_signature(video, "same-document", segments=segments[1:]) == long_auto


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
@pytest.mark.parametrize("speaker_mode", ["single", "multiple"])
@pytest.mark.parametrize("text", ["Đồ ngốc!", "90.000 đô la.", "Xin lỗi, coo nhỏ.",
                                  "Đây là một câu nói dài bình thường vẫn cần giữ đầy đủ âm cuối."])
def test_worker_preserves_legacy_generation_and_does_not_gate_short_speech_on_asr(tmp_path, device, speaker_mode, text):
    calls, writes, statuses = [], [], []
    def generate(**kwargs):
        calls.append(kwargs)
        return [fake_speech_wave(4800)]
    model = SimpleNamespace(generate=generate, sampling_rate=24000)
    torch = fake_torch()
    runtime = {"modules": (np, SimpleNamespace(write=lambda *args, **kwargs: writes.append(args)), torch, Mock()),
               "model": model, "model_key": ("model", device)}
    request = {"site_packages": str(tmp_path), "model_root": "model", "device": device, "language": "vi",
               "speaker_mode": speaker_mode, "status_path": str(tmp_path / "status.json"),
               "quality_model_root": "obsolete-request-must-not-load", "inference_steps": 32,
               "items": [{"text": text, "voice": "omnivoice:female", "wav_path": str(tmp_path / "voice.wav")}]}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    with patch.object(voice, "_write_status_file", side_effect=lambda _path, payload: statuses.append(payload)):
        assert voice._worker_main(str(path), runtime) == 0
    assert len(calls) == 1 and len(writes) == 1
    assert calls[0]["text"] == text
    assert calls[0]["fade_duration"] == 0.0
    assert calls[0]["num_step"] == 32 and calls[0]["normalize_text"] is False
    assert calls[0]["audio_chunk_duration"] == 10.0 and calls[0]["audio_chunk_threshold"] == 8.0
    assert not {'duration', 'speed', 'pad_duration'} & calls[0].keys()
    assert not any(s["stage"] in {'retrying_short_utterance', 'loading_short_speech_verifier',
                                  'creating_short_voice_reference', 'validating_short_speech'} for s in statuses)


@pytest.mark.parametrize("written,spoken", [
    ("90.000 đô la.", "Chín mươi nghìn đô la."),
    ("90000 đô la.", "Chín mươi nghìn đô la."),
    ("giá 105 đô la", "giá một trăm lẻ năm đô la"),
    ("1001 đồng", "Một nghìn không trăm lẻ một đồng"),
    ("1.000.000.000.000 đồng", "Một nghìn tỷ đồng"),
    ("-12,5 độ", "Âm mười hai phẩy năm độ"),
    ("007", "Không không bảy"),
    ("1.2.3 12/10/2026 10:30 X123 5kg", "1.2.3 12/10/2026 10:30 X123 5kg"),
])
def test_vietnamese_spoken_numbers_are_safe_and_local_to_tts(written, spoken):
    assert spoken_text_for_omnivoice(written, "Vietnamese") == spoken
    assert spoken_text_for_omnivoice(written, "English") == written


def test_quality_guard_rejects_beeps_even_with_speech_afterwards():
    rate = 24000
    tone = .2 * np.sin(2 * np.pi * 600 * np.arange(2880) / rate)
    with pytest.raises(RuntimeError, match="beep"):
        validate_speech_waveform(np.concatenate([np.zeros(2400), tone, np.zeros(2400), tone,
                                                np.zeros(2400), fake_speech_wave()]), rate)
    with pytest.raises(RuntimeError, match="tone/DC"):
        validate_speech_waveform(np.ones(rate), rate)
    validate_speech_waveform(fake_speech_wave(), rate)
    # High register is not itself a failure: valid speech has harmonics.
    t = np.arange(rate) / rate
    validate_speech_waveform(.2 * np.sin(2*np.pi*800*t) + .13 * np.sin(2*np.pi*1600*t)
                            + fake_speech_wave() * .1, rate)
    validate_speech_waveform(.2 * np.sin(2*np.pi*50*t) + .05 * np.sin(2*np.pi*100*t), rate)


def test_number_policy_invalidates_only_numeric_local_cache():
    from hflow.pipeline import tts_quality
    video = SimpleNamespace(speaker_mode="single", tts_voice="omnivoice:male", tts_provider="omnivoice-gpu",
                            target_language="vi", files={}, manual_tool_generations={})
    segments = [{"text": "90.000 đô la."}, {"text": "Đây là một câu nói dài hoàn toàn bình thường."}]
    before = manual_tools._voice_clip_signatures(video, segments)
    with patch.object(tts_quality, "NUMBER_SPEECH_VERSION", "test-number-policy"):
        after = manual_tools._voice_clip_signatures(video, segments)
        assert before[0] != after[0] and before[1] == after[1]
    video.tts_provider = "edge"
    before = manual_tools._voice_clip_signatures(video, segments)
    with patch.object(tts_quality, "NUMBER_SPEECH_VERSION", "test-number-policy"):
        assert before == manual_tools._voice_clip_signatures(video, segments)


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
@pytest.mark.parametrize("permanently_bad", [False, True])
def test_worker_retries_beeps_once_without_changing_voice_or_publishing_bad_audio(tmp_path, device, permanently_bad):
    torch, calls, writes = fake_torch(), [], []
    prompt = object()
    def generate(**kwargs):
        calls.append((kwargs, torch.manual_seed.call_args.args[0]))
        return [np.ones(24000, dtype=np.float32) if permanently_bad or len(calls) == 1 else fake_speech_wave()]
    model = SimpleNamespace(generate=generate, sampling_rate=24000, create_voice_clone_prompt=lambda **kw: prompt)
    runtime = {"modules": (np, SimpleNamespace(write=lambda *args, **kw: writes.append(args)), torch, Mock()),
               "model": model, "model_key": ("model", device)}
    request = {"site_packages": str(tmp_path), "model_root": "model", "device": device, "language": "vi",
               "speaker_mode": "multiple", "status_path": str(tmp_path / "status.json"), "inference_steps": 32,
               "items": [{"text": "90.000 đô la.", "voice": "omnivoice:male", "wav_path": str(tmp_path / "voice.wav"),
                          "preset_reference_path": "preset.mp3", "preset_reference_text": "Giọng mẫu."}]}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    if permanently_bad:
        with pytest.raises(RuntimeError, match="tone/DC"):
            voice._worker_main(str(path), runtime)
    else:
        assert voice._worker_main(str(path), runtime) == 0
    assert len(calls) == 2 and len(writes) == (0 if permanently_bad else 1)
    assert calls[0][1] != calls[1][1]
    for settings, _seed in calls:
        assert settings["text"] == "90.000 đô la."
        assert settings["voice_clone_prompt"] is prompt
        assert settings["num_step"] == 32 and not {'duration', 'speed', 'pad_duration'} & settings.keys()
    assert request["items"][0]["text"] == "90.000 đô la."


def test_auto_checkpoint_includes_numeric_policy_without_invalidating_other_inputs():
    from hflow.pipeline import tts_quality
    video = SimpleNamespace(speaker_mode="single", tts_voice="omnivoice:male", tts_provider="omnivoice-gpu",
                            target_language="vi", files={})
    segments = [{"text": "90.000 đô la."}]
    before = process_video._voice_checkpoint_signature(video, "same-subtitle", segments=segments)
    with patch.object(tts_quality, "NUMBER_SPEECH_VERSION", "test-number-policy"):
        assert before != process_video._voice_checkpoint_signature(video, "same-subtitle", segments=segments)
    video.tts_provider = "edge"
    before = process_video._voice_checkpoint_signature(video, "same-subtitle", segments=segments)
    with patch.object(tts_quality, "NUMBER_SPEECH_VERSION", "test-number-policy"):
        assert before == process_video._voice_checkpoint_signature(video, "same-subtitle", segments=segments)


def test_quiet_speech_matches_own_reference_without_changing_duration_or_pumping():
    quiet = fake_speech_wave() * .25
    corrected = match_quiet_speech_level(quiet, 24000, .10)
    assert active_speech_rms(corrected, 24000) == pytest.approx(active_speech_rms(quiet, 24000) * 10**(9/20), rel=1e-5)
    assert np.allclose(corrected / quiet, corrected[0] / quiet[0])
    assert corrected.shape == quiet.shape and corrected.dtype == np.float32
    near_normal = fake_speech_wave()
    assert np.array_equal(match_quiet_speech_level(near_normal, 24000, .10), near_normal)
    assert np.array_equal(match_quiet_speech_level(quiet, 24000, 0), quiet)
    # Absolute silence and vanishing codec residue are not "quiet speech".
    assert np.array_equal(match_quiet_speech_level(quiet * .001, 24000, .1), quiet * .001)


def test_speech_level_ignores_silence_and_dc_and_never_clips_transients():
    speech = fake_speech_wave() * .3
    padded = np.concatenate([np.zeros(24000), speech + .2, np.zeros(24000)]).astype(np.float32)
    assert active_speech_rms(padded, 24000) == pytest.approx(active_speech_rms(speech, 24000), rel=1e-5)
    speech[3000] = .85
    corrected = match_quiet_speech_level(speech, 24000, .1)
    assert abs(corrected).max() <= 10**(-1/20) + 1e-6
    assert np.allclose(corrected, speech * (corrected[3000] / speech[3000]))


def test_reference_level_cache_is_bounded_and_detects_changed_audio(tmp_path):
    import soundfile as sf
    runtime = {}
    p = tmp_path / "ref.wav"
    sf.write(p, fake_speech_wave(), 24000, subtype="FLOAT")
    reader = Mock(wraps=sf.SoundFile)
    lib = SimpleNamespace(SoundFile=reader)
    first = voice._reference_speech_level(runtime, lib, p)
    assert first == pytest.approx(.1, abs=.002)
    assert voice._reference_speech_level(runtime, lib, p) == first
    assert reader.call_count == 1
    sf.write(p, fake_speech_wave(48000) * .5, 24000, subtype="FLOAT")
    assert voice._reference_speech_level(runtime, lib, p) == pytest.approx(.05, abs=.002)
    for i in range(5):
        path = tmp_path / f"ref-{i}.wav"
        sf.write(path, fake_speech_wave(), 24000, subtype="FLOAT")
        voice._reference_speech_level(runtime, lib, path)
    assert len(runtime['reference_loudness_cache']) == 4
    assert voice._reference_speech_level(runtime, lib, tmp_path / "missing.wav", .09) == .09


def test_unicode_normalization_alone_does_not_enable_number_leveling():
    import unicodedata
    assert not uses_spoken_number_normalization(unicodedata.normalize("NFD", "Đồ ngốc!"), "vi")
    assert uses_spoken_number_normalization("90.000 đô la.", "vi")
    assert not uses_spoken_number_normalization("90.000 đô la.", "en")


@pytest.mark.parametrize("device,four_gb", [("cpu", False), ("cuda:0", False), ("cuda:0", True)])
def test_worker_levels_quiet_numeric_and_regular_speech_on_cpu_and_gpu(tmp_path, device, four_gb):
    import soundfile as sf
    torch = fake_torch()
    if four_gb:
        torch.cuda.mem_get_info = lambda: (3 * 1024**3, 4 * 1024**3)
    reference = tmp_path / "ref.wav"
    sf.write(reference, fake_speech_wave() * .8, 24000, subtype="FLOAT")
    quiet, writes = fake_speech_wave() * .3, []
    model = SimpleNamespace(generate=lambda **kw: [quiet.copy()], sampling_rate=24000,
                            create_voice_clone_prompt=lambda **kw: SimpleNamespace(ref_rms=.07))
    lib = SimpleNamespace(SoundFile=sf.SoundFile, write=lambda _p, wave, _rate, **kw: writes.append(wave))
    runtime = {"modules": (np, lib, torch, Mock()), "model": model, "model_key": ("model", device)}
    items = [{"text": text, "voice": "omnivoice:male", "wav_path": str(tmp_path / f"{i}.wav"),
              "preset_reference_path": str(reference), "preset_reference_text": "Giọng mẫu."}
             for i, text in enumerate(["90.000 đô la.", "Đây là một câu nói bình thường khác."])]
    request = {"site_packages": str(tmp_path), "model_root": "model", "device": device, "language": "vi",
               "speaker_mode": "multiple", "items": items, "status_path": str(tmp_path / "status.json")}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    assert voice._worker_main(str(path), runtime) == 0
    assert len(writes) == 2
    assert active_speech_rms(writes[0], 24000) == pytest.approx(.08, abs=.002)
    assert active_speech_rms(writes[1], 24000) == pytest.approx(.08, abs=.002)
    assert len(runtime['reference_loudness_cache']) == 1
