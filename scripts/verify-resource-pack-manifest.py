#!/usr/bin/env python3
"""Validate the immutable resource-pack catalog shipped with HaizFlow Core."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "runtime" / "resource-pack-manifest.json"
ENGINE_PACKS = {
    "engine-cpu-py313",
    "engine-cuda128-py313",
    "engine-vision-onnx",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _positive_integer(value: object, field: str, pack_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"{pack_id}.{field} must be a positive integer.")
    return value


def validate_manifest(path: Path, *, strict: bool) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Resource-pack manifest is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Resource-pack manifest is invalid JSON: {path}") from exc

    if payload.get("schema") != 1:
        raise RuntimeError("Resource-pack manifest schema must be 1.")
    if payload.get("protocol_version") != 1:
        raise RuntimeError("Resource-pack protocol_version must be 1.")
    packs = payload.get("packs")
    if not isinstance(packs, dict):
        raise RuntimeError("Resource-pack manifest packs must be an object.")
    missing = ENGINE_PACKS.difference(packs)
    if missing:
        raise RuntimeError("Resource-pack manifest is missing: " + ", ".join(sorted(missing)))

    ready = 0
    for pack_id in sorted(ENGINE_PACKS):
        record = packs[pack_id]
        if not isinstance(record, dict):
            raise RuntimeError(f"{pack_id} must be an object.")
        version = record.get("version")
        if not isinstance(version, str) or not version.strip():
            raise RuntimeError(f"{pack_id}.version must be a non-empty string.")
        _positive_integer(record.get("download_size"), "download_size", pack_id)
        _positive_integer(record.get("installed_size"), "installed_size", pack_id)
        url = record.get("url")
        digest = record.get("sha256")
        if not isinstance(url, str) or not isinstance(digest, str):
            raise RuntimeError(f"{pack_id}.url and sha256 must be strings.")
        if bool(url) != bool(digest):
            raise RuntimeError(f"{pack_id}.url and sha256 must either both be set or both be empty.")
        if not url:
            if strict:
                raise RuntimeError(f"{pack_id} has no immutable release URL and SHA-256.")
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise RuntimeError(f"{pack_id}.url must be an absolute credential-free HTTPS URL.")
        if not SHA256_PATTERN.fullmatch(digest.lower()):
            raise RuntimeError(f"{pack_id}.sha256 must contain 64 lowercase hexadecimal characters.")
        ready += 1

    return {"packs": len(packs), "engine_packs": len(ENGINE_PACKS), "release_ready": ready}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = validate_manifest(args.manifest.resolve(), strict=args.strict)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
