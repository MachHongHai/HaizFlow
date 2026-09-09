"""Qt presentation layer for optional engines and model resource packs."""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from PySide6.QtCore import Property, QAbstractListModel, QModelIndex, QObject, Qt, Signal, Slot

from haizflow.desktop.localization import QFileDialog
from haizflow.desktop.presenters import format_memory_size
from haizflow.services.model_bootstrap import ModelBootstrapCancelled, ModelProgress
from haizflow.services.resource_packs import ResourcePackError, ResourcePackManager


class ResourcePackListModel(QAbstractListModel):
    PackIdRole = Qt.ItemDataRole.UserRole + 1
    LabelRole = Qt.ItemDataRole.UserRole + 2
    GroupRole = Qt.ItemDataRole.UserRole + 3
    VersionRole = Qt.ItemDataRole.UserRole + 4
    StatusRole = Qt.ItemDataRole.UserRole + 5
    ProgressRole = Qt.ItemDataRole.UserRole + 6
    DetailRole = Qt.ItemDataRole.UserRole + 7
    DownloadSizeTextRole = Qt.ItemDataRole.UserRole + 8
    InstalledSizeTextRole = Qt.ItemDataRole.UserRole + 9
    LocationRole = Qt.ItemDataRole.UserRole + 10
    CanInstallRole = Qt.ItemDataRole.UserRole + 11
    CanRemoveRole = Qt.ItemDataRole.UserRole + 12
    BlockedReasonRole = Qt.ItemDataRole.UserRole + 13
    GroupFirstRole = Qt.ItemDataRole.UserRole + 14
    GroupTitleRole = Qt.ItemDataRole.UserRole + 15

    def __init__(self, manager: ResourcePackManager):
        super().__init__()
        self._manager = manager
        self._rows: list[dict] = []
        self._operation_state: dict[str, dict] = {}
        self.refresh()

    def roleNames(self):
        return {
            self.PackIdRole: b"packId",
            self.LabelRole: b"label",
            self.GroupRole: b"group",
            self.VersionRole: b"version",
            self.StatusRole: b"status",
            self.ProgressRole: b"progress",
            self.DetailRole: b"detail",
            self.DownloadSizeTextRole: b"downloadSizeText",
            self.InstalledSizeTextRole: b"installedSizeText",
            self.LocationRole: b"location",
            self.CanInstallRole: b"canInstall",
            self.CanRemoveRole: b"canRemove",
            self.BlockedReasonRole: b"blockedReason",
            self.GroupFirstRole: b"groupFirst",
            self.GroupTitleRole: b"groupTitle",
        }

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        key = {
            self.PackIdRole: "packId",
            self.LabelRole: "label",
            self.GroupRole: "group",
            self.VersionRole: "version",
            self.StatusRole: "status",
            self.ProgressRole: "progress",
            self.DetailRole: "detail",
            self.DownloadSizeTextRole: "downloadSizeText",
            self.InstalledSizeTextRole: "installedSizeText",
            self.LocationRole: "location",
            self.CanInstallRole: "canInstall",
            self.CanRemoveRole: "canRemove",
            self.BlockedReasonRole: "blockedReason",
            self.GroupFirstRole: "groupFirst",
            self.GroupTitleRole: "groupTitle",
        }.get(role)
        return row.get(key) if key else None

    def refresh(self) -> None:
        rows = []
        previous_group = ""
        group_titles = {
            "processor": "Bộ xử lý",
            "recognition": "Nhận dạng",
            "translation": "Dịch",
            "voice": "Giọng đọc",
            "image": "Hình ảnh",
        }
        for snapshot in self._manager.snapshot():
            operation = self._operation_state.get(snapshot["packId"], {})
            status = operation.get("status", snapshot["status"])
            rows.append(
                {
                    **snapshot,
                    "status": status,
                    "progress": int(operation.get("progress", -1)),
                    "detail": str(operation.get("detail", "")),
                    "downloadSizeText": format_memory_size(snapshot["downloadSize"]),
                    "installedSizeText": format_memory_size(snapshot["installedSize"]),
                    "canInstall": snapshot["canInstall"] and status not in {"downloading", "verifying"},
                    "canRemove": snapshot["canRemove"] and status not in {"downloading", "verifying"},
                    "groupFirst": snapshot["group"] != previous_group,
                    "groupTitle": group_titles.get(snapshot["group"], snapshot["group"]),
                }
            )
            previous_group = snapshot["group"]
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def set_operation(self, pack_id: str, *, status: str, progress: int = -1, detail: str = "") -> None:
        self._operation_state[pack_id] = {"status": status, "progress": progress, "detail": detail}
        self.refresh()

    def clear_operation(self, pack_id: str) -> None:
        self._operation_state.pop(pack_id, None)
        self.refresh()


