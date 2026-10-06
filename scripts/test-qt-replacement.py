"""Verify standalone frozen Core startup after a local Qt DLL change.

This tests the replacement mechanism, not the ABI of arbitrary rebuilt Qt.
Only the PE checksum field is changed; Qt behavior remains identical. All
changes happen in a disposable build fixture, never an installed application.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[1]


def test(core: Path) -> dict:
    core = core.resolve()
    if not (core / "HaizFlowCore.exe").is_file():
        raise ValueError("A frozen HaizFlowCore artifact is required.")
    parent = ROOT / "build/qt-replacement-tests"
    parent.mkdir(parents=True, exist_ok=True)
    # Windows startup-probe children can briefly keep the fixture cwd open
    # after Core exits. Never turn a successful startup into a false failure
    # or terminate unrelated processes just to remove a test directory.
    with tempfile.TemporaryDirectory(prefix="local-", dir=parent, ignore_cleanup_errors=True) as directory:
        fixture = Path(directory)
        copy = fixture / "Core"
        shutil.copytree(core, copy)
        library = copy / "_internal/PySide6/Qt6Core.dll"
        original_hash = hashlib.sha256(library.read_bytes()).hexdigest()
        with pefile.PE(str(library)) as pe:
            pe.OPTIONAL_HEADER.CheckSum ^= 1
            changed_library = pe.write()
        library.write_bytes(changed_library)
        changed_hash = hashlib.sha256(library.read_bytes()).hexdigest()
        if changed_hash == original_hash:
            raise ValueError("Test did not change the DLL checksum.")
        environment = os.environ.copy()
        environment.update(HAIZFLOW_SMOKE_TEST="1", QT_QPA_PLATFORM="offscreen",
                           HAIZFLOW_HOME=str(fixture / "runtime"),
                           RUNTIME_DATA_DIR=str(fixture / "runtime/data"),
                           HAIZFLOW_RESOURCE_ROOT=str(fixture / "resources"))
        for name in ("HAIZFLOW_BOOTSTRAP_ROOT", "HAIZFLOW_HEALTH_TOKEN", "HAIZFLOW_HEALTH_ATTEMPT"):
            environment.pop(name, None)
        process = subprocess.run([str(copy / "HaizFlowCore.exe"), "--ui-smoke-test"],
                                 cwd=copy, env=environment, capture_output=True, timeout=90,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        if process.returncode:
            raise ValueError("Modified Qt standalone startup failed: " + process.stderr.decode("utf-8", "replace")[-3000:])
        result = dict(ok=True, test="standalone Qt DLL replacement mechanism",
                      modification="PE checksum only; behavior and ABI unchanged",
                      original_sha256=original_hash, modified_sha256=changed_hash,
                      publisher_key_required=False, user_installation_modified=False)
        (parent / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    args = parser.parse_args()
    test(args.core)
