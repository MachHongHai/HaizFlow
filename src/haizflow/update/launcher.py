"""Independent stdlib launcher and bounded startup health/rollback protocol."""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from .filesystem import UpdateError, atomic_json, child, file_lock, read_json
from .state import Layout, validate_pointer


class CoreStillRunningError(UpdateError):
    """Startup could not stop safely; leave activation unchanged."""


def acknowledge_ready() -> bool:
    """Called only after Python, PySide and the QML main window are ready."""
    root_text = os.getenv("HAIZFLOW_BOOTSTRAP_ROOT")
    token = os.getenv("HAIZFLOW_HEALTH_TOKEN")
    attempt = os.getenv("HAIZFLOW_HEALTH_ATTEMPT")
    if not root_text or not token or not attempt:
        return False
    import re
    if not re.fullmatch(r"[a-f0-9]{32}", attempt) or not re.fullmatch(r"[a-f0-9]{64}", token):
        raise UpdateError("Health handshake không hợp lệ.")
    layout = Layout(Path(root_text))
    request = read_json(child(layout.ipc, attempt + ".request.json"))
    core_root = Path(sys.executable).absolute().parent
    if (request.get("token") != token or request.get("version") != core_root.name
            or layout.core(core_root.name) != core_root):
        raise UpdateError("Core không khớp yêu cầu health của launcher.")
    atomic_json(child(layout.ipc, attempt + ".ack.json"), {"token": token,
                "version": core_root.name, "pid": os.getpid(), "ready": True})
    os.environ.pop("HAIZFLOW_STARTUP_HEALTH_PENDING", None)
    return True


def start_core(layout: Layout, value: str, *, timeout: float = 90, popen=subprocess.Popen,
               command_for=None, clock=time.monotonic, sleep=time.sleep):
    layout.validate_core(value)
    attempt = secrets.token_hex(16)
    token = secrets.token_hex(32)
    request_path = child(layout.ipc, attempt + ".request.json")
    ack_path = child(layout.ipc, attempt + ".ack.json")
    atomic_json(request_path, {"version": value, "token": token})
    environment = os.environ.copy()
    # Do not propagate arbitrary versioned runtime overrides. Source fixtures
    # may pass their own env to command_for; frozen paths derive the root.
    for key in ("HAIZFLOW_HOME", "APP_DATA_DIR", "RUNTIME_DATA_DIR", "HAIZFLOW_INSTALL_ROOT",
                "HAIZFLOW_RESOURCE_ROOT", "HAIZFLOW_SMOKE_TEST"):
        environment.pop(key, None)
    environment.update({"HAIZFLOW_BOOTSTRAP_ROOT": str(layout.root), "HAIZFLOW_HEALTH_TOKEN": token,
                        "HAIZFLOW_HEALTH_ATTEMPT": attempt, "HAIZFLOW_STARTUP_HEALTH_PENDING": "1"})
    command = command_for(layout.core(value)) if command_for else [str(layout.core(value) / "HaizFlowCore.exe")]
    process = None
    try:
        process = popen(command, cwd=layout.core(value), env=environment, shell=False)
        deadline = clock() + timeout
        while clock() < deadline:
            if ack_path.exists():
                ack = read_json(ack_path)
                if ack == {"token": token, "version": value, "pid": process.pid, "ready": True}:
                    # A graceful quit AFTER ack is still a successful startup.
                    return process
                raise UpdateError("Core gửi health acknowledgment không hợp lệ.")
            code = process.poll()
            if code is not None:
                raise UpdateError(f"Core thoát trước khi giao diện sẵn sàng (mã {code}).")
            sleep(0.1)
        raise UpdateError("Core chưa xác nhận giao diện sẵn sàng trong thời gian chờ.")
    except Exception:
        # Only the newly started, UNCONFIRMED Core can be terminated. It has
        # not been permitted to start user jobs; never kill an established Core.
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=10)
            except (OSError, subprocess.SubprocessError) as exc:
                raise CoreStillRunningError("Core khởi động chưa đóng; không rollback khi tiến trình vẫn chạy.") from exc
        raise
    finally:
        request_path.unlink(missing_ok=True)
        ack_path.unlink(missing_ok=True)


def launch(root: Path, *, timeout: float = 90, popen=subprocess.Popen, command_for=None,
           wait_for_exit: bool = True, on_ready=None, on_starting=None):
    layout = Layout(root)
    # Keep this lock for the full Core lifetime in the real launcher.
    with file_lock(child(layout.state, "launcher.lock")):
        with layout.lock():
            layout.recover(launcher=True)
            try:
                pointer = layout.active()
            except (OSError, ValueError) as exc:
                # Durable CONFIRMED snapshot only, never directory enumeration.
                snapshot = validate_pointer(read_json(child(layout.state, "last-confirmed.json")))
                if snapshot.get("schema") != 1 or snapshot.get("active") not in snapshot.get("known_good", []):
                    raise UpdateError("Không có pointer đã xác nhận để phục hồi.") from exc
                layout.validate_core(snapshot["active"])
                atomic_json(layout.active_path, snapshot)
                pointer = layout.active()
            journal = layout.journal()
            pending = journal if journal and journal["state"] == "pending_health" else None
            try:
                layout.validate_core(pointer["active"])
            except (OSError, ValueError) as exc:
                if pending:
                    layout.rollback(pending, "Core mới không còn hợp lệ: " + str(exc))
                    pointer = layout.active()
                    pending = None
                    fallback = pointer["active"]
                else:
                    fallback = pointer.get("previous")
                if not fallback or fallback not in pointer["known_good"]:
                    raise UpdateError("Không có Core hợp lệ để mở. Cần sửa bản cài; dữ liệu runtime vẫn được giữ.") from exc
                layout.validate_core(fallback)
                pointer = {"schema": 1, "active": fallback, "previous": None, "known_good": [fallback]}
                atomic_json(layout.active_path, pointer)
                pending = None
            if pending:
                pending = layout.transition(pending, "pending_health", attempts=1)
        try:
            if on_starting is not None:
                on_starting()
            process = start_core(layout, pointer["active"], timeout=timeout, popen=popen, command_for=command_for)
        except CoreStillRunningError:
            raise
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            if not pending:
                raise UpdateError("Không thể khởi động Core đã chọn: " + str(exc)) from exc
            with layout.lock():
                layout.rollback(pending, str(exc))
            # Exactly one fallback, never recursive restart/rollback loops.
            process = start_core(layout, pending["base"], timeout=timeout, popen=popen, command_for=command_for)
        else:
            if pending:
                with layout.lock():
                    layout.confirm(pending)
        if on_ready is not None:
            on_ready()
        if wait_for_exit:
            # Normal exit or crash AFTER confirmation never rolls back.
            return process.wait()
        return process
