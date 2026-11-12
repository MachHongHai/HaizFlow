"""Project-local editor navigation, separate from processing configuration."""

from __future__ import annotations

import json
import threading
import time
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


class EditorViewStateWriter:
    """Coalesce navigation writes off the GUI thread, preserving video ownership."""

    def __init__(self, delay=.25):
        self._delay = delay
        self._condition = threading.Condition()
        self._pending = {}
        self._latest = {}
        self._thread = None
        self._closed = False

    def load(self, video_id):
        with self._condition:
            if video_id in self._latest:
                return dict(self._latest[video_id])
        return load(video_id)

    def schedule(self, video_id, state):
        if not video_id:
            return False
        normalized = normalize(state)
        with self._condition:
            if self._closed:
                return False
            if self._latest.get(video_id) == normalized:
                return True
            self._latest[video_id] = normalized
            self._pending[video_id] = (time.monotonic() + self._delay, normalized)
            if len(self._latest) > 128:
                for key in list(self._latest):
                    if key not in self._pending and key != video_id:
                        self._latest.pop(key)
                        break
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True, name="editor-view-save")
                self._thread.start()
            self._condition.notify_all()
        return True

    def _run(self):
        while True:
            with self._condition:
                while not self._pending:
                    if self._closed:
                        return
                    self._condition.wait()
                video_id = min(self._pending, key=lambda key: self._pending[key][0])
                deadline, state = self._pending[video_id]
                remaining = deadline - time.monotonic()
                if not self._closed and remaining > 0:
                    self._condition.wait(remaining)
                    continue
                self._pending.pop(video_id)
            if not save(video_id, state):
                with self._condition:
                    if self._latest.get(video_id) == state and video_id not in self._pending:
                        self._latest.pop(video_id, None)

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()
