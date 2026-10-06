"""Checksum-pinned multipart archives; no network or application side effects."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_PART_BYTES = 2 * 1024**3 - 1


@dataclass(frozen=True)
class ArchivePart:
    url: str
    size: int
    sha256: str


def archive_matches(path: Path, *, size: int, sha256: str,
                    cancelled=lambda: False, progress=lambda _done: None) -> bool:
    try:
        if path.stat().st_size != size:
            return False
        digest = hashlib.sha256()
        completed = 0
        with path.open("rb") as stream:
            while chunk := stream.read(4 * 1024 * 1024):
                if cancelled():
                    raise InterruptedError("Archive verification cancelled.")
                digest.update(chunk)
                completed += len(chunk)
                progress(completed)
        return digest.hexdigest() == sha256
    except FileNotFoundError:
        return False


def parse_archive_parts(record: dict) -> tuple[ArchivePart, ...]:
    rows = record.get("parts")
    if rows is None:
        return ()
    if not isinstance(rows, list) or not 2 <= len(rows) <= 16:
        raise ValueError("Multipart archive requires 2–16 pinned parts.")
    if record.get("url"):
        raise ValueError("Choose a single URL or multipart URLs, not both.")
    parts = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid archive part.")
        url, size, digest = row.get("url"), row.get("size"), row.get("sha256")
        if not isinstance(url, str):
            raise ValueError("Invalid part URL.")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("Part URL must be credential-free HTTPS.")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_PART_BYTES:
            raise ValueError("Invalid part size or GitHub asset limit exceeded.")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError("Every part requires a lowercase SHA-256.")
        parts.append(ArchivePart(url, size, digest))
    if len({part.url for part in parts}) != len(parts):
        raise ValueError("Duplicate part URL.")
    if sum(part.size for part in parts) != record.get("download_size"):
        raise ValueError("Part sizes do not match the complete archive size.")
    if not SHA256.fullmatch(str(record.get("sha256") or "")):
        raise ValueError("Complete multipart archive requires a SHA-256.")
    return tuple(parts)


def join_archive_parts(
    sources: tuple[tuple[Path, ArchivePart], ...],
    destination: Path,
    *,
    size: int,
    sha256: str,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int], None] = lambda _done: None,
) -> None:
    """Verify every part and the whole stream before atomic publication.

    Cancellation/failure preserves resumable parts and any previous archive.
    The caller translates InterruptedError into its normal cancellation flow.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".engine-join-", suffix=".tmp", dir=destination.parent)
    temporary = Path(name)
    total = 0
    whole = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "wb") as output:
            for source, part in sources:
                digest = hashlib.sha256()
                count = 0
                with source.open("rb") as stream:
                    while chunk := stream.read(4 * 1024 * 1024):
                        if cancelled():
                            raise InterruptedError("Multipart assembly cancelled.")
                        count += len(chunk)
                        total += len(chunk)
                        if count > part.size or total > size:
                            raise ValueError("Archive part exceeds its pinned size.")
                        digest.update(chunk)
                        whole.update(chunk)
                        output.write(chunk)
                        progress(total)
                if count != part.size or digest.hexdigest() != part.sha256:
                    raise ValueError("Archive part does not match its pinned size/SHA-256.")
            if total != size or whole.hexdigest() != sha256:
                raise ValueError("Complete archive does not match its pinned size/SHA-256.")
            if cancelled():
                raise InterruptedError("Multipart assembly cancelled.")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
