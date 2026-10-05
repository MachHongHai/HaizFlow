"""Publish complete files without truncating the previous Windows-readable copy."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path


def replace_with_retry(source: str | Path, destination: str | Path) -> None:
    """Allow short-lived reader/antivirus locks, not permanent write failures."""
    for attempt in range(8):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            transient = isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32, 33}
            if not transient or attempt == 7:
                raise
            time.sleep(min(0.02 * 2 ** attempt, 0.5))


def atomic_json(path: str | Path, data, *, indent: int | None = None) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.stem}-", suffix=".json.tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=indent)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(name, destination)
    finally:
        # Preserve the original error if Windows also locks the temporary file.
        try:
            Path(name).unlink(missing_ok=True)
        except OSError:
            pass
