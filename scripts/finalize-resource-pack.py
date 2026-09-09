#!/usr/bin/env python3
"""Pin a built engine archive into the resource-pack release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "runtime" / "resource-pack-manifest.json"
ENGINE_REQUIRED_COMMANDS = {
    "engine-cpu-py313": {
        "smoke_command",
        "rpc_command",
        "hymt2_server",
        "omnivoice_worker",
        "omnivoice_server",
        "demucs",
        "transcribe",
        "runtime_probe",
    },
    "engine-cuda128-py313": {
        "smoke_command",
        "rpc_command",
        "hymt2_server",
        "omnivoice_worker",
        "omnivoice_server",
        "demucs",
        "transcribe",
        "runtime_probe",
    },
    "engine-vision-onnx": {"smoke_command", "rpc_command", "subtitle_ocr"},
}
ENGINE_PROFILE_BY_PACK = {
    "engine-cpu-py313": "cpu",
    "engine-cuda128-py313": "cuda128",
    "engine-vision-onnx": "vision",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_engine_archive(path: Path, pack_id: str, version: str) -> tuple[int, dict]:
    try:
        with zipfile.ZipFile(path) as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            for item in files:
                member = PurePosixPath(item.filename.replace("\\", "/"))
                if member.is_absolute() or ".." in member.parts:
                    raise RuntimeError(f"Unsafe archive member: {item.filename}")
            engine_entries = [item for item in files if PurePosixPath(item.filename).as_posix() == "engine.json"]
            if len(engine_entries) != 1:
                raise RuntimeError("Engine archive must contain one root engine.json.")
            engine = json.loads(archive.read(engine_entries[0]).decode("utf-8"))
            installed_size = sum(item.file_size for item in files)
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid engine archive: {path}") from exc
    if engine.get("pack_id") != pack_id or str(engine.get("version")) != version:
        raise RuntimeError("engine.json identity does not match --pack-id/--version.")
    if engine.get("profile") != ENGINE_PROFILE_BY_PACK.get(pack_id):
        raise RuntimeError("engine.json profile does not match --pack-id.")
    if engine.get("protocol_version") != 1:
        raise RuntimeError("engine.json protocol_version must be 1.")
    for command_name in sorted(ENGINE_REQUIRED_COMMANDS.get(pack_id, {"smoke_command", "rpc_command"})):
        command = engine.get(command_name)
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise RuntimeError(f"engine.json must declare a non-empty {command_name} array.")
    return installed_size, engine


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    archive_path = args.archive.resolve()
    parsed = urlparse(args.url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise RuntimeError("--url must be an absolute credential-free HTTPS URL.")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    packs = payload.get("packs")
    if not isinstance(packs, dict) or args.pack_id not in packs:
        raise RuntimeError(f"Unknown engine pack: {args.pack_id}")
    installed_size, _engine = _read_engine_archive(archive_path, args.pack_id, args.version)
    packs[args.pack_id] = {
        "version": args.version,
        "url": args.url,
        "sha256": _sha256(archive_path),
        "download_size": archive_path.stat().st_size,
        "installed_size": installed_size,
    }
    _write_atomic(manifest_path, payload)
    print(
        json.dumps(
            {"pack_id": args.pack_id, "download_size": archive_path.stat().st_size, "installed_size": installed_size},
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
