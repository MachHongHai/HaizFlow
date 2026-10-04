"""Installer initialization for verified versioned payloads; no data migration."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from .filesystem import UpdateError, atomic_json, child, file_lock, sha256, version, version_tuple
from .state import Layout


def initialize(root: Path, target: str) -> None:
    version(target)
    layout = Layout(root)
    layout.validate_core(target)
    # The launcher owns this lock until its Core exits. An installer must not
    # change the pointer while that Core can still write project data.
    with file_lock(child(layout.state, "launcher.lock")):
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


def report_error(message: str) -> None:
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    if os.name == "nt" and getattr(sys, "frozen", False):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "HaizFlow", 0x10)
