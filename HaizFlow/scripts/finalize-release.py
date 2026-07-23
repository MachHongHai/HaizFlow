"""Create release metadata and a SHA-256 manifest for a frozen artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _git_value(*arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(artifact_directory: Path) -> None:
    artifact = artifact_directory.resolve()
    manifest_path = artifact / "SHA256SUMS.txt"
    if not manifest_path.is_file():
        raise RuntimeError(f"Release checksum manifest is missing: {manifest_path}")
    expected: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition(" *")
        if not separator or len(digest) != 64 or not relative:
            raise RuntimeError(f"Invalid checksum manifest line: {line!r}")
        if relative in expected:
            raise RuntimeError(f"Duplicate checksum manifest entry: {relative}")
        expected[relative] = digest
    actual = {
        path.relative_to(artifact).as_posix(): path
        for path in artifact.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if set(expected) != set(actual):
        missing = sorted(set(actual) - set(expected))
        stale = sorted(set(expected) - set(actual))
        raise RuntimeError(f"Checksum manifest file set mismatch; missing={missing[:3]}, stale={stale[:3]}")
    for relative, path in actual.items():
        if _sha256(path) != expected[relative]:
            raise RuntimeError(f"Checksum mismatch: {relative}")
    print(f"Release manifest verified: {len(actual)} files", flush=True)


def _release_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def _read_build_info(artifact: Path) -> dict[str, object]:
    path = artifact / "BUILD-INFO.json"
    if not path.is_file():
        raise RuntimeError(f"Release build metadata is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Release build metadata is invalid: {path}") from error
    if not isinstance(value, dict):
        raise RuntimeError("Release build metadata must be a JSON object.")
    return value


def _require_build_value(build_info: dict[str, object], name: str, expected: object) -> None:
    if build_info.get(name) != expected:
        raise RuntimeError(
            f"Release build metadata is not eligible for installer packaging: "
            f"{name}={build_info.get(name)!r}, expected {expected!r}"
        )


def verify_installer_eligibility(artifact_directory: Path) -> None:
    """Reject a stale, partial, dirty, or differently-versioned frozen build.

    A checksum proves files did not change after finalization. This gate also
    proves that they were finalised from this clean source revision and carry
    every offline model component promised by the installer.
    """
    artifact = artifact_directory.resolve()
    verify_manifest(artifact)
    build_info = _read_build_info(artifact)

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from haizflow.core.model_integrity import HYMT2_CPU_FILE, HYMT2_CPU_REVISION, HYMT2_GPU_REVISION, WHISPER_REVISION

    current_commit = _git_value("rev-parse", "HEAD")
    current_status = _git_value("status", "--porcelain")
    if current_commit == "unknown":
        raise RuntimeError("Cannot establish the current Git commit; refusing installer packaging.")
    if current_status == "unknown":
        raise RuntimeError("Cannot establish Git worktree status; refusing installer packaging.")
    if current_status:
        raise RuntimeError("Git worktree is dirty; refusing installer packaging.")

    for name, expected in (
        ("application", "HaizFlow"),
        ("version", _release_version()),
        ("git_commit", current_commit),
        ("git_dirty", False),
        ("packaging", "PyInstaller onedir"),
        ("bundled_cpu_model", True),
        ("bundled_gpu_model", True),
        ("bundled_whisper_model", True),
        ("hymt2_cpu_revision", HYMT2_CPU_REVISION),
        ("hymt2_gpu_revision", HYMT2_GPU_REVISION),
        ("whisper_revision", WHISPER_REVISION),
    ):
        _require_build_value(build_info, name, expected)

    required_paths = (
        artifact / "HaizFlow.exe",
        artifact / "_internal" / "models" / "whisper" / "small" / "model.bin",
        artifact / "_internal" / "models" / "hymt2-gguf" / HYMT2_CPU_FILE,
        artifact / "_internal" / "models" / "hymt2-transformers" / "config.json",
    )
    missing = [str(path.relative_to(artifact)) for path in required_paths if not path.is_file()]
    gpu_weights = list((artifact / "_internal" / "models" / "hymt2-transformers").glob("*.safetensors"))
    if missing or not gpu_weights:
        details = missing + ([] if gpu_weights else ["_internal/models/hymt2-transformers/*.safetensors"])
        raise RuntimeError(f"Required bundled model payload is missing: {', '.join(details)}")
    print("Release artifact is eligible for installer packaging.", flush=True)


def finalize(artifact_directory: Path, *, cpu_model: bool, gpu_model: bool, whisper_model: bool) -> None:
    artifact = artifact_directory.resolve()
    executable = artifact / "HaizFlow.exe"
    if not executable.is_file():
        raise RuntimeError(f"Frozen executable is missing: {executable}")

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from haizflow.core.model_integrity import HYMT2_CPU_REVISION, HYMT2_GPU_REVISION, WHISPER_REVISION

    version = _release_version()
    build_info = {
        "application": "HaizFlow",
        "version": version,
        "built_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("branch", "--show-current"),
        "git_dirty": bool(_git_value("status", "--porcelain")),
        "python": sys.version.split()[0],
        "bundled_cpu_model": cpu_model,
        "bundled_gpu_model": gpu_model,
        "bundled_whisper_model": whisper_model,
        "hymt2_cpu_revision": HYMT2_CPU_REVISION,
        "hymt2_gpu_revision": HYMT2_GPU_REVISION,
        "whisper_revision": WHISPER_REVISION,
        "packaging": "PyInstaller onedir",
    }
    (artifact / "BUILD-INFO.json").write_text(
        json.dumps(build_info, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_path = artifact / "SHA256SUMS.txt"
    files = sorted(
        (path for path in artifact.rglob("*") if path.is_file() and path != manifest_path),
        key=lambda path: path.relative_to(artifact).as_posix().lower(),
    )
    lines = []
    for index, path in enumerate(files, start=1):
        relative = path.relative_to(artifact).as_posix()
        lines.append(f"{_sha256(path)} *{relative}")
        if index % 500 == 0:
            print(f"Hashed {index}/{len(files)} release files", flush=True)
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Release metadata finalized: {len(files)} files", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--cpu-model", action="store_true")
    parser.add_argument("--gpu-model", action="store_true")
    parser.add_argument("--whisper-model", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--verify-installer-eligibility", action="store_true")
    args = parser.parse_args(argv)
    if args.verify and args.verify_installer_eligibility:
        parser.error("--verify and --verify-installer-eligibility cannot be combined")
    if args.verify:
        verify_manifest(args.artifact)
    elif args.verify_installer_eligibility:
        verify_installer_eligibility(args.artifact)
    else:
        finalize(
            args.artifact,
            cpu_model=args.cpu_model,
            gpu_model=args.gpu_model,
            whisper_model=args.whisper_model,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
