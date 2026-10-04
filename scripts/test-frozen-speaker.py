"""Exercise the integrated CPU speaker worker without any external engine."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.core.bundled_models import MODEL_FILE
from haizflow.update.filesystem import atomic_json, remove_owned, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    args = parser.parse_args()
    core = args.core.absolute()
    model_root = core / "_internal/models/speaker-identification"
    model = model_root / MODEL_FILE
    model_hash = sha256(model)
    before = {path.name for path in model_root.iterdir()}
    parent = ROOT / "build/frozen-speaker-smoke"
    root = parent / uuid.uuid4().hex
    root.mkdir(parents=True)
    response = root / "response.json"
    status = root / "status.json"
    request = root / "request.json"
    atomic_json(request, dict(protocol_version=1, context={"device": "cpu"}, operation="speaker_identification",
        payload=dict(audio_path=str(ROOT / "src/haizflow/desktop/assets/voice_samples/omnivoice/omnivoice_female/en.mp3"),
            model_directory=str(model_root), video_id="frozen-speaker-test",
            segments=[dict(start=0, end=4, text="Sample one"), dict(start=4, end=8, text="Sample two")]),
        response_path=str(response), status_path=str(status)))
    environment = os.environ.copy()
    environment.update(HAIZFLOW_SMOKE_TEST="1", HAIZFLOW_HOME=str(root), RUNTIME_DATA_DIR=str(root / "data"),
        HAIZFLOW_RESOURCE_ROOT=str(root / "resources"), HAIZFLOW_TMP_DIR=str(root / "tmp"),
        TEMP=str(root), TMP=str(root))
    passed = False
    try:
        result = subprocess.run([str(core / "HaizFlowCore.exe"), "--engine-worker", "--request", str(request)],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode or not response.is_file():
            raise RuntimeError("Frozen speaker failed: " + result.stderr.decode("utf-8", errors="replace")[-4000:])
        data = json.loads(response.read_text(encoding="utf-8"))
        assert data.get("ok") and len(data["result"]["segments"]) == 2, data
        assert json.loads(status.read_text(encoding="utf-8"))["device"] == "cpu"
        assert sha256(model) == model_hash and before == {path.name for path in model_root.iterdir()}
        report = ROOT / "build/frozen-speaker-report.json"
        atomic_json(report, dict(passed=True, integrated_cpu_inference=True, external_engine_installed=False,
            immutable_model_unchanged=True, user_media_used=False, segments=2))
        passed = True
        print("Integrated frozen CPU speaker inference passed. Report: " + str(report))
    finally:
        if passed:
            remove_owned(parent, root)
        else:
            print("Failed speaker fixture preserved: " + str(root))


if __name__ == "__main__":
    main()
