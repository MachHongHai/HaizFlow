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

from haizflow.core.storage_policy import MINIMUM_OPERATIONAL_FREE_BYTES  # noqa: E402


GIB = 1024**3
WORKING_HEADROOM_BYTES = MINIMUM_OPERATIONAL_FREE_BYTES
RECOMMENDED_HEADROOM_BYTES = 4 * GIB


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def requirements_for_size(artifact_bytes: int, *, upgrade: bool) -> dict[str, int | bool]:
    # Optional engines/models have their own preflight in Resource Manager.
    # Core setup only reserves the final files (and the old copy on upgrade)
    # plus 2 GiB that remains available after installation.
    installation_copies = 2 if upgrade else 1
    staging_bytes = 0
    required_free_bytes = artifact_bytes * installation_copies + staging_bytes + WORKING_HEADROOM_BYTES
    recommended_free_bytes = max(required_free_bytes, RECOMMENDED_HEADROOM_BYTES)
    return {
        "artifact_bytes": artifact_bytes,
        "installation_copies": installation_copies,
        "cpu_first_run_model_bytes": 0,
        "gpu_first_run_model_bytes": 0,
        "first_run_model_bytes": 0,
        "model_download_headroom_bytes": 0,
        "staging_bytes": staging_bytes,
        "working_headroom_bytes": WORKING_HEADROOM_BYTES,
        "project_reserve_bytes": 0,
        "resource_packs_included": False,
        "required_free_bytes": required_free_bytes,
        "recommended_free_bytes": recommended_free_bytes,
        "upgrade": upgrade,
    }


def requirements(artifact: Path, *, upgrade: bool) -> dict[str, int | bool]:
    return requirements_for_size(directory_size(artifact), upgrade=upgrade)


def requirements_with_embedded_manifest(
    artifact: Path,
    manifest_path: Path,
    *,
    upgrade: bool,
) -> tuple[dict[str, int | bool], str]:
    """Return a stable payload whose byte count includes its own JSON file."""

    artifact = artifact.resolve()
    manifest_path = manifest_path.resolve()
    try:
        manifest_path.relative_to(artifact)
    except ValueError:
        payload = requirements(artifact, upgrade=upgrade)
        return payload, json.dumps(payload, indent=2) + "\n"

    existing_size = manifest_path.stat().st_size if manifest_path.is_file() else 0
    base_size = directory_size(artifact) - existing_size
    manifest_size = existing_size
    for _ in range(16):
        payload = requirements_for_size(base_size + manifest_size, upgrade=upgrade)
        serialized = json.dumps(payload, indent=2) + "\n"
        next_size = len(serialized.encode("utf-8"))
        if next_size == manifest_size:
            return payload, serialized
        manifest_size = next_size
    raise RuntimeError("Embedded install-requirements manifest did not converge.")


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
    if args.write:
        payload, serialized_payload = requirements_with_embedded_manifest(
            artifact,
            args.write,
            upgrade=not args.fresh_install,
        )
    else:
        payload = requirements(artifact, upgrade=not args.fresh_install)
        serialized_payload = ""
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        # Force LF so the byte count used by the self-inclusive calculation is
        # identical on Windows instead of being expanded to CRLF on write.
        args.write.write_text(serialized_payload, encoding="utf-8", newline="\n")
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
