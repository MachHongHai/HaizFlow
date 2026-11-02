"""Coalesced read-only tool/cache presentation, never on Qt's event thread."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal, Slot


class ManualToolStateController(QObject):
    changed = Signal()
    _ready = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self._video = None
        self._context = None
        self._generation = 0
        self._pending = None
        self._busy = False
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="manual-tool-state")
        self._ready.connect(self._accept)

    def request(self, video, language, queued=False, revision=None):
        if self._closed:
            return
        context = (language, queued, revision)
        if self._video is video and self._context == context:
            return
        switched = getattr(self._video, "video_id", "") != getattr(video, "video_id", "")
        self._video, self._context = video, context
        self._generation += 1
        self._pending = None
        if switched and self.rows:
            self.rows = []
            self.changed.emit()
        if video is None or getattr(video, "project_type", "") != "manual":
            if self.rows:
                self.rows = []
                self.changed.emit()
            return
        # Treat store snapshots as read-only. Copy the phantom-running
        # correction instead of mutating the selected record.
        if video.status in {"pending", "processing"} and getattr(video, "manual_target_tool", "") and not queued:
            video = video.model_copy(update={"status": "manual_ready", "manual_target_tool": ""})
        self._pending = (self._generation, video, language)
        self._start()

    def _start(self):
        if self._closed or self._busy or self._pending is None:
            return
        generation, video, language = self._pending
        self._pending = None
        self._busy = True

        def work():
            from haizflow.pipeline.manual_tools import tool_states

            try:
                rows = tool_states(video, language=language)
            except (OSError, RuntimeError, ValueError):
                rows = []
            except Exception:
                logging.getLogger(__name__).exception("Cannot refresh Manual tool presentation")
                rows = []
            if not self._closed:
                try:
                    self._ready.emit(generation, rows)
                except RuntimeError:
                    pass  # The owning Qt window may already have been destroyed.

        self._executor.submit(work)

    @Slot(int, object)
    def _accept(self, generation, rows):
        if self._closed:
            return
        self._busy = False
        if generation == self._generation and rows != self.rows:
            self.rows = rows
            self.changed.emit()
        self._start()

    def close(self):
        self._closed = True
        self._pending = None
        self._executor.shutdown(wait=False, cancel_futures=True)
