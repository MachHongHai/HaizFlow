"""Collect exact-version upstream Qt/PySide source archives for release review.

This prepares evidence in build/, not legal approval. Every archive is checked
against the SHA-256 published by Qt's download service. Its manifest is an input
to the separate module/relinking review, not a declaration of compatibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "qtbase", "qtdeclarative", "qtmultimedia", "qtimageformats", "qtsvg",
    "qtshadertools", "qtremoteobjects", "qtscxml", "qtsensors", "qtspeech",
    "qtwebchannel", "qtwebsockets", "qtwebview", "qttools",
)


def collect(output: Path) -> dict:
    output = output.resolve()
    if (ROOT / "build").resolve() not in output.parents:
        raise ValueError("Evidence must be collected below build/.")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    version = "6.11.1"
    base = "https://download.qt.io/official_releases/qt/6.11/6.11.1/submodules/"
    urls = [base + f"{module}-everywhere-src-{version}.tar.xz" for module in MODULES]
    urls.append("https://download.qt.io/official_releases/QtForPython/pyside6/"
                "PySide6-6.11.1-src/pyside-setup-everywhere-src-6.11.1.tar.xz")
    for url in urls:
        with urllib.request.urlopen(url + ".mirrorlist", timeout=60) as response:
            metadata = response.read().decode("utf-8")
        plain_metadata = re.sub(r"<[^>]+>", "", metadata)
        match = re.search(r"SHA-256\s+Hash:.*?([0-9a-f]{64})", plain_metadata, re.S)
        if not match:
            raise ValueError(f"No published source hash: {url}")
        expected = match.group(1)
        destination = output / url.rsplit("/", 1)[1]
        if not destination.is_file():
            print(f"Downloading {destination.name}", flush=True)
            with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as stream:
                for data in iter(lambda: response.read(1024 * 1024), b""):
                    stream.write(data)
        with destination.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"Source checksum mismatch: {destination.name}")
        rows.append(dict(file=destination.name, url=url, sha256=actual,
                         size=destination.stat().st_size, hash_source=url + ".mirrorlist"))
        with tarfile.open(destination, "r:xz") as archive:
            for member in archive:
                path = Path(member.name)
                if not member.isfile() or not 0 < member.size < 4 * 1024 * 1024:
                    continue
                if "LICENSES" not in path.parts and path.name != "qt_attribution.json":
                    continue
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Unsafe source archive member.")
                target = output / "licenses" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream:
                    target.write_bytes(stream.read())
        print(f"Verified {destination.name}", flush=True)
    manifest = dict(schema=1, qt_version=version, pyside_version=version, sources=rows)
    (output / "upstream-sources.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/qt-source-evidence")
    args = parser.parse_args()
    collect(args.output)
