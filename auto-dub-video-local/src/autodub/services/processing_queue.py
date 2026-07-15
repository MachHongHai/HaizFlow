"""A single-worker FIFO queue for resource-intensive video pipelines."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import threading


class SerialProcessingQueue:
    """Run one pipeline at a time while allowing the UI to keep accepting work."""

    def __init__(
        self,
        runner: Callable[[str], None],
        on_started: Callable[[str], None] | None = None,
        on_finished: Callable[[str], None] | None = None,
        on_idle: Callable[[], None] | None = None,
    ):
        self._runner = runner
        self._on_started = on_started
        self._on_finished = on_finished
        self._on_idle = on_idle
        self._pending: deque[str] = deque()
        self._active_job_id: str | None = None
        self._worker: threading.Thread | None = None
        self._lock = threading.RLock()

    @property
    def active_job_id(self) -> str | None:
        with self._lock:
            return self._active_job_id

    def pending_ids(self) -> list[str]:
        with self._lock:
            return list(self._pending)

    def contains(self, job_id: str) -> bool:
        with self._lock:
            return job_id == self._active_job_id or job_id in self._pending

    def enqueue(self, job_id: str) -> bool:
        """Add a job once. Returns False when it is already queued or active."""
        with self._lock:
            if job_id == self._active_job_id or job_id in self._pending:
                return False
            self._pending.append(job_id)
            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name="autodub-processing-queue", daemon=True)
                self._worker.start()
            return True

    def discard(self, job_id: str) -> bool:
        """Remove a waiting job. The active job must be cancelled by its pipeline manager."""
        with self._lock:
            try:
                self._pending.remove(job_id)
            except ValueError:
                return False
            return True

    def _run(self) -> None:
        while True:
            with self._lock:
                if not self._pending:
                    self._active_job_id = None
                    self._worker = None
                    break
                job_id = self._pending.popleft()
                self._active_job_id = job_id
            if self._on_started:
                self._on_started(job_id)
            try:
                self._runner(job_id)
            finally:
                if self._on_finished:
                    self._on_finished(job_id)
                with self._lock:
                    if self._active_job_id == job_id:
                        self._active_job_id = None
        if self._on_idle:
            self._on_idle()
