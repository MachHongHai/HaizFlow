"""Independent render-to-user-copy jobs. No copy result mutates pipeline status."""

import errno
import queue
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

from haizflow.desktop.localization import QFileDialog, QMessageBox, native_media_dialog_directory
from haizflow.services import desktop_settings, video_store
from haizflow.services.video_export import (
    EXPORT_PRESETS, ExportCancelled, adopt_legacy_render, batch_filename, current_render, destination_identity,
    export_filename, export_video, legacy_render_owned, preset_settings, project_display_name, validate_export_destination,
)


class VideoExportController(QObject):
    def __init__(self, host, *, copier=export_video):
        super().__init__(host)
        self.host = host
        self.copier = copier
        self.jobs: list[dict] = []
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.events = queue.Queue()
        self._last_busy = False
        self._chosen_targets = {}
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    @property
    def busy(self):
        return bool((self.worker and self.worker.is_alive()) or any(job["status"] == "rendering" for job in self.jobs))

    def text(self, vi, en):
        return vi if self.host._settings_language == "vi" else en

    def changed(self):
        self.host.exportStateChanged.emit()

    def settings(self, video) -> dict:
        if not video:
            return {}
        return {
            "videoId": video.video_id,
            "filename": export_filename(project_display_name(video)),
            "preset": getattr(video, "export_preset", "source"),
            "ready": bool(current_render(video, verify=False)),
            "presets": [{"value": value, "label": item["label" if self.host._settings_language == "vi" else "en"]}
                        for value, item in EXPORT_PRESETS.items()],
        }

    def choose_file(self, video_id) -> str:
        video = video_store.get_video(str(video_id))
        if not video:
            return ""
        settings = desktop_settings.load_settings()
        directory = settings.get("last_export_directory") or native_media_dialog_directory()
        path, _ = QFileDialog.getSaveFileName(
            None, self.text("Chọn nơi xuất video", "Choose video export location"),
            str(Path(directory) / export_filename(project_display_name(video))), "MP4 (*.mp4)",
        )
        if not path:
            return ""
        try:
            target = validate_export_destination(path)
        except (OSError, ValueError) as exc:
            self.alert(exc)
            return ""
        self._chosen_targets[str(target)] = destination_identity(target)
        return str(target)

    def alert(self, error):
        self.host.appAlertRequested.emit(
            self.text("Không thể xuất video", "Video export failed"), self.error_text(error), "warning",
        )

    def error_text(self, error) -> str:
        if isinstance(error, ExportCancelled):
            return self.text("Đã hủy xuất. Bản dựng trong dự án được giữ nguyên.", "Export cancelled. The internal render is unchanged.")
        if isinstance(error, FileExistsError):
            return self.text("Tệp đích đã tồn tại. Chọn tên khác hoặc xác nhận thay thế.", "Destination exists. Choose another name or confirm replacement.")
        if isinstance(error, PermissionError):
            return self.text("Không có quyền ghi hoặc tệp đang được ứng dụng khác sử dụng. Đóng tệp hoặc chọn vị trí khác.",
                             "Write permission denied or file in use. Close the file or choose another location.")
        if isinstance(error, OSError) and error.errno == errno.ENOSPC:
            return self.text("Ổ lưu không đủ dung lượng. Chọn ổ khác và thử lại.", "Not enough disk space. Choose another drive and retry.")
        if isinstance(error, FileNotFoundError):
            return self.text("Không truy cập được thư mục hoặc bản dựng. Kết nối lại ổ đĩa; nếu bản dựng bị thiếu, dựng lại video.",
                             "Folder or render is unavailable. Reconnect the drive; rebuild the result if the render is missing.")
        return self.text("Không thể lưu ở vị trí này. Chọn thư mục ngoài dữ liệu dự án và thử lại. ",
                         "Cannot save here. Choose a folder outside managed project data and retry. ") + str(error)

    def start(self, video_id, preset, destination, *, overwrite=False) -> bool:
        if self.busy:
            return False
        video = video_store.get_video(str(video_id))
        try:
            preset_settings(str(preset))
            target = validate_export_destination(destination)
            if target.exists() and not overwrite:
                raise FileExistsError(str(target))
        except (OSError, ValueError) as exc:
            self.alert(exc)
            return False
        if not video or self.host._processing_queue.contains(video.video_id):
            return False
        video_store.update_video(video.video_id, export_preset=preset)
        video = video_store.get_video(video.video_id)
        job = {"videoId": video.video_id, "name": target.name, "path": str(target),
               "status": "pending", "progress": 0, "error": "", "overwrite": bool(overwrite),
               "targetIdentity": self._chosen_targets.get(str(target), destination_identity(target))}
        self.jobs = [job]
        self.cancel.clear()
        ready = current_render(video, verify=False)
        legacy = str((video.files or {}).get("final_video") or "")
        legacy_candidate = (not (video.active_artifacts or {}).get("export") and video.status == "done"
                            and bool(video.checkpoints.get("render")) and legacy and Path(legacy).is_file()
                            and legacy_render_owned(video, legacy))
        if not ready:
            # A legacy copy may be adopted only on the worker, never while QML
            # paints. If a rebuild is required, reuse upstream checkpoints.
            if legacy_candidate and video.project_type != "manual":
                self.launch([job])
            elif not self.request_render(video, job):
                self.jobs = []
                return False
        else:
            self.launch([job])
        self.changed()
        return True

    def request_render(self, video, job):
        if video.project_type == "manual":
            if str(self.host._selected_video_id or "") != video.video_id or not self.host.runManualTool("export"):
                return False
        else:
            from haizflow.pipeline.process_registry import prepare_video_resume

            prepare_video_resume(video.video_id)
            video_store.update_video(video.video_id, resume_step="rendering", error=None)
            if not self.host._enqueue_video(video.video_id):
                return False
        job["status"] = "rendering"
        return True

    def launch(self, jobs):
        self.worker = threading.Thread(target=self.copy_jobs, args=(jobs,), name="haizflow-video-export", daemon=False)
        self.worker.start()

    def copy_jobs(self, jobs):
        for job in jobs:
            identifier = job["videoId"]
            if self.cancel.is_set():
                self.events.put((identifier, "cancelled", 0, self.error_text(ExportCancelled())))
                continue
            self.events.put((identifier, "exporting", 0, ""))
            try:
                video = video_store.get_video(identifier)
                if not video:
                    raise FileNotFoundError(identifier)
                if not current_render(video):
                    adopt_legacy_render(video)
                    video = video_store.get_video(identifier)
                arguments = {"overwrite": job["overwrite"], "cancel": self.cancel,
                             "progress": lambda value, key=identifier: self.events.put((key, "exporting", value, ""))}
                if self.copier is export_video:
                    arguments["expected_target"] = job.get("targetIdentity")
                result = self.copier(video, job["path"], **arguments)
                try:
                    desktop_settings.save_settings({"last_export_directory": str(Path(result).parent)})
                except OSError:
                    pass
                self.events.put((identifier, "done", 100, ""))
            except Exception as exc:
                self.events.put((identifier, "cancelled" if isinstance(exc, ExportCancelled) else "failed", 0, self.error_text(exc)))

    def start_batch(self) -> bool:
        if self.busy:
            return False
        videos = [video_store.get_video(identifier) for identifier in self.host._batch_video_ids]
        videos = [video for video in videos if video]
        if not videos:
            self.alert(FileNotFoundError("No current render is available."))
            return False
        directory = QFileDialog.getExistingDirectory(None, self.text("Xuất các video đã dựng", "Export rendered videos"),
                                                     desktop_settings.load_settings().get("last_export_directory") or native_media_dialog_directory())
        if not directory:
            return False
        jobs = []
        for video in videos:
            try:
                target = validate_export_destination(Path(directory) / batch_filename(video))
            except (OSError, ValueError) as exc:
                self.alert(exc)
                return False
            jobs.append({"videoId": video.video_id, "name": target.name, "path": str(target), "status": "pending",
                         "progress": 0, "error": "", "overwrite": False,
                         "targetIdentity": destination_identity(target)})
        if any(Path(job["path"]).exists() for job in jobs):
            if QMessageBox.question(None, self.text("Thay thế tệp đã có?", "Replace existing files?"),
                                    self.text("Một số tệp đích đã tồn tại. Bạn muốn thay thế chúng?", "Some destination files already exist. Replace them?")) != QMessageBox.StandardButton.Yes:
                return False
            for job in jobs:
                job["overwrite"] = Path(job["path"]).exists()
        self.jobs = jobs
        self.cancel.clear()
        self.launch(jobs)
        self.changed()
        return True

    def retry_failed(self):
        if self.busy:
            return False
        jobs = [job for job in self.jobs if job["status"] in {"failed", "cancelled"}]
        if not jobs:
            return False
        for job in jobs:
            # A changed existing destination needs a new explicit confirmation,
            # not an automatic overwrite on retry.
            if job.get("overwrite") and destination_identity(job["path"]) != job.get("targetIdentity"):
                self.alert(FileExistsError(job["path"]))
                return False
        for job in jobs:
            job.update(status="pending", progress=0, error="")
        self.cancel.clear()
        self.launch(jobs)
        self.changed()
        return True

    def cancel_all(self):
        self.cancel.set()
        for job in self.jobs:
            if job["status"] == "rendering":
                job.update(status="cancelled", error=self.error_text(ExportCancelled()))
        self.changed()

    def poll(self):
        changed = False
        while not self.events.empty():
            identifier, status, progress, error = self.events.get_nowait()
            job = next((item for item in self.jobs if item["videoId"] == identifier), None)
            if job:
                job.update(status=status, progress=progress, error=error)
                changed = True
                if status == "done":
                    self.host.videoExportCompleted.emit(identifier, job["path"])
        for job in self.jobs:
            if job["status"] != "rendering" or self.host._processing_queue.contains(job["videoId"]):
                continue
            video = video_store.get_video(job["videoId"])
            if video and current_render(video, verify=False):
                job["status"] = "pending"
                self.launch([job])
            else:
                job.update(status="failed", error=self.text("Chưa hoàn tất dựng video. Tiếp tục tác vụ trong dự án rồi xuất lại.",
                                                            "Render not completed. Resume the project task, then export again."))
            changed = True
        if changed:
            self.changed()
        if self.busy != self._last_busy:
            self._last_busy = self.busy
            self.changed()

    def shutdown(self):
        self.timer.stop()
        self.cancel.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=10)
