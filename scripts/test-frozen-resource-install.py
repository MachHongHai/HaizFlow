"""Install cached real engine ZIPs through the app manager, without network/user data."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, action="append", required=True)
    parser.add_argument("--parts-manifest", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--pause-resume", action="store_true")
    parser.add_argument("--exercise-storage", action="store_true")
    args = parser.parse_args()
    parent = ROOT / "build/resource-install-smoke"
    root = parent / uuid.uuid4().hex
    root.mkdir(parents=True)
    os.environ.update(HAIZFLOW_SMOKE_TEST="1", HAIZFLOW_HOME=str(root),
        RUNTIME_DATA_DIR=str(root / "data"), HAIZFLOW_RESOURCE_ROOT=str(root / "resources"),
        MODELS_DIR=str(root / "resources/models"), HAIZFLOW_TMP_DIR=str(root / "tmp"),
        TEMP=str(root), TMP=str(root))
    from haizflow.core.paths import engines_dir, resource_packages_dir
    from haizflow.core.resource_archive import ArchivePart
    from haizflow.services.resource_packs import ResourcePackDefinition, ResourcePackManager, ModelBootstrapCancelled
    from haizflow.update.filesystem import atomic_json, no_links, remove_owned, sha256

    results = []
    passed = False
    try:
        for archive in args.archive:
            archive = archive.resolve(strict=True)
            no_links(archive)
            with zipfile.ZipFile(archive) as package:
                assert not any(row.filename.split("/")[0] in {"runtime", "update-state"}
                               for row in package.infolist()), "Mutable data in engine ZIP"
                engine = json.loads(package.read("engine.json"))
                installed_size = sum(row.file_size for row in package.infolist())
            package_id = engine["pack_id"]
            version = engine["version"]
            digest = sha256(archive)
            cache = resource_packages_dir()
            cache.mkdir(parents=True, exist_ok=True)
            name = f"{package_id}-{version}.zip"
            parts = ()
            if args.parts_manifest:
                index = json.loads(args.parts_manifest.read_text(encoding="utf-8"))
                if index["archive"] == archive.name:
                    assert index["sha256"] == digest and index["download_size"] == archive.stat().st_size
                    parts = tuple(ArchivePart("https://example.invalid/" + row["file"], row["size"], row["sha256"])
                                  for row in index["parts"])
                    for number, row in enumerate(index["parts"], 1):
                        shutil.copy2(args.parts_manifest.parent / row["file"], cache / (name + f".{number:03d}"))
            if not parts and not args.offline:
                shutil.copy2(archive, cache / name)
            definition = ResourcePackDefinition(package_id, package_id, "processor", version, "engine",
                engine_modules=("test_clean_core_no_ai_module",), download_size=archive.stat().st_size,
                installed_size=installed_size, archive_url="" if parts or args.offline else "https://example.invalid/" + name,
                archive_sha256=digest, archive_parts=parts, offline_archive=name if args.offline else "")
            manager = ResourcePackManager((definition,))
            events = []
            with patch("urllib.request.urlopen", side_effect=AssertionError("Network is forbidden in this cached test")), \
                    patch.object(manager, "_offline_root", return_value=archive.parent):
                assert manager.archive_available(package_id)
                if args.pause_resume:
                    def pause_during_extraction(unit, event):
                        if event.phase == "installing" and event.completed_bytes > 2 * 1024**2:
                            manager.cancel(unit)
                    try:
                        manager.install(package_id, pause_during_extraction)
                    except ModelBootstrapCancelled:
                        pass
                    else:
                        raise AssertionError("Extraction did not pause")
                    assert manager.status(package_id) != "installed"
                    assert not list((engines_dir() / package_id).glob("*.partial"))
                manager.install(package_id, lambda _pack, event: events.append(event.state))
            target = engines_dir() / package_id / version
            assert manager.status(package_id) == "installed"
            assert not (target / "runtime").exists()
            assert sha256(archive if args.offline else cache / name) == digest
            if args.offline:
                assert not (cache / name).exists(), "Offline install must not duplicate the compressed archive"
            assert not list(cache.glob(name + ".00*"))
            actual_payload = sum(path.stat().st_size for path in target.rglob("*")
                                 if path.is_file() and path.name != "complete.json")
            assert actual_payload == installed_size
            assert events[-1] == "ready"
            results.append(dict(pack_id=package_id, version=version, multipart=bool(parts), offline=args.offline,
                archive_bytes=archive.stat().st_size, installed_bytes=actual_payload,
                engine_smoke_passed=True, installed_status=True, storage_exact=True,
                pause_resume_passed=args.pause_resume))
            if args.exercise_storage:
                sentinel = root / "data/user-data.txt"
                sentinel.parent.mkdir(parents=True, exist_ok=True)
                sentinel.write_bytes(b"PRIVATE TEST DATA")
                moved = manager.move_storage(root / "moved")
                os.environ.pop("HAIZFLOW_RESOURCE_ROOT", None)
                os.environ.pop("MODELS_DIR", None)
                assert manager.storage_root == moved
                assert manager.status(package_id) == "installed"
                manager.verify_installed(package_id)
                manager.cleanup_previous_storage()
                assert sentinel.read_bytes() == b"PRIVATE TEST DATA"
                assert manager.remove(package_id) > 0
                assert manager.status(package_id) != "installed"
                assert sentinel.read_bytes() == b"PRIVATE TEST DATA"
                results[-1]["move_verify_remove_preserved_data"] = True
            print("Actual cached install and frozen engine smoke passed: " + package_id, flush=True)
        report = ROOT / "build/resource-install-reports" / root.name / "result.json"
        atomic_json(report, dict(passed=True, network_tested=False, actual_frozen_engines=True,
                               user_data_used=False, packs=results))
        passed = True
        print("Reports: " + str(report), flush=True)
    finally:
        if passed:
            remove_owned(parent, root)
        else:
            print("Failed isolated fixture preserved: " + str(root), flush=True)


if __name__ == "__main__":
    main()
