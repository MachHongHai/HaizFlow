"""Full/delta generation and verified staging; never patches an active tree."""
from __future__ import annotations

import os
import shutil
import stat
import zipfile
from pathlib import Path

from .filesystem import UpdateError, atomic_json, child, no_links, sha256, version
from .manifest import Manifest, inventory


def generate(base: Path | None, target: Path, output: Path, *, base_version: str | None,
             target_version: str, project_schema: int = 4, video_schema: int = 19) -> Manifest:
    version(target_version)
    if base is not None:
        version(base_version)
    no_links(output)
    if output.resolve().is_relative_to(target.resolve()) or (base and output.resolve().is_relative_to(base.resolve())):
        raise UpdateError("Thư mục package không được nằm trong Core.")
    target_files = inventory(target)
    base_files = inventory(base) if base else []
    old = {e["path"]: e for e in base_files}
    new = {e["path"]: e for e in target_files}
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    changed = sorted(p for p in set(new) & set(old) if new[p] != old[p])
    suffix = f"from-{base_version}" if base else "full"
    name = f"HaizFlow-Core-{target_version}-windows-x64-{suffix}.zip"
    output.mkdir(parents=True, exist_ok=True)
    package = child(output, name)
    temporary = child(output, name + ".part")
    if package.exists() or temporary.exists():
        raise UpdateError("Package đã tồn tại; chọn thư mục đầu ra mới.")
    owns_temporary = False
    try:
        with temporary.open("xb") as stream:
            owns_temporary = True
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for name_to_add in sorted(added + changed):
                    archive.write(child(target, name_to_add), name_to_add)
            stream.flush()
            os.fsync(stream.fileno())
        data = {"product": "HaizFlow", "manifest_schema": 1, "target_version": target_version,
                "base_version": base_version if base else None, "channel": "stable", "platform": "windows",
                "architecture": "x64", "package_type": "delta" if base else "full", "package_name": name,
                "package_size": temporary.stat().st_size, "package_sha256": sha256(temporary),
                "target_files": target_files, "base_files": base_files, "added_files": added,
                "changed_files": changed, "removed_files": removed,
                "data_compatibility": {"project_schema": project_schema, "video_schema": video_schema,
                                       "rollback_safe": True, "migration_before_health": False}}
        manifest = Manifest.parse(data)
        inspect_archive(temporary, manifest)
        os.replace(temporary, package)
        atomic_json(child(output, name.removesuffix(".zip") + ".manifest.json"), data)
        return manifest
    finally:
        if owns_temporary:
            temporary.unlink(missing_ok=True)


def inspect_archive(package: Path, manifest: Manifest) -> None:
    no_links(package)
    if package.stat().st_size != manifest.data["package_size"] or sha256(package) != manifest.data["package_sha256"]:
        raise UpdateError("Gói cập nhật chưa đầy đủ hoặc SHA-256 không khớp.")
    expected = set(manifest.data["added_files"] + manifest.data["changed_files"])
    entries = {entry["path"]: entry for entry in manifest.data["target_files"]}
    with zipfile.ZipFile(package) as archive:
        actual = []
        for info in archive.infolist():
            if (info.filename not in expected or info.is_dir() or info.flag_bits & 1
                    or stat.S_ISLNK(info.external_attr >> 16)
                    or info.file_size != entries[info.filename]["size"]):
                raise UpdateError("Nội dung ZIP không khớp manifest.")
            actual.append(info.filename)
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise UpdateError("ZIP chứa tệp trùng, thiếu hoặc không được phép.")


def reconstruct(package: Path, manifest: Manifest, staging: Path, base: Path | None) -> None:
    inspect_archive(package, manifest)
    no_links(staging)
    if staging.exists():
        raise UpdateError("Staging đã tồn tại; không ghi đè Core.")
    if manifest.data["package_type"] == "delta":
        if base is None:
            raise UpdateError("Delta thiếu base Core.")
        manifest.verify_tree(base, base=True)
    required = sum(e["size"] for e in manifest.data["target_files"]) + 64 * 1024**2
    staging.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(staging.parent).free < required:
        raise UpdateError("Không đủ dung lượng đĩa để chuẩn bị Core mới.")
    staging.mkdir()
    changed = set(manifest.data["added_files"] + manifest.data["changed_files"])
    with zipfile.ZipFile(package) as archive:
        for entry in manifest.data["target_files"]:
            name = entry["path"]
            destination = child(staging, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if name in changed:
                with archive.open(name) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
            else:
                # Copy, never hardlink; reverify after copying in case base changed.
                shutil.copyfile(child(base, name), destination)
                with destination.open("r+b") as output:
                    os.fsync(output.fileno())
            if destination.stat().st_size != entry["size"] or sha256(destination) != entry["sha256"]:
                raise UpdateError("Tệp được dựng không khớp manifest.")
    manifest.verify_tree(staging)
    atomic_json(child(staging, "core-manifest.json"), manifest.data)
    atomic_json(child(staging, "core-complete.json"), {"product": "HaizFlow", "schema": 1,
                "version": manifest.data["target_version"], "manifest_sha256": sha256(staging / "core-manifest.json")})
