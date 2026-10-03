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
        return bool((self.worker and self.worker.is_alive()) or not self.events.empty()
                    or any(job["status"] == "rendering" for job in self.jobs))

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

    def batch_settings(self) -> dict:
        videos = [video_store.get_video(key) for key in self.host._batch_video_ids]
        videos = [video for video in videos if video]
        result = self.settings(videos[0]) if videos else {}
        result.update(projectKey=str(self.host._selected_project_key or ""),
                      videoIds=[video.video_id for video in videos], count=len(videos))
        return result

    def choose_batch_directory(self) -> str:
        directory = QFileDialog.getExistingDirectory(
            None, self.text("Chọn thư mục xuất video", "Choose video export folder"),
            desktop_settings.load_settings().get("last_export_directory") or native_media_dialog_directory(),
        )
        if not directory:
            return ""
        try:
            targets = []
            for video_id in self.host._batch_video_ids:
                video = video_store.get_video(video_id)
                if video:
                    target = validate_export_destination(Path(directory) / batch_filename(video))
                    targets.append((target, destination_identity(target)))
            existing = sum(target.exists() for target, _identity in targets)
            if existing and QMessageBox.question(
                None, self.text("Thay thế video đã có?", "Replace existing videos?"),
                self.text(f"Có {existing} tệp trùng tên trong thư mục đã chọn. Thay thế khi xuất?",
                          f"{existing} files already exist in the selected folder. Replace them when exporting?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return ""
            for target, identity in targets:
                self._chosen_targets[str(target)] = identity
        except (OSError, ValueError) as exc:
            self.alert(exc)
            return ""
        return str(Path(directory).resolve())

    def batch_destination_exists(self, directory) -> bool:
        return any((Path(directory) / batch_filename(video)).exists()
                   for key in self.host._batch_video_ids if (video := video_store.get_video(key)))

    def _set_jobs(self, jobs):
        # Paused exports from another project must survive navigation and a
        # new job. Replacing a destination for the same video is explicit.
        identifiers = {job["videoId"] for job in jobs}
        waiting = [job for job in self.jobs if job["status"] in {"paused", "awaiting_review"}
                   and job["videoId"] not in identifiers]
        self.jobs = waiting + jobs

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

    def start(self, video_id, preset, destination, *, overwrite=False, process=False) -> bool:
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
        if process and (video.project_type not in {"single", "batch"}
                        or video.video_id != str(self.host._selected_video_id or "")):
            return False
        previous_preset = video.export_preset
        video_store.update_video(video.video_id, export_preset=preset)
        video = video_store.get_video(video.video_id)
        job = {"videoId": video.video_id, "name": target.name, "path": str(target),
               "status": "pending", "progress": 0, "error": "", "overwrite": bool(overwrite),
               "process": bool(process),
               "targetIdentity": self._chosen_targets.get(str(target), destination_identity(target))}
        previous_jobs = self.jobs
        self._set_jobs([job])
        self.cancel.clear()
        ready = current_render(video, verify=False)
        legacy = str((video.files or {}).get("final_video") or "")
        legacy_candidate = (not (video.active_artifacts or {}).get("export") and video.status == "done"
                            and preset == previous_preset
                            and bool(video.checkpoints.get("render")) and legacy and Path(legacy).is_file()
                            and legacy_render_owned(video, legacy))
        if process:
            from haizflow.desktop.project_commands_controller import ProjectCommandsController

            if not ProjectCommandsController(self.host).process_for_export(video.video_id):
                video_store.update_video(video.video_id, export_preset=previous_preset)
                self.jobs = previous_jobs
                self.changed()
                return False
            job["status"] = "rendering"
        elif not ready:
            # A legacy copy may be adopted only on the worker, never while QML
            # paints. If a rebuild is required, reuse upstream checkpoints.
            if legacy_candidate and video.project_type != "manual":
                self.launch([job])
            elif not self.request_render(video, job):
                video_store.update_video(video.video_id, export_preset=previous_preset)
                self.jobs = previous_jobs
                return False
        else:
            self.launch([job])
        self.changed()
        return True

    def start_batch_to(self, project_key, video_ids, preset, directory, *, overwrite=False, process=True) -> bool:
        """Capture destinations and validate the whole batch before enqueueing."""
        if (self.busy or not video_ids or project_key != str(self.host._selected_project_key or "")
                or list(video_ids) != list(self.host._batch_video_ids)):
            return False
        videos = [video_store.get_video(key) for key in video_ids]
        if any(not video or video.project_type != "batch" or video.project_key != project_key
               or self.host._processing_queue.contains(video.video_id) or video.status == "processing"
               for video in videos):
            return False
        jobs = []
        try:
            preset_settings(str(preset))
            if not Path(directory).is_dir():
                raise FileNotFoundError(directory)
            for video in videos:
                target = validate_export_destination(Path(directory) / batch_filename(video))
                if target.exists() and not overwrite:
                    raise FileExistsError(str(target))
                jobs.append({"videoId": video.video_id, "name": target.name, "path": str(target),
                             "status": "rendering" if process else "pending", "progress": 0, "error": "",
                             "overwrite": bool(overwrite), "process": bool(process),
                             "targetIdentity": self._chosen_targets.get(str(target), destination_identity(target))})
        except (OSError, ValueError) as exc:
            self.alert(exc)
            return False
        from haizflow.desktop.project_commands_controller import ProjectCommandsController

        if process and not ProjectCommandsController._resources_ready_for_videos(self.host, videos):
            return False
        if process:
            try:
                # Validate every member before touching any cached result.
                for video in videos:
                    video_store.validate_video_restart(video.video_id)
                for video in videos:
                    video_store.prepare_video_restart(video.video_id)
            except (OSError, RuntimeError, ValueError) as exc:
                self.alert(exc)
                return False
        previous_jobs = self.jobs
        self._set_jobs(jobs)
        self.cancel.clear()
        for video in videos:
            video_store.update_video(video.video_id, export_preset=str(preset))
        if process:
            from haizflow.pipeline.process_registry import prepare_video_resume

            for video in videos:
                prepare_video_resume(video.video_id)
            self.host._batch_running = True
            self.host._batch_stop_requested = False
            if not self.host._enqueue_videos(list(video_ids)):
                self.host._batch_running = False
                self.jobs = previous_jobs
                self.changed()
                return False
            self.host.batchChanged.emit()
            self.host.refreshVideos()
        else:
            ready = []
            for job in jobs:
                video = video_store.get_video(job["videoId"])
                if current_render(video, verify=False):
                    ready.append(job)
                elif not self.request_render(video, job):
                    job.update(status="failed", error=self.text("Không thể dựng video.", "Cannot render video."))
            if ready:
                self.launch(ready)
        self.changed()
        return True

    def request_render(self, video, job):
        if video.project_type == "manual":
            if str(self.host._selected_video_id or "") != video.video_id or not self.host.runManualTool("export"):
                return False
        else:
            from haizflow.desktop.project_commands_controller import ProjectCommandsController
            from haizflow.pipeline.process_registry import prepare_video_resume

            if not ProjectCommandsController._resources_ready(self.host, video):
                return False
            prepare_video_resume(video.video_id)
            # A resume hint enables checkpoint reuse, not stage skipping. The
            # pipeline still validates every upstream signature and output.
            video_store.update_video(video.video_id, status="pending", resume_step="rendering", error=None)
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
        ready_videos = [video for video in videos if video.status == "done"
                        and not self.host._processing_queue.contains(video.video_id)
                        and (current_render(video, verify=False)
                             or (not (video.active_artifacts or {}).get("export")
                                 and video.checkpoints.get("render")
                                 and Path(str((video.files or {}).get("final_video") or "")).is_file()
                                 and legacy_render_owned(video, video.files["final_video"])))]
        if not ready_videos:
            self.alert(FileNotFoundError("No current render is available."))
            return False
        skipped = len(videos) - len(ready_videos)
        videos = ready_videos
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
        if skipped:
            self.host.appAlertRequested.emit(
                self.text("Xuất hàng loạt", "Batch export"),
                self.text(f"Xuất {len(videos)} video đã dựng. Bỏ qua {skipped} video chưa hoàn tất hoặc cần dựng lại.",
                          f"Exporting {len(videos)} rendered videos. Skipping {skipped} unfinished or outdated videos."),
                "info",
            )
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
        ready = []
        for job in jobs:
            video = video_store.get_video(job["videoId"])
            if video and (video.project_type == "manual" or video.status == "done") and current_render(video, verify=False):
                ready.append(job)
            elif video and not self.host._processing_queue.contains(video.video_id) and self.request_render(video, job):
                continue
            else:
                job.update(status="failed", error=self.text("Tiếp tục xử lý trong dự án trước khi xuất lại.",
                                                            "Resume processing in the project before retrying export."))
        if ready:
            self.launch(ready)
        self.changed()
        return True

    def cancel_all(self):
        self.cancel.set()
        for job in self.jobs:
            if job["status"] in {"rendering", "paused", "awaiting_review"}:
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
            if job["status"] not in {"rendering", "paused", "awaiting_review"}:
                continue
            if self.host._processing_queue.contains(job["videoId"]):
                if job["status"] != "rendering":
                    job.update(status="rendering", error="")
                    changed = True
                continue
            if self.worker and self.worker.is_alive():
                continue
            video = video_store.get_video(job["videoId"])
            if video and video.status == "processing":
                # The queue must remain the owner until it detaches the item.
                continue
            if video and video.status in {"paused", "awaiting_review"}:
                if job["status"] != video.status:
                    job.update(status=video.status, error=self.text(
                        "Đang chờ tiếp tục xử lý hoặc duyệt phụ đề trong dự án.",
                        "Waiting for processing to resume or subtitles to be approved in the project."))
                    changed = True
                continue
            if video and video.status == "done" and current_render(video, verify=False):
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
