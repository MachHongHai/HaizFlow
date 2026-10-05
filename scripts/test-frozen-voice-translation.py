"""Run real voice, translation and OCR workers against private pinned model copies."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import wave
import zipfile
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
    parser.add_argument("--vision", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--cleanup-models", action="store_true")
    args = parser.parse_args()
    parent = (ROOT / "build/frozen-voice-smoke").resolve()
    fixture = args.fixture.resolve() if args.fixture else parent / uuid.uuid4().hex
    no_links(fixture)
    if fixture.parent != parent or len(fixture.name) != 32 or any(ch not in "0123456789abcdef" for ch in fixture.name):
        raise ValueError("Reuse only an owned GUID fixture below build/frozen-voice-smoke")
    fixture.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"fixture": str(fixture)}), flush=True)
    app = fixture / "installation"
    provision(app)
    models = app / "runtime/models"
    groups = _assets_by_component()
    components = ("omnivoice", "omnivoice-sdk", "omnivoice-runtime", "hymt2-cpu", "hymt2-gpu", "subtitle-ocr")
    for component in components:
        for asset in groups[component]:
            source, target = args.models / asset.relative_path, models / asset.relative_path
            no_links(source)
            if not source.is_file() or source.stat().st_size != asset.size:
                raise ValueError(f"Missing pinned fixture source: {source}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(source, target)
    # Use the same pinned wheel set as production, never the developer venv SDK.
    sdk = models / "omnivoice/sdk"
    site = sdk / "site-packages"
    site.mkdir(exist_ok=True)
    from haizflow.core.model_integrity import OMNIVOICE_RUNTIME_FILES

    for name in OMNIVOICE_RUNTIME_FILES:
        with zipfile.ZipFile(sdk / name) as archive:
            for member in archive.infolist():
                target = (site / member.filename).resolve()
                if not target.is_relative_to(site.resolve()):
                    raise ValueError("Unsafe SDK wheel")
            archive.extractall(site)
    if args.prepare_only:
        return
    environment = os.environ.copy()
    for name in ("HAIZFLOW_HOME", "HAIZFLOW_INSTALL_ROOT", "HAIZFLOW_RESOURCE_ROOT", "MODELS_DIR",
                 "RUNTIME_DATA_DIR", "APP_DATA_DIR", "HAIZFLOW_SMOKE_TEST", "HYMT2_CPU_MODEL_PATH",
                 "HYMT2_GPU_MODEL_PATH"):
        environment.pop(name, None)
    environment.update(HAIZFLOW_ENGINE_APP_ROOT=str(app), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       PYANNOTE_METRICS_ENABLED="false", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    environment["PATH"] = str(ROOT / "runtime/bin") + os.pathsep + environment.get("PATH", "")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    results = []

    def run(label, command, extra=None, stdin=None, timeout=420):
        started = time.monotonic()
        completed = subprocess.run([str(part) for part in command], env={**environment, **(extra or {})},
            input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=flags)
        (fixture / f"{label}-stdout.log").write_text(completed.stdout, encoding="utf-8")
        (fixture / f"{label}-stderr.log").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError(f"{label} failed ({completed.returncode}); see {fixture}: {completed.stderr[-1600:]}")
        record = dict(task=label, seconds=round(time.monotonic() - started, 2))
        results.append(record)
        print(json.dumps(record), flush=True)
        return completed

    for label, engine, device in (("cpu", args.cpu, "cpu"), ("gpu", args.gpu, "cuda")):
        run(f"{label}-sdk", [engine.resolve(), "--voice-sdk-smoke", site])
        output = fixture / f"{label}-voice.wav"
        response, request = fixture / f"{label}-voice-response.json", fixture / f"{label}-voice.json"
        atomic_json(request, dict(site_packages=str(site), model_root=str(models / "omnivoice"), device=device,
            language="en", inference_steps=2, voice_seed=42, speaker_mode="single",
            status_path=str(fixture / f"{label}-voice-status.json"), response_path=str(response),
            items=[dict(text="Hello, this is a short voice test.", voice="omnivoice:female", wav_path=str(output))]))
        run(f"{label}-voice", [engine.resolve(), "--omnivoice-server"], stdin=str(request) + "\n__quit__\n")
        result = json.loads(response.read_text(encoding="utf-8")) if response.exists() else {}
        if result.get("return_code") != 0:
            raise RuntimeError(f"{label} voice failed: {result}")
        with wave.open(str(output)) as audio:
            if audio.getnframes() < 240 or audio.getframerate() < 16000:
                raise RuntimeError("Voice output is empty or invalid")
            results[-1]["audio_seconds"] = round(audio.getnframes() / audio.getframerate(), 3)
        # Test the JSON-lines server contract used by the app, not the generic
        # engine --request endpoint (which accepts a different task envelope).
        translation_input = json.dumps(dict(request_id="translate", payload=dict(
            texts=["Hello, how are you?"], source_language="English",
            target_language_name="Vietnamese", include_context=False))) + "\n"
        translation_input += json.dumps(dict(request_id="shutdown", command="shutdown")) + "\n"
        completed = run(f"{label}-translation", [engine.resolve(), "--hymt2-worker", "--server"],
            stdin=translation_input,
            extra={"HAIZFLOW_PROCESSING_DEVICE": "gpu" if label == "gpu" else "cpu",
                   "HAIZFLOW_TRANSLATION_MODEL": "full" if label == "gpu" else "q4"})
        responses = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]
        translation = next((entry for entry in responses if entry.get("request_id") == "translate"
                            and entry.get("event") == "response"), {})
        if translation.get("error") or not translation.get("translations", [""])[0].strip():
            raise RuntimeError(f"{label} translation failed: {translation}")
        results[-1]["translation"] = translation["translations"][0]

    # A generated text fixture checks OCR's model session as well as its import.
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 42)
    for index, text in enumerate(("HELLO WORLD", "WELCOME HOME", "GOOD MORNING"), 1):
        image = Image.new("RGB", (640, 360), "black")
        draw = ImageDraw.Draw(image)
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((640 - box[2] + box[0]) / 2, 275), text, fill="white", font=font)
        image.save(fixture / f"ocr-frame-{index:02d}.png")
    run("ocr-fixture", [ROOT / "runtime/bin/ffmpeg.exe", "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", "0.5", "-start_number", "1", "-i", fixture / "ocr-frame-%02d.png",
        "-t", "6", "-pix_fmt", "yuv420p", fixture / "ocr.mp4"])
    response, request = fixture / "ocr-response.json", fixture / "ocr-request.json"
    temp = fixture / "ocr-temp"
    temp.mkdir(exist_ok=True)
    atomic_json(request, dict(protocol_version=1, operation="subtitle_ocr",
        payload=dict(video_path=str(fixture / "ocr.mp4"), temp_dir=str(temp), video_id="frozen-ocr"),
        response_path=str(response), status_path=str(fixture / "ocr-status.json")))
    run("ocr", [args.vision.resolve(), "--request", request])
    ocr = json.loads(response.read_text(encoding="utf-8"))
    if not ocr.get("ok") or not ocr.get("result", {}).get("region"):
        raise RuntimeError(f"OCR did not detect the text fixture: {ocr}")
    results[-1]["region"] = ocr["result"]["region"]
    atomic_json(fixture / "result.json", dict(passed=True, user_data_modified=False, network_used=False,
                                               inference_steps=2, results=results))
    if args.cleanup_models:
        remove_owned(app / "runtime", models)
    print(json.dumps(dict(passed=True, fixture=str(fixture))), flush=True)


if __name__ == "__main__":
    main()
