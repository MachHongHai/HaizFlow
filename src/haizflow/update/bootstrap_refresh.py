"""Upgrade legacy launchers after graceful shutdown, without changing Core/data pointers.

Each new executable uses a version-named PyInstaller runtime. Old executables and
their _internal directories remain usable until the atomic executable swap.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from .filesystem import UpdateError, atomic_json, child, file_lock, no_links, read_json, relative_path, sha256
from .manifest import inventory
from .state import Layout

ENTRIES = (("HaizFlow", "HaizFlow.exe", ""), ("HaizFlowUpdater", "HaizFlowUpdater.exe", "updater"))


def verify_payload(core: Path, value: str, commit: str) -> list[tuple[Path, str, str, dict]]:
    """Every payload byte must belong to the same clean source as its containing Core."""
    payload = child(core, "bootstrap-update")
    runtime = "_bootstrap-" + value
    result = []
    for directory, executable, destination in ENTRIES:
        source = child(payload, directory)
        metadata = read_json(child(source, "BOOTSTRAP-INFO.json"))
        if any(
            metadata.get(key) != expected
            for key, expected in {
                "schema": 1,
                "application": "HaizFlow",
                "entrypoint": executable,
                "version": value,
                "git_commit": commit,
                "git_dirty": False,
                "engineering": False,
                "contents_directory": runtime,
                "packaging": "PyInstaller onedir",
            }.items()
        ):
            raise UpdateError("Launcher mới không khớp nguồn Core đã xác minh.")
        if not child(source, runtime).is_dir() or not child(source, executable).is_file():
            raise UpdateError("Gói launcher mới chưa đầy đủ.")
        expected = {}
        for line in child(source, "SHA256SUMS.txt").read_text("utf-8").splitlines():
            digest, separator, name = line.partition(" *")
            if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise UpdateError("Checksum launcher không hợp lệ.")
            name = relative_path(name)
            if name in expected or name.split("/", 1)[0] not in {runtime, executable, "BOOTSTRAP-INFO.json"}:
                raise UpdateError("Đường dẫn launcher không hợp lệ.")
            expected[name] = digest
        actual = {row["path"]: row["sha256"] for row in inventory(source) if row["path"] != "SHA256SUMS.txt"}
        if not expected or expected != actual:
            raise UpdateError("Tệp launcher mới thiếu, thừa hoặc sai checksum.")
        result.append((source, executable, destination, metadata))
    return result


def install(layout: Layout, core: Path) -> bool:
    """Caller owns launcher/updater/update locks. No runtime/project/model files are modified."""
    value = core.name
    if core.absolute() != layout.core(value):
        raise UpdateError("Nguồn launcher phải nằm trong Core của bản cài hiện tại.")
    pointer = layout.active()
    if pointer["active"] != value or value not in pointer["known_good"]:
        return False  # Never install an older, failed, or merely staged bootstrap.
    manifest = layout.validate_core(value)
    info = read_json(child(core, "BUILD-INFO.json"))
    if info.get("application") != "HaizFlow" or info.get("version") != value:
        raise UpdateError("Không xác minh được Core chứa launcher mới.")
    records = verify_payload(core, value, info["git_commit"])
    runtime = "_bootstrap-" + value
    targets = [
        (source, executable, child(layout.root, destination) if destination else layout.root, metadata)
        for source, executable, destination, metadata in records
    ]
    executable_hashes = {executable: sha256(child(source, executable)) for source, executable, _, _ in targets}
    if all(
        child(target, executable).is_file() and sha256(child(target, executable)) == sha256(child(source, executable))
        for source, executable, target, _ in targets
    ):
        atomic_json(
            child(layout.state, "bootstrap-version.json"),
            {
                "schema": 1,
                "version": value,
                "git_commit": info["git_commit"],
                "executables": executable_hashes,
                "state": "installed",
            },
        )
        return False
    # Core verification also proves payload membership, not just a replaceable
    # adjacent checksum file. Reject manifests excluding any bootstrap file.
    listed = {entry["path"] for entry in manifest.data["target_files"]}
    for path in child(core, "bootstrap-update").rglob("*"):
        if path.is_file() and path.relative_to(core).as_posix() not in listed:
            raise UpdateError("Launcher không thuộc manifest Core đã xác minh.")
    backup_parent = child(layout.state, "bootstrap-backups")
    backup_parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=value + "-", dir=backup_parent))
    replaced = []
    try:
        for source, executable, target, _ in targets:
            target.mkdir(parents=True, exist_ok=True)
            source_runtime, target_runtime = child(source, runtime), child(target, runtime)
            if target_runtime.exists():
                if inventory(target_runtime) != inventory(source_runtime):
                    raise UpdateError("Runtime launcher đã tồn tại nhưng không khớp; giữ nguyên bản cũ.")
            else:
                staged = backup / (executable + ".runtime")
                shutil.copytree(source_runtime, staged)
                if inventory(staged) != inventory(source_runtime):
                    raise UpdateError("Không sao chép đầy đủ runtime launcher mới.")
                os.replace(staged, target_runtime)
            executable_path = child(target, executable)
            if not executable_path.is_file():
                raise UpdateError("Thiếu launcher gốc; không tự sửa bản cài không hợp lệ.")
            shutil.copy2(executable_path, backup / executable)
            staged_executable = backup / (executable + ".new")
            shutil.copy2(child(source, executable), staged_executable)
            if sha256(staged_executable) != sha256(child(source, executable)):
                raise UpdateError("Sao chép launcher mới không khớp checksum.")
            os.replace(staged_executable, executable_path)
            replaced.append((executable_path, backup / executable))
        atomic_json(
            child(layout.state, "bootstrap-version.json"),
            {
                "schema": 1,
                "version": value,
                "git_commit": info["git_commit"],
                "backup": backup.name,
                "state": "installed",
                "executables": executable_hashes,
            },
        )
        return True
    except BaseException:
        for target, original in reversed(replaced):
            os.replace(original, target)
        raise


def run(core: Path, *, timeout: float = 90) -> bool:
    no_links(core)
    if core.parent.name != "versions":
        raise UpdateError("Chỉ cập nhật launcher của bản cài versioned.")
    layout = Layout(core.parent.parent)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with ExitStack() as locks:
            try:
                for name in ("updater.lock", "launcher.lock", "update.lock"):
                    locks.enter_context(file_lock(child(layout.state, name)))
            except UpdateError:
                pass
            else:
                return install(layout, core)
        time.sleep(0.1)
    raise UpdateError("Launcher cũ chưa đóng; sẽ thử lại ở lần thoát ứng dụng tiếp theo.")


def schedule() -> bool:
    """Called only after a healthy desktop shuts down; never interrupt active user work."""
    if not getattr(sys, "frozen", False):
        return False
    core = Path(sys.executable).absolute().parent
    if core.parent.name != "versions" or not (core / "bootstrap-update").is_dir():
        return False
    layout = Layout(core.parent.parent)
    state_path = child(layout.state, "bootstrap-version.json")
    if state_path.is_file():
        state = read_json(state_path)
        if state.get("version") == core.name and state.get("state") == "installed":
            hashes = state.get("executables", {})
            if all(
                hashes.get(executable) == sha256(child(layout.root / destination, executable))
                for _, executable, destination in ENTRIES
            ):
                return False
    subprocess.Popen(
        [sys.executable, "--refresh-bootstrap"],
        cwd=core,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return True


def worker_main() -> int:
    if not getattr(sys, "frozen", False):
        return 1
    core = Path(sys.executable).absolute().parent
    try:
        run(core)
    except (OSError, ValueError) as exc:
        try:
            layout = Layout(core.parent.parent)
            atomic_json(child(layout.state, "bootstrap-refresh-error.json"), {"error": str(exc), "version": core.name})
        except (OSError, ValueError):
            pass
        return 1
    return 0