class ResourcePackController(QObject):
    changed = Signal()

    def __init__(self, host, manager: ResourcePackManager | None = None):
        super().__init__(host)
        self._host = host
        self.manager = manager or ResourcePackManager()
        self.model = ResourcePackListModel(self.manager)
        self._events: queue.Queue[dict] = queue.Queue()
        self._threads: dict[str, threading.Thread] = {}
        self._move_thread: threading.Thread | None = None
        # A previous cross-drive move can leave several gigabytes to remove.
        # Never perform that recursive deletion while the QML singleton is
        # constructing its first frame.
        self._maintenance_thread = threading.Thread(
            target=self.manager.cleanup_previous_storage,
            name="resource-storage-cleanup",
            daemon=True,
        )
        self._maintenance_thread.start()

    @Property(QObject, constant=True)
    def packModel(self):
        return self.model

    @Property(str, notify=changed)
    def storageLocation(self):
        return str(self.manager.storage_root)

    @Property(str, notify=changed)
    def totalInstalledText(self):
        total = sum(self.manager.installed_bytes(pack_id) for pack_id in self.manager.definitions)
        return format_memory_size(total)

    @Property(str, notify=changed)
    def freeSpaceText(self):
        rows = self.manager.snapshot()
        return format_memory_size(rows[0]["freeBytes"] if rows else 0)

    @Property(bool, notify=changed)
    def busy(self):
        return any(thread.is_alive() for thread in self._threads.values()) or bool(
            self._move_thread and self._move_thread.is_alive()
        )

    def _report(self, pack_id: str, progress: ModelProgress) -> None:
        percentage = -1
        if progress.total_bytes:
            percentage = min(100, round(progress.completed_bytes * 100 / progress.total_bytes))
        self._events.put(
            {
                "kind": "progress",
                "pack_id": pack_id,
                "status": progress.state,
                "progress": percentage,
                "detail": progress.detail,
            }
        )

    def _run_install(self, pack_id: str) -> None:
        try:
            self.manager.install(pack_id, self._report)
            self._events.put({"kind": "done", "pack_id": pack_id})
        except ModelBootstrapCancelled:
            self._events.put({"kind": "paused", "pack_id": pack_id})
        except Exception as exc:
            self._events.put({"kind": "error", "pack_id": pack_id, "message": str(exc)})

    @Slot("QVariantList")
    def installResourcePacks(self, pack_ids) -> None:
        for raw_pack_id in pack_ids:
            pack_id = str(raw_pack_id)
            if pack_id not in self.manager.definitions:
                continue
            current = self._threads.get(pack_id)
            if current is not None and current.is_alive():
                continue
            self.model.set_operation(pack_id, status="checking", progress=0, detail="Đang kiểm tra")
            thread = threading.Thread(
                target=self._run_install,
                args=(pack_id,),
                name=f"resource-pack-{pack_id}",
                daemon=True,
            )
            self._threads[pack_id] = thread
            thread.start()
        self.changed.emit()

    @Slot(str)
    def cancelResourcePackOperation(self, pack_id: str) -> None:
        self.manager.cancel(str(pack_id))

    @Slot(str)
    def repairResourcePack(self, pack_id: str) -> None:
        self.installResourcePacks([pack_id])

    @Slot(str, result=bool)
    def removeResourcePack(self, pack_id: str) -> bool:
        pack_id = str(pack_id)
        warmup = getattr(self._host, "_smart_warmup", None)
        in_use = bool(
            self._host._processing_queue.has_work
            or getattr(self._host, "_device_switching", False)
            or (warmup is not None and warmup.pack_in_use(pack_id))
        )
        try:
            if not in_use:
                # Foreground work is already excluded above. Stop persistent
                # orchestration processes so Windows does not keep the engine
                # executable or model files locked after inference.
                definition = self.manager.definitions[pack_id]
                if definition.engine_modules or definition.capability == "translation":
                    from haizflow.services.translation import shutdown_hymt2_worker

                    shutdown_hymt2_worker()
                if definition.engine_modules or definition.capability == "voice":
                    from haizflow.pipeline.omnivoice_tts import clear_runtime

                    clear_runtime()
                if warmup is not None:
                    warmup.close_idle_pack(pack_id)
            self.manager.remove(pack_id, in_use=in_use)
        except (KeyError, OSError, ResourcePackError) as exc:
            self._host.appAlertRequested.emit("Không thể gỡ gói", str(exc), "error")
            return False
        self.model.refresh()
        self.changed.emit()
        return True

    @Slot(result=str)
    def cleanUnusedResourcePacks(self) -> str:
        removed = self.manager.clean_unused()
        self.model.refresh()
        self.changed.emit()
        return format_memory_size(removed)

    @Slot(str, "QVariantMap", result="QStringList")
    def requiredPacksForCapability(self, capability: str, context) -> list[str]:
        return self.manager.required_packs(str(capability), dict(context or {}))

    @Slot("QVariantList", result="QVariantMap")
    def resourceRequirementSummary(self, pack_ids) -> dict:
        return self.manager.requirement_summary(str(pack_id) for pack_id in pack_ids)

    @Slot(str, result=bool)
    def moveResourceStorage(self, destination: str) -> bool:
        if self.busy or self._host._processing_queue.has_work:
            self._host.appAlertRequested.emit("Không thể chuyển", "Hãy chờ tác vụ hiện tại hoàn tất.", "info")
            return False
        if not str(destination).strip():
            return False
        self._start_storage_move(Path(destination))
        return True

    def _start_storage_move(self, destination: Path) -> None:
        def move() -> None:
            warmup = getattr(self._host, "_smart_warmup", None)
            try:
                if warmup is not None:
                    warmup.suspend_for_storage_move()
                target = self.manager.move_storage(destination)
                self._events.put({"kind": "moved", "pack_id": "", "target": str(target)})
                self._maintenance_thread = threading.Thread(
                    target=self.manager.cleanup_previous_storage,
                    name="resource-storage-cleanup",
                    daemon=True,
                )
                self._maintenance_thread.start()
            except Exception as exc:
                self._events.put({"kind": "move_error", "pack_id": "", "message": str(exc)})
            finally:
                if warmup is not None:
                    warmup.resume_after_storage_move()

        self._move_thread = threading.Thread(target=move, name="resource-storage-move", daemon=True)
        self._move_thread.start()
        self.changed.emit()

    @Slot()
    def browseAndMoveResourceStorage(self) -> None:
        if self.busy or self._host._processing_queue.has_work:
            self._host.appAlertRequested.emit("Không thể chuyển", "Hãy chờ tác vụ hiện tại hoàn tất.", "info")
            return
        selected = QFileDialog.getExistingDirectory(
            None,
            "Chọn ổ hoặc thư mục lưu gói tài nguyên",
            str(self.manager.storage_root.parent),
            QFileDialog.Option.ShowDirsOnly,
        )
        if not selected:
            return

        self._start_storage_move(Path(selected))

    def drain_events(self) -> None:
        changed = False
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            changed = True
            pack_id = event["pack_id"]
            kind = event["kind"]
            if kind == "moved":
                self._host.appAlertRequested.emit(
                    "Đã chuyển gói tài nguyên",
                    f"Vị trí mới: {event['target']}",
                    "info",
                )
                self.model.refresh()
            elif kind == "move_error":
                self._host.appAlertRequested.emit("Không thể chuyển", event.get("message", ""), "error")
            elif kind == "progress":
                self.model.set_operation(
                    pack_id,
                    status=event["status"],
                    progress=event["progress"],
                    detail=event["detail"],
                )
            elif kind == "done":
                self.model.clear_operation(pack_id)
                self._host.appAlertRequested.emit("Gói đã sẵn sàng", self.manager.definitions[pack_id].label, "info")
                warmup = getattr(self._host, "_smart_warmup", None)
                if warmup is not None:
                    warmup.request_project_prediction()
            elif kind == "paused":
                self.model.set_operation(pack_id, status="paused", detail="Đã tạm dừng")
            else:
                self.model.set_operation(pack_id, status="failed", detail=event.get("message", ""))
                self._host.appAlertRequested.emit("Không cài được gói", event.get("message", ""), "error")
        if changed:
            self.changed.emit()

    def shutdown(self) -> None:
        for pack_id in tuple(self._threads):
            self.manager.cancel(pack_id)
        for thread in tuple(self._threads.values()):
            if thread.is_alive():
                thread.join(timeout=0.5)
        if self._move_thread is not None and self._move_thread.is_alive():
            self._move_thread.join(timeout=0.5)
        if self._maintenance_thread.is_alive():
            self._maintenance_thread.join(timeout=0.5)
