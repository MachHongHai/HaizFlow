"""Read-only ASR comparison for any video's generated voice clips.

Example: python scripts/check-voice-quality.py --transcript translated.json
--voice-dir voice_parts --whisper-model /path/to/local/model --segments 1,3
This diagnostic never generates speech or changes project metadata/cache.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--voice-dir", type=Path, required=True)
    parser.add_argument("--whisper-model", type=Path, required=True)
    parser.add_argument("--segments", default="", help="Comma-separated 1-based indices; empty means all.")
    parser.add_argument("--format", choices=("mp3", "wav"), default="mp3", help="Clip format; WAV supports standalone synthesis benchmarks.")
    args = parser.parse_args()
    if not args.transcript.is_file() or not args.voice_dir.is_dir() or not args.whisper_model.is_dir():
        parser.error("Transcript, voice directory and local Whisper model must exist.")
    try:
        segments = json.loads(args.transcript.read_text(encoding="utf-8"))
        if not isinstance(segments, list) or not segments:
            raise ValueError("Transcript must contain a nonempty list.")
        indices = [int(value.strip()) for value in args.segments.split(",") if value.strip()]
        indices = indices or list(range(1, len(segments) + 1))
        if any(index < 1 or index > len(segments) for index in indices):
            raise ValueError("Segment index is outside the transcript.")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    from faster_whisper import WhisperModel

    model = WhisperModel(
        str(args.whisper_model.resolve()), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True
    )
    missing = False
    for index in indices:
        clip = args.voice_dir / f"voice_{index:04d}.{args.format}"
        if not clip.is_file():
            print(json.dumps({"segment": index, "error": "Missing voice clip"}, ensure_ascii=False), flush=True)
            missing = True
            continue
        detected, info = model.transcribe(str(clip), beam_size=3, condition_on_previous_text=False)
        print(
            json.dumps(
                {
                    "segment": index,
                    "expected": segments[index - 1].get("text", ""),
                    "detected": " ".join(part.text.strip() for part in detected),
                    "language": info.language,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
