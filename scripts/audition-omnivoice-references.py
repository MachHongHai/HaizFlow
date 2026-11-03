"""Make controlled old/new listening clips; never alter projects or publish assets."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EXAMPLES = {
    "vi": "Cảm ơn mẹ. Mọi chuyện rồi sẽ ổn thôi. Chúc mẹ ngủ ngon.",
    "en": "I don't feel a thing. Thank you for being here. Have a good night.",
    "zh": "我什么也感觉不到。谢谢你一直陪着我。祝你晚安。",
    "ja": "私は何も感じません。そばにいてくれてありがとう。おやすみなさい。",
    "ko": "아무것도 느껴지지 않아요. 곁에 있어 줘서 고마워요. 안녕히 주무세요.",
    "es": "No siento nada. Gracias por estar aquí. Que tengas buenas noches.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--bank", type=Path, default=ROOT / "build/omnivoice-reference-bank-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "build/omnivoice-reference-audition-v1")
    parser.add_argument("--verify", action="store_true", help="Read-only ASR check after synthesis has exited.")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ.update(MODELS_DIR=str(args.models.resolve()), HAIZFLOW_SMOKE_TEST="1",
                      RUNTIME_DATA_DIR=str(root / "runtime"), TMP_DIR=str(root / "tmp"),
                      HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    if args.verify:
        import importlib.util
        import subprocess

        import numpy as np
        from faster_whisper import WhisperModel

        from haizflow.pipeline.tts_quality import active_speech_rms
        from haizflow.utils.ffmpeg import _binary

        spec = importlib.util.spec_from_file_location(
            "reference_builder", Path(__file__).with_name("prepare-omnivoice-references.py"))
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        report_path = root / "report.json"
        report = json.loads(report_path.read_text("utf-8"))
        asr = WhisperModel(str(args.models / "whisper/small"), device="cpu", compute_type="int8",
                           cpu_threads=2, local_files_only=True)
        for entry in report:
            if not entry.get("created"):
                continue
            path = root / entry["path"]
            segments, _ = asr.transcribe(str(path), language=entry["language"], beam_size=5,
                                         condition_on_previous_text=False, vad_filter=False)
            transcript = " ".join(s.text.strip() for s in segments)
            pcm = subprocess.run([_binary("ffmpeg"), "-v", "error", "-i", str(path), "-ac", "1",
                                  "-ar", "24000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
            audio = np.frombuffer(pcm, dtype="<f4")
            rms = active_speech_rms(audio, 24000)
            entry.update(asr=transcript,
                         character_error_rate=round(builder.character_error(entry["text"], transcript), 4),
                         active_dbfs=round(20 * np.log10(max(1e-8, rms)), 2),
                         duration_seconds=round(len(audio) / 24000, 3))
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
            print(f"{entry['path']} CER={entry['character_error_rate']} {transcript}", flush=True)
        return 0
    from haizflow.core.memory import GIB, memory_snapshot
    from haizflow.pipeline import omnivoice_tts as voice

    memory = memory_snapshot()
    if ((memory.available_bytes or 0) < 2.5 * GIB or (memory.commit_available_bytes or 0) < 8 * GIB):
        raise RuntimeError(f"Insufficient headroom: {memory.diagnostic()}")
    candidates = json.loads((args.bank / "candidates.json").read_text("utf-8"))
    verified = json.loads((args.bank / "verification.json").read_text("utf-8"))
    samples = ROOT / "src/haizflow/desktop/assets/voice_samples"
    previews = json.loads((samples / "samples.json").read_text("utf-8"))
    report = []
    try:
        for language, text in EXAMPLES.items():
            for preset in ("omnivoice:male", "omnivoice:female"):
                key = f"{preset}/{language}"
                if not verified.get(key, {}).get("passed"):
                    print(f"Skipped unverified {key}", flush=True)
                    continue
                safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "_", preset).strip("_")
                baseline_language = language if language in {"vi", "en", "zh"} else "en"
                old = (str(samples / "omnivoice" / safe_id / f"{baseline_language}.mp3"),
                       previews["sentences"][baseline_language])
                candidate = candidates[key]
                new = (str((args.bank / candidate["path"]).resolve()), candidate["text"])
                cases = [("normal", text)]
                if language == "vi":
                    cases += [("short", "Tôi không biết."), ("ending", "Chúc ngủ ngon.")]
                for name, phrase in cases:
                    for variant, reference in (("old", old), ("new", new)):
                        destination = root / f"{language}-{safe_id}-{name}-{variant}.mp3"
                        entry = dict(language=language, voice=preset, text=phrase,
                                     variant=variant, steps=48, path=destination.name)
                        if not destination.exists():
                            print(f"Generating {destination.name}", flush=True)
                            with (patch.object(voice, "_preset_reference", return_value=reference),
                                  patch.object(voice, "log_to_video", lambda *a, **kw: None)):
                                try:
                                    voice.synthesize_to_mp3(phrase, preset, str(destination), "reference-audition",
                                                            language_id=language, device="gpu", inference_steps=48,
                                                            keep_worker_warm=True)
                                except RuntimeError as exc:
                                    entry["error"] = str(exc)[-1000:]
                                    print(f"Failed: {entry['error']}", flush=True)
                        entry["created"] = destination.is_file()
                        report.append(entry)
                        (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    finally:
        voice.clear_runtime()
    lines = ["# OmniVoice: đối chứng mẫu tham chiếu", "",
             "Cùng câu, giọng, seed và 48 bước; chỉ thay mẫu tham chiếu. Fade = 0. Không đổi dữ liệu dự án.", "",
             "Mẫu mới được tạo tổng hợp từ đúng preset cũ, không phải bản thu người bản ngữ. "
             "Kiểm tra ASR không thay thế việc nghe đánh giá độ tự nhiên.", "",
             "| Ngôn ngữ / giọng / câu | Mẫu cũ | Mẫu mới |", "|---|---|---|"]
    for old in report:
        if old["variant"] != "old":
            continue
        new = next((e for e in report if e["variant"] == "new" and e["voice"] == old["voice"]
                    and e["language"] == old["language"] and e["text"] == old["text"]), {})
        def link(entry):
            return f"[Nghe](<{(root / entry['path']).as_posix()}>)" if entry.get("created") else "Không tạo được"
        lines.append(f"| {old['language']} / {old['voice']} — {old['text']} | {link(old)} | {link(new)} |")
    (root / "Nghe-doi-chung.md").write_text("\n".join(lines) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
