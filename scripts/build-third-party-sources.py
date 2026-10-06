"""Create a checksum-inventoried source asset from the reviewed build inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(output: Path) -> dict:
    output = output.resolve()
    if not output.is_relative_to(ROOT / "dist"):
        raise ValueError("Source release output must remain below dist/.")
    groups = {
        "ffmpeg-cli": ROOT / "build/ffmpeg-release-inputs/sources",
        "ffmpeg-engine": ROOT / "build/engine-ffmpeg-release-inputs/sources",
        "qt-pyside": ROOT / "build/qt-source-evidence",
        "licenses": ROOT / "licenses",
    }
    for name, directory in groups.items():
        if not directory.is_dir() or not any(directory.iterdir()):
            raise ValueError(f"Missing source material: {name}")
    for path in (ROOT / "build/ffmpeg-release-inputs/closure.json",
                 ROOT / "build/engine-ffmpeg-release-inputs/closure.json"):
        closure = json.loads(path.read_text(encoding="utf-8"))
        for row in closure["sources"]:
            file = path.parent / "sources" / row["file"]
            if Path(row["file"]).name != row["file"] or digest(file) != row["sha256"]:
                raise ValueError("Collected source archive differs from its inventory.")
    qt = groups["qt-pyside"]
    for row in json.loads((qt / "upstream-sources.json").read_text(encoding="utf-8"))["sources"]:
        if digest(qt / row["file"]) != row["sha256"]:
            raise ValueError("Qt source archive differs from the published checksum.")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
        for name, directory in groups.items():
            for file in sorted(directory.rglob("*")):
                if file.is_symlink() or file.is_junction():
                    raise ValueError("Source bundle cannot include filesystem links.")
                if file.is_file():
                    relative = f"{name}/{file.relative_to(directory).as_posix()}"
                    bundle.write(file, relative)
                    rows.append(dict(file=relative, size=file.stat().st_size, sha256=digest(file)))
        for relative in ("scripts/ffmpeg/build-msys2.sh", "scripts/ffmpeg/build-engine-msys2.sh",
                         "scripts/package-engine-media.py", "scripts/collect-built-ffmpeg.py",
                         "docs/third-party-library-replacement.md", "docs/media-builds.md",
                         "runtime/ffmpeg-manifest.json", "runtime/engine-ffmpeg-manifest.json",
                         "NOTICE", "LICENSE"):
            file = ROOT / relative
            bundle.write(file, relative)
            rows.append(dict(file=relative, size=file.stat().st_size, sha256=digest(file)))
        for name in ("ffmpeg-release-inputs", "engine-ffmpeg-release-inputs"):
            file = ROOT / "build" / name / "closure.json"
            relative = name + "/closure.json"
            bundle.write(file, relative)
            rows.append(dict(file=relative, size=file.stat().st_size, sha256=digest(file)))
        inventory = dict(schema=1, release_version="0.1.0", files=rows)
        bundle.writestr("SOURCE-INVENTORY.json", json.dumps(inventory, indent=2) + "\n")
    with zipfile.ZipFile(output) as bundle:
        if bundle.testzip():
            raise ValueError("Source asset ZIP verification failed.")
    result = dict(schema=1, release_version="0.1.0", file=output.name,
                  sha256=digest(output), size=output.stat().st_size,
                  url="https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.0/" + output.name,
                  files=rows)
    manifest = output.with_suffix(".json")
    manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/release-sources/HaizFlow-0.1.0-ThirdPartySources.zip")
    build(parser.parse_args().output)
