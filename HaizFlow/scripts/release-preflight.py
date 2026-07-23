"""Calculate and validate disk space required to install a frozen artifact."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


GIB = 1024**3
WORKING_HEADROOM_BYTES = 2 * GIB


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def requirements(artifact: Path, *, upgrade: bool) -> dict[str, int | bool]:
    artifact_bytes = directory_size(artifact)
    # An upgrade can temporarily hold the previous installation and the staged
    # replacement. Reserve both copies plus workspace/cache headroom.
    installation_copies = 2 if upgrade else 1
    required_free_bytes = artifact_bytes * installation_copies + WORKING_HEADROOM_BYTES
    return {
        "artifact_bytes": artifact_bytes,
        "installation_copies": installation_copies,
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
