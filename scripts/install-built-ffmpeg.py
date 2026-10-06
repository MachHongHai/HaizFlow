"""Validate and install a locally collected media runtime, preserving a backup."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate(inputs: Path) -> dict:
    inputs = inputs.resolve()
    report = json.loads((inputs / "closure.json").read_text(encoding="utf-8"))
    if report.get("variant") != "haizflow" or report.get("version") != "8.1.2":
        raise ValueError("Unexpected media build identity.")
    for section, directory in (("binaries", "bin"), ("sources", "sources")):
        for row in report[section]:
            file = inputs / directory / row["file"]
            if Path(row["file"]).name != row["file"] or file.is_symlink() or not file.is_file():
                raise ValueError("Unsafe or missing media input.")
            if digest(file) != row["sha256"] or file.stat().st_size != row["size"]:
                raise ValueError(f"Media input differs from its collected evidence: {file.name}")
    subprocess.run([str(ROOT / ".venv/Scripts/python.exe"),
                    str(ROOT / "scripts/test-ffmpeg-runtime.py"), "--bin-directory", str(inputs / "bin")],
                   check=True)
    return report


def install(inputs: Path) -> None:
    inputs = inputs.resolve()
    report = validate(inputs)
    backup = ROOT / "build/media-runtime-backups" / uuid.uuid4().hex
    backup.mkdir(parents=True)
    binary_directory = ROOT / "runtime/bin"
    binary_directory.mkdir(parents=True, exist_ok=True)
    if (ROOT / "runtime/ffmpeg-manifest.json").is_file():
        shutil.copy2(ROOT / "runtime/ffmpeg-manifest.json", backup / "ffmpeg-manifest.json")
    for row in report["binaries"]:
        destination = binary_directory / row["file"]
        if destination.exists():
            shutil.copy2(destination, backup / destination.name)
        shutil.copy2(inputs / "bin" / row["file"], destination)
    compliance = ROOT / "runtime/compliance/ffmpeg"
    compliance.mkdir(parents=True, exist_ok=True)
    shutil.copy2(inputs / "closure.json", compliance / "closure.json")
    for name in ("ffmpeg-8.1.2.tar.xz", "ffmpeg-8.1.2.tar.xz.asc", "config.log", "config.h",
                 "config.mak", "toolchain-packages.txt", "compiler-version.txt", "build-msys2.sh"):
        shutil.copy2(inputs / "sources" / name, compliance / name)
    shutil.copy2(ROOT / "licenses/GPL-3.0.txt", compliance / "LICENSE.txt")
    shutil.copy2(ROOT / "licenses/FFmpeg-NOTICE.md", compliance / "README.txt")
    binaries = {row["file"]: row for row in report["binaries"]}
    source_rows = {row["file"]: row for row in report["sources"]}
    result = subprocess.run([str(binary_directory / "ffmpeg.exe"), "-version"], check=True,
                            capture_output=True, text=True, encoding="utf-8")
    manifest = dict(version="8.1.2", variant="haizflow", architecture="windows-x64",
                    license="GPL-3.0-or-later configured CLI build",
                    build_recipe="scripts/ffmpeg/build-msys2.sh",
                    source_url="https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz",
                    source_sha256=source_rows["ffmpeg-8.1.2.tar.xz"]["sha256"],
                    source_signature_url="https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz.asc",
                    source_signature_sha256=source_rows["ffmpeg-8.1.2.tar.xz.asc"]["sha256"],
                    ffmpeg_sha256=binaries["ffmpeg.exe"]["sha256"],
                    ffprobe_sha256=binaries["ffprobe.exe"]["sha256"],
                    version_line=result.stdout.splitlines()[0],
                    required_configuration=["--enable-gpl", "--enable-libass", "--enable-librubberband", "--enable-libx264", "--enable-libmp3lame"],
                    required_filters=["adelay", "amix", "ass", "atempo"], required_encoders=["libx264", "libmp3lame"],
                    runtime_files=report["binaries"], corresponding_source_manifest_sha256=digest(inputs / "closure.json"))
    (ROOT / "runtime/ffmpeg-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Installed verified media runtime. Previous files preserved at {backup}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=ROOT / "build/ffmpeg-release-inputs")
    install(parser.parse_args().inputs)
