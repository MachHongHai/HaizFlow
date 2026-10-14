"""Independent render-to-user-copy jobs. No copy result mutates pipeline status."""

import errno
import queue
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

from hflow.desktop.localization import QFileDialog, QMessageBox, native_media_dialog_directory
from hflow.services import desktop_settings, video_store
from hflow.services.video_export import (
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
        self._batch_notices = []
        self._cancelling_render_tokens = {}
        self._pending_run_cleanup = False
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    @property
    def busy(self):
        from hflow.services.processing_runs import discard_pending

        return bool((self.worker and self.worker.is_alive()) or not self.events.empty()
                    or self._pending_run_cleanup
                    or any(discard_pending(job["videoId"], job.get("runScopeId")) for job in self.jobs
                           if job["status"] == "cancelled" and job.get("runScopeId"))
                    or any(job["status"] == "rendering" for job in self.jobs)
                    or any(self.host._processing_queue.token_for(key) == token
                           for key, token in self._cancelling_render_tokens.items()))

    def text(self, vi, en):
        return vi if self.host._settings_language == "vi" else en

    def changed(self):
        self.host.exportStateChanged.emit()

    def _capture_render_owner(self, job):
        task_queue = self.host._processing_queue
        if hasattr(task_queue, "token_for"):
            job["renderToken"] = task_queue.token_for(job["videoId"])

    def _watch_batch(self, jobs):
        # Capture actual job objects, not the currently open project. Paused
        # batches survive navigation and cannot be confused with a later run.
        identifiers = {job["videoId"] for job in jobs}
        self._batch_notices = [group for group in self._batch_notices
                               if not any(job["videoId"] in identifiers for job in group)]
        self._batch_notices.append(list(jobs))

    def _report_finished_batches(self):
        from hflow.services.batch_feedback import completion_notice

        for group in list(self._batch_notices):
            if any(job["videoId"] in self._cancelling_render_tokens for job in group):
                continue
            if any(job["status"] not in {"done", "failed", "cancelled"} for job in group):
                continue
            summary = {"succeeded": sum(job["status"] == "done" for job in group),
                       "failed": sum(job["status"] == "failed" for job in group),
                       "cancelled": sum(job["status"] == "cancelled" for job in group)}
            self._batch_notices.remove(group)
            self.host.appAlertRequested.emit(*completion_notice(summary, self.host._settings_language))

    def settings(self, video) -> dict:
        if not video:
            return {}
        from hflow.services import editor_documents, result_segments

        document = editor_documents.load(video.video_id) if video.project_type == "manual" else None
        return {
            "videoId": video.video_id,
            "filename": export_filename(project_display_name(video)),
            "preset": getattr(video, "export_preset", "source"),
            "ready": bool(current_render(video, verify=False)),
            "segments": result_segments.ranges(document) if document else [],
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
            return self.text("Đã hủy xuất. Kết quả từ trước lượt này được giữ nguyên.",
                             "Export cancelled. Results from before this run are unchanged.")
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

    def start(self, video_id, preset, destination, *, overwrite=False, process=False, segment_id="") -> bool:
        if self.busy:
            return False
        video = video_store.get_video(str(video_id))
        selected_range = None
        try:
            if segment_id:
                from hflow.services import editor_documents, result_segments

                document = editor_documents.load(video.video_id) if video and video.project_type == "manual" else None
                selected_range = next((item for item in result_segments.ranges(document)
                                       if item["id"] == str(segment_id)), None) if document else None
                if selected_range is None or process:
                    raise ValueError(self.text("Đoạn kết quả không còn hợp lệ. Mở lại cửa sổ xuất.",
                                               "The result segment changed. Reopen the export dialog."))
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
               "rangeMs": [selected_range["startMs"], selected_range["endMs"]] if selected_range else None,
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
        if selected_range:
            # Segment jobs own a bounded render, never enqueue a whole-video
            # manual export merely because the full render cache is absent.
            self.launch([job])
        elif process:
            from hflow.desktop.project_commands_controller import ProjectCommandsController
            from hflow.services import processing_runs

            job["runScopeId"] = processing_runs.arm_export(video.video_id)
            job["renderRequired"] = True
            if not ProjectCommandsController(self.host).process_for_export(video.video_id):
                processing_runs.disarm_export(video.video_id)
                video_store.update_video(video.video_id, export_preset=previous_preset)
                self.jobs = previous_jobs
                self.changed()
                return False
            job["status"] = "rendering"
            self._capture_render_owner(job)
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
        from hflow.desktop.project_commands_controller import ProjectCommandsController

        if process and not ProjectCommandsController._resources_ready_for_videos(self.host, videos):
            return False
        if process:
            try:
                # Validate every member before touching any cached result.
                for video in videos:
                    video_store.validate_video_restart(video.video_id)
            except (OSError, RuntimeError, ValueError) as exc:
                self.alert(exc)
                return False
            ready_videos = []
            for video, job in zip(videos, jobs):
                try:
                    video_store.prepare_video_restart(video.video_id)
                    ready_videos.append(video)
                except (OSError, RuntimeError, ValueError) as exc:
                    # A per-file cleanup failure after the safe preflight is
                    # isolated. Never discard other members' successful work.
                    job.update(status="failed", error=str(exc))
            videos = ready_videos
        self._set_jobs(jobs)
        self.cancel.clear()
        for video in videos:
            video_store.update_video(video.video_id, export_preset=str(preset))
        if process:
            from hflow.pipeline.process_registry import prepare_video_resume
            from hflow.services import processing_runs

            for video in videos:
                job = next(item for item in jobs if item["videoId"] == video.video_id)
                job["renderRequired"] = True
                job["runScopeId"] = processing_runs.arm_export(video.video_id)
                prepare_video_resume(video.video_id)
            self.host._batch_running = True
            self.host._batch_stop_requested = False
            if not videos or not self.host._enqueue_videos([video.video_id for video in videos]):
                self.host._batch_running = False
                for job in jobs:
                    if job["status"] == "rendering":
                        processing_runs.disarm_export(job["videoId"])
                        video = video_store.get_video(job["videoId"])
                        job.update(status="failed", error=str(getattr(video, "error", "") or "") or self.text(
                            "Không thể đưa video vào hàng đợi.", "Cannot enqueue video."))
            self.host.batchChanged.emit()
            self.host.refreshVideos()
            for job in jobs:
                if job["status"] == "rendering":
                    self._capture_render_owner(job)
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
        self._watch_batch(jobs)
        return True

    def request_render(self, video, job):
        from hflow.services import processing_runs

        job["manualIdleState"] = processing_runs.manual_export_state(video)
        job["renderRequired"] = True
        job["runScopeId"] = processing_runs.arm_export(video.video_id)
        if video.project_type == "manual":
            if str(self.host._selected_video_id or "") != video.video_id or not self.host.runManualTool("export"):
                processing_runs.disarm_export(video.video_id)
                return False
        else:
            from hflow.desktop.project_commands_controller import ProjectCommandsController
            from hflow.pipeline.process_registry import prepare_video_resume

            if not ProjectCommandsController._resources_ready(self.host, video):
                processing_runs.disarm_export(video.video_id)
                return False
            prepare_video_resume(video.video_id)
            # A resume hint enables checkpoint reuse, not stage skipping. The
            # pipeline still validates every upstream signature and output.
            video_store.update_video(video.video_id, status="pending", resume_step="rendering", error=None)
            if not self.host._enqueue_video(video.video_id):
                processing_runs.disarm_export(video.video_id)
                return False
        job["status"] = "rendering"
        self._capture_render_owner(job)
        return True

    def launch(self, jobs):
        self.worker = threading.Thread(target=self.copy_jobs, args=(jobs,), name="hflow-video-export", daemon=False)
        self.worker.start()

    def copy_jobs(self, jobs):
        for job in jobs:
            identifier = job["videoId"]
            if self.cancel.is_set():
                self.events.put((identifier, "cancelled", 0, self.error_text(ExportCancelled())))
                continue
            self.events.put((identifier, "exporting", 0, ""))
            try:
                if not job.get("runScopeId"):
                    from hflow.services.processing_runs import commit_previous_ready

                    commit_previous_ready(identifier)
                video = video_store.get_video(identifier)
                if not video:
                    raise FileNotFoundError(identifier)
                # The copier hashes the source as it streams it and verifies
                # the destination. Do not pre-read an entire large render here.
                if not job.get("rangeMs") and not current_render(video, verify=False):
                    adopt_legacy_render(video)
                    video = video_store.get_video(identifier)
                arguments = {"overwrite": job["overwrite"], "cancel": self.cancel,
                             "progress": lambda value, key=identifier: self.events.put((key, "exporting", value, ""))}
                if self.copier is export_video:
                    arguments["expected_target"] = job.get("targetIdentity")
                    if job.get("rangeMs"):
                        arguments["range_ms"] = tuple(job["rangeMs"])
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
        self._watch_batch(jobs)
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
            job.pop("runSettled", None)
        if any((video := video_store.get_video(job["videoId"])) and video.project_type == "batch" for job in jobs):
            self._watch_batch(jobs)
        self.cancel.clear()
        ready = []
        for job in jobs:
            video = video_store.get_video(job["videoId"])
            if video and (job.get("rangeMs") or (
                    (video.project_type == "manual" or video.status == "done") and current_render(video, verify=False))):
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
        task_queue = self.host._processing_queue
        tokens = {job["videoId"]: job["renderToken"] for job in self.jobs
                  if job.get("renderToken") is not None
                  and job["status"] in {"rendering", "paused", "awaiting_review"}}
        from hflow.pipeline.process_registry import cancel_video
        from hflow.services import processing_runs

        def cancel_owned(identifier):
            job = next(item for item in self.jobs if item["videoId"] == identifier)
            if job.get("runScopeId"):
                processing_runs.request_discard(identifier, job["runScopeId"])
            cancel_video(identifier)

        active, removed = task_queue.detach_owned(tokens, on_active=cancel_owned) if tokens else (None, [])
        if active:
            self._cancelling_render_tokens[active] = tokens[active]
        for identifier in [*removed, *([active] if active else [])]:
            job = next(item for item in self.jobs if item["videoId"] == identifier)
            if job.get("runScopeId"):
                processing_runs.request_discard(identifier, job["runScopeId"])
            video = video_store.get_video(identifier)
            if video:
                video_store.update_video(identifier, status="cancelled", error=None, step="cancelled",
                    resume_step="", step_detail="Đã hủy lượt xuất.")
        for job in self.jobs:
            if job["status"] in {"rendering", "paused", "awaiting_review"}:
                job.update(status="cancelled", error=self.error_text(ExportCancelled()))
        self.changed()
        if active or removed:
            self.host.selectedVideoChanged.emit()
            self.host.processingChanged.emit()
            self.host.refreshVideos()

    @staticmethod
    def job_progress(job, status, value):
        """One measured meter across rendering, verification and publication."""
        if status == "done":
            return 100
        raw = max(0, min(100, int(value or 0)))
        if status == "rendering":
            return round(raw * .90)
        if status == "exporting" and job.get("renderRequired"):
            return min(99, 90 + round(raw * .09))
        return min(99, raw)

    def poll(self):
        self._cancelling_render_tokens = {
            key: token for key, token in self._cancelling_render_tokens.items()
            if self.host._processing_queue.token_for(key) == token
        }
        changed = False
        pending_cleanup = False
        settled_run = False
        while not self.events.empty():
            identifier, status, progress, error = self.events.get_nowait()
            job = next((item for item in self.jobs if item["videoId"] == identifier), None)
            if job:
                measured_progress = self.job_progress(job, status, progress)
                if status in {"rendering", "exporting", "pending"}:
                    measured_progress = max(int(job.get("progress", 0)), measured_progress)
                job.update(status=status, progress=measured_progress, error=error)
                changed = True
                if status == "done":
                    self.host.videoExportCompleted.emit(identifier, job["path"])
        for job in self.jobs:
            if (job.get("runScopeId") and not job.get("runSettled") and job["status"] in {"done", "failed", "cancelled"}
                    and not self.host._processing_queue.contains(job["videoId"])):
                from hflow.services import processing_runs

                if job["status"] == "cancelled":
                    processing_runs.request_discard(job["videoId"], job.get("runScopeId"))
                complete = processing_runs.settle_export(job["videoId"], job["status"], job.get("runScopeId"))
                if complete and job["status"] == "cancelled":
                    processing_runs.restore_cancelled_manual_export(job["videoId"], job.get("manualIdleState"))
                job["runSettled"] = complete
                pending_cleanup = pending_cleanup or not complete
                settled_run = settled_run or bool(job.get("runScopeId"))
            if job["status"] not in {"rendering", "paused", "awaiting_review"}:
                continue
            video = video_store.get_video(job["videoId"])
            if video:
                measured = str(video.step or "") not in {
                    "extracting_audio", "separating_audio", "transcribing",
                    "creating_subtitle", "building_audio_timeline", "manual_source",
                    "manual_separation", "manual_recognition", "manual_audio",
                    "waiting_for_models", "starting",
                }
                progress = max(int(job.get("progress", 0)), self.job_progress(job, "rendering", video.progress))
                if job.get("progressMeasured") != measured or job["progress"] != progress:
                    job.update(progress=progress, progressMeasured=measured)
                    changed = True
            if self.host._processing_queue.contains(job["videoId"]):
                if job.get("runScopeId"):
                    from hflow.services.processing_runs import current_id

                    current_scope = current_id(job["videoId"])
                    if current_scope is not None and current_scope != job["runScopeId"]:
                        if job["status"] != "paused":
                            job.update(status="paused", error=self.text("Đang xử lý lượt khác trong dự án.",
                                                                         "Another project run is active."))
                            changed = True
                        continue
                if job["status"] != "rendering":
                    job.update(status="rendering", error="")
                    self._capture_render_owner(job)
                    changed = True
                continue
            if self.worker and self.worker.is_alive():
                continue
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
                job.update(status="failed", error=str(getattr(video, "error", "") or "") or self.text("Chưa hoàn tất dựng video. Tiếp tục tác vụ trong dự án rồi xuất lại.",
                                                            "Render not completed. Resume the project task, then export again."))
            changed = True
        if changed:
            self.changed()
        if pending_cleanup != self._pending_run_cleanup or settled_run:
            self._pending_run_cleanup = pending_cleanup
            if hasattr(self.host, "selectedVideoChanged"):
                self.host.selectedVideoChanged.emit()
                self.host.refreshVideos()
            self.changed()
        self._report_finished_batches()
        if self.busy != self._last_busy:
            self._last_busy = self.busy
            self.changed()

    def shutdown(self):
        self.timer.stop()
        self.cancel.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=10)
