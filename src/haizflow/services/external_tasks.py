"""File-based bridge for long-running tasks hosted by optional engines."""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS, TMP_DIR
from haizflow.pipeline.process_registry import check_cancellation
from haizflow.services.external_engine import shared_external_engine_pool
from haizflow.services.resource_packs import installed_engine_command


def run_external_task(
    capability: str,
    command_name: str,
    payload: dict,
    video_id: str,
    *,
    context: dict | None = None,
    progress_callback=None,
) -> dict | None:
    """Run an installed engine command, or return ``None`` for a bundled runtime."""
    command = installed_engine_command(capability, command_name, context)
    if not command:
        return None
    root = Path(TMP_DIR)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="engine-task-", dir=root) as temp_dir:
        directory = Path(temp_dir)
        request_path = directory / "request.json"
        response_path = directory / "response.json"
        status_path = directory / "status.json"
        request = {
            "protocol_version": 1,
            "operation": command_name,
            "payload": dict(payload),
            "response_path": str(response_path),
            "status_path": str(status_path),
        }
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        pool = shared_external_engine_pool()
        failure: list[BaseException] = []

        def execute() -> None:
            try:
                if not pool.run_file_task(capability, context, str(request_path)):
                    raise RuntimeError(f"{command_name} engine is no longer installed.")
            except BaseException as exc:
                failure.append(exc)

        worker = threading.Thread(target=execute, name=f"{command_name}-engine-task", daemon=True)
        worker.start()
        revision = None
        deadline = time.monotonic() + MEDIA_PROCESS_TIMEOUT_SECONDS
        while worker.is_alive():
            try:
                check_cancellation(video_id)
            except Exception:
                pool.preempt(capability)
                worker.join(timeout=2)
                raise
            if time.monotonic() >= deadline:
                pool.preempt(capability)
                worker.join(timeout=2)
                raise RuntimeError(f"{command_name} engine task timed out.")
            try:
                stat = status_path.stat()
                current_revision = (stat.st_mtime_ns, stat.st_size)
                if current_revision != revision:
                    revision = current_revision
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    if progress_callback is not None:
                        progress_callback(status)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
            worker.join(timeout=0.15)
        if failure:
            raise RuntimeError(str(failure[0])) from failure[0]
        if status_path.is_file() and progress_callback is not None:
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
                progress_callback(status)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        try:
            response = json.loads(response_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{command_name} engine did not publish a valid response.") from exc
        if response.get("protocol_version") != 1 or not bool(response.get("ok")):
            raise RuntimeError(str(response.get("error") or f"{command_name} engine task failed."))
        result = response.get("result")
        return dict(result) if isinstance(result, dict) else {}


__all__ = ["run_external_task"]
