"""Acceptance checks executed by the frozen release artifact itself."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from haizflow.core.paths import bundle_root, project_root


def _check(condition: bool, message: str, failures: list[str], details: list[str]) -> None:
    details.append(message)
    if not condition:
        failures.append(message)


def _run_native_tool(path: Path) -> bool:
    try:
        completed = subprocess.run(
            [str(path), "-version"],
            capture_output=True,
            timeout=20,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_release_smoke(
    *,
    pre_finalize: bool = False,
) -> dict[str, object]:
    failures: list[str] = []
    details: list[str] = []
    bundle = bundle_root()
    artifact = project_root()

    _check(bool(getattr(sys, "frozen", False)), "Running from a frozen executable", failures, details)
    _check((bundle / "haizflow" / "desktop" / "qml" / "Main.qml").is_file(), "QML bundle", failures, details)

    for executable in ("ffmpeg.exe", "ffprobe.exe"):
        path = bundle / "bin" / executable
        _check(path.is_file(), f"Bundled {executable}", failures, details)
        if path.is_file():
            _check(_run_native_tool(path), f"Executable {executable}", failures, details)

    ffmpeg_manifest_path = artifact / "FFMPEG-MANIFEST.json"
    try:
        ffmpeg_manifest = json.loads(ffmpeg_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ffmpeg_manifest = {}
        failures.append(f"FFmpeg manifest failed: {type(exc).__name__}: {exc}")
    _check(ffmpeg_manifest.get("version") == "8.1.2", "Pinned FFmpeg 8.1.2", failures, details)
    for executable in ("ffmpeg.exe", "ffprobe.exe"):
        path = bundle / "bin" / executable
        expected = ffmpeg_manifest.get(executable.removesuffix(".exe") + "_sha256")
        _check(path.is_file() and bool(expected) and _sha256(path) == expected, f"Checksum {executable}", failures, details)
    for filename, hash_key in (
        ("ffmpeg-8.1.2.tar.xz", "source_sha256"),
        ("ffmpeg-8.1.2.tar.xz.asc", "source_signature_sha256"),
    ):
        path = artifact / "sources" / "ffmpeg" / filename
        expected = ffmpeg_manifest.get(hash_key)
        _check(path.is_file() and bool(expected) and _sha256(path) == expected, f"FFmpeg source: {filename}", failures, details)

    release_files = [
        (artifact / "LICENSE.txt", "Application license"),
        (artifact / "NOTICE.txt", "Application notice"),
        (artifact / "THIRD_PARTY_NOTICES.md", "Third-party notices"),
        (artifact / "licenses", "Third-party license directory"),
        (artifact / "sources" / "ffmpeg" / "LICENSE.txt", "FFmpeg package license"),
        (artifact / "sources" / "ffmpeg" / "README.txt", "FFmpeg package build information"),
    ]
    if not pre_finalize:
        release_files.extend(
            (
                (artifact / "BUILD-INFO.json", "Build metadata"),
                (artifact / "SHA256SUMS.txt", "Artifact checksum manifest"),
            )
        )
    for path, label in release_files:
        _check(path.exists(), label, failures, details)
    _check(
        not (artifact / "runtime").exists(),
        "Mutable root runtime excluded from frozen artifact",
        failures,
        details,
    )

    try:
        from PySide6 import QtCore, QtMultimedia, QtQml, QtQuick  # noqa: F401

        details.append("Qt Core/QML/Quick/Multimedia imports")
    except Exception as exc:
        failures.append(f"Qt runtime import failed: {type(exc).__name__}: {exc}")

    bundled_model_files = (
        list((bundle / "models").rglob("*")) if (bundle / "models").exists() else []
    )
    _check(
        not any(path.is_file() for path in bundled_model_files),
        "Model payload excluded from frozen artifact",
        failures,
        details,
    )
    try:
        from haizflow.core.model_integrity import (
            ALIGNMENT_MODELS,
            DEMUCS_MODEL_FILE,
            DEMUCS_MODEL_SIZE,
            HYMT2_CPU_FILE,
            HYMT2_GPU_FILES,
            WHISPER_FILES,
            WHISPERX_VAD_FILE,
            WHISPERX_VAD_SIZE,
        )
        from haizflow.services.model_bootstrap import required_assets

        cpu_assets = required_assets("cpu")
        gpu_assets = required_assets("gpu")
        forbidden_model_files = {
            (filename.lower(), size)
            for filename, (size, _digest) in {**WHISPER_FILES, **HYMT2_GPU_FILES}.items()
        }
        forbidden_model_files.update(
            {
                (HYMT2_CPU_FILE.lower(), 1_133_080_448),
                (DEMUCS_MODEL_FILE.lower(), DEMUCS_MODEL_SIZE),
                (WHISPERX_VAD_FILE.lower(), WHISPERX_VAD_SIZE),
                *(
                    (filename.lower(), size)
                    for _bundle, filename, size, _digest in ALIGNMENT_MODELS.values()
                ),
            }
        )
        accidental_models = [
            path
            for path in bundle.rglob("*")
            if path.is_file() and (path.name.lower(), path.stat().st_size) in forbidden_model_files
        ]
        bootstrap_manifest_valid = (
            bool(cpu_assets)
            and bool(gpu_assets)
            and not accidental_models
            and all(asset.url.startswith("https://") for asset in (*cpu_assets, *gpu_assets))
            and all(len(asset.sha256) == 64 and asset.size > 0 for asset in (*cpu_assets, *gpu_assets))
        )
    except Exception as exc:
        bootstrap_manifest_valid = False
        failures.append(f"Model bootstrap import failed: {type(exc).__name__}: {exc}")
    _check(
        bootstrap_manifest_valid,
        "Pinned first-run model bootstrap manifest",
        failures,
        details,
    )

    return {
        "event": "release_smoke",
        "ok": not failures,
        "failures": failures,
        "details": details,
        "artifact": str(artifact),
        "bundle": str(bundle),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-finalize", action="store_true")
    args = parser.parse_args(argv)
    result = run_release_smoke(
        pre_finalize=args.pre_finalize,
    )
    if sys.stdout is not None:
        print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
