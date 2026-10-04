"""Bind each independent bootstrap to its source commit and exact file inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.update.filesystem import no_links  # noqa: E402

ENTRIES = {"HaizFlow.exe": "launcher", "HaizFlowUpdater.exe": "updater"}


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", timeout=15, check=True)
    return result.stdout.strip()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def check_tree(artifact: Path, entrypoint: str) -> None:
    no_links(artifact)
    if entrypoint not in ENTRIES or not (artifact / entrypoint).is_file() or not (artifact / "_internal").is_dir():
        raise ValueError("Independent bootstrap payload is incomplete.")
    if any((artifact / name).exists() for name in ("runtime", "update-state")):
        raise ValueError("Bootstrap contains mutable user data.")
    if any(path.name.lower().startswith(("pyside6", "torch")) for path in artifact.rglob("*")):
        raise ValueError("Bootstrap must not depend on GUI or AI runtimes.")


def verify(artifact: Path, entrypoint: str, *, source_commit: str, version: str, engineering: bool) -> None:
    check_tree(artifact, entrypoint)
    metadata = json.loads((artifact / "BOOTSTRAP-INFO.json").read_text(encoding="utf-8"))
    expected = dict(schema=1, application="HaizFlow", entrypoint=entrypoint,
                    kind=ENTRIES[entrypoint], version=version, git_commit=source_commit,
                    engineering=engineering, packaging="PyInstaller onedir")
    if not isinstance(metadata, dict) or any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("Bootstrap provenance differs from the Core release.")
    if type(metadata.get("git_dirty")) is not bool or (metadata["git_dirty"] and not engineering):
        raise ValueError("Public bootstrap has dirty or missing source provenance.")
    manifest = artifact / "SHA256SUMS.txt"
    expected_files = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        checksum, separator, name = line.partition(" *")
        if not separator or len(checksum) != 64 or not name or name in expected_files:
            raise ValueError("Invalid bootstrap checksum manifest.")
        expected_files[name] = checksum
    actual_files = {path.relative_to(artifact).as_posix(): digest(path)
                    for path in artifact.rglob("*") if path.is_file() and path != manifest}
    if not expected_files or actual_files != expected_files:
        raise ValueError("Bootstrap checksum or file inventory mismatch.")


def finalize(artifact: Path, entrypoint: str, *, source_commit: str, engineering: bool) -> None:
    check_tree(artifact, entrypoint)
    if git("rev-parse", "HEAD") != source_commit:
        raise ValueError("Source commit changed during the bootstrap build.")
    dirty = bool(git("status", "--porcelain"))
    if dirty and not engineering:
        raise ValueError("Public bootstrap requires a clean source checkout.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    metadata = dict(schema=1, application="HaizFlow", entrypoint=entrypoint,
                    kind=ENTRIES[entrypoint], version=version, git_commit=source_commit,
                    git_dirty=dirty, engineering=engineering, packaging="PyInstaller onedir")
    (artifact / "BOOTSTRAP-INFO.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n")
    manifest = artifact / "SHA256SUMS.txt"
    paths = sorted(path for path in artifact.rglob("*") if path.is_file() and path != manifest)
    manifest.write_text("".join(f"{digest(path)} *{path.relative_to(artifact).as_posix()}\n" for path in paths),
                        encoding="utf-8", newline="\n")
    verify(artifact, entrypoint, source_commit=source_commit, version=version, engineering=engineering)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--entrypoint", choices=ENTRIES, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--engineering", action="store_true")
    args = parser.parse_args()
    finalize(args.artifact.resolve(), args.entrypoint, source_commit=args.source_commit, engineering=args.engineering)
