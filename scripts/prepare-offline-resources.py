"""Create a local, checksum-pinned companion bundle for engineering installers."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.update.filesystem import atomic_json, no_links, sha256  # noqa: E402


def prepare(archives: list[Path], output: Path, manifest: Path, *, link_archives: bool = False) -> dict:
    spec = importlib.util.spec_from_file_location("pack_finalize", ROOT / "scripts/finalize-resource-pack.py")
    finalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finalizer)
    payload = {"schema": 1, "protocol_version": 1, "engineering_offline": True, "packs": {}}
    no_links(output)
    if output.exists():
        raise ValueError("Choose a new companion directory; never overwrite an existing bundle.")
    records = []
    for path in archives:
        no_links(path)
        with zipfile.ZipFile(path) as bundle:
            engine = json.loads(bundle.read("engine.json"))
        pack_id, version = engine["pack_id"], engine["version"]
        if pack_id not in finalizer.ENGINE_REQUIRED_COMMANDS or pack_id in payload["packs"]:
            raise ValueError("Unknown or duplicate engine archive.")
        installed, _ = finalizer._read_engine_archive(path, pack_id, version)
        filename = f"{pack_id}-{version}.zip"
        if path.name != filename:
            raise ValueError("Archive filename must match its pack identity/version.")
        record = dict(version=version, url="", sha256=sha256(path), offline_archive=filename,
                      download_size=path.stat().st_size, installed_size=installed)
        payload["packs"][pack_id] = record
        records.append((path, record))
    if set(payload["packs"]) != set(finalizer.ENGINE_REQUIRED_COMMANDS):
        raise ValueError("Include all three CPU, CUDA and vision engines.")
    output.mkdir(parents=True)
    for path, record in records:
        target = output / record["offline_archive"]
        if link_archives:
            # Immutable, checksum-pinned archives on the same volume can share
            # storage without removing an older installer or its fallback data.
            os.link(path, target)
        else:
            shutil.copy2(path, target)
        if target.stat().st_size != record["download_size"] or sha256(target) != record["sha256"]:
            raise ValueError("Companion archive copy failed verification.")
    atomic_json(manifest, payload)
    atomic_json(output / "RESOURCE-PACKS.json", payload)
    print(json.dumps({"manifest": str(manifest), "companion": str(output),
                      "archive_bytes": sum(record["download_size"] for _, record in records)}))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--link-archives", action="store_true", help="Use same-volume hard links for immutable local archives")
    args = parser.parse_args()
    prepare(args.archive, args.output, args.manifest, link_archives=args.link_archives)
