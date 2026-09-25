"""Versioned JSON-lines client for optional HaizFlow inference engines."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from haizflow.services.resource_packs import PACK_PROTOCOL_VERSION, ResourcePackManager


class ExternalEngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineResponse:
    result: dict
    status_events: tuple[dict, ...]


class ExternalEngineClient:
    """Own one persistent engine process and serialize protocol requests."""

    def __init__(self, manager: ResourcePackManager, pack_id: str):
        self._manager = manager
        self.pack_id = str(pack_id)
        self._request_lock = threading.Lock()
        self._process_lock = threading.RLock()
        self._output: queue.Queue[str] = queue.Queue()
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None

    def _start_locked(self) -> subprocess.Popen[str]:
        process = self._process
        if process is not None and process.poll() is None and process.stdin is not None:
            return process
        self._terminate_locked()
        # A terminated process may leave late protocol lines in its reader
        # queue. A new generation must never consume those stale messages.
        self._output = queue.Queue()
        command = self._manager.engine_command(self.pack_id, "rpc_command")
        if not command:
            raise ExternalEngineError(f"Engine {self.pack_id} does not expose a valid rpc_command.")
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            }
        )
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        engine_root = self._manager._engine_marker(self._manager.definitions[self.pack_id]).parent
        # Installed packs run from their immutable version directory.  During
        # source development the same protocol is hosted by the current
        # virtual environment and no installed-engine directory exists yet.
        # In that case use the interpreter directory instead of passing an
        # invalid cwd to Popen.
        working_directory = engine_root if engine_root.is_dir() else Path(command[0]).resolve().parent
        process = subprocess.Popen(
            command,
            cwd=str(working_directory),
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            startupinfo=startupinfo,
        )
        output = self._output

        def read_output() -> None:
            for line in process.stdout or ():
                output.put(line)

        self._reader = threading.Thread(
            target=read_output,
            name=f"{self.pack_id}-rpc-reader",
            daemon=True,
        )
        self._reader.start()
        self._process = process
        return process

    def _start(self) -> subprocess.Popen[str]:
        with self._process_lock:
            return self._start_locked()

    def request(self, operation: str, payload: dict | None = None, *, timeout_seconds: float = 300) -> EngineResponse:
        with self._request_lock:
            process = self._start()
            request_id = uuid.uuid4().hex
            message = {
                "protocol_version": PACK_PROTOCOL_VERSION,
                "request_id": request_id,
                "operation": str(operation),
                "payload": dict(payload or {}),
            }
            try:
                assert process.stdin is not None
                process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                self.terminate()
                raise ExternalEngineError(f"Could not send a request to {self.pack_id}.") from exc
            deadline = time.monotonic() + max(1.0, float(timeout_seconds))
            statuses: list[dict] = []
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    self.terminate()
                    raise ExternalEngineError(f"Engine {self.pack_id} stopped unexpectedly.")
                try:
                    line = self._output.get(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("request_id") != request_id:
                    continue
                if event.get("event") == "status":
                    statuses.append(event)
                    continue
                if event.get("event") != "response":
                    continue
                if event.get("protocol_version") != PACK_PROTOCOL_VERSION:
                    self.terminate()
                    raise ExternalEngineError("Engine protocol version changed during the request.")
                if not bool(event.get("ok")):
                    raise ExternalEngineError(str(event.get("error") or "Engine request failed."))
                result = event.get("result")
                return EngineResponse(dict(result) if isinstance(result, dict) else {}, tuple(statuses))
            self.terminate()
            raise ExternalEngineError(f"Engine {self.pack_id} did not respond before the timeout.")

    def _terminate_locked(self) -> None:
        process = self._process
        self._process = None
        reader = self._reader
        self._reader = None
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                pass
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if reader is not None and reader is not threading.current_thread() and reader.is_alive():
                reader.join(timeout=0.5)

    def terminate(self) -> None:
        """Preempt an in-flight speculative request without waiting for its lock."""
        with self._process_lock:
            self._terminate_locked()

    def close(self) -> None:
        with self._process_lock:
            self._terminate_locked()


class ExternalEnginePool:
    """Reuse installed engine processes across warm-up and inference boundaries."""

    def __init__(self, manager: ResourcePackManager):
        self._manager = manager
        self._lock = threading.RLock()
        self._clients: dict[str, ExternalEngineClient] = {}
        self._capability_packs: dict[str, str] = {}

    def engine_pack(self, capability: str, context: dict | None = None) -> str:
        resolver = getattr(self._manager, "warm_engine_pack", None)
        if callable(resolver):
            return resolver(capability, context)
        return self._manager.external_engine_pack(capability, context)

    def _client(self, pack_id: str) -> ExternalEngineClient:
        with self._lock:
            client = self._clients.get(pack_id)
            if client is None:
                client = ExternalEngineClient(self._manager, pack_id)
                self._clients[pack_id] = client
            return client

    def _bind_capability_pack(self, capability: str, pack_id: str) -> None:
        """Bind a capability to one engine and retire a superseded profile."""

        stale_client = None
        with self._lock:
            previous = self._capability_packs.get(capability, "")
            if previous and previous != pack_id:
                stale_client = self._clients.get(previous)
                for name, mapped_pack in tuple(self._capability_packs.items()):
                    if mapped_pack == previous:
                        self._capability_packs.pop(name, None)
            self._capability_packs[capability] = pack_id
        if stale_client is not None:
            stale_client.terminate()

    def warm(self, capability: str, context: dict | None = None) -> bool:
        pack_id = self.engine_pack(capability, context)
        if not pack_id:
            return False
        self._bind_capability_pack(str(capability), pack_id)
        try:
            self._client(pack_id).request(
                "warm",
                {"capability": str(capability), "context": dict(context or {})},
                timeout_seconds=600,
            )
        except Exception:
            with self._lock:
                self._capability_packs.pop(str(capability), None)
            raise
        return True

    def run_file_task(self, capability: str, context: dict | None, request_path: str) -> bool:
        """Run a task in the same process that owns the warmed model."""

        pack_id = self.engine_pack(capability, context)
        if not pack_id:
            return False
        self._bind_capability_pack(str(capability), pack_id)
        self._client(pack_id).request(
            "file_task",
            {"request_path": str(request_path)},
            timeout_seconds=24 * 60 * 60,
        )
        return True

    def preempt(self, capability: str) -> bool:
        with self._lock:
            pack_id = self._capability_packs.pop(str(capability), "")
            client = self._clients.get(pack_id) if pack_id else None
        if client is None:
            return False
        client.terminate()
        return True

    def release(self, capabilities: set[str]) -> set[str]:
        released: set[str] = set()
        for capability in sorted(capabilities):
            with self._lock:
                pack_id = self._capability_packs.pop(capability, "")
            if not pack_id:
                continue
            try:
                self._client(pack_id).request(
                    "release",
                    {"capability": capability},
                    timeout_seconds=15,
                )
            except ExternalEngineError:
                self._client(pack_id).close()
            released.add(capability)
        return released

    def close_pack(self, pack_id: str) -> None:
        """Stop one idle engine before its versioned files are removed."""

        with self._lock:
            client = self._clients.pop(str(pack_id), None)
            for capability, mapped_pack in tuple(self._capability_packs.items()):
                if mapped_pack == pack_id:
                    self._capability_packs.pop(capability, None)
        if client is not None:
            client.close()

    def close(self) -> None:
        with self._lock:
            clients = tuple(self._clients.values())
            self._clients.clear()
            self._capability_packs.clear()
        for client in clients:
            client.close()


_SHARED_POOL_LOCK = threading.Lock()
_SHARED_POOL: ExternalEnginePool | None = None


def shared_external_engine_pool(manager: ResourcePackManager | None = None) -> ExternalEnginePool:
    """Return the process pool shared by speculative warm-up and real tasks."""

    global _SHARED_POOL
    with _SHARED_POOL_LOCK:
        if _SHARED_POOL is None:
            _SHARED_POOL = ExternalEnginePool(manager or ResourcePackManager())
        return _SHARED_POOL


def close_shared_external_engine_pool() -> None:
    global _SHARED_POOL
    with _SHARED_POOL_LOCK:
        pool = _SHARED_POOL
        _SHARED_POOL = None
    if pool is not None:
        pool.close()


__all__ = [
    "EngineResponse",
    "ExternalEngineClient",
    "ExternalEngineError",
    "ExternalEnginePool",
    "close_shared_external_engine_pool",
    "shared_external_engine_pool",
]
