"""Small, offline-verified synthesis references, independent of UI previews.

Only scalar metadata is cached. No ASR, model load or media transcoding occurs
when a project chooses a reference. Missing/corrupt optional assets fail closed
so the caller can retain that exact preset's legacy reference.
"""
from __future__ import annotations

import hashlib
import json
import math
import wave
from functools import lru_cache
from pathlib import Path

REFERENCE_ROOT = Path(__file__).resolve().parents[1] / "desktop/assets/voice_samples/references/omnivoice"
REFERENCE_LANGUAGES = frozenset({"vi", "en", "zh", "ja", "ko", "es"})


@lru_cache(maxsize=4)
def _read_catalog(path: str, size: int, modified: int) -> dict:
    del size, modified  # Cache identity includes replacements during development/update.
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schema_version") == 1 and isinstance(data.get("references"), dict):
            return data["references"]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {}


@lru_cache(maxsize=256)
def _verified_wav(path: str, size: int, modified: int, digest: str) -> bool:
    del size, modified
    try:
        audio = Path(path)
        if hashlib.sha256(audio.read_bytes()).hexdigest() != digest:
            return False
        with wave.open(str(audio), "rb") as stream:
            return (stream.getnchannels() == 1 and stream.getframerate() == 24000
                    and stream.getsampwidth() == 2 and stream.getcomptype() == "NONE"
                    and 3.0 <= stream.getnframes() / 24000 <= 10.0)
    except (OSError, ValueError, EOFError, wave.Error):
        return False


def prepared_reference(voice: str, language: str, *, root: Path | None = None) -> tuple[str, str]:
    """Return only the requested voice/language, never another speaker's audio."""
    if language not in REFERENCE_LANGUAGES:
        return "", ""
    root = (root or REFERENCE_ROOT).resolve()
    manifest = root / "manifest.json"
    try:
        stat = manifest.stat()
        if stat.st_size > 512_000:
            return "", ""
        entry = _read_catalog(str(manifest), stat.st_size, stat.st_mtime_ns).get(f"{voice}/{language}")
        if not isinstance(entry, dict) or entry.get("voice") != voice or entry.get("language") != language:
            return "", ""
        transcript = entry.get("text")
        digest = entry.get("sha256")
        quality = entry.get("verification", {})
        error = float(quality.get("character_error_rate", 1))
        if (not isinstance(transcript, str) or not transcript.strip()
                or not isinstance(digest, str) or len(digest) != 64
                or not quality.get("waveform_valid") or not math.isfinite(error) or not 0 <= error <= .05):
            return "", ""
        audio = (root / str(entry["path"])).resolve()
        if not audio.is_relative_to(root) or audio.suffix != ".wav":
            return "", ""
        stat = audio.stat()
        if not 144_000 <= stat.st_size <= 481_024:
            return "", ""
        if _verified_wav(str(audio), stat.st_size, stat.st_mtime_ns, digest):
            return str(audio), transcript.strip()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return "", ""


def reference_identity(path: str, transcript: str) -> tuple:
    """Invalidate warm prompt caches when an asset or its transcript changes."""
    try:
        stat = Path(path).stat()
        return (path, stat.st_size, stat.st_mtime_ns, transcript)
    except OSError:
        return (path, None, None, transcript)
