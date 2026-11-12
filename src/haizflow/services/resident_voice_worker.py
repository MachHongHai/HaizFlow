"""Cancellable file requests in one bounded-lifetime, isolated voice process."""
from __future__ import annotations

import atexit
from collections import deque
import json
from pathlib import Path
import subprocess
import threading
import time

from haizflow.pipeline.process_registry import check_cancellation, register_process, unregister_process


def can_retain_model():
    from haizflow.core.memory import GIB, memory_snapshot

    snapshot = memory_snapshot()
    return (snapshot.available_bytes is not None and snapshot.available_bytes >= 2 * GIB
            and snapshot.commit_available_bytes is not None and snapshot.commit_available_bytes >= 3 * GIB)


class ResidentVoiceWorker:
    def __init__(self, name: str, idle_seconds: float = 300):
        self.name = name
        self.idle_seconds = idle_seconds
        self._operation = threading.Lock()
        self._state = threading.RLock()
        self._process = None
        self._key = None
        self._timer = None
        self._stderr = deque(maxlen=12)
        self._stderr_lock = threading.Lock()
        self._stderr_thread = None
        atexit.register(self.close)

    def _close_locked(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        process, self._process = self._process, None
        self._key = None
        if process is None:
            return
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        unregister_process(self.name, process, force=True)
        if process.stdin is not None:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=.5)
        self._stderr_thread = None

    def close(self, *, only_idle=False):
        # Do not wait behind inference: release/cancel must interrupt it.
        with self._state:
            if only_idle and self._operation.locked():
                return
            self._close_locked()

    def _drain(self, process):
        try:
            while chunk := process.stderr.read(1024):
                with self._stderr_lock:
                    self._stderr.append(chunk)
        except (OSError, ValueError):
            pass
        finally:
            process.stderr.close()

    def run(self, command, environment, key, request_path: Path, request: dict,
            video_id: str, accept_status, stall_seconds: float):
        response_path = request_path.with_name("response.json")
        response_path.unlink(missing_ok=True)
        request["response_path"] = str(response_path)
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        while not self._operation.acquire(timeout=.1):
            check_cancellation(video_id)
        process = None
        success = False
        try:
            check_cancellation(video_id)
            with self._state:
                if self._timer is not None:
                    self._timer.cancel()
                    self._timer = None
                if self._process is not None and (self._key != key or self._process.poll() is not None):
                    self._close_locked()
                if self._process is None:
                    with self._stderr_lock:
                        self._stderr.clear()
                    self._process = subprocess.Popen(command, env=environment, stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                        encoding="utf-8", errors="replace", bufsize=1,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    self._key = key
                    process = self._process
                    register_process(self.name, self._process)
                    self._stderr_thread = threading.Thread(target=self._drain, args=(self._process,),
                                                           daemon=True, name=self.name + "-stderr")
                    self._stderr_thread.start()
                process = self._process
                register_process(video_id, process)
                process.stdin.write(str(request_path) + "\n")
                process.stdin.flush()
            last_state, last_activity = None, time.monotonic()
            status_path = Path(request["status"])
            while True:
                check_cancellation(video_id)
                if response_path.is_file():
                    response = json.loads(response_path.read_text(encoding="utf-8"))
                    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else None
                    if status is not None:
                        accept_status(status)
                    check_cancellation(video_id)
                    success = int(response.get("return_code", 1)) == 0
                    return int(response.get("return_code", 1)), str(response.get("error") or "")
                if process.poll() is not None:
                    with self._stderr_lock:
                        detail = "".join(self._stderr)[-1800:]
                    raise RuntimeError(f"{self.name} worker stopped unexpectedly: " + detail)
                try:
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    status = None
                if isinstance(status, dict):
                    state = (status.get("completed"), status.get("stage"), status.get("quality_retries"))
                    if state != last_state:
                        last_state = state
                        accept_status(status)
                        last_activity = time.monotonic()
                if time.monotonic() - last_activity >= stall_seconds:
                    raise RuntimeError(f"VieNeu không có tiến triển trong {stall_seconds:g} giây.")
                time.sleep(.1)
        finally:
            try:
                if process is not None:
                    unregister_process(video_id, process)
                with self._state:
                    if process is not None and self._process is process:
                        if not success or process.poll() is not None or not can_retain_model():
                            self._close_locked()
                        else:
                            def expire():
                                with self._state:
                                    if self._timer is timer:
                                        self._close_locked()
                            timer = threading.Timer(self.idle_seconds, expire)
                            timer.daemon = True
                            self._timer = timer
                            timer.start()
            finally:
                self._operation.release()
