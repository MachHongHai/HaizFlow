"""Durable, input-bound translations; never published as final subtitles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from haizflow.utils.atomic_file import atomic_json


def manual_progress_path(video_id: str) -> Path:
    from haizflow.services.video_store import get_video_dir

    return Path(get_video_dir(video_id)) / "temp" / "translation-progress.json"


def clear_manual_progress(video_id: str) -> None:
    manual_progress_path(video_id).unlink(missing_ok=True)


class TranslationProgress:
    def __init__(self, path: str | Path, inputs: dict, count: int):
        self.path = Path(path)
        self.signature = hashlib.sha256(json.dumps(
            inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        self.values: list[str | None] = [None] * count
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            values = stored.get("translations")
            if (stored.get("schema") == 1 and stored.get("signature") == self.signature
                    and isinstance(values, list) and len(values) == count
                    and all(value is None or isinstance(value, str) and value.strip() for value in values)):
                self.values = values
        except (OSError, ValueError, AttributeError, UnicodeDecodeError):
            pass

    def save_batch(self, indices: list[int], values: list[str]) -> None:
        if len(indices) != len(values) or any(
            type(index) is not int or not 0 <= index < len(self.values)
            or not isinstance(value, str) or not value.strip()
            for index, value in zip(indices, values)
        ):
            raise ValueError("Invalid partial translation batch.")
        pending = list(self.values)
        for index, value in zip(indices, values):
            pending[index] = value
        # Preserve escaped storage for raw model text (including malformed
        # Unicode). Manual validation must be able to warn/edit, not crash
        # while saving the unfinished translation checkpoint.
        atomic_json(self.path, {"schema": 1, "signature": self.signature, "translations": pending}, ensure_ascii=True)
        # Memory and disk agree even if an access/space error prevents publish.
        self.values = pending

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
