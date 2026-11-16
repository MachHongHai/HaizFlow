"""Generate packaged voice-library samples during development.

The desktop runtime only plays the resulting MP3 files; it never loads a TTS
model for a voice-row preview. Run this script explicitly when the catalog or
the locked sample sentence changes.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from haizflow.desktop.catalog import OMNIVOICE_TTS_VOICES
from haizflow.pipeline.omnivoice_tts import clear_runtime, synthesize_to_mp3

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / "src" / "haizflow" / "desktop" / "assets" / "voice_samples"
MANIFEST_PATH = SAMPLE_ROOT / "samples.json"


def safe_voice_id(voice: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", voice).strip("_")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--languages", default="vi,en,zh,ko,ja,es")
    parser.add_argument("--steps", type=int, choices=(32, 48, 64), default=48)
    parser.add_argument("--device", choices=("cpu", "gpu"), default="gpu")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--voices", default="")
    parser.add_argument("--reference-language", default="",
                        help="Use this same preset's existing sample as the authorised reference")
    args = parser.parse_args()
    from haizflow.core.hardware import configure_processing_device
    configure_processing_device(args.device)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    languages = [code.strip() for code in args.languages.split(",") if code.strip()]
    if any(code not in manifest["sentences"] for code in languages):
        parser.error("Every requested language needs a sentence in samples.json")
    if args.reference_language and args.reference_language not in manifest["sentences"]:
        parser.error("The reference language needs a sentence in samples.json")
    voices = list(OMNIVOICE_TTS_VOICES)
    if args.voices:
        requested = set(args.voices.split(","))
        if requested - {row[0] for row in voices}:
            parser.error("Unknown voice ID")
        voices = [row for row in voices if row[0] in requested]
    if args.limit > 0:
        voices = voices[: args.limit]

    generated: list[dict[str, str]] = []
    failures = []
    try:
        for language in languages:
            for index, (voice, label, _category) in enumerate(voices, 1):
                output = SAMPLE_ROOT / "omnivoice" / safe_voice_id(voice) / f"{language}.mp3"
                output.parent.mkdir(parents=True, exist_ok=True)
                if args.force or not output.is_file() or output.stat().st_size <= 0:
                    print(f"[{language} {index}/{len(voices)}] {label}", flush=True)
                    try:
                        reference = {}
                        if args.reference_language:
                            source = output.with_name(args.reference_language + ".mp3")
                            if source == output or not source.is_file() or source.stat().st_size <= 512:
                                raise RuntimeError("Missing exact-preset reference sample")
                            reference = dict(reference_path=str(source),
                                             reference_text=manifest["sentences"][args.reference_language])
                        synthesize_to_mp3(
                            str(manifest["sentences"][language]), voice, str(output), "voice-sample-assets",
                            language_id=language, keep_worker_warm=True, inference_steps=args.steps,
                            **reference,
                        )
                    except RuntimeError as exc:
                        if not args.keep_going:
                            raise
                        failures.append({"language": language, "voice": voice, "error": str(exc)})
                        print(f"FAILED: {language} {voice}: {type(exc).__name__}", flush=True)
    finally:
        clear_runtime()
        # Publish completed samples even if a later voice needs a retry.
        for language in manifest["sentences"]:
            for voice, _label, category in OMNIVOICE_TTS_VOICES:
                output = SAMPLE_ROOT / "omnivoice" / safe_voice_id(voice) / f"{language}.mp3"
                if output.is_file() and output.stat().st_size > 0:
                    generated.append({
                        "provider": "omnivoice", "voice": voice, "language": language,
                        "category": category, "path": output.relative_to(SAMPLE_ROOT).as_posix(),
                    })
        # Preserve other providers indexed while GPU generation was running.
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["samples"] = generated + [item for item in manifest["samples"] if item["provider"] != "omnivoice"]
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if failures:
        print(json.dumps({"failed_samples": failures}, ensure_ascii=True), flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
