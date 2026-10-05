"""Exercise real CPU/GPU Whisper inference and alignment in an isolated fixture."""
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
from haizflow.update.filesystem import atomic_json, no_links, remove_owned  # noqa: E402
from haizflow.update.state import provision  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=Path, required=True)
    parser.add_argument("--gpu", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True, help="Read-only source for pinned model copies")
    parser.add_argument("--fixture", type=Path, help="Reuse an owned fixture's model copies")
    parser.add_argument("--cleanup-models", action="store_true")
    args = parser.parse_args()
    parent = (ROOT / "build/frozen-recognition-smoke").resolve()
    fixture = args.fixture.resolve() if args.fixture else parent / uuid.uuid4().hex
    no_links(fixture)
    if fixture.parent != parent or len(fixture.name) != 32 or any(ch not in "0123456789abcdef" for ch in fixture.name):
        raise ValueError("Reuse only a GUID fixture directly below build/frozen-recognition-smoke")
    fixture.mkdir(parents=True, exist_ok=True)
    app = fixture / "installation"
    provision(app)
    groups = _assets_by_component()
    assets = list(groups["whisper"]) + list(groups["whisper-turbo"]) + list(groups["whisperx-vad"])
    assets += [asset for asset in groups["alignment"] if "ls960" in asset.relative_path]
    for asset in assets:
        source = args.models / asset.relative_path
        no_links(source)
        target = app / "runtime/models" / asset.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
    sample = ROOT / "src/haizflow/desktop/assets/voice_samples/omnivoice/omnivoice_female/en.mp3"
    audio = fixture / "sample.wav"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run([str(ROOT / "runtime/bin/ffmpeg.exe"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(sample),
                    "-t", "8", "-ar", "16000", "-ac", "1", str(audio)], check=True, creationflags=flags)
    environment = os.environ.copy()
    for name in ("HAIZFLOW_HOME", "HAIZFLOW_INSTALL_ROOT", "HAIZFLOW_RESOURCE_ROOT", "MODELS_DIR",
                 "RUNTIME_DATA_DIR", "APP_DATA_DIR", "HAIZFLOW_SMOKE_TEST"):
        environment.pop(name, None)
    environment.update(HAIZFLOW_ENGINE_APP_ROOT=str(app), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       PYANNOTE_METRICS_ENABLED="false")
    environment["PATH"] = str(ROOT / "runtime/bin") + os.pathsep + environment.get("PATH", "")
    results = []
    for label, engine, device, model in (("cpu-small", args.cpu, "cpu", "small"),
                                       ("gpu-turbo", args.gpu, "gpu", "large-v3-turbo")):
        log = app / "runtime/data/jobs" / f"frozen-{label}" / "logs.txt"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("", encoding="utf-8")
        request, response = fixture / f"{label}-request.json", fixture / f"{label}-response.json"
        atomic_json(request, dict(protocol_version=1, operation="transcribe", context=dict(device=device, model=model),
            payload=dict(audio_path=str(audio), output_json_path=str(fixture / f"{label}-segments.json"),
                         source_language="auto", video_id=f"frozen-{label}", model_name=model),
            response_path=str(response), status_path=str(fixture / f"{label}-status.json")))
        start = time.monotonic()
        completed = subprocess.run([str(engine.resolve()), "--request", str(request)], env=environment,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=420, creationflags=flags)
        (fixture / f"{label}-stdout.log").write_text(completed.stdout, encoding="utf-8")
        (fixture / f"{label}-stderr.log").write_text(completed.stderr, encoding="utf-8")
        result = json.loads(response.read_text(encoding="utf-8")) if response.exists() else {}
        if completed.returncode or not result.get("ok"):
            raise RuntimeError(f"{label} failed in {fixture}: {result}; {completed.stderr[-1200:]}")
        segments = result["result"]["segments"]
        if not segments or not any(str(segment.get("text", "")).strip() for segment in segments):
            raise RuntimeError(f"{label} produced no speech in {fixture}")
        activity = log.read_text(encoding="utf-8")
        if "Context alignment failed" in activity or "Alignment model failed" in activity:
            raise RuntimeError(f"{label} alignment failed; see {log}")
        if "Aligned 'en' source sentences" not in activity and "Rejected 'en' context alignment" not in activity:
            raise RuntimeError(f"{label} did not exercise English alignment; see {log}")
        if not all(segment.get("timing_source") and 0 <= segment["start"] < segment["end"] <= 8.1
                   for segment in segments):
            raise RuntimeError(f"{label} produced invalid sentence timestamps in {fixture}")
        if (engine.parent / "runtime").exists():
            raise RuntimeError("Inference wrote data beside the immutable engine")
        results.append(dict(profile=label, seconds=round(time.monotonic() - start, 2), segments=len(segments),
                            language=result["result"]["detected_language"]))
        reference_request, reference_response = fixture / f"{label}-reference.json", fixture / f"{label}-reference-result.json"
        atomic_json(reference_request, dict(protocol_version=1, operation="reference_transcribe",
            payload=dict(audio_path=str(audio), model_root=str(app / "runtime/models/whisper" / model), device=device),
            response_path=str(reference_response), status_path=str(fixture / f"{label}-reference-status.json")))
        reference = subprocess.run([str(engine.resolve()), "--request", str(reference_request)], env=environment,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, creationflags=flags)
        (fixture / f"{label}-reference-stderr.log").write_text(reference.stderr, encoding="utf-8")
        reference_result = json.loads(reference_response.read_text(encoding="utf-8")) if reference_response.exists() else {}
        if reference.returncode or not reference_result.get("ok") or not str(reference_result.get("result", {}).get("text", "")).strip():
            raise RuntimeError(f"{label} reference recognition failed: {reference_result}")
        expected_device = "cuda" if device == "gpu" else "cpu"
        if f"device={expected_device}" not in reference.stderr or "[CLONE-ASR][WARN]" in reference.stderr:
            raise RuntimeError(f"{label} reference recognition did not use the selected device")
        results[-1]["reference_recognition"] = True
        print(json.dumps(results[-1]), flush=True)
    atomic_json(fixture / "result.json", dict(passed=True, models_copied=True, user_data_modified=False,
                                               network_used=False, results=results))
    if args.cleanup_models:
        remove_owned(app / "runtime", app / "runtime/models")
    print(json.dumps(dict(passed=True, fixture=str(fixture))), flush=True)


if __name__ == "__main__":
    main()
