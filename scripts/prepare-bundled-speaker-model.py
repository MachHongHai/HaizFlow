"""Stage only the checksum-pinned, immutable speaker model for Core packaging."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haizflow.pipeline.speaker_identity import MODEL_FILE, model_root, verify_model  # noqa: E402
from haizflow.services.model_bootstrap import install_model_assets  # noqa: E402
from haizflow.services.resource_packs import _speaker_asset  # noqa: E402


def stage(source: Path, destination: Path) -> Path:
    original = verify_model(source)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / MODEL_FILE
    if original.resolve() != target.resolve():
        shutil.copyfile(original, target)
    return verify_model(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "build" / "bundled-models" / "speaker-identification"
    source = args.source or model_root()
    if not (source / MODEL_FILE).is_file():
        if not args.download:
            parser.error("Speaker model is missing; supply --source or --download.")
        install_model_assets(destination.parent, (_speaker_asset(),), progress=lambda event: None)
        source = destination
    print(stage(source, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
