"""Installer initialization for verified versioned payloads; no data migration."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from .filesystem import UpdateError, atomic_json, child, file_lock, no_links, remove_owned, sha256, version, version_tuple
from .state import Layout


def check_install(root: Path, target: str) -> None:
    """Mandatory pre-copy gate: prevent replacing a running/newer installation."""
    version(target)
    layout = Layout(root)
    with file_lock(child(layout.state, "launcher.lock")), file_lock(child(layout.state, "updater.lock")), layout.lock():
        if not layout.active_path.exists():
            return
        pointer = layout.active()
        if version_tuple(pointer["active"]) > version_tuple(target):
            raise UpdateError("Bản cài đang dùng mới hơn bộ cài này. Không hạ phiên bản.")
        journal = layout.journal()
        if journal and journal["state"] not in {"confirmed", "rolled_back", "failed"}:
            raise UpdateError("Còn cập nhật đang chờ xử lý; hoàn tất hoặc phục hồi trước khi cài.")


def initialize(root: Path, target: str) -> None:
    version(target)
    layout = Layout(root)
    layout.validate_core(target)
    # The launcher owns this lock until its Core exits. An installer must not
    # change the pointer while that Core can still write project data.
    with file_lock(child(layout.state, "launcher.lock")), file_lock(child(layout.state, "updater.lock")):
        if not layout.active_path.exists():
            layout.seed(target)
            return
        with layout.lock():
            layout.recover()
            pointer = layout.active()
            layout.validate_core(pointer["active"])
            if pointer["active"] == target:
                return
            if version_tuple(pointer["active"]) > version_tuple(target):
                raise UpdateError("Bản cài đang dùng mới hơn bộ cài này. Không hạ phiên bản.")
            existing = layout.journal()
            if existing and existing["state"] not in {"confirmed", "rolled_back", "failed"}:
                raise UpdateError("Còn cập nhật đang chờ xử lý; hoàn tất hoặc phục hồi trước khi cài.")
            atomic_json(layout.journal_path, dict(schema=1, id=uuid.uuid4().hex, state="ready",
                base=pointer["active"], target=target, attempts=0, error="", prior_pointer=pointer,
                manifest_sha256=sha256(layout.core(target) / "core-manifest.json")))
            layout.activate(core_exited=True)


def uninstall_cores(root: Path) -> None:
    """Remove only verified immutable Core trees; never touch runtime data."""
    layout = Layout(root)
    with file_lock(child(layout.state, "launcher.lock")), file_lock(child(layout.state, "updater.lock")), layout.lock():
        directories = list(layout.versions.iterdir()) if layout.versions.exists() else []
        for directory in directories:
            layout.validate_core(version(directory.name))
        # Validate every cleanup target before deleting the first Core.
        for name in ("staging", "downloads", "ipc"):
            target = child(layout.state, name)
            for parent, folders, files in os.walk(target, followlinks=False):
                for item in folders + files:
                    no_links(Path(parent) / item)
        for name in ("active-version.json", "transaction.json", "last-confirmed.json"):
            child(layout.state, name)
        for directory in directories:
            remove_owned(layout.versions, directory)
        for name in ("staging", "downloads", "ipc"):
            remove_owned(layout.state, child(layout.state, name))
        for name in ("active-version.json", "transaction.json", "last-confirmed.json"):
            child(layout.state, name).unlink(missing_ok=True)


def report_error(message: str, *, show_dialog: bool = True) -> None:
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    if show_dialog and os.name == "nt" and getattr(sys, "frozen", False):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "HaizFlow", 0x10)
