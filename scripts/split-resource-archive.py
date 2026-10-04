"""Create GitHub-sized, checksum-pinned parts without changing a ZIP's bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

MAX_PART_BYTES = 2 * 1024**3 - 1


def split_archive(archive: Path, output: Path, *, part_bytes: int = 1536 * 1024**2) -> dict:
    if not 0 < part_bytes <= MAX_PART_BYTES:
        raise ValueError("Each GitHub asset must be smaller than 2 GiB.")
    if archive.stat().st_size <= part_bytes:
        raise ValueError("This archive does not need multipart packaging.")
    if (archive.stat().st_size + part_bytes - 1) // part_bytes > 16:
        raise ValueError("Archives require at most 16 parts; increase the part size.")
    if output.exists():
        raise ValueError("Choose a new output folder; never overwrite previously finalized parts.")
    output.mkdir(parents=True)
    whole = hashlib.sha256()
    parts = []
    with archive.open("rb") as stream:
        while True:
            first = stream.read(min(4 * 1024**2, part_bytes))
            if not first:
                break
            filename = archive.name + f".{len(parts) + 1:03d}"
            digest = hashlib.sha256()
            size = 0
            with (output / filename).open("xb") as part:
                chunk = first
                while chunk:
                    part.write(chunk)
                    digest.update(chunk)
                    whole.update(chunk)
                    size += len(chunk)
                    chunk = stream.read(min(4 * 1024**2, part_bytes - size)) if size < part_bytes else b""
            parts.append(dict(file=filename, size=size, sha256=digest.hexdigest()))
    if not 2 <= len(parts) <= 16:
        raise ValueError("Archives require 2–16 parts; increase the part size.")
    result = dict(schema=1, archive=archive.name, download_size=sum(p["size"] for p in parts),
                  sha256=whole.hexdigest(), parts=parts)
    (output / "parts.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--part-bytes", type=int, default=1536 * 1024**2)
    args = parser.parse_args()
    print(json.dumps(split_archive(args.archive, args.output, part_bytes=args.part_bytes), indent=2))
