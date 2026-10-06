"""Collect the DLL and corresponding-source closure of a local FFmpeg build.

The binaries are staged under build/, never installed over a working runtime.
Sources are identified from the package database that owns each imported DLL;
unknown imports and unavailable exact-version sources fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[1]
SYSTEM32 = Path("C:/Windows/System32")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sections(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    key = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("%") and line.endswith("%"):
            key = line.strip("%")
            result[key] = []
        elif line and key:
            result[key].append(line)
    return result


def collect(msys: Path, build: Path, output: Path, *, engine: bool = False) -> dict:
    output = output.resolve()
    if (ROOT / "build").resolve() not in output.parents:
        raise ValueError("Collection output must stay below build/.")
    binaries, sources = output / "bin", output / "sources"
    binaries.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    packages = {}
    owners = {}
    for directory in (msys / "var/lib/pacman/local").iterdir():
        if not (directory / "desc").is_file():
            continue
        desc = sections(directory / "desc")
        name = desc["NAME"][0]
        packages[name] = desc
        if (directory / "files").is_file():
            for file in sections(directory / "files").get("FILES", []):
                if file.startswith("mingw64/bin/") and file.lower().endswith(".dll"):
                    owners[Path(file).name.lower()] = (name, msys / file)
    built_files = {file.name.lower(): file for file in (build / "output/bin").glob("*.dll")}
    queue = list(built_files.values()) if engine else [build / "output/bin/ffmpeg.exe", build / "output/bin/ffprobe.exe"]
    if not queue:
        raise ValueError("No built media libraries found.")
    seen = set()
    used = set()
    rows = []
    while queue:
        file = queue.pop()
        if file.name.lower() in seen:
            continue
        if not file.is_file():
            raise ValueError(f"Built runtime file is missing: {file}")
        seen.add(file.name.lower())
        with pefile.PE(str(file), fast_load=True) as pe:
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
            for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
                name = entry.dll.decode("ascii").lower()
                if name in built_files:
                    queue.append(built_files[name])
                elif name in owners:
                    owner, dependency = owners[name]
                    used.add(owner)
                    queue.append(dependency)
                elif name.startswith(("api-ms-win-", "ext-ms-win-")) or (SYSTEM32 / name).is_file():
                    continue
                else:
                    raise ValueError(f"Unresolved import {name} from {file.name}")
        shutil.copy2(file, binaries / file.name)
        rows.append(dict(file=file.name, sha256=digest(file), size=file.stat().st_size))
    # Include exact compiler/CRT/header inputs in addition to linked libraries.
    used.update({"mingw-w64-x86_64-gcc", "mingw-w64-x86_64-crt", "mingw-w64-x86_64-headers"})
    if not engine:
        used.add("mingw-w64-x86_64-ffnvcodec-headers")
    source_rows = []
    source_seen = set()
    for package in sorted(used):
        desc = packages[package]
        base, version = desc["BASE"][0], desc["VERSION"][0]
        filename = f"{base}-{version}.src.tar.zst"
        if filename in source_seen:
            continue
        source_seen.add(filename)
        destination = sources / filename
        url = f"https://repo.msys2.org/mingw/sources/{filename}"
        cached = ROOT / "build/ffmpeg-release-inputs/sources" / filename
        if not destination.exists() and cached.is_file():
            shutil.copy2(cached, destination)
        if not destination.is_file():
            print(f"Collecting {filename}", flush=True)
            partial = destination.with_suffix(destination.suffix + ".part")
            with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as stream:
                shutil.copyfileobj(response, stream, 1024 * 1024)
            partial.replace(destination)
        listing = subprocess.run(["tar", "-tf", str(destination)], capture_output=True,
                                 text=True, check=True).stdout.splitlines()
        if not any(Path(member).name == "PKGBUILD" for member in listing):
            raise ValueError(f"Source archive lacks its build recipe: {filename}")
        source_rows.append(dict(file=filename, sha256=digest(destination),
                                size=destination.stat().st_size, url=url,
                                package_base=base, package_version=version))
        local_package = next(directory for directory in (msys / "var/lib/pacman/local").iterdir()
                             if (directory / "desc").is_file() and sections(directory / "desc")["NAME"][0] == package)
        for name in sections(local_package / "files").get("FILES", []):
            file = msys / name
            if name.startswith("mingw64/share/licenses/") and file.is_file():
                target = output / "licenses" / Path(name).relative_to("mingw64/share/licenses")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)
    for name in ("ffmpeg-8.1.2.tar.xz", "ffmpeg-8.1.2.tar.xz.asc"):
        source = ROOT / "runtime/compliance/ffmpeg" / name
        shutil.copy2(source, sources / name)
        source_rows.append(dict(file=name, sha256=digest(source), size=source.stat().st_size,
                                url="https://ffmpeg.org/releases/" + name))
    for name in ("config.log", "config.h", "config.mak", "toolchain-packages.txt", "compiler-version.txt"):
        shutil.copy2(build / name, sources / name)
    recipe = "build-engine-msys2.sh" if engine else "build-msys2.sh"
    shutil.copy2(ROOT / "scripts/ffmpeg" / recipe, sources / recipe)
    report = dict(schema=1, version="8.1.2", variant="haizflow-engine" if engine else "haizflow", architecture="windows-x64",
                  binaries=sorted(rows, key=lambda item: item["file"]),
                  sources=source_rows, packages={name: packages[name] for name in sorted(used)})
    (output / "closure.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(rows)} runtime files and {len(source_rows)} source archives.", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msys", type=Path, default=ROOT / "build/ffmpeg-toolchain/msys64")
    parser.add_argument("--build", type=Path, default=ROOT / "build/ffmpeg-source-build")
    parser.add_argument("--output", type=Path, default=ROOT / "build/ffmpeg-release-inputs")
    parser.add_argument("--engine", action="store_true")
    args = parser.parse_args()
    collect(args.msys, args.build, args.output, engine=args.engine)
