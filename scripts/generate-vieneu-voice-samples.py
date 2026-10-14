"""Generate local, sentence-locked VieNeu previews; never read user projects.

Only MP3 assets are generated. Catalog metadata is printed for review instead
of rewriting samples.json or changing existing OmniVoice/Edge previews.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sample_details(path: Path) -> dict:
    import numpy as np

    from hflow.utils.ffmpeg import _binary, get_video_duration

    duration = get_video_duration(str(path)) if path.is_file() else 0
    if not 8 <= duration <= 120:
        raise RuntimeError(f"Invalid preview duration: {path} ({duration:.3f}s)")
    decoded = subprocess.run(
        [_binary("ffmpeg"), "-v", "error", "-xerror", "-i", str(path),
         "-ac", "1", "-ar", "24000", "-f", "f32le", "-"],
        capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if decoded.returncode:
        raise RuntimeError(f"Could not decode preview {path}: {decoded.stderr.decode(errors='replace')}")
    wave = np.frombuffer(decoded.stdout, dtype="<f4")
    if not wave.size or not np.isfinite(wave).all():
        raise RuntimeError(f"Invalid preview waveform: {path}")
    peak, rms = float(np.max(np.abs(wave))), float(np.sqrt(np.mean(wave ** 2)))
    if rms < .002 or peak >= .999:
        raise RuntimeError(f"Silent/clipped preview: {path} (rms={rms:.4f}, peak={peak:.4f})")
    return dict(duration=round(duration, 3), peak=round(peak, 4), rms=round(rms, 4), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-root", type=Path, required=True, help="Existing verified model packs")
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.models_root.is_dir():
        parser.error("--models-root must be an existing directory; no models are downloaded")
    sys.path.insert(0, str(ROOT / "src"))
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vieneu-samples-", dir=ROOT / "build") as temporary:
        os.environ.update(HFLOW_SMOKE_TEST="1", HFLOW_HOME=temporary,
                          RUNTIME_DATA_DIR=str(Path(temporary) / "data"), MODELS_DIR=str(args.models_root.resolve()),
                          HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        from hflow import config

        # Development-only shared read-only models; keep all mutable runtime
        # data under the temporary home instead of relaxing production paths.
        config.MODELS_DIR = str(args.models_root.resolve())
        from hflow.core.vieneu_voices import VIENEU_VOICES, sample_voice_id
        from hflow.pipeline.vieneu_tts import synthesize_batch_to_mp3

        samples = ROOT / "src/hflow/desktop/assets/voice_samples"
        manifest = json.loads((samples / "samples.json").read_text(encoding="utf-8"))
        requests = []
        entries = []
        for name, gender, region in VIENEU_VOICES:
            voice = "vieneu:" + name
            path = samples / "vieneu" / sample_voice_id(voice) / "vi.mp3"
            path.parent.mkdir(parents=True, exist_ok=True)
            entries.append(dict(provider="vieneu", voice=voice, language="vi", category="natural",
                                gender=gender, region=region, path=path.relative_to(samples).as_posix()))
            valid = False
            if path.is_file() and not args.force:
                try:
                    sample_details(path)
                    valid = True
                except RuntimeError:
                    pass
            if not valid:
                requests.append(dict(text=manifest["sentences"]["vi"], voice=voice, output_path=str(path)))
        if requests:
            synthesize_batch_to_mp3(requests, "vieneu-packaged-sample", language_id="vi", device=args.device,
                                    progress_callback=lambda done, total, stage:
                                    print(f"[{done}/{total}] {stage}", flush=True))
        for entry in entries:
            details = sample_details(samples / entry["path"])
            print(json.dumps({**entry, **details}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
