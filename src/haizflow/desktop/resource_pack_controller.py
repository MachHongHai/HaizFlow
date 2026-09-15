"""Qt presentation layer for optional engines and model resource packs."""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from PySide6.QtCore import Property, QAbstractListModel, QModelIndex, QObject, Qt, Signal, Slot

from haizflow.desktop.localization import QFileDialog
from haizflow.desktop.presenters import format_memory_size
from haizflow.core.hardware import validate_processing_device
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
        self._snapshots: dict[str, dict] = {}
        self._operation_state: dict[str, dict] = {}
        self._seed_rows()

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

    def _seed_rows(self) -> None:
        """Present the manifest immediately; disk inventory runs off-thread."""
        self._snapshots = {
            definition.pack_id: {
                "packId": definition.pack_id,
                "label": definition.label,
                "group": definition.group,
                "version": definition.version,
                "capability": definition.capability,
                "backend": definition.backend,
                "status": "inventory",
                "downloadSize": definition.download_size,
                "installedSize": 0,
                "totalInstalledBytes": 0,
                "location": str(self._manager.storage_root),
                "dependencies": list(definition.dependencies),
                "canInstall": False,
                "canRemove": False,
                "blockedReason": "",
                "freeBytes": 0,
            }
            for definition in self._manager.definitions.values()
        }
        self._rebuild_rows()

    def _row(self, snapshot: dict, previous_group: str) -> dict:
        operation = self._operation_state.get(snapshot["packId"], {})
        status = operation.get("status", snapshot["status"])
        group_titles = {
            "processor": "Bộ xử lý",
            "recognition": "Nhận dạng",
            "translation": "Dịch",
            "voice": "Giọng đọc",
            "image": "Hình ảnh",
        }
        busy_states = {"checking", "downloading", "verifying", "removing"}
        return {
            **snapshot,
            "status": status,
            "progress": int(operation.get("progress", -1)),
            "detail": str(operation.get("detail", "")),
            "downloadSizeText": format_memory_size(snapshot["downloadSize"]),
            "installedSizeText": format_memory_size(snapshot["installedSize"]),
            "canInstall": snapshot["canInstall"] and status not in busy_states,
            "canRemove": snapshot["canRemove"] and status not in busy_states,
            "groupFirst": snapshot["group"] != previous_group,
            "groupTitle": group_titles.get(snapshot["group"], snapshot["group"]),
        }

    def _rebuild_rows(self) -> None:
        rows = []
        previous_group = ""
        for definition in self._manager.definitions.values():
            snapshot = self._snapshots[definition.pack_id]
            rows.append(self._row(snapshot, previous_group))
            previous_group = snapshot["group"]
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def apply_snapshot(self, snapshots: list[dict]) -> None:
        incoming = {str(item["packId"]): dict(item) for item in snapshots}
        if incoming:
            self._snapshots.update(incoming)
        self._rebuild_rows()

    def refresh(self) -> None:
        """Synchronous compatibility hook; controllers use background inventory."""
        self.apply_snapshot(self._manager.snapshot())

    def _update_operation_row(self, pack_id: str) -> None:
        for row_index, row in enumerate(self._rows):
            if row.get("packId") != pack_id:
                continue
            previous_group = self._rows[row_index - 1]["group"] if row_index else ""
            self._rows[row_index] = self._row(self._snapshots[pack_id], previous_group)
            model_index = self.index(row_index)
            self.dataChanged.emit(model_index, model_index)
            return

    def set_operation(self, pack_id: str, *, status: str, progress: int = -1, detail: str = "") -> None:
        self._operation_state[pack_id] = {"status": status, "progress": progress, "detail": detail}
        self._update_operation_row(pack_id)

    def clear_operation(self, pack_id: str) -> None:
        self._operation_state.pop(pack_id, None)
        self._update_operation_row(pack_id)

    @property
    def installed_bytes(self) -> int:
        measured = max(
            (int(item.get("totalInstalledBytes", 0)) for item in self._snapshots.values()),
            default=0,
        )
        return measured or sum(int(item.get("installedSize", 0)) for item in self._snapshots.values())

    @property
    def free_bytes(self) -> int:
        return max((int(item.get("freeBytes", 0)) for item in self._snapshots.values()), default=0)


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
        self._inventory_thread: threading.Thread | None = None
        self._clean_thread: threading.Thread | None = None
        # A previous cross-drive move can leave several gigabytes to remove.
        # Never perform that recursive deletion while the QML singleton is
        # constructing its first frame.
        self._maintenance_thread = threading.Thread(
            target=self._run_startup_maintenance,
            name="resource-storage-cleanup",
            daemon=True,
        )
        self._maintenance_thread.start()
        self._start_inventory()

    def _run_startup_maintenance(self) -> None:
        self.manager.cleanup_previous_storage()
        # Keep resumable downloads from recent sessions. Only abandoned
        # staging files older than a week are safe to remove automatically.
        self.manager.clean_unused(minimum_age_seconds=7 * 24 * 60 * 60)

    @Property(QObject, constant=True)
    def packModel(self):
        return self.model

    def _display_context(self) -> dict:
        selected_video = None
        selected_video_getter = getattr(self._host, "_selected_video", None)
        if callable(selected_video_getter):
            selected_video = selected_video_getter()
        return {
            "device": str(getattr(self._host, "_settings_processing_device", "cpu") or "cpu"),
            "model": str(
                getattr(selected_video, "speech_recognition_model", "")
                or getattr(self._host, "_speech_recognition_model", "small")
                or "small"
            ),
            "source_language": str(getattr(selected_video, "source_language", "") or ""),
            "language": str(
                getattr(selected_video, "target_language", "")
                or getattr(self._host, "_target_language", "")
                or ""
            ),
        }

    def _hardware_compatibility(self, pack_id: str) -> tuple[bool, str]:
        capabilities = getattr(self._host, "_hardware_capabilities", None)
        if capabilities is None:
            return True, ""
        if pack_id in {"engine-cuda128-py313", "model-speech-gpu"}:
            compatible, reason = validate_processing_device("gpu", capabilities)
            if not compatible and getattr(self._host, "_settings_language", "vi") == "vi":
                if not capabilities.cuda_available:
                    reason = "Không phát hiện GPU NVIDIA tương thích CUDA."
                elif capabilities.ac_powered is False:
                    reason = "Hãy cắm sạc trước khi dùng cấu hình NVIDIA."
                elif capabilities.total_vram_bytes < 7 * 1024**3:
                    reason = (
                        "Cần ít nhất 7 GB VRAM; máy này có "
                        f"{capabilities.total_vram_bytes / (1024**3):.1f} GB."
                    )
                elif capabilities.free_vram_bytes and capabilities.free_vram_bytes < 5 * 1024**3:
                    reason = (
                        "Cần ít nhất 5 GB VRAM trống; hiện còn "
                        f"{capabilities.free_vram_bytes / (1024**3):.1f} GB."
                    )
                else:
                    reason = "Cấu hình NVIDIA cần máy có ít nhất 16 GB RAM."
            return compatible, reason
        if pack_id in {"engine-cpu-py313", "model-speech-cpu"}:
            compatible, reason = validate_processing_device("cpu", capabilities)
            if not compatible and getattr(self._host, "_settings_language", "vi") == "vi":
                reason = "Cấu hình CPU cần máy có ít nhất 16 GB RAM."
            return compatible, reason
        return True, ""

    @property
    def displayRows(self) -> list[dict]:
        """Return honest install units grouped by machine profile."""
        context = self._display_context()
        device = "gpu" if context["device"] == "gpu" else "cpu"
        gpu_compatible, gpu_warning = self._hardware_compatibility("engine-cuda128-py313")
        cpu_compatible, cpu_warning = self._hardware_compatibility("engine-cpu-py313")
        ordered_ids = [
            "engine-cuda128-py313",
            "model-speech-gpu",
            "engine-cpu-py313",
            "model-speech-cpu",
            "model-omnivoice",
            "model-demucs",
            "engine-vision-onnx",
            "model-subtitle-ocr",
        ]
        source_rows = {str(row.get("packId")): row for row in self.model._rows}
        descriptions = {
            "engine-cpu-py313": "Môi trường chạy model trên bộ xử lý chính.",
            "engine-cuda128-py313": "Môi trường tăng tốc dành cho GPU NVIDIA.",
            "engine-vision-onnx": "Môi trường nhận biết vùng chữ trong khung hình.",
            "model-speech-cpu": "Whisper Small, HY-MT2 và căn thời gian lời thoại.",
            "model-speech-gpu": "Whisper Small/Turbo, HY-MT2 và căn thời gian lời thoại.",
            "model-omnivoice": "Tạo giọng đọc cục bộ.",
            "model-demucs": "Tách lời thoại và âm thanh nền.",
            "model-subtitle-ocr": "Nhận biết vị trí phụ đề gốc.",
        }
        result: list[dict] = []
        previous_group = ""
        for pack_id in ordered_ids:
            if pack_id not in source_rows:
                continue
            source = dict(source_rows[pack_id])
            if pack_id in {"engine-cuda128-py313", "model-speech-gpu"}:
                group = "gpu"
                title = "NVIDIA · Khuyên dùng" if device == "gpu" and gpu_compatible else "NVIDIA"
                compatible, warning = gpu_compatible, "" if gpu_compatible else gpu_warning
            elif pack_id in {"engine-cpu-py313", "model-speech-cpu"}:
                group = "cpu"
                title = "CPU · Khuyên dùng" if device == "cpu" or not gpu_compatible else "CPU · Tùy chọn"
                compatible, warning = cpu_compatible, "" if cpu_compatible else cpu_warning
            else:
                group, title = "tools", "Công cụ bổ sung"
                compatible, warning = True, ""
            source.update(
                {
                    "group": group,
                    "groupTitle": title,
                    "groupFirst": group != previous_group,
                    "summary": descriptions.get(pack_id, ""),
                    "hardwareCompatible": compatible,
                    "hardwareWarning": warning,
                    "recommended": (group == device and compatible),
                    "canInstall": bool(source.get("canInstall")) and compatible,
                }
            )
            result.append(source)
            previous_group = group
        return result

    @Property(str, notify=changed)
    def storageLocation(self):
        return str(self.manager.storage_root)

    @Property(str, notify=changed)
    def totalInstalledText(self):
        return format_memory_size(self.model.installed_bytes)

    @Property(str, notify=changed)
    def freeSpaceText(self):
        return format_memory_size(self.model.free_bytes)

    @Property(bool, notify=changed)
    def busy(self):
        return any(thread.is_alive() for thread in self._threads.values()) or bool(
            self._move_thread and self._move_thread.is_alive()
        ) or bool(self._inventory_thread and self._inventory_thread.is_alive()) or bool(
            self._clean_thread and self._clean_thread.is_alive()
        )

    @Property(str, notify=changed)
    def activityText(self):
        if self._move_thread is not None and self._move_thread.is_alive():
            return "Đang chuyển gói cài đặt"
        if self._clean_thread is not None and self._clean_thread.is_alive():
            return "Đang dọn tệp tải dở"
        active_states = {"checking", "downloading", "verifying", "removing"}
        for row in self.model._rows:
            if row.get("status") not in active_states:
                continue
            detail = str(row.get("detail") or "").strip()
            label = str(row.get("label") or row.get("packId") or "").strip()
            return " · ".join(part for part in (label, detail) if part)
        if self._inventory_thread is not None and self._inventory_thread.is_alive():
            return "Đang kiểm tra gói cài đặt"
        return ""

    @Property(int, notify=changed)
    def activityProgress(self):
        if self._move_thread is not None and self._move_thread.is_alive():
            return -1
        active_states = {"checking", "downloading", "verifying", "removing"}
        for row in self.model._rows:
            if row.get("status") in active_states:
                return int(row.get("progress", -1))
        return -1

    def _start_inventory(self) -> None:
        if self._inventory_thread is not None and self._inventory_thread.is_alive():
            return

        def inventory() -> None:
            try:
                self._events.put({"kind": "inventory", "pack_id": "", "snapshot": self.manager.snapshot()})
            except Exception as exc:
                self._events.put({"kind": "inventory_error", "pack_id": "", "message": str(exc)})

        self._inventory_thread = threading.Thread(
            target=inventory,
            name="resource-pack-inventory",
            daemon=True,
        )
        self._inventory_thread.start()

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
            self._events.put({
                "kind": "done",
                "pack_id": pack_id,
                "snapshot": self.manager.snapshot(),
            })
        except ModelBootstrapCancelled:
            self._events.put({
                "kind": "paused",
                "pack_id": pack_id,
                "snapshot": self.manager.snapshot(),
            })
        except Exception as exc:
            try:
                snapshot = self.manager.snapshot()
            except Exception:
                snapshot = []
            self._events.put({
                "kind": "error",
                "pack_id": pack_id,
                "message": str(exc),
                "snapshot": snapshot,
            })

    @Slot("QVariantList")
    def installResourcePacks(self, pack_ids) -> None:
        for raw_pack_id in pack_ids:
            pack_id = str(raw_pack_id)
            if pack_id not in self.manager.definitions:
                continue
            compatible, reason = self._hardware_compatibility(pack_id)
            if not compatible:
                self._host.appAlertRequested.emit(
                    "Gói không phù hợp với máy này",
                    reason,
                    "warning",
                )
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
        if pack_id not in self.manager.definitions:
            return False
        current = self._threads.get(pack_id)
        if current is not None and current.is_alive():
            return False
        if in_use:
            self._host.appAlertRequested.emit(
                "Không thể gỡ gói",
                "Gói đang được model hoặc tác vụ hiện tại sử dụng.",
                "error",
            )
            return False
        self.model.set_operation(pack_id, status="removing", detail="Đang gỡ")

        def remove() -> None:
            try:
                # Stop persistent orchestration processes on this worker so a
                # slow Windows process shutdown or multi-gigabyte deletion can
                # never block QML input/rendering.
                definition = self.manager.definitions[pack_id]
                if definition.engine_modules or definition.capability == "translation":
                    from haizflow.services.translation import shutdown_hymt2_worker

                    shutdown_hymt2_worker()
                if definition.engine_modules or definition.capability == "voice":
                    from haizflow.pipeline.omnivoice_tts import clear_runtime

                    clear_runtime()
                if warmup is not None:
                    warmup.close_idle_pack(pack_id)
                removed = self.manager.remove(pack_id, in_use=False)
                self._events.put({
                    "kind": "removed",
                    "pack_id": pack_id,
                    "removed": removed,
                    "snapshot": self.manager.snapshot(),
                })
            except (KeyError, OSError, ResourcePackError) as error:
                try:
                    snapshot = self.manager.snapshot()
                except Exception:
                    snapshot = []
                self._events.put({
                    "kind": "remove_error",
                    "pack_id": pack_id,
                    "message": str(error),
                    "snapshot": snapshot,
                })

        thread = threading.Thread(target=remove, name=f"resource-remove-{pack_id}", daemon=True)
        self._threads[pack_id] = thread
        thread.start()
        self.changed.emit()
        return True

    @Slot(result=str)
    def cleanUnusedResourcePacks(self) -> str:
        if self._clean_thread is not None and self._clean_thread.is_alive():
            return ""

        def clean() -> None:
            try:
                removed = self.manager.clean_unused()
                self._events.put({
                    "kind": "cleaned",
                    "pack_id": "",
                    "removed": removed,
                    "snapshot": self.manager.snapshot(),
                })
            except OSError as exc:
                self._events.put({"kind": "clean_error", "pack_id": "", "message": str(exc)})

        self._clean_thread = threading.Thread(target=clean, name="resource-pack-clean", daemon=True)
        self._clean_thread.start()
        self.changed.emit()
        return ""

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
                self._events.put({
                    "kind": "moved",
                    "pack_id": "",
                    "target": str(target),
                    "snapshot": self.manager.snapshot(),
                })
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
            "Chọn ổ hoặc thư mục lưu gói cài đặt",
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
                    "Đã chuyển gói cài đặt",
                    f"Vị trí mới: {event['target']}",
                    "info",
                )
                self.model.apply_snapshot(event["snapshot"])
            elif kind == "move_error":
                self._host.appAlertRequested.emit("Không thể chuyển", event.get("message", ""), "error")
            elif kind == "inventory":
                self.model.apply_snapshot(event["snapshot"])
            elif kind == "inventory_error":
                self._host.appAlertRequested.emit("Không thể đọc gói cài đặt", event.get("message", ""), "error")
            elif kind == "progress":
                self.model.set_operation(
                    pack_id,
                    status=event["status"],
                    progress=event["progress"],
                    detail=event["detail"],
                )
            elif kind == "done":
                self.model.apply_snapshot(event["snapshot"])
                self.model.clear_operation(pack_id)
                self._host.appAlertRequested.emit("Gói đã sẵn sàng", self.manager.definitions[pack_id].label, "info")
                warmup = getattr(self._host, "_smart_warmup", None)
                if warmup is not None:
                    warmup.request_project_prediction()
            elif kind == "removed":
                self.model.apply_snapshot(event["snapshot"])
                self.model.clear_operation(pack_id)
                self._host.appAlertRequested.emit(
                    "Đã gỡ gói",
                    f"Đã giải phóng {format_memory_size(event.get('removed', 0))}.",
                    "info",
                )
            elif kind == "remove_error":
                self.model.apply_snapshot(event.get("snapshot", []))
                self.model.clear_operation(pack_id)
                self._host.appAlertRequested.emit("Không thể gỡ gói", event.get("message", ""), "error")
            elif kind == "cleaned":
                self.model.apply_snapshot(event["snapshot"])
                self._host.appAlertRequested.emit(
                    "Đã dọn tệp tải dở",
                    f"Đã giải phóng {format_memory_size(event.get('removed', 0))}.",
                    "info",
                )
            elif kind == "clean_error":
                self._host.appAlertRequested.emit("Không thể dọn tệp", event.get("message", ""), "error")
            elif kind == "paused":
                self.model.apply_snapshot(event.get("snapshot", []))
                self.model.set_operation(pack_id, status="paused", detail="Đã tạm dừng")
            else:
                self.model.apply_snapshot(event.get("snapshot", []))
                snapshot_status = self.model._snapshots.get(pack_id, {}).get("status")
                if snapshot_status in {"installed", "bundled"}:
                    self.model.clear_operation(pack_id)
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
        if self._inventory_thread is not None and self._inventory_thread.is_alive():
            self._inventory_thread.join(timeout=0.5)
        if self._clean_thread is not None and self._clean_thread.is_alive():
            self._clean_thread.join(timeout=0.5)
        if self._maintenance_thread.is_alive():
            self._maintenance_thread.join(timeout=0.5)
