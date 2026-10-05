"""Verify the installed Core dispatches Q4/full HY-MT2 to real resource engines."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.services.resource_packs import _assets_by_component  # noqa: E402
from haizflow.update.filesystem import atomic_json, no_links  # noqa: E402
from haizflow.update.state import provision  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--cpu", type=Path, required=True)
    parser.add_argument("--gpu", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    args = parser.parse_args()
    core = args.core.resolve()
    if not core.is_file() or core.name != "HaizFlowCore.exe":
        raise ValueError("Supply the frozen Core executable.")
    catalog = json.loads((core.parent / "RESOURCE-PACKS.json").read_text(encoding="utf-8"))
    fixture = ROOT / "build/translation-dispatch-smoke" / uuid.uuid4().hex
    no_links(fixture)
    fixture.mkdir(parents=True)
    app = fixture / "installation"
    provision(app)
    print(json.dumps({"fixture": str(fixture)}), flush=True)
    for engine in (args.cpu.resolve(), args.gpu.resolve()):
        metadata = json.loads((engine.parent / "engine.json").read_text(encoding="utf-8"))
        pack_id = metadata["pack_id"]
        pinned = catalog["packs"][pack_id]
        if metadata["version"] != pinned["version"]:
            raise ValueError("Core and engine fixture versions must match.")
        target = app / "runtime/engines" / pack_id / metadata["version"]
        # Immutable payloads can share disk blocks; all mutable test data is
        # private and neither source engines nor the user's models are edited.
        shutil.copytree(engine.parent, target, copy_function=os.link)
        atomic_json(target / "complete.json", dict(pack_id=pack_id, version=metadata["version"],
                    protocol_version=metadata["protocol_version"], archive_sha256=pinned["sha256"]))
    assets = _assets_by_component()
    models = app / "runtime/models"
    for component in ("hymt2-cpu", "hymt2-gpu"):
        for asset in assets[component]:
            source = args.models.resolve() / asset.relative_path
            target = models / asset.relative_path
            no_links(source)
            if not source.is_file() or source.stat().st_size != asset.size:
                raise ValueError(f"Incomplete pinned model fixture: {source}")
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, target)
    environment = os.environ.copy()
    for name in ("HAIZFLOW_HOME", "HAIZFLOW_INSTALL_ROOT", "HAIZFLOW_RESOURCE_ROOT", "MODELS_DIR",
                 "RUNTIME_DATA_DIR", "APP_DATA_DIR", "HAIZFLOW_ENGINE_APP_ROOT", "HYMT2_CPU_MODEL_PATH", "HYMT2_GPU_MODEL_PATH"):
        environment.pop(name, None)
    environment.update(HAIZFLOW_SMOKE_TEST="1", HAIZFLOW_INSTALL_ROOT=str(app),
                       HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    results = []
    for preference in ("q4", "full"):
        started = time.monotonic()
        completed = subprocess.run([str(core), "--release-smoke", "--translation-model", preference],
            env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=420, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        (fixture / f"{preference}-stdout.log").write_text(completed.stdout, encoding="utf-8")
        (fixture / f"{preference}-stderr.log").write_text(completed.stderr, encoding="utf-8")
        events = []
        for line in completed.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        result = next((event for event in events if isinstance(event, dict) and event.get("model") == preference), {})
        if completed.returncode or not result.get("ok"):
            raise RuntimeError(f"Core parent dispatch failed for {preference}; inspect {fixture}")
        expected = "engine-cpu-py313" if preference == "q4" else "engine-cuda128-py313"
        if expected not in Path(result["command"][0]).parts:
            raise RuntimeError("Core dispatched to the wrong engine.")
        result["seconds"] = round(time.monotonic() - started, 2)
        results.append(result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    atomic_json(fixture / "result.json", {"ok": True, "results": results})


if __name__ == "__main__":
    main()
