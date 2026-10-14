"""Stage the small checksum-pinned CPU voice-profile model; never build the app."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hflow.core.voice_profile_model import (  # noqa: E402
    MODEL_FILE, MODEL_SIZE, MODEL_SHA256, MODEL_URL, verify_voice_profile,
)
from hflow.services.model_bootstrap import ModelAsset, install_model_assets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    destination = ROOT / "build/bundled-models/speaker-identification"
    source = args.source or destination
    if not (source / MODEL_FILE).is_file():
        if not args.download:
            parser.error("Voice profile model missing; supply --source or --download.")
        asset = ModelAsset("speaker-identification", "Voice profile", MODEL_URL,
                           "speaker-identification/" + MODEL_FILE, MODEL_SIZE, MODEL_SHA256)
        install_model_assets(destination.parent, (asset,), progress=lambda event: None)
        source = destination
    original = verify_voice_profile(source)
    destination.mkdir(parents=True, exist_ok=True)
    if original.resolve() != (destination / MODEL_FILE).resolve():
        shutil.copyfile(original, destination / MODEL_FILE)
    print(verify_voice_profile(destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
