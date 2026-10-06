"""Verify the exact corresponding-source asset required by public builds."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(root: Path = ROOT) -> None:
    manifest = json.loads((root / "runtime/third-party-sources-manifest.json").read_text(encoding="utf-8"))
    filename = manifest["file"]
    release = str(manifest.get("release_version") or "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", release) or filename != f"HaizFlow-{release}-ThirdPartySources.zip":
        raise ValueError("Unexpected source release identity.")
    if manifest["url"] != f"https://github.com/MachHongHai/HaizFlow/releases/download/v{release}/" + filename:
        raise ValueError("Corresponding sources must use the binary release channel.")
    archive = root / "dist/release-sources" / filename
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != manifest["sha256"] or archive.stat().st_size != manifest["size"]:
        raise ValueError("Corresponding-source release asset differs from its pin.")
    with zipfile.ZipFile(archive) as bundle:
        inventory = json.loads(bundle.read("SOURCE-INVENTORY.json"))
        if inventory.get("release_version") != release:
            raise ValueError("Source inventory release differs from its manifest.")
        names = set(bundle.namelist())
        rows = inventory["files"]
        if len(rows) != len({row["file"] for row in rows}) or names != {row["file"] for row in rows} | {"SOURCE-INVENTORY.json"}:
            raise ValueError("Source inventory does not cover the exact ZIP file set.")
        for row in rows:
            with bundle.open(row["file"]) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != row["sha256"] or bundle.getinfo(row["file"]).file_size != row["size"]:
                raise ValueError("A corresponding-source input changed.")
        cli = json.loads((root / "runtime/ffmpeg-manifest.json").read_text(encoding="utf-8"))
        engine = json.loads((root / "runtime/engine-ffmpeg-manifest.json").read_text(encoding="utf-8"))
        for name, expected in (("ffmpeg-release-inputs/closure.json", cli["corresponding_source_manifest_sha256"]),
                               ("engine-ffmpeg-release-inputs/closure.json", engine["closure_sha256"])):
            if hashlib.sha256(bundle.read(name)).hexdigest() != expected:
                raise ValueError("Source closure differs from the packaged media inventory.")
        engine_config = bundle.read("ffmpeg-engine/config.h").decode()
        if "#define CONFIG_GPL 0" not in engine_config or "#define CONFIG_NONFREE 0" not in engine_config:
            raise ValueError("Engine media backend is not the reviewed LGPL-only build.")
        for required in ("qt-pyside/qtbase-everywhere-src-6.11.1.tar.xz",
                         "qt-pyside/pyside-setup-everywhere-src-6.11.1.tar.xz",
                         "qt-pyside/ffmpeg-backend/ffmpeg-7.1.3.tar.xz",
                         "qt-pyside/ffmpeg-backend/zlib-1.3.1.tar.gz",
                         "licenses/LGPL-3.0.txt", "licenses/LGPL-2.1.txt",
                         "docs/third-party-library-replacement.md"):
            if required not in names:
                raise ValueError(f"Missing corresponding-source material: {required}")
    print("Corresponding-source asset and exact media closures verified.")


if __name__ == "__main__":
    verify()
