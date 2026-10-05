"""Execute authorised sample ASR, per-speaker presets and cloning in frozen workers."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
import wave
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.services.resource_packs import _assets_by_component  # noqa: E402
from haizflow.core.model_integrity import OMNIVOICE_RUNTIME_FILES  # noqa: E402
from haizflow.update.filesystem import atomic_json, no_links, remove_owned  # noqa: E402
from haizflow.update.state import provision  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=Path, required=True)
    parser.add_argument("--gpu", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    args = parser.parse_args()
    parent = ROOT / "build/frozen-voice-modes"
    root = parent / uuid.uuid4().hex
    app = root / "Ứng dụng kiểm thử 日本語"
    provision(app)
    models = app / "runtime/models"
    groups = _assets_by_component()
    for component in ("omnivoice", "omnivoice-sdk", "omnivoice-runtime", "whisper"):
        assert component in groups, component
        for asset in groups[component]:
            source, target = args.models.resolve() / asset.relative_path, models / asset.relative_path
            no_links(source)
            assert source.is_file() and source.stat().st_size == asset.size, str(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Immutable model copies share disk blocks; the worker never writes
            # them. Generated SDK site, outputs and caches are private, separate.
            os.link(source, target)
    site = models / "omnivoice/sdk/site-packages"
    site.mkdir()
    for name in OMNIVOICE_RUNTIME_FILES:
        with zipfile.ZipFile(models / "omnivoice/sdk" / name) as archive:
            for member in archive.infolist():
                assert (site / member.filename).resolve().is_relative_to(site.resolve())
            archive.extractall(site)
    env = os.environ.copy()
    for name in ("HAIZFLOW_HOME", "HAIZFLOW_INSTALL_ROOT", "HAIZFLOW_RESOURCE_ROOT", "MODELS_DIR",
                 "RUNTIME_DATA_DIR", "APP_DATA_DIR", "HAIZFLOW_SMOKE_TEST"):
        env.pop(name, None)
    env.update(HAIZFLOW_ENGINE_APP_ROOT=str(app), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="cp1252")
    env["PATH"] = str(ROOT / "runtime/bin") + os.pathsep + env.get("PATH", "")
    samples = ROOT / "src/haizflow/desktop/assets/voice_samples"
    sentences = json.loads((samples / "samples.json").read_text(encoding="utf-8"))["sentences"]
    reference = samples / "omnivoice/omnivoice_female/en.mp3"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    results, passed = [], False

    def run(label, engine, arguments, stdin=None):
        completed = subprocess.run([str(engine.resolve()), *map(str, arguments)], env=env,
            input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=flags, timeout=900)
        (root / f"{label}-stderr.log").write_text(completed.stderr, encoding="utf-8")
        assert completed.returncode == 0, completed.stderr[-3000:]

    try:
        for name, engine, device in (("cpu", args.cpu, "cpu"), ("gpu", args.gpu, "cuda")):
            request, response = app / f"{name}-nhận dạng.json", app / f"{name}-asr-response.json"
            atomic_json(request, dict(protocol_version=1, operation="reference_transcribe",
                payload=dict(audio_path=str(reference), model_root=str(models / "whisper/small"),
                             device="gpu" if device == "cuda" else "cpu"),
                response_path=str(response), status_path=str(app / "status.json")))
            run(name + "-asr", engine, ["--request", request])
            data = json.loads(response.read_text(encoding="utf-8"))
            transcript = str(data.get("result", {}).get("text") or "").strip()
            assert data.get("ok") and len(transcript.split()) >= 8, data
            results.append(dict(task=name + "-reference-asr", words=len(transcript.split()), passed=True))
            inputs = []
            jobs = []
            for mode in ("multiple", "clone"):
                response = app / f"{name}-{mode}-response.json"
                request = app / f"{name}-{mode}-tạo giọng.json"
                items = []
                for i, voice in enumerate(("omnivoice:male", "omnivoice:female") if mode == "multiple"
                                          else ("omnivoice:clone",)):
                    wav = root / f"{name}-{mode}-{i}.wav"
                    item = dict(text="Hello, this is a short voice test.", voice=voice, wav_path=str(wav))
                    if mode == "clone":
                        item.update(reference_path=str(reference), reference_text=transcript)
                    else:
                        preset = "omnivoice_male" if i == 0 else "omnivoice_female"
                        item.update(preset_reference_path=str(samples / "omnivoice" / preset / "en.mp3"),
                                    preset_reference_text=sentences["en"])
                    items.append(item)
                atomic_json(request, dict(site_packages=str(site), model_root=str(models / "omnivoice"),
                    device=device, language="en", inference_steps=2, voice_seed=42,
                    speaker_mode="multiple" if mode == "multiple" else "single", items=items,
                    response_path=str(response), status_path=str(app / "status.json")))
                inputs.append(str(request))
                jobs.append((mode, response, items))
            run(name + "-tts", engine, ["--omnivoice-server"], "\n".join([*inputs, "__quit__", ""]))
            for mode, response, items in jobs:
                data = json.loads(response.read_text(encoding="utf-8"))
                assert data.get("return_code") == 0, data
                for item in items:
                    with wave.open(item["wav_path"]) as audio:
                        assert audio.getnframes() > 240 and audio.getframerate() >= 16000
                results.append(dict(task=name + "-" + mode, generated=len(items), passed=True))
            print(json.dumps({"profile": name, "passed": True}), flush=True)
        atomic_json(ROOT / "build/frozen-voice-modes-report.json", dict(passed=True, frozen=True,
            unicode_paths=True, reused_worker=True, inference_steps=2, quality_benchmark=False,
            user_data_modified=False, results=results))
        passed = True
    finally:
        if passed:
            remove_owned(parent, root)
        else:
            print("Preserved failed fixture: " + str(root))


if __name__ == "__main__":
    main()
