"""Windows-aware, scoped update filesystem operations."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path


class UpdateError(ValueError):
    """User-reportable failure which must leave the active Core intact."""


def version(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value):
        raise UpdateError("Phiên bản cập nhật không hợp lệ.")
    return value


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(map(int, version(value).split(".")))


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 220 or "\\" in value:
        raise UpdateError("Đường dẫn trong gói cập nhật không hợp lệ.")
    parts = value.split("/")
    for part in parts:
        if (part in {"", ".", ".."} or part.endswith((".", " "))
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I)):
            raise UpdateError("Đường dẫn trong gói cập nhật không hợp lệ.")
    return value


def no_links(path: Path) -> None:
    """Check each existing lexical ancestor BEFORE resolve follows reparse points."""
    path = Path(os.path.abspath(path))
    for candidate in (*reversed(path.parents), path):
        try:
            attrs = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(attrs.st_mode) or getattr(attrs, "st_file_attributes", 0) & 0x400:
            raise UpdateError("Vị trí cập nhật chứa liên kết hoặc junction; không thể tiếp tục.")


def child(root: Path, name: str) -> Path:
    relative_path(name)
    no_links(root)
    candidate = root.joinpath(*name.split("/"))
    no_links(candidate)
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise UpdateError("Đường dẫn thoát khỏi vùng cập nhật.")
    return candidate


def sha256(path: Path, *, progress=lambda *_: None) -> str:
    no_links(path)
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            count += len(block)
            progress(count)
    return digest.hexdigest()


def read_json(path: Path, limit: int = 8 * 1024**2) -> dict:
    no_links(path)
    if path.stat().st_size > limit:
        raise UpdateError("Metadata cập nhật vượt giới hạn dung lượng.")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise UpdateError("Metadata có trường trùng nhau.")
            result[key] = value
        return result
    try:
        result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise UpdateError("Metadata cập nhật bị hỏng.") from exc
    if not isinstance(result, dict):
        raise UpdateError("Metadata cập nhật không phải đối tượng.")
    return result


def atomic_json(path: Path, value: dict) -> None:
    no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".update-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        # POSIX directory durability; Windows uses flushed files + atomic
        # same-volume replacement. No claim of power-loss atomicity on all FS.
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def file_lock(path: Path):
    """Kernel-held lock; crash releases it, no stale lock-file PID guessing."""
    no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise UpdateError("Một tiến trình HaizFlow khác đang quản lý cập nhật.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def remove_owned(root: Path, target: Path) -> None:
    """Only direct updater-owned children, never installation/runtime roots."""
    no_links(root)
    no_links(target)
    if target.parent.resolve() != root.resolve() or target.resolve() == root.resolve():
        raise UpdateError("Không được dọn đường dẫn ngoài vùng cập nhật.")
    if not target.exists():
        return
    # Refuse the entire cleanup if ANY nested reparse point is present.
    for directory, dirs, files in os.walk(target, followlinks=False):
        for name in dirs + files:
            no_links(Path(directory) / name)
    shutil.rmtree(target)
