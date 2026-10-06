"""Durable journal and version pointer, scoped to a provisioned installation."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from .filesystem import (UpdateError, atomic_json, child, file_lock, no_links,
                         read_json, remove_owned, sha256, version, version_tuple)
from .manifest import Manifest
from .packages import reconstruct

STATES = {"downloaded", "verified", "staged", "ready", "activating", "pending_health",
          "confirmed", "rolled_back", "failed"}
TRANSITIONS = {
    "downloaded": {"verified", "failed"}, "verified": {"staged", "failed"},
    "staged": {"ready", "failed"}, "ready": {"activating", "failed"},
    "activating": {"pending_health", "rolled_back", "failed"},
    "pending_health": {"confirmed", "rolled_back", "failed"},
    "confirmed": set(), "rolled_back": set(), "failed": set(),
}


def validate_pointer(data: dict) -> dict:
    if (not isinstance(data, dict) or set(data) != {"schema", "active", "previous", "known_good"}
            or type(data["schema"]) is not int or data["schema"] != 1
            or not isinstance(data["known_good"], list) or not 1 <= len(data["known_good"]) <= 2):
        raise UpdateError("Trạng thái phiên bản bị hỏng; cần pointer đã xác nhận để phục hồi.")
    version(data["active"])
    if data["previous"] is not None:
        version(data["previous"])
    for value in data["known_good"]:
        version(value)
    if len(data["known_good"]) != len(set(data["known_good"])):
        raise UpdateError("Known-good pointer trùng nhau.")
    return data


def provision(root: Path) -> None:
    """Explicit bootstrap/fixture setup only; never auto-migrates a legacy install."""
    no_links(root)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "update-layout.json"
    if marker.exists():
        Layout(root)
        return
    atomic_json(marker, {"product": "HaizFlow", "schema": 1, "core_layout": "versions",
                         "runtime_layout": "runtime", "architecture": "x64"})


class Layout:
    def __init__(self, root: Path):
        no_links(root)
        self.root = root.resolve()
        if read_json(self.root / "update-layout.json") != {
                "product": "HaizFlow", "schema": 1, "core_layout": "versions",
                "runtime_layout": "runtime", "architecture": "x64"}:
            raise UpdateError("Bố cục cài đặt không hỗ trợ Core delta update.")
        self.versions = child(self.root, "versions")
        self.state = child(self.root, "update-state")
        self.staging = child(self.state, "staging")
        self.downloads = child(self.state, "downloads")
        self.ipc = child(self.state, "ipc")
        self.runtime = child(self.root, "runtime")
        self.active_path = child(self.state, "active-version.json")
        self.journal_path = child(self.state, "transaction.json")

    def lock(self):
        return file_lock(child(self.state, "update.lock"))

    def core(self, value: str) -> Path:
        return child(self.versions, version(value))

    def validate_core(self, value: str, *, root: Path | None = None) -> Manifest:
        root = root if root is not None else self.core(value)
        no_links(root)
        complete = read_json(child(root, "core-complete.json"))
        manifest_path = child(root, "core-manifest.json")
        if complete != {"product": "HaizFlow", "schema": 1, "version": value,
                        "manifest_sha256": sha256(manifest_path)}:
            raise UpdateError("Core chưa hoàn tất staging hoặc marker bị hỏng.")
        manifest = Manifest.parse(read_json(manifest_path))
        if manifest.data["target_version"] != value:
            raise UpdateError("Core manifest không khớp thư mục phiên bản.")
        manifest.verify_tree(root)
        return manifest

    def active(self) -> dict:
        return validate_pointer(read_json(self.active_path))

    def journal(self) -> dict | None:
        if not self.journal_path.exists():
            return None
        data = read_json(self.journal_path)
        required = {"schema", "id", "state", "base", "target", "attempts", "error", "prior_pointer"}
        if (not required <= set(data) or set(data) - required - {"manifest_sha256"}
                or type(data.get("schema")) is not int or data.get("schema") != 1
                or not isinstance(data.get("state"), str) or data.get("state") not in STATES
                or not isinstance(data.get("id"), str) or not re.fullmatch(r"[a-f0-9]{32}", data["id"])
                or type(data.get("attempts")) is not int or not 0 <= data["attempts"] <= 1):
            raise UpdateError("Transaction bị hỏng; không tự đoán hoặc kích hoạt Core.")
        version(data["base"])
        version(data["target"])
        prior = validate_pointer(data["prior_pointer"])
        if prior["active"] != data["base"] or version_tuple(data["target"]) <= version_tuple(data["base"]):
            raise UpdateError("Transaction không khớp prior pointer.")
        if data["state"] in {"staged", "ready", "activating", "pending_health", "confirmed", "rolled_back"}:
            if not re.fullmatch(r"[a-f0-9]{64}", str(data.get("manifest_sha256"))):
                raise UpdateError("Transaction thiếu hash manifest đã staging.")
        return data

    def transition(self, journal: dict, state: str, **values) -> dict:
        if state != journal["state"] and state not in TRANSITIONS[journal["state"]]:
            raise UpdateError("Chuyển trạng thái cập nhật không hợp lệ.")
        journal = dict(journal, state=state, **values)
        atomic_json(self.journal_path, journal)
        return journal

    def seed(self, value: str) -> None:
        """Packaging/fixture initialization after full tree verification."""
        with self.lock():
            self.validate_core(value)
            if self.active_path.exists():
                raise UpdateError("Đã có active pointer; không tự ghi đè.")
            atomic_json(self.active_path, {"schema": 1, "active": value, "previous": None, "known_good": [value]})
            atomic_json(child(self.state, "last-confirmed.json"), self.active())

    def prepare(self, package: Path, manifest: Manifest, *, progress=lambda *_: None) -> dict:
        with self.lock():
            self.recover()
            previous = self.journal()
            if previous and previous["state"] not in {"confirmed", "rolled_back", "failed"}:
                raise UpdateError("Đang có bản cập nhật chờ xử lý.")
            active = self.active()
            if manifest.data["package_type"] == "delta":
                base_manifest = self.validate_core(active["active"])
            else:
                # A full Core repairs missing/modified base FILES. Its existing
                # compatibility metadata must still be authentic to the local
                # completion marker; otherwise require explicit install repair.
                base_root = self.core(active["active"])
                metadata_path = child(base_root, "core-manifest.json")
                marker = read_json(child(base_root, "core-complete.json"))
                if marker.get("manifest_sha256") != sha256(metadata_path):
                    raise UpdateError("Base metadata bị hỏng; cần sửa bản cài trước khi cập nhật.")
                base_manifest = Manifest.parse(read_json(metadata_path))
            target = manifest.data["target_version"]
            if version_tuple(target) <= version_tuple(active["active"]):
                raise UpdateError("Bản cập nhật không mới hơn Core đang dùng.")
            if manifest.data["package_type"] == "delta" and manifest.data["base_version"] != active["active"]:
                raise UpdateError("Delta không hỗ trợ phiên bản đang dùng; cần Full Core.")
            # Reject migrations BEFORE activation. Health acknowledgment must
            # precede future unsafe migrations; current updates permit none.
            if manifest.data["data_compatibility"] != base_manifest.data["data_compatibility"]:
                raise UpdateError("Schema dữ liệu thay đổi. Cần quy trình migration và backup riêng.")
            transaction_id = uuid.uuid4().hex
            journal = {"schema": 1, "id": transaction_id, "state": "downloaded", "base": active["active"],
                       "target": target, "attempts": 0, "error": "", "prior_pointer": active}
            atomic_json(self.journal_path, journal)
            stage = child(self.staging, transaction_id)
            try:
                progress("verifying", 50)
                from .packages import inspect_archive
                inspect_archive(package, manifest, progress=progress)
                journal = self.transition(journal, "verified")
                progress("preparing", 65)
                reconstruct(package, manifest, stage, self.core(active["active"]), progress=progress)
                progress("preparing", 88)
                journal = self.transition(journal, "staged", manifest_sha256=sha256(stage / "core-manifest.json"))
                self._promote(journal)
                progress("preparing", 89)
                journal = self.transition(journal, "ready")
                progress("ready", 90)
                return journal
            except Exception as exc:
                self.transition(journal, "failed", error=str(exc))
                if stage.exists():
                    remove_owned(self.staging, stage)
                raise

    def _promote(self, journal: dict) -> None:
        stage = child(self.staging, journal["id"])
        target = self.core(journal["target"])
        if target.exists():
            self.validate_core(journal["target"])
            if sha256(target / "core-manifest.json") != journal.get("manifest_sha256"):
                raise UpdateError("Core đích khác manifest của transaction.")
            if stage.exists():
                if sha256(stage / "core-manifest.json") != sha256(target / "core-manifest.json"):
                    raise UpdateError("Phiên bản đích đã tồn tại với nội dung khác.")
                remove_owned(self.staging, stage)
            return
        self.versions.mkdir(parents=True, exist_ok=True)
        no_links(stage)
        self.validate_core(journal["target"], root=stage)
        if sha256(stage / "core-manifest.json") != journal.get("manifest_sha256"):
            raise UpdateError("Staging khác manifest của transaction.")
        # Both directories are installation-owned on the same filesystem.
        # A Windows/AV lock raises and leaves the old active pointer intact.
        os.rename(stage, target)
        self.validate_core(journal["target"])

    def activate(self, *, core_exited: bool) -> dict:
        """Caller must hold update lock and prove graceful Core process exit."""
        journal = self.journal()
        if not core_exited or not journal or journal["state"] != "ready":
            raise UpdateError("Core chưa đóng an toàn hoặc bản cập nhật chưa sẵn sàng.")
        self.validate_core(journal["target"])
        if self.active() != journal["prior_pointer"]:
            raise UpdateError("Active pointer đã thay đổi; không kích hoạt.")
        journal = self.transition(journal, "activating")
        atomic_json(self.active_path, {"schema": 1, "active": journal["target"],
                    "previous": journal["base"], "known_good": journal["prior_pointer"]["known_good"]})
        return self.transition(journal, "pending_health")

    def rollback(self, journal: dict, error: str) -> dict:
        prior = journal["prior_pointer"]
        if prior["active"] not in prior["known_good"]:
            raise UpdateError("Không có Core cũ đã xác nhận để rollback.")
        self.validate_core(prior["active"])
        atomic_json(self.active_path, prior)
        return self.transition(journal, "rolled_back", error=error)

    def confirm(self, journal: dict) -> dict:
        self.validate_core(journal["target"])
        pointer = self.active()
        if pointer["active"] != journal["target"]:
            raise UpdateError("Core đã đổi trong lúc health check.")
        pointer["known_good"] = [journal["target"], journal["base"]]
        atomic_json(self.active_path, pointer)
        atomic_json(child(self.state, "last-confirmed.json"), pointer)
        return self.transition(journal, "confirmed", error="")

    def recover(self, *, launcher: bool = False) -> str:
        """Under lock; never invents a version by enumerating directories."""
        journal = self.journal()
        if not journal:
            return "idle"
        state = journal["state"]
        if state in {"downloaded", "verified"}:
            stage = child(self.staging, journal["id"])
            if stage.exists():
                remove_owned(self.staging, stage)
            journal = self.transition(journal, "failed", error="Chuẩn bị cập nhật bị gián đoạn; Core cũ được giữ nguyên.")
        elif state == "staged":
            try:
                self._promote(journal)
                journal = self.transition(journal, "ready")
            except (OSError, ValueError) as exc:
                journal = self.transition(journal, "failed", error=str(exc))
        elif state == "activating":
            # Covers crash both before and after pointer replacement.
            journal = self.rollback(journal, "Kích hoạt bị gián đoạn; đã khôi phục Core cũ.")
        elif state == "pending_health" and launcher and journal["attempts"]:
            try:
                confirmed = read_json(child(self.state, "last-confirmed.json"))
            except (OSError, ValueError):
                confirmed = {}
            if (confirmed.get("active") == journal["target"] and self.active() == confirmed
                    and journal["target"] in confirmed.get("known_good", [])):
                self.validate_core(journal["target"])
                journal = self.transition(journal, "confirmed", error="")
            else:
                journal = self.rollback(journal, "Health check trước đó bị gián đoạn; đã khôi phục Core cũ.")
        return journal["state"]

    def cleanup_versions(self, *, running_versions: set[str]) -> list[str]:
        """Explicit maintenance only; preserve all recovery/runtime/project data."""
        with self.lock():
            pointer = self.active()
            journal = self.journal()
            protected = set(pointer["known_good"]) | running_versions | {pointer["active"], pointer["previous"]}
            if journal and journal["state"] not in {"confirmed", "rolled_back", "failed"}:
                protected.update({journal["base"], journal["target"]})
            removed = []
            if not self.versions.exists():
                return removed
            for directory in self.versions.iterdir():
                if directory.name in protected:
                    continue
                self.validate_core(version(directory.name))
                remove_owned(self.versions, directory)
                removed.append(directory.name)
            return removed
