"""Known-preset speaker fixtures, including dialogue with only short turns."""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import uuid
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.update.filesystem import atomic_json, remove_owned  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path)
    args = parser.parse_args()
    parent = ROOT / "build/speaker-dialogue-fixtures"
    root = parent / uuid.uuid4().hex
    root.mkdir(parents=True)
    env = os.environ.copy()
    env.update(HAIZFLOW_HOME=str(root / "ứng dụng"), HAIZFLOW_SMOKE_TEST="1",
               HAIZFLOW_TMP_DIR=str(root / "tmp"), PYTHONPATH=str(ROOT / "src"), OPENBLAS_NUM_THREADS="1")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    command = ([str(args.core.resolve() / "HaizFlowCore.exe"), "--engine-worker"] if args.core
               else [sys.executable, "-m", "haizflow.engine.main"])
    models = (args.core.resolve() / "_internal/models/speaker-identification" if args.core
              else ROOT / "build/bundled-models/speaker-identification")
    samples = ROOT / "src/haizflow/desktop/assets/voice_samples/omnivoice"
    decoded = []
    for name in ("omnivoice_male", "omnivoice_female"):
        result = subprocess.run([str(ROOT / "runtime/bin/ffmpeg.exe"), "-v", "error", "-i",
            str(samples / name / "en.mp3"), "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"],
            capture_output=True, check=True, creationflags=flags)
        with wave.open(io.BytesIO(result.stdout)) as stream:
            decoded.append(stream.readframes(32000 * 20))
    reports = []
    passed = False
    try:
        for label, length in (("long-turns", 3.2), ("short-only", 1.4)):
            pcm, segments, truth = bytearray(), [], []
            for i in range(8):
                person = i % 2
                offset = (i // 2) * 2.7 + .3
                start = int(offset * 16000) * 2
                end = start + int(length * 16000) * 2
                chunk = decoded[person][start:end]
                assert len(chunk) == int(length * 16000) * 2, "Fixture sample is too short"
                segments.append(dict(start=len(pcm) / 32000, end=(len(pcm) + len(chunk)) / 32000,
                                     text=f"Neutral test turn {i + 1}"))
                pcm.extend(chunk)
                pcm.extend(bytes(6400))
                truth.append(person)
            audio = root / f"{label}.wav"
            with wave.open(str(audio), "wb") as stream:
                stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                stream.writeframes(pcm)
            response, request = root / f"{label}-response.json", root / f"{label}-request.json"
            atomic_json(request, dict(protocol_version=1, operation="speaker_identification",
                payload=dict(audio_path=str(audio), model_directory=str(models), video_id="speaker-quality",
                             segments=segments), response_path=str(response), status_path=str(root / "status.json")))
            result = subprocess.run([*command, "--request", str(request)], env=env,
                                    capture_output=True, timeout=90, creationflags=flags)
            assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")[-4000:]
            data = json.loads(response.read_text(encoding="utf-8"))
            assert data.get("ok"), data
            identities = [item["speaker_id"] for item in data["result"]["segments"]]
            pairs = [(i, j) for i in range(8) for j in range(i + 1, 8)]
            correct = sum((truth[i] == truth[j]) == (identities[i] == identities[j]) for i, j in pairs)
            record = dict(fixture=label, turns=8, expected_speakers=2, detected_speakers=len(set(identities)),
                          identities=identities, correct_pairs=correct, total_pairs=len(pairs))
            reports.append(record)
            print(json.dumps(record), flush=True)
            assert correct == len(pairs), "Known-preset identity assignment regressed"
        atomic_json(ROOT / "build/speaker-dialogue-report.json", dict(passed=True, frozen=bool(args.core),
                    user_media_used=False, synthetic_presets_not_real_world_accuracy=True, fixtures=reports))
        passed = True
    finally:
        if passed:
            remove_owned(parent, root)
        else:
            print("Preserved failed fixture: " + str(root))


if __name__ == "__main__":
    main()
