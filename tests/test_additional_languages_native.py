"""Opt-in real multilingual Edge -> Whisper -> timed SRT integration check."""
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import srt

pytestmark = pytest.mark.skipif(os.getenv("HAIZFLOW_RUN_LANGUAGE_NATIVE") != "1",
                                reason="Opt-in inference/network test; set HAIZFLOW_RUN_LANGUAGE_NATIVE=1")


@pytest.mark.parametrize("language,text,voice", [
    ("ko", "안녕하세요. 오늘은 날씨가 아주 좋습니다. 내일 다시 만나요.", "ko-KR-SunHiNeural"),
    ("ja", "こんにちは。今日はとてもいい天気です。明日また会いましょう。", "ja-JP-NanamiNeural"),
    ("es", "Hola, buenos días. Hoy hace muy buen tiempo. Muchas gracias y hasta mañana.", "es-ES-ElviraNeural"),
])
def test_real_speech_detection_and_no_captions_in_silent_outro(tmp_path, monkeypatch, language, text, voice):
    from haizflow.pipeline import edge_tts_backend, subtitle, transcribe
    from haizflow.utils.ffmpeg import _binary, get_video_duration

    model_root = Path(os.environ["HAIZFLOW_LANGUAGE_MODELS"]).resolve(strict=True)
    monkeypatch.setattr(transcribe, "MODELS_DIR", str(model_root))
    monkeypatch.setattr(transcribe, "runtime_profile", lambda: SimpleNamespace(
        cuda_available=True, total_vram_bytes=8 * 1024**3, cpu_threads=2, whisper_batch_size=2))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    identifier = "native-language-" + language
    speech, audio = tmp_path / "speech.mp3", tmp_path / "audio.wav"
    edge_tts_backend.synthesize_to_mp3(text, voice, str(speech), identifier, language_id=language)
    duration = get_video_duration(str(speech))
    subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-i", str(speech),
                    "-af", "apad=pad_dur=3", "-ar", "16000", "-ac", "1", str(audio)],
                   check=True, capture_output=True, timeout=30)
    output = tmp_path / "transcript.json"
    try:
        segments, detected = transcribe.transcribe(str(audio), str(output), "auto", identifier,
                                                   model_name="small", device_preference="gpu")
    finally:
        transcribe.release_warm_whisperx_model()
    assert detected == language, segments
    assert segments and {item["language"] for item in segments} == {language}
    transcribe._validate_timestamp_invariants(segments, duration + 3)
    assert segments[-1]["end"] <= duration + .35, segments  # No speech in the 3-second outro.
    destination = tmp_path / "result.srt"
    subtitle.generate_srt(str(output), str(destination), 32, identifier, preserve_segment_boundaries=True)
    cues = list(srt.parse(destination.read_text("utf-8")))
    assert [(cue.start.total_seconds(), cue.end.total_seconds()) for cue in cues] == [
        (item["start"], item["end"]) for item in segments]
    summary = {"language": language, "detected": detected, "speech_seconds": duration,
               "outro_seconds": 3, "segments": segments}
    evidence = Path(__file__).parents[1] / "build" / f"language-native-{language}-2026-10-31.json"
    evidence.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
