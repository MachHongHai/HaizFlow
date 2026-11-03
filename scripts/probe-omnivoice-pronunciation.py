"""Offline diagnostic: separate ASR uncertainty from short-utterance TTS errors."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/omnivoice-pronunciation-probe-v1")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build/omnivoice-reference-audition-v1/report.json")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.update(MODELS_DIR=str(args.models), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    import numpy as np
    from faster_whisper import WhisperModel

    from haizflow.core.memory import GIB, memory_snapshot
    from haizflow.utils.ffmpeg import _binary

    memory = memory_snapshot()
    if (memory.available_bytes or 0) < 2 * GIB or (memory.commit_available_bytes or 0) < 5 * GIB:
        raise RuntimeError(f"Not enough memory for independent ASR: {memory.diagnostic()}")
    spec = importlib.util.spec_from_file_location("reference_builder", ROOT / "scripts/prepare-omnivoice-references.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    audition = args.report.resolve().parent
    clips = json.loads(args.report.read_text("utf-8"))
    model = WhisperModel(str(args.models / "whisper/large-v3-turbo"), device="cuda", compute_type="int8_float16",
                         cpu_threads=2, local_files_only=True)
    report = []
    for entry in clips:
        if not ((entry["language"] == "vi" and "-normal-" not in entry["path"])
                or (entry["language"] == "ko" and entry["voice"] == "omnivoice:female")):
            continue
        raw = subprocess.run([_binary("ffmpeg"), "-v", "error", "-i", str(audition / entry["path"]),
                              "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                             check=True, capture_output=True).stdout
        audio = np.frombuffer(raw, dtype="<f4")
        # No text hint/initial prompt: do not teach the recognizer the answer.
        # Padding affects only this diagnostic, not the listening sample.
        for pad in (0, 8000):
            waveform = np.pad(audio, (pad, pad)) if pad else audio
            pieces, _ = model.transcribe(waveform, language=entry["language"], beam_size=5,
                                         condition_on_previous_text=False, vad_filter=False, temperature=0)
            actual = " ".join(s.text.strip() for s in pieces)
            row = dict(path=entry["path"], expected=entry["text"], asr=actual,
                       model="large-v3-turbo-int8-float16-cuda", diagnostic_pad_seconds=pad / 16000,
                       character_error_rate=round(builder.character_error(entry["text"], actual), 4))
            report.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            (args.output / "independent-asr.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
