"""Bounded background probes for media metadata used by the desktop UI."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from haizflow.utils.ffmpeg import get_video_dimensions


class VideoDimensionProbe:
    """Run at most a few ffprobe calls away from the Qt GUI thread."""

    def __init__(self, on_ready: Callable[[str, int, int], None], *, workers: int = 2):
        self._on_ready = on_ready
        self._executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="haizflow-ffprobe")
        self._pending: set[str] = set()
        self._failures: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _signature(path: str) -> str:
        try:
            stat = os.stat(path)
            return f"{os.path.abspath(path)}:{stat.st_mtime_ns}:{stat.st_size}"
        except OSError:
            return f"{os.path.abspath(path)}:missing"

    def request(self, video_id: str, path: str) -> None:
        if not path:
            return
        signature = self._signature(path)
        with self._lock:
            if video_id in self._pending:
                return
            failure = self._failures.get(video_id)
            if failure and failure[0] == signature and time.monotonic() < failure[1]:
                return
            self._pending.add(video_id)
        self._executor.submit(self._probe, video_id, path, signature)

    def _probe(self, video_id: str, path: str, signature: str) -> None:
        try:
            width, height = get_video_dimensions(path, timeout_seconds=15)
        except RuntimeError:
            with self._lock:
                self._failures[video_id] = (signature, time.monotonic() + 60.0)
        else:
            self._on_ready(video_id, width, height)
            with self._lock:
                self._failures.pop(video_id, None)
        finally:
            with self._lock:
                self._pending.discard(video_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
