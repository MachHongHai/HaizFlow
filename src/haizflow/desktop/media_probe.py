"""Bounded background probes for media metadata used by the desktop UI."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Callable

from haizflow.utils.ffmpeg import get_video_dimensions

LOGGER = logging.getLogger(__name__)


class VideoDimensionProbe:
    """Run at most a few ffprobe calls away from the Qt GUI thread."""

    def __init__(self, on_ready: Callable[[str, int, int], None], *, workers: int = 2):
        self._on_ready = on_ready
        self._tasks: queue.Queue[tuple[str, str, str] | None] = queue.Queue()
        self._shutdown = threading.Event()
        self._pending: set[str] = set()
        self._failures: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()
        self._workers = [
            threading.Thread(
                target=self._worker,
                name=f"haizflow-ffprobe-{index + 1}",
                daemon=True,
            )
            for index in range(max(1, workers))
        ]
        for worker in self._workers:
            worker.start()

    @staticmethod
    def _signature(path: str) -> str:
        try:
            stat = os.stat(path)
            return f"{os.path.abspath(path)}:{stat.st_mtime_ns}:{stat.st_size}"
        except OSError:
            return f"{os.path.abspath(path)}:missing"

    def request(self, video_id: str, path: str) -> None:
        if not path or self._shutdown.is_set():
            return
        signature = self._signature(path)
        with self._lock:
            if video_id in self._pending:
                return
            failure = self._failures.get(video_id)
            if failure and failure[0] == signature and time.monotonic() < failure[1]:
                return
            self._pending.add(video_id)
        self._tasks.put((video_id, path, signature))

    def _worker(self) -> None:
        while True:
            task = self._tasks.get()
            try:
                if task is None:
                    return
                video_id, path, signature = task
                if self._shutdown.is_set():
                    with self._lock:
                        self._pending.discard(video_id)
                    continue
                try:
                    self._probe(video_id, path, signature)
                except Exception:
                    LOGGER.exception("Video dimension probe callback failed for %s", video_id)
            finally:
                self._tasks.task_done()

    def _probe(self, video_id: str, path: str, signature: str) -> None:
        try:
            width, height = get_video_dimensions(path, timeout_seconds=15)
        except RuntimeError:
            with self._lock:
                self._failures[video_id] = (signature, time.monotonic() + 60.0)
        else:
            if not self._shutdown.is_set():
                self._on_ready(video_id, width, height)
            with self._lock:
                self._failures.pop(video_id, None)
        finally:
            with self._lock:
                self._pending.discard(video_id)

    def shutdown(self) -> None:
        if self._shutdown.is_set():
            return
        self._shutdown.set()
        while True:
            try:
                task = self._tasks.get_nowait()
            except queue.Empty:
                break
            if task is not None:
                with self._lock:
                    self._pending.discard(task[0])
            self._tasks.task_done()
        for _worker in self._workers:
            self._tasks.put(None)
