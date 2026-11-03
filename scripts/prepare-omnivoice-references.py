"""Build short lossless reference assets OFFLINE, never during a user's video.

Run synthesize first, then verify in a separate process (models never overlap).
Only --publish installs candidates passing waveform, duration and ASR checks.
ASR is an intelligibility gate, NOT proof of a natural voice/native accent.
Existing UI previews and user projects are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SAMPLES = ROOT / "src/haizflow/desktop/assets/voice_samples"
TEXTS = {
    "vi": "Hôm nay trời rất đẹp. Chúng ta hãy cùng bắt đầu một câu chuyện mới nhé.",
    "en": "It is a beautiful day today. Let us begin a new story together, and see what happens next.",
    "zh": "今天的天气真好。让我们一起开始一个新的故事，看看接下来会发生什么吧。",
    "ja": "今日はいい天気ですね。一緒に新しい物語を始めましょう。次に何が起こるのでしょうか。",
    "ko": "오늘은 날씨가 참 좋아요. 함께 새로운 이야기를 시작해 봐요. 다음에는 무슨 일이 생길까요?",
    "es": "Hoy hace un día precioso. Vamos a empezar una nueva historia juntos y descubrir qué sucede después.",
}


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def character_error(expected, actual):
    left, right = normalized(expected), normalized(actual)
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        following = [i]
        for j, b in enumerate(right, 1):
            following.append(min(row[j] + 1, following[-1] + 1, row[j - 1] + (a != b)))
        row = following
    return row[-1] / max(1, len(left))


def save_json(path, data):
    temporary = path.with_suffix(".partial.json")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("synthesize", "verify"), required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/omnivoice-reference-bank-v1")
    parser.add_argument("--voices", default="", help="Comma-separated exact preset IDs; default all.")
    parser.add_argument("--languages", default=",".join(TEXTS))
    parser.add_argument("--publish", action="store_true", help="Install verified assets; verify stage only.")
    parser.add_argument("--asr-model", choices=("small", "large-v3-turbo"), default="small")
    parser.add_argument("--asr-device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    if args.publish and args.stage != "verify":
        parser.error("Publishing requires verification in a separate process.")
    output = args.output.resolve()
    if output.is_relative_to(SAMPLES.resolve()):
        parser.error("Candidate output must be outside the packaged asset tree.")
    output.mkdir(parents=True, exist_ok=True)
    os.environ.update(MODELS_DIR=str(args.models.resolve()), HAIZFLOW_SMOKE_TEST="1",
                      RUNTIME_DATA_DIR=str(output / "runtime"), TMP_DIR=str(output / "tmp"),
                      HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="2")
    from haizflow.pipeline import omnivoice_tts as voice

    languages = args.languages.split(",")
    voices = args.voices.split(",") if args.voices else list(voice.OMNIVOICE_VOICE_INSTRUCTIONS)
    if any(lang not in TEXTS for lang in languages) or any(v not in voice.OMNIVOICE_VOICE_INSTRUCTIONS for v in voices):
        parser.error("Unknown language or preset.")
    plan_path = output / "candidates.json"
    plan = json.loads(plan_path.read_text("utf-8")) if plan_path.exists() else {}
    if args.stage == "synthesize":
        from haizflow.core.memory import GIB, memory_snapshot
        memory = memory_snapshot()
        # This opt-in builder runs ONE short GPU item at a time, with the ASR
        # verifier in another process afterwards. Still require both physical
        # and commit headroom for the low_cpu_mem_usage checkpoint loader.
        if ((memory.available_bytes or 0) < 2.5 * GIB
                or (memory.commit_available_bytes or 0) < 8 * GIB):
            raise RuntimeError(f"Insufficient RAM/commit headroom. No model was loaded. {memory.diagnostic()}")
        voice._prepare_isolated_runtime()
        model = voice.verify_omnivoice_model(args.models / "omnivoice")
        previews = json.loads((SAMPLES / "samples.json").read_text("utf-8"))
        try:
            for preset in voices:
                safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "_", preset).strip("_")
                for language in languages:
                    key = f"{preset}/{language}"
                    clip = output / safe_id / f"{language}.wav"
                    clip.parent.mkdir(exist_ok=True)
                    if clip.is_file() and key in plan:
                        continue
                    # Bootstrap the SAME identity from existing packaged audio.
                    # New JA/KO/ES assets are synthetic target-language references,
                    # not recordings by native speakers and not another preset.
                    base_language = language if language in {"vi", "en", "zh"} else "en"
                    reference = SAMPLES / "omnivoice" / safe_id / f"{base_language}.mp3"
                    if not reference.is_file():
                        raise RuntimeError(f"Missing identity reference: {reference}")
                    entry = dict(voice=preset, language=language, text=TEXTS[language],
                                 path=clip.relative_to(output).as_posix(), inference_steps=48,
                                 bootstrap_language=base_language,
                                 bootstrap_sha256=hashlib.sha256(reference.read_bytes()).hexdigest())
                    request = dict(model_root=str(model), site_packages=str(voice._sdk_root() / "site-packages"),
                                   device="cuda:0", language=language, speaker_mode="multiple", inference_steps=48,
                                   status_path=str(output / "status.json"),
                                   voice_seed=int.from_bytes(hashlib.sha256(preset.encode()).digest()[:4], "big"),
                                   items=[dict(text=entry["text"], voice=preset, wav_path=str(clip),
                                               preset_reference_path=str(reference),
                                               preset_reference_text=previews["sentences"][base_language])])
                    request_path = output / "request.json"
                    save_json(request_path, request)
                    print(f"Generating {key}", flush=True)
                    code, error = voice._run_persistent_worker_process(request_path, request, "reference-bank-build")
                    if code:
                        print(f"Rejected {key}: {error[-500:]}", flush=True)
                        continue
                    plan[key] = entry
                    save_json(plan_path, plan)
        finally:
            voice.clear_runtime()
        return 0

    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel

    from haizflow.pipeline.omnivoice_references import REFERENCE_ROOT
    from haizflow.pipeline.tts_quality import active_speech_rms, validate_speech_waveform

    asr = WhisperModel(str(args.models / "whisper" / args.asr_model), device=args.asr_device,
                       compute_type="int8_float16" if args.asr_device == "cuda" else "int8",
                       cpu_threads=2, local_files_only=True)
    manifest_path = REFERENCE_ROOT / "manifest.json"
    manifest = (json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists()
                else {"schema_version": 1, "references": {}})
    report = {}
    for key, entry in plan.items():
        if entry["voice"] not in voices or entry["language"] not in languages:
            continue
        clip = output / entry["path"]
        try:
            waveform, rate = sf.read(clip, dtype="float32")
            if waveform.ndim != 1 or rate != 24000 or not 3 <= len(waveform) / rate <= 10:
                raise ValueError("Reference must be mono 24 kHz and 3–10 seconds, without truncation.")
            validate_speech_waveform(waveform, rate)
            pieces, _ = asr.transcribe(str(clip), language=entry["language"], beam_size=5,
                                      condition_on_previous_text=False, vad_filter=False)
            actual = " ".join(piece.text.strip() for piece in pieces)
            error = character_error(entry["text"], actual)
            verification = dict(waveform_valid=True, character_error_rate=round(error, 6),
                                asr_model=f"faster-whisper-{args.asr_model}", asr_device=args.asr_device,
                                transcript=actual,
                                duration_seconds=round(len(waveform) / rate, 4),
                                active_rms=round(active_speech_rms(waveform, rate), 6),
                                peak=float(np.max(np.abs(waveform))))
            report[key] = dict(passed=error <= .05, **verification)
            if error > .05:
                print(f"Rejected {key}: CER={error:.3f} {actual}", flush=True)
                continue
            if args.publish:
                destination = REFERENCE_ROOT / entry["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(".partial.wav")
                temporary.write_bytes(clip.read_bytes())
                os.replace(temporary, destination)
                manifest["references"][key] = {
                    **entry, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                    "verification": verification,
                }
                save_json(manifest_path, manifest)
            print(f"Passed {key}: CER={error:.3f}", flush=True)
        except (OSError, RuntimeError, ValueError) as exc:
            report[key] = dict(passed=False, error=str(exc))
            print(f"Rejected {key}: {exc}", flush=True)
    save_json(output / "verification.json", report)
    print(f"Passed {sum(item['passed'] for item in report.values())}/{len(report)}", flush=True)
    return 0 if report and all(item["passed"] for item in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
