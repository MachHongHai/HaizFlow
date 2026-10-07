"""Project-local editor navigation, separate from processing configuration."""

from __future__ import annotations

import json
from pathlib import Path

from haizflow.services import video_store
from haizflow.utils.atomic_file import atomic_json


def normalize(value: dict) -> dict:
    try:
        stage = int(value.get("stage", 0))
    except (TypeError, ValueError, OverflowError):
        stage = 0
    return {
        "stage": stage if 0 <= stage <= 7 else 0,
        "rightActive": "properties" if value.get("rightActive") == "properties" else "tasks",
        "monitor": "source" if value.get("monitor") == "source" else "result",
    }


def load(video_id: str) -> dict:
    try:
        if not video_id or not video_store.get_video(video_id):
            return {}
        value = json.loads((Path(video_store.get_video_dir(video_id)) / "editor/view.json").read_text(encoding="utf-8"))
        return normalize(value) if isinstance(value, dict) else {}
    except (OSError, ValueError, RuntimeError):
        return {}


def save(video_id: str, state: dict) -> bool:
    normalized = normalize(state)
    try:
        if not video_id or not video_store.get_video(video_id):
            return False
        if normalized != load(video_id):
            path = Path(video_store.get_video_dir(video_id)) / "editor/view.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(path, normalized)
        return True
    except (OSError, ValueError, RuntimeError):
        return False
