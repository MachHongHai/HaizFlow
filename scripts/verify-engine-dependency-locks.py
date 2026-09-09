#!/usr/bin/env python3
"""Validate reproducible dependency locks for every external engine profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("cpu", "cuda128", "vision")
HASH_PATTERN = re.compile(r"--hash=sha256:([0-9a-f]{64})(?:\s|$)")
FORBIDDEN_VISION = {
    "torch",
    "torchaudio",
    "torchvision",
    "whisperx",
    "transformers",
    "demucs",
    "ctranslate2",
    "llama-cpp-python",
}
INTENTIONALLY_OMITTED_BUILD_PACKAGES = {"setuptools", "wheel"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _logical_requirements(path: Path) -> list[str]:
    logical: list[str] = []
    current = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("--") and not current:
            continue
        current = f"{current} {stripped}".strip()
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        logical.append(current)
        current = ""
    if current:
        logical.append(current)
    return logical


def _parse_lock(path: Path) -> dict[str, Requirement]:
    locked: dict[str, Requirement] = {}
    for logical in _logical_requirements(path):
        requirement_text = logical.split(" --hash=", 1)[0].strip()
        requirement = Requirement(requirement_text)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        versions = [item.version for item in requirement.specifier if item.operator == "=="]
        if len(versions) != 1 or len(list(requirement.specifier)) != 1:
            raise RuntimeError(f"{path.name} contains a non-exact entry: {requirement_text}")
        if not HASH_PATTERN.search(logical):
            raise RuntimeError(f"{path.name} contains an unhashed entry: {requirement_text}")
        name = canonicalize_name(requirement.name)
        if name in locked:
            raise RuntimeError(f"{path.name} contains duplicate package {requirement.name}.")
        locked[name] = requirement
    if not locked:
        raise RuntimeError(f"{path.name} contains no installable requirements.")
    return locked


def _direct_requirements(path: Path) -> dict[str, Requirement]:
    values: dict[str, Requirement] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "--")):
            continue
        requirement = Requirement(stripped)
        values[canonicalize_name(requirement.name)] = requirement
    return values


def validate() -> dict:
    build_input = ROOT / "requirements-build.in"
    common_input = ROOT / "requirements-engine-common.in"
    if not common_input.is_file():
        raise RuntimeError("The shared engine dependency input is missing.")
    inputs: dict[str, str] = {
        build_input.name: _sha256(build_input),
        common_input.name: _sha256(common_input),
    }
    locks: dict[str, dict] = {}
    for profile in PROFILES:
        input_path = ROOT / f"requirements-engine-{profile}.in"
        lock_path = ROOT / f"requirements-lock-engine-{profile}-py313-win64.txt"
        if not input_path.is_file() or not lock_path.is_file():
            raise RuntimeError(f"The {profile} engine input or lock is missing.")
        locked = _parse_lock(lock_path)
        direct = {
            **_direct_requirements(build_input),
            **_direct_requirements(common_input),
            **_direct_requirements(input_path),
        }
        direct = {name: value for name, value in direct.items() if name not in INTENTIONALLY_OMITTED_BUILD_PACKAGES}
        for name, requirement in direct.items():
            resolved = locked.get(name)
            if resolved is None:
                raise RuntimeError(f"{lock_path.name} does not contain direct dependency {requirement.name}.")
            locked_version = next(item.version for item in resolved.specifier if item.operator == "==")
            if locked_version not in requirement.specifier:
                raise RuntimeError(
                    f"{lock_path.name} resolves {requirement.name} to {locked_version}, "
                    f"outside {requirement.specifier}."
                )
        if profile == "vision":
            forbidden = FORBIDDEN_VISION.intersection(locked)
            if forbidden:
                raise RuntimeError("Vision engine lock contains AI compute packages: " + ", ".join(sorted(forbidden)))
        if "pyside6" in locked:
            raise RuntimeError(f"{lock_path.name} must not contain the Qt desktop runtime.")
        if profile == "cpu":
            torch_version = next(item.version for item in locked["torch"].specifier if item.operator == "==")
            if not torch_version.endswith("+cpu"):
                raise RuntimeError(f"CPU engine must lock the +cpu Torch wheel, found {torch_version}.")
        if profile == "cuda128":
            torch_version = next(item.version for item in locked["torch"].specifier if item.operator == "==")
            if not torch_version.endswith("+cu128"):
                raise RuntimeError(f"CUDA engine must lock the +cu128 Torch wheel, found {torch_version}.")
        inputs[input_path.name] = _sha256(input_path)
        locks[profile] = {
            "file": lock_path.name,
            "sha256": _sha256(lock_path),
            "packages": len(locked),
        }
    return {
        "schema_version": 1,
        "target": "windows-x86_64-python-3.13",
        "inputs": dict(sorted(inputs.items())),
        "locks": locks,
    }


def _write_atomic(path: Path, payload: dict) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "engine-dependency-lock-manifest.json")
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    actual = validate()
    manifest_path = args.manifest.resolve()
    if args.write_manifest:
        _write_atomic(manifest_path, actual)
    else:
        try:
            expected = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Engine dependency lock manifest is missing or invalid: {manifest_path}") from exc
        if actual != expected:
            raise RuntimeError("Engine dependency inputs or locks changed; regenerate and review the engine locks.")
    print(json.dumps(actual, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
