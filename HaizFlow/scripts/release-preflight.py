"""Calculate and validate disk space required to install a frozen artifact."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from haizflow.services.model_bootstrap import (  # noqa: E402
    DOWNLOAD_HEADROOM_BYTES,
    required_download_bytes,
)


GIB = 1024**3
WORKING_HEADROOM_BYTES = 2 * GIB
FIRST_RUN_MODEL_BYTES = max(
    required_download_bytes("cpu"),
    required_download_bytes("gpu"),
)


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def requirements(artifact: Path, *, upgrade: bool) -> dict[str, int | bool]:
    artifact_bytes = directory_size(artifact)
    # An upgrade can temporarily hold the previous installation and the staged
    # replacement. Models are fetched after first launch rather than embedded
    # in the installer, but they still live on the selected installation drive
    # and are required for a usable installation. Reserve the larger CPU/GPU
    # first-run set plus the bootstrap's atomic-download headroom so setup
    # cannot succeed only to run out of space during model installation.
    installation_copies = 2 if upgrade else 1
    required_free_bytes = (
        artifact_bytes * installation_copies + FIRST_RUN_MODEL_BYTES + DOWNLOAD_HEADROOM_BYTES + WORKING_HEADROOM_BYTES
    )
    return {
        "artifact_bytes": artifact_bytes,
        "installation_copies": installation_copies,
        "first_run_model_bytes": FIRST_RUN_MODEL_BYTES,
        "model_download_headroom_bytes": DOWNLOAD_HEADROOM_BYTES,
        "working_headroom_bytes": WORKING_HEADROOM_BYTES,
        "required_free_bytes": required_free_bytes,
        "upgrade": upgrade,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate release disk requirements from the actual artifact size.")
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--target-directory", type=Path)
    parser.add_argument("--fresh-install", action="store_true")
    parser.add_argument("--write", type=Path, help="Write the calculated requirements as JSON.")
    args = parser.parse_args(argv)

    artifact = args.artifact.resolve()
    if not (artifact / "HaizFlow.exe").is_file():
        raise SystemExit(f"Frozen artifact is missing HaizFlow.exe: {artifact}")
    payload = requirements(artifact, upgrade=not args.fresh_install)
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.target_directory:
        target = args.target_directory.resolve()
        target.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(target).free
        payload["target_directory"] = str(target)
        payload["available_free_bytes"] = free
        if free < payload["required_free_bytes"]:
            raise SystemExit(
                f"Insufficient disk space at {target}: need {payload['required_free_bytes'] / GIB:.1f} GB, "
                f"have {free / GIB:.1f} GB."
            )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
