"""Test packaged PyAV bindings and backend without altering an engine environment."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test(profile: str) -> dict:
    build = ROOT / "build/resource-engines" / f"engine-{profile}-py313"
    artifact = build / "dist/HaizFlowEngine"
    original_package = build / "venv/Lib/site-packages/av"
    parent = ROOT / "build/engine-media-tests"
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=profile + "-", dir=parent) as directory:
        fixture = Path(directory)
        shutil.copytree(original_package, fixture / "av")
        for file in (artifact / "_internal/av").rglob("*.pyd"):
            shutil.copy2(file, fixture / "av" / file.relative_to(artifact / "_internal/av"))
        shutil.copytree(artifact / "_internal/av.libs", fixture / "av.libs")
        environment = os.environ.copy()
        environment.update(PYTHONPATH=str(fixture) + os.pathsep + str(ROOT / "src"), HAIZFLOW_SMOKE_TEST="1",
                           HAIZFLOW_HOME=str(fixture / "runtime"))
        code = ("import av,json; from haizflow.engine.main import media_smoke_test; "
                "assert 'libx264' not in av.codecs_available and 'libx265' not in av.codecs_available; "
                "print(json.dumps(media_smoke_test()))")
        process = subprocess.run([str(build / "venv/Scripts/python.exe"), "-c", code],
                                 env=environment, capture_output=True, text=True, timeout=60,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
        result = json.loads(process.stdout)
        result.update(profile=profile, ok=True, gpl_encoders_available=False)
        (parent / f"{profile}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("cpu", "cuda128"), required=True)
    test(parser.parse_args().profile)
