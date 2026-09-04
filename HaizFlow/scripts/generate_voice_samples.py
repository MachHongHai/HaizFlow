"""Generate packaged voice-library samples during development.

The desktop runtime only plays the resulting MP3 files; it never loads a TTS
model for a voice-row preview. Run this script explicitly when the catalog or
the locked sample sentence changes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from haizflow.desktop.catalog import EDGE_TTS_VOICES_BY_LANGUAGE, OMNIVOICE_TTS_VOICES
from haizflow.pipeline.omnivoice_tts import clear_runtime, synthesize_to_mp3
from haizflow.pipeline.tts import tts_segment_with_retry


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / "src" / "haizflow" / "desktop" / "assets" / "voice_samples"
MANIFEST_PATH = SAMPLE_ROOT / "samples.json"


def safe_voice_id(voice: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", voice).strip("_")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--provider", choices=("all", "omnivoice", "edge"), default="all")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sentence = str(manifest["sentences"]["vi"])
    voices = list(OMNIVOICE_TTS_VOICES)
    if args.limit > 0:
        voices = voices[: args.limit]

    generated: list[dict[str, str]] = []
    try:
        if args.provider in {"all", "omnivoice"}:
            for index, (voice, label, category) in enumerate(voices, 1):
                output = SAMPLE_ROOT / "omnivoice" / safe_voice_id(voice) / "vi.mp3"
                output.parent.mkdir(parents=True, exist_ok=True)
                if args.force or not output.is_file() or output.stat().st_size <= 0:
                    print(f"[{index}/{len(voices)}] {label}", flush=True)
                    synthesize_to_mp3(
                        sentence,
                        voice,
                        str(output),
                        "voice-sample-assets",
                        language_id="vi",
                        keep_worker_warm=True,
                        inference_steps=8,
                    )
    finally:
        clear_runtime()

    if args.provider in {"all", "edge"}:
        edge_voices = EDGE_TTS_VOICES_BY_LANGUAGE["vi"]
        for index, (voice, label) in enumerate(edge_voices, 1):
            output = SAMPLE_ROOT / "edge" / safe_voice_id(voice) / "vi.mp3"
            output.parent.mkdir(parents=True, exist_ok=True)
            if args.force or not output.is_file() or output.stat().st_size <= 0:
                print(f"[Edge {index}/{len(edge_voices)}] {label}", flush=True)
                asyncio.run(tts_segment_with_retry(sentence, voice, str(output), video_id=None))

    for voice, _label, category in OMNIVOICE_TTS_VOICES:
        output = SAMPLE_ROOT / "omnivoice" / safe_voice_id(voice) / "vi.mp3"
        if output.is_file() and output.stat().st_size > 0:
            generated.append(
                {
                    "provider": "omnivoice",
                    "voice": voice,
                    "language": "vi",
                    "category": category,
                    "path": output.relative_to(SAMPLE_ROOT).as_posix(),
                }
            )
    for voice, _label in EDGE_TTS_VOICES_BY_LANGUAGE["vi"]:
        output = SAMPLE_ROOT / "edge" / safe_voice_id(voice) / "vi.mp3"
        if output.is_file() and output.stat().st_size > 0:
            generated.append(
                {
                    "provider": "edge",
                    "voice": voice,
                    "language": "vi",
                    "category": "language",
                    "path": output.relative_to(SAMPLE_ROOT).as_posix(),
                }
            )

    manifest["samples"] = generated
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
