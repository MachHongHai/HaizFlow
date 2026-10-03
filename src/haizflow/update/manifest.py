"""Strict versioned file-level manifests, independent of GUI/network."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .filesystem import UpdateError, child, no_links, relative_path, sha256, version

RESERVED = {"core-manifest.json", "core-complete.json"}
MAX_FILES = 40000
MAX_BYTES = 8 * 1024**3


def inventory(root: Path) -> list[dict]:
    no_links(root)
    if not root.is_dir():
        raise UpdateError("Không tìm thấy thư mục Core.")
    result = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        no_links(path)
        if path.is_dir():
            continue
        name = relative_path(path.relative_to(root).as_posix())
        if name.casefold() in RESERVED:
            continue
        if not path.is_file():
            raise UpdateError("Core chứa mục không phải tệp thông thường.")
        result.append({"path": name, "size": path.stat().st_size, "sha256": sha256(path)})
    validate_files(result)
    return result


def validate_files(files: list) -> dict[str, dict]:
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        raise UpdateError("Danh sách tệp Core không hợp lệ.")
    result = {}
    folded = set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            raise UpdateError("Thông tin tệp Core không hợp lệ.")
        name = relative_path(entry["path"])
        if name.split("/", 1)[0].casefold() in {"runtime", "update-state", "versions"}:
            raise UpdateError("Dữ liệu bền vững không được đóng gói trong Core.")
        if name.casefold() in folded or name.casefold() in RESERVED:
            raise UpdateError("Tên tệp Core trùng nhau hoặc dành riêng.")
        if type(entry["size"]) is not int or not 0 <= entry["size"] <= MAX_BYTES:
            raise UpdateError("Dung lượng tệp Core không hợp lệ.")
        if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise UpdateError("SHA-256 của tệp không hợp lệ.")
        folded.add(name.casefold())
        result[name] = entry
    for name in folded:
        parts = name.split("/")
        if any("/".join(parts[:n]) in folded for n in range(1, len(parts))):
            raise UpdateError("Tệp và thư mục Core xung đột.")
    if sum(e["size"] for e in files) > MAX_BYTES:
        raise UpdateError("Core vượt giới hạn dung lượng.")
    return result


@dataclass(frozen=True)
class Manifest:
    data: dict

    @classmethod
    def parse(cls, data: dict) -> "Manifest":
        required = {"product", "manifest_schema", "target_version", "base_version", "channel",
                    "platform", "architecture", "package_type", "package_name", "package_size",
                    "package_sha256", "target_files", "base_files", "added_files", "changed_files",
                    "removed_files", "data_compatibility"}
        if not isinstance(data, dict) or set(data) != required:
            raise UpdateError("Manifest thiếu trường hoặc có trường không được hỗ trợ.")
        if (data["product"] != "HaizFlow" or type(data["manifest_schema"]) is not int
                or data["manifest_schema"] != 1 or data["channel"] != "stable"
                or data["platform"] != "windows" or data["architecture"] != "x64"
                or data["package_type"] not in {"full", "delta"}):
            raise UpdateError("Manifest không dành cho bản HaizFlow Windows x64 này.")
        target = version(data["target_version"])
        base = data["base_version"]
        if data["package_type"] == "delta":
            version(base)
            if tuple(map(int, base.split("."))) >= tuple(map(int, target.split("."))):
                raise UpdateError("Delta không phải nâng cấp phiên bản.")
            expected_name = f"HaizFlow-Core-{target}-windows-x64-from-{base}.zip"
            source = validate_files(data["base_files"])
        else:
            if base is not None or data["base_files"]:
                raise UpdateError("Full Core không được phụ thuộc base.")
            expected_name = f"HaizFlow-Core-{target}-windows-x64-full.zip"
            source = {}
        if (data["package_name"] != expected_name or type(data["package_size"]) is not int
                or not 0 < data["package_size"] <= MAX_BYTES
                or not re.fullmatch(r"[0-9a-f]{64}", str(data["package_sha256"]))):
            raise UpdateError("Thông tin package không hợp lệ.")
        target_files = validate_files(data["target_files"])
        # A frozen Core always has this fixed entrypoint. Never execute a
        # filename or argument supplied by network metadata.
        if "HaizFlowCore.exe" not in target_files:
            raise UpdateError("Manifest thiếu HaizFlowCore.exe.")
        categories = {}
        for key in ("added_files", "changed_files", "removed_files"):
            value = data[key]
            if not isinstance(value, list) or not all(isinstance(p, str) for p in value) or len(value) != len(set(value)):
                raise UpdateError("Danh sách thay đổi không hợp lệ.")
            categories[key] = set(relative_path(name) for name in value)
        added = set(target_files) - set(source)
        removed = set(source) - set(target_files)
        changed = {p for p in set(source) & set(target_files) if source[p] != target_files[p]}
        if categories != {"added_files": added, "changed_files": changed, "removed_files": removed}:
            raise UpdateError("Phân loại delta không khớp danh sách tệp.")
        compatibility = data["data_compatibility"]
        if (not isinstance(compatibility, dict) or set(compatibility) != {"project_schema", "video_schema", "rollback_safe", "migration_before_health"}
                or type(compatibility["project_schema"]) is not int or compatibility["project_schema"] < 1
                or type(compatibility["video_schema"]) is not int or compatibility["video_schema"] < 1
                or compatibility["rollback_safe"] is not True or compatibility["migration_before_health"] is not False):
            raise UpdateError("Bản cập nhật yêu cầu migration không thể rollback an toàn. Cần quy trình nâng cấp riêng.")
        return cls(data)

    def verify_tree(self, root: Path, *, base: bool = False) -> None:
        expected = self.data["base_files" if base else "target_files"]
        if inventory(root) != sorted(expected, key=lambda e: e["path"]):
            raise UpdateError("Tệp Core bị thiếu, thay đổi hoặc không khớp SHA-256.")
        for entry in expected:
            child(root, entry["path"])
