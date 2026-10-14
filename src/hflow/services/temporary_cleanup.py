"""Retry only explicitly abandoned, identity-checked app temporary paths."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path

from hflow.core.storage_ownership import owned_path, safe_tree

_LOG = logging.getLogger(__name__)


def _validate(path: Path, tree: bool) -> None:
    owned_path(path, path.parent)
    if tree:
        allowed = (path.parent.name in {"downloads", ".downloads", ".hflow-downloads"}
                   or path.name.startswith(".hflow-segment-")
                   or path.name.startswith(".processing-backup-") and (path.parent / "video.json").is_file()
                   or path.parent.name == "subtitles" and path.parent.parent.name == "input"
                   and len(path.name) == 32 and all(char in "0123456789abcdef" for char in path.name))
        if not allowed:
            raise ValueError("Not a download/export temporary directory.")
        safe_tree(path)
    elif not (path.name.startswith(".hflow-export-")
              or path.parent.name.startswith(".hflow-segment-") and path.name == "segment.progress"):
        raise ValueError("Not an export temporary file.")


def _identity(path: Path, tree: bool) -> list:
    info = path.stat()
    result = [info.st_dev, info.st_ino, getattr(info, "st_birthtime_ns", None)]
    if not tree:
        result.extend((info.st_size, info.st_mtime_ns))
    return result


class TemporaryCleanupManager:
    def __init__(self, journal: Path):
        self.journal = Path(journal)
        self._lock = threading.RLock()
        self._pending = {}
        self._wake = threading.Event()
        self._thread = None
        try:
            entries = json.loads(self.journal.read_text(encoding="utf-8"))
            for entry in entries:
                if (isinstance(entry, dict) and isinstance(entry.get("path"), str)
                        and isinstance(entry.get("tree"), bool) and isinstance(entry.get("identity"), list)):
                    self._pending[entry["path"]] = entry
        except (OSError, ValueError, TypeError):
            pass

    def _save(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        handle, staged = tempfile.mkstemp(prefix=".cleanup-", suffix=".tmp", dir=self.journal.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(list(self._pending.values()), stream, ensure_ascii=False)
            os.replace(staged, self.journal)
        finally:
            Path(staged).unlink(missing_ok=True)

    def _remove(self, entry):
        path = Path(entry["path"])
        try:
            _validate(path, entry["tree"])
            if _identity(path, entry["tree"]) != entry["identity"]:
                return True  # The path was replaced; it is no longer ours.
            if entry["tree"]:
                shutil.rmtree(path)
                if path.parent.name in {"downloads", ".downloads", ".hflow-downloads"}:
                    try:
                        path.parent.rmdir()  # Only an empty staging parent.
                    except OSError:
                        pass
            else:
                path.unlink()
            return True
        except FileNotFoundError:
            return True
        except (ValueError, RuntimeError):
            _LOG.warning("Temporary cleanup refused unsafe path: %s", path)
            return True
        except OSError:
            return False

    def discard(self, path, *, tree):
        target = Path(os.path.abspath(path))
        with self._lock:
            try:
                _validate(target, tree)
                entry = {"path": str(target), "tree": tree, "identity": _identity(target, tree)}
            except FileNotFoundError:
                return
            except (OSError, ValueError, RuntimeError):
                _LOG.warning("Temporary cleanup could not validate: %s", target)
                return
            if self._remove(entry):
                self._pending.pop(str(target), None)
            else:
                self._pending[str(target)] = entry
                _LOG.info("Temporary cleanup deferred until the file lock is released: %s", target)
            if self._pending or self.journal.exists():
                try:
                    self._save()
                except OSError:
                    _LOG.exception("Could not persist pending temporary cleanup")
        if self._pending:
            self.start()

    def retry(self):
        with self._lock:
            changed = False
            for key, entry in list(self._pending.items()):
                if self._remove(entry):
                    self._pending.pop(key, None)
                    changed = True
            if changed:
                try:
                    self._save()
                except OSError:
                    _LOG.exception("Could not update temporary cleanup journal")

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if not self._pending:
                return
            self._thread = threading.Thread(target=self._run, name="temporary-cleanup", daemon=True)
            self._thread.start()

    def _run(self):
        self._wake.wait(1)
        while True:
            self.retry()
            with self._lock:
                if not self._pending:
                    self._thread = None
                    return
            self._wake.wait(10)


_MANAGER = None
_MANAGER_LOCK = threading.Lock()


def _manager():
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            from hflow.config import APP_DATA_DIR

            _MANAGER = TemporaryCleanupManager(Path(APP_DATA_DIR) / "pending-temporary-cleanup.json")
        return _MANAGER


def discard_tree(path):
    _manager().discard(path, tree=True)


def discard_file(path):
    _manager().discard(path, tree=False)


def resume_pending_cleanup():
    """No scan: only exact abandoned paths recorded by earlier operations."""
    _manager().start()
