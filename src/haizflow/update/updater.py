"""Independent preparation process with controlled file IPC and graceful activation."""
from __future__ import annotations

import os
import secrets
import subprocess
import time
from pathlib import Path

from .filesystem import UpdateError, atomic_json, child, file_lock, read_json, version
from .network import GitHubClient
from .state import Layout


def prepare_latest(layout: Layout, target: str, *, client=None, progress=lambda *_: None):
    """Missing/inefficient/invalid-base delta falls back only to verified full."""
    version(target)
    client = client or GitHubClient()
    release = client.latest()
    if release["tag_name"] != "v" + target:
        raise UpdateError("Bản phát hành đã thay đổi; kiểm tra cập nhật lại.")
    active = layout.active()["active"]
    prefix = f"HaizFlow-Core-{target}-windows-x64-"
    names = {a.get("name") for a in release["assets"] if isinstance(a, dict)}
    full_name = prefix + "full.manifest.json"
    delta_name = prefix + f"from-{active}.manifest.json"
    full = client.fetch_manifest(release, full_name, layout.downloads)
    manifest = full
    if delta_name in names:
        delta = client.fetch_manifest(release, delta_name, layout.downloads)
        if delta.data["base_version"] != active:
            raise UpdateError("Delta manifest có base không hợp lệ.")
        if delta.data["package_name"] in names and delta.data["package_size"] < full.data["package_size"] * 0.85:
            try:
                delta.verify_tree(layout.core(active), base=True)
            except (OSError, ValueError):
                pass  # Trusted full package, never relax checks on delta.
            else:
                manifest = delta
    asset = client.asset(release, manifest.data["package_name"])
    if asset["sha256"] != manifest.data["package_sha256"] or asset["size"] != manifest.data["package_size"]:
        raise UpdateError("Package metadata khác manifest.")
    package = client.download(asset, layout.downloads, progress=progress)
    return layout.prepare(package, manifest, progress=progress)


def process_alive(pid: int) -> bool:
    if type(pid) is not int or pid <= 0:
        raise UpdateError("Core PID không hợp lệ.")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE only
        if not handle:
            if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: exited
                return False
            raise UpdateError("Không thể kiểm tra Core đã đóng; chưa kích hoạt cập nhật.")
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def create_request(layout: Layout, target: str) -> str:
    token = secrets.token_hex(32)
    atomic_json(child(layout.ipc, token + ".update.json"), {"product": "HaizFlow", "schema": 1,
                "target": version(target), "pid": os.getpid(), "token": token})
    return token


def run_request(root: Path, token: str, *, client=None, activation_timeout: float = 3600,
                alive=process_alive, launch_process=subprocess.Popen) -> None:
    import re
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise UpdateError("Update IPC token không hợp lệ.")
    layout = Layout(root)
    request = read_json(child(layout.ipc, token + ".update.json"))
    if (set(request) != {"product", "schema", "target", "pid", "token"} or request["token"] != token
            or request["product"] != "HaizFlow" or request["schema"] != 1
            or type(request["pid"]) is not int or request["pid"] <= 0):
        raise UpdateError("Yêu cầu cập nhật không hợp lệ.")
    status_path = child(layout.ipc, token + ".status.json")
    permission_path = child(layout.ipc, token + ".activate.json")
    def report(state, progress, error=""):
        atomic_json(status_path, {"state": state, "progress": progress, "error": error, "token": token})
    # Serialize DOWNLOADS too, not merely pointer swaps.
    with file_lock(child(layout.state, "updater.lock")):
        try:
            with layout.lock():
                layout.recover()
                journal = layout.journal()
            if not (journal and journal["state"] == "ready" and journal["target"] == request["target"]):
                prepare_latest(layout, request["target"], client=client, progress=report)
            report("ready", 90)
            deadline = time.monotonic() + activation_timeout
            while time.monotonic() < deadline:
                if permission_path.exists():
                    if read_json(permission_path) != {"token": token, "activate": True}:
                        raise UpdateError("Yêu cầu khởi động lại không hợp lệ.")
                    # Never terminate old Core, even if it refuses to close.
                    if not alive(request["pid"]):
                        break
                time.sleep(0.2)
            else:
                report("ready", 90, "Bản cập nhật đã sẵn sàng. Có thể kích hoạt ở lần mở ứng dụng tiếp theo.")
                return
            with layout.lock():
                layout.activate(core_exited=True)
            report("restarting", 95)
            launcher = child(layout.root, "HaizFlow.exe")
            if not launcher.is_file():
                with layout.lock():
                    layout.rollback(layout.journal(), "Thiếu launcher đã đóng gói.")
                raise UpdateError("Thiếu launcher đã đóng gói; không thể khởi động Core mới.")
            # The old launcher owns this lock until it has reaped old Core.
            # Do not race its final few milliseconds of graceful shutdown.
            deadline = time.monotonic() + 15
            while True:
                try:
                    with file_lock(child(layout.state, "launcher.lock")):
                        pass
                    break
                except UpdateError:
                    if time.monotonic() >= deadline:
                        raise UpdateError("Launcher cũ chưa đóng. Bản mới sẽ được kiểm tra ở lần mở tiếp theo.")
                    time.sleep(0.1)
            launch_process([str(launcher)], cwd=layout.root, shell=False)
        except Exception as exc:
            report("failed", 0, str(exc))
            # Activation failures recover old pointer; pending_health is left
            # for the independent launcher to verify/rollback, not guessed here.
            with layout.lock():
                layout.recover()
            raise
