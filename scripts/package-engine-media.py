"""Replace vendor PyAV media DLLs with the pinned LGPL-only shared backend.

The PyAV wheel remains the locked binding input. Import-table names are changed
only after every imported media symbol is verified against the replacement ABI.
This packaging transformation and both binding hashes are recorded explicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from functools import lru_cache
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[1]
MEDIA_NAME = re.compile(r"^(avcodec|avdevice|avfilter|avformat|avutil|swresample|swscale)-(\d+)(?:-[a-f0-9]+)?\.dll$", re.I)


def digest(file: Path) -> str:
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@lru_cache(maxsize=16)
def export_symbols(file: Path) -> frozenset:
    with pefile.PE(str(file), fast_load=True) as library:
        library.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
        return frozenset(symbol.name for symbol in library.DIRECTORY_ENTRY_EXPORT.symbols if symbol.name)


def patch_imports(file: Path, replacements: dict[str, Path]) -> tuple[bytes, list[dict]]:
    changes = []
    content = bytearray(file.read_bytes())
    with pefile.PE(data=bytes(content), fast_load=True) as binding:
        binding.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        for entry in getattr(binding, "DIRECTORY_ENTRY_IMPORT", []):
            original = entry.dll.decode("ascii")
            match = MEDIA_NAME.fullmatch(original)
            if not match:
                continue
            name = f"{match[1]}-{match[2]}.dll".lower()
            replacement = replacements.get(name)
            if replacement is None:
                raise ValueError(f"Missing compatible backend for {original}")
            exports = export_symbols(replacement)
            missing = [symbol.name for symbol in entry.imports if symbol.name not in exports]
            if missing:
                raise ValueError(f"Replacement ABI misses imports in {file.name}: {missing}")
            encoded = name.encode("ascii")
            if len(encoded) > len(entry.dll):
                raise ValueError("Replacement import name cannot grow the PE string table.")
            offset = binding.get_offset_from_rva(entry.struct.Name)
            content[offset:offset + len(entry.dll) + 1] = encoded + b"\0" * (len(entry.dll) + 1 - len(encoded))
            changes.append(dict(original=original, replacement=name))
    return bytes(content), changes


def package(artifact: Path, inputs: Path) -> dict:
    artifact, inputs = artifact.resolve(), inputs.resolve()
    if not artifact.is_relative_to(ROOT / "build/resource-engines"):
        raise ValueError("Native packaging is limited to generated engine artifacts.")
    if not (artifact / "HaizFlowEngine.exe").is_file():
        raise ValueError("Frozen engine is missing.")
    manifest = json.loads((ROOT / "runtime/engine-ffmpeg-manifest.json").read_text(encoding="utf-8"))
    closure = inputs / "closure.json"
    if digest(closure) != manifest["closure_sha256"]:
        raise ValueError("Native backend source/binary inventory is not pinned.")
    report = json.loads(closure.read_text(encoding="utf-8"))
    if report.get("variant") != "haizflow-engine":
        raise ValueError("Only the separately built engine backend is permitted.")
    replacements = {}
    for row in report["binaries"]:
        file = inputs / "bin" / row["file"]
        if Path(row["file"]).name != row["file"] or file.is_symlink() or digest(file) != row["sha256"]:
            raise ValueError("Native backend file differs from its inventory.")
        replacements[file.name.lower()] = file
    bindings = artifact / "_internal/av"
    vendor = artifact / "_internal/av.libs"
    if not vendor.is_dir() or not bindings.is_dir():
        raise ValueError("Frozen PyAV bindings and vendor DLL directory are required.")
    pending = []
    for file in bindings.rglob("*.pyd"):
        content, changes = patch_imports(file, replacements)
        if changes:
            pending.append((file, content, changes))
    if not pending:
        raise ValueError("No PyAV media imports were found; packaging cannot be assumed successful.")
    backup = ROOT / "build/engine-media-backups" / uuid.uuid4().hex
    backup.mkdir(parents=True)
    # All files and imported symbols have been validated before mutation.
    shutil.move(str(vendor), str(backup / "av.libs"))
    vendor.mkdir()
    for file in replacements.values():
        shutil.copy2(file, vendor / file.name)
    modifications = []
    for file, content, changes in pending:
        relative = file.relative_to(bindings)
        copy = backup / "av" / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, copy)
        original_hash = digest(file)
        file.write_bytes(content)
        modifications.append(dict(file=file.relative_to(artifact).as_posix(), original_sha256=original_hash,
                                  packaged_sha256=digest(file), import_changes=changes))
    result = dict(schema=1, pyav_version="18.1.0", ffmpeg_version="8.1.2", ffmpeg_license="LGPL-2.1-or-later",
                  closure_sha256=digest(closure), binding_changes=modifications,
                  backend_files=report["binaries"], gpl_encoder_libraries_bundled=False)
    (artifact / "AV-BACKEND.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Packaged LGPL media backend; verified imports in {len(modifications)} bindings. Backup: {backup}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=ROOT / "build/engine-ffmpeg-release-inputs")
    args = parser.parse_args()
    package(args.artifact, args.inputs)
