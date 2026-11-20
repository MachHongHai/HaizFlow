"""Queue, pipeline, and log lifecycle kept outside the QML singleton facade."""

from __future__ import annotations

import os
import queue
import threading

from haizflow.core.hardware import runtime_profile
from haizflow.core.memory import cpu_memory_constrained
from haizflow.desktop.activity_log import ActivityLogBuffer
from haizflow.pipeline.process_registry import is_cancelled, is_paused, prepare_video_resume
from haizflow.services import project_store, video_store


class ProcessingLifecycleController:
    def __init__(self, host):
        self._host = host
        self._disk_log_revision = None
        self._wake_lock = threading.Lock()
        self._wake_pending = False
        self._previewed_translation = None

    def _wake_ui(self) -> None:
        """One queued Qt wake-up for a burst of control events, not log lines."""
        signal = getattr(self._host, "_processingEventsReady", None)
        if signal is None or getattr(self._host, "_shutdown_started", False):
            return
        with self._wake_lock:
            if self._wake_pending:
                return
            self._wake_pending = True
        try:
            signal.emit()
        except RuntimeError:
            with self._wake_lock:
                self._wake_pending = False

    def enqueue_video(self, video_id: str) -> bool:
        host = self._host
        if getattr(host, "_model_setup_state", "ready") != "ready":
            host._status_message = "Finish model setup before starting a video."
            host.statusMessageChanged.emit()
            return False
        video = video_store.get_video(video_id)
        if not video or video.status == "processing" or host._processing_queue.contains(video_id):
            return False
        from haizflow.services.processing_resume import can_resume, configuration_snapshot

        resuming = video.status == "paused"
        if not can_resume(host, video):
            return False
        manual_tool = (
            str(getattr(video, "manual_target_tool", "") or "")
            if getattr(video, "project_type", "single") == "manual"
            else ""
        )
        needs_translation = not manual_tool or manual_tool == "translation"
        from haizflow.core.translation_models import is_api_model

        if needs_translation and is_api_model(str(getattr(video, "translation_model", ""))):
            from haizflow.services.translation_connections import resolve

            try:
                resolve(video.translation_model, with_key=True)
            except (OSError, ValueError) as exc:
                host.appAlertRequested.emit("Kết nối dịch", str(exc), "warning")
                return False
        if needs_translation and str(getattr(video, "translation_model", "")).startswith("gemini-"):
            from haizflow.services.gemini_translation import key_configured

            if not key_configured():
                from haizflow.desktop.resource_progress import gemini_key_notice

                title, message = gemini_key_notice(getattr(host, "_settings_language", "vi"))
                host.appAlertRequested.emit(title, message, "warning")
                return False
        # Fresh retries and resumed jobs both start a new queue ownership
        # interval. Only here may old stop flags be cleared; the worker must
        # preserve requests received while it was queued/preparing models.
        prepare_video_resume(video_id)
        video_store.update_video(
            video_id,
            status="pending",
            processing_configuration=(getattr(video, "processing_configuration", {}) if resuming else configuration_snapshot(
                video, getattr(host, "_settings_processing_device", "cpu"))),
            progress=0 if manual_tool and not resuming else getattr(video, "progress", 0),
            current_item=0 if manual_tool and not resuming else getattr(video, "current_item", 0),
            total_items=0 if manual_tool and not resuming else getattr(video, "total_items", 0),
            estimated_remaining_seconds=(
                None if manual_tool else getattr(video, "estimated_remaining_seconds", None)
            ),
            step="queued",
            step_detail="Đang chờ xử lý" if manual_tool else "Queued for processing",
        )
        if not host._processing_queue.enqueue(video_id):
            return False
        project_store.touch_project_by_key(str(getattr(video, "project_key", "") or ""))
        video_store.log_to_video(video_id, "Added to the processing queue.")
        self.update_queue_positions()
        host.processingChanged.emit()
        host.selectedVideoChanged.emit()
        host._log_queue.put("__QUEUE_CHANGED__")
        return True

    def enqueue_videos(self, video_ids) -> int:
        return sum(1 for video_id in video_ids if self.enqueue_video(video_id))

    def update_queue_positions(self) -> None:
        host = self._host
        for position, video_id in enumerate(host._processing_queue.pending_ids(), start=1):
            video = video_store.get_video(video_id)
            if video and video.status == "pending":
                video_store.update_video(video_id, step="queued", step_detail=f"Queued: position {position}")

    def on_queue_video_started(self, video_id: str) -> None:
        host = self._host
        if video_id in host._deleted_video_ids:
            return
        video = video_store.get_video(video_id)
        if (not video or video.status in {"paused", "cancelled"}
                or is_cancelled(video_id) or is_paused(video_id)):
            return
        host._activate_pending_device_for_next_video(video_id)
        video = video_store.get_video(video_id)
        if (not video or video.status not in {"pending", "processing"}
                or is_cancelled(video_id) or is_paused(video_id)):
            return
        manual_tool = (
            str(getattr(video, "manual_target_tool", "") or "")
            if getattr(video, "project_type", "single") == "manual"
            else ""
        )
        video_store.update_video(
            video_id,
            status="processing",
            progress=0 if manual_tool and not video.resume_step else getattr(video, "progress", 0),
            current_item=0 if manual_tool and not video.resume_step else getattr(video, "current_item", 0),
            total_items=0 if manual_tool and not video.resume_step else getattr(video, "total_items", 0),
            step="starting",
            step_detail="Đang chuẩn bị công cụ" if manual_tool else "Processing started",
        )
        if is_cancelled(video_id) or is_paused(video_id):
            current = video_store.get_video(video_id)
            if current and current.status in {"pending", "processing"}:
                state = "paused" if is_paused(video_id) else "cancelled"
                video_store.update_video(video_id, status=state, step=state, error=None)
            return
        video_store.log_to_video(video_id, "Processing started from the shared queue.")
        self.update_queue_positions()
        host._log_queue.put(f"__QUEUE_STARTED__:{video_id}")

    def on_queue_video_finished(self, video_id: str) -> None:
        video = video_store.get_video(video_id)
        if video:
            project_store.touch_project_by_key(str(getattr(video, "project_key", "") or ""))
        self.update_queue_positions()
        self._host._log_queue.put(f"__QUEUE_FINISHED__:{video_id}")
        self._wake_ui()

    def on_translation_published(self, video_id: str) -> None:
        self._host._log_queue.put(f"__TRANSLATION_PUBLISHED__:{video_id}")
        self._wake_ui()

    @staticmethod
    def _translation_preview_key(video):
        if (video is not None and getattr(video, "status", "") == "manual_ready"
                and getattr(video, "step", "") == "manual_translation"):
            files = getattr(video, "files", {}) or {}
            if transcript := files.get("transcript_json"):
                return video.video_id, str(transcript)
        return None

    def _reconcile_manual_preview(self, video, *, translation: bool = False) -> bool:
        host = self._host
        if (video is None or video.video_id != str(host._selected_video_id or "")
                or getattr(video, "project_type", "") != "manual"
                or getattr(video, "status", "") not in {"manual_ready", "done"}
                or getattr(video, "manual_target_tool", "")
                or getattr(host, "_manual_editor_document", None) is None):
            return False
        try:
            from haizflow.services import editor_documents

            refresh_snapshot = getattr(host, "_refresh_selected_video_snapshot", None)
            if callable(refresh_snapshot):
                refresh_snapshot()
            subtitles = getattr(host, "_manual_subtitles", None)
            saving_or_failed = getattr(subtitles, "video_id", video.video_id) == video.video_id and any(
                state in {"saving", "error"} for state in getattr(subtitles, "_states", {}).values()
            )
            # A selected cue is not a pending write. QML keeps uncommitted
            # text in its draft buffer; do not hold old published captions.
            reload_subtitles = subtitles is not None and not saving_or_failed and (
                translation or not getattr(host, "_manual_editing_segment_id", "")
            )
            if reload_subtitles:
                subtitles.load(video.video_id, host.reviewSegments)
                document = editor_documents.sync_subtitle_clips(video, subtitles.segments)
            elif translation:
                return False
            else:
                document = editor_documents.ensure(video)
            host._manual_editor_document.set_document(document)
            remember = getattr(host, "_remember_loaded_manual_subtitles", None)
            if reload_subtitles and callable(remember):
                remember(getattr(host, "_selected_video_snapshot", None) or video)
            return True
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            video_store.log_to_video(video.video_id, f"Editor preview reconciliation failed: {exc}")
            return False

    def on_processing_queue_idle(self) -> None:
        warmup = getattr(self._host, "_smart_warmup", None)
        if warmup is not None:
            warmup.resume_after_foreground()
        self._host._log_queue.put("__QUEUE_IDLE__")
        self._wake_ui()

    def on_processing_queue_error(self, video_id: str, exc: Exception) -> None:
        host = self._host
        if not video_id or video_id in host._deleted_video_ids:
            return
        video = video_store.get_video(video_id)
        if not video:
            return
        message = f"Processing queue recovered from an internal error: {exc}"
        video_store.log_to_video(video_id, message)
        video_store.update_video(video_id, status="failed", error=str(exc), step="failed", step_detail=message)

    def execute_pipeline(self, video_id: str) -> None:
        host = self._host
        video = video_store.get_video(video_id)
        if not video or video.status == "cancelled" or video_id in host._deleted_video_ids:
            return
        try:
            from haizflow.services import processing_runs

            processing_runs.begin(video_id, resuming=bool(getattr(video, "resume_step", "")))
            manual_tool = (
                str(getattr(video, "manual_target_tool", "") or "")
                if getattr(video, "project_type", "single") == "manual"
                else ""
            )
            requires_model_runtime = not manual_tool or manual_tool in {
                "separation", "recognition", "translation", "image", "voice"
            }
            if requires_model_runtime and not host._initial_model_warmup_done.is_set():
                video_store.log_to_video(video_id, "Waiting for startup model warm-up to finish.")
                video_store.update_video(
                    video_id,
                    status="processing",
                    progress=0,
                    current_item=0,
                    total_items=0,
                    step="waiting_for_models",
                    step_detail="Đang chuẩn bị model" if manual_tool else "Waiting for startup model warm-up",
                )
                # Do not use one uninterruptible wait here.  The project is
                # already the queue's active item, so a user may pause it
                # before warm-up has finished.  In that case it must stay
                # paused; process_video_sync() calls start_video(), which
                # deliberately clears cancellation flags for a *new* run.
                while not host._initial_model_warmup_done.wait(timeout=0.20):
                    if is_cancelled(video_id) or is_paused(video_id) or getattr(host, "_shutdown_started", False):
                        return
            if is_cancelled(video_id) or is_paused(video_id):
                video_store.log_to_video(video_id, "Startup warm-up completed after this video was paused; it remains paused.")
                return
            if getattr(host, "_shutdown_started", False):
                return
            current_video = video_store.get_video(video_id)
            if not current_video or current_video.status in {"paused", "cancelled"}:
                return
            warmup = getattr(host, "_smart_warmup", None)
            if warmup is not None and not requires_model_runtime:
                warmup.foreground_work_requested(set())
            if requires_model_runtime:
                profile = runtime_profile()
                constrained = profile.total_ram_gib < 24 or (profile.cuda_available and profile.total_vram_gib < 12)
                if warmup is not None and not constrained:
                    required = {
                        "separation": {"separation"}, "translation": {"recognition"},
                        "image": {"ocr"}, "voice": {"voice"},
                    }.get(manual_tool, set()) if manual_tool else set(warmup.resident)
                    if manual_tool == "translation":
                        from haizflow.pipeline.process_video import foreground_capability

                        required = {foreground_capability(current_video, manual_tool)}
                    warmup.foreground_work_requested(required)
                if profile.total_ram_gib < 24 or (not profile.cuda_available and cpu_memory_constrained()) or (
                    profile.cuda_available and profile.total_vram_gib < 12
                ):
                    warmup = getattr(host, "_smart_warmup", None)
                    if warmup is not None:
                        video_store.log_to_video(video_id, "Releasing speculative models before foreground processing.")
                        # Keep at most the immediately used model; release
                        # other predictions before stage-to-stage handoff.
                        from haizflow.pipeline.process_video import foreground_capability

                        capability = foreground_capability(current_video, manual_tool)
                        required = {capability} if capability else set()
                        if required:
                            warmup.quiesce_for_foreground(required_capabilities=required)
                        else:
                            warmup.quiesce_for_foreground()
                runtime_probe_error = getattr(host, "_runtime_probe_error", "")
                if runtime_probe_error:
                    raise RuntimeError(f"Model runtime validation failed: {runtime_probe_error}")
                if getattr(host, "_model_setup_state", "ready") != "ready":
                    raise RuntimeError("Required models are not ready.")
                while not host._model_runtime_lock.acquire(timeout=0.2):
                    if is_cancelled(video_id) or is_paused(video_id) or getattr(host, "_shutdown_started", False):
                        return
                host._model_runtime_lock.release()
            # Model handoff/quiescing can take time. Refresh rather than
            # replacing a Pause/Cancel with stale "processing" metadata.
            if is_cancelled(video_id) or is_paused(video_id) or getattr(host, "_shutdown_started", False):
                return
            current_video = video_store.get_video(video_id)
            if not current_video or current_video.status in {"paused", "cancelled"}:
                return
            video_store.update_video(
                video_id,
                status="processing",
                progress=0 if manual_tool and not current_video.resume_step else getattr(current_video, "progress", 0),
                current_item=0 if manual_tool and not current_video.resume_step else getattr(current_video, "current_item", 0),
                total_items=0 if manual_tool and not current_video.resume_step else getattr(current_video, "total_items", 0),
                step="starting",
                step_detail=(
                    "Đang khởi tạo công cụ"
                    if manual_tool
                    else "Model warm-up complete; starting tool"
                    if requires_model_runtime else "Starting Manual tool"
                ),
            )

            stop_after = None
            if getattr(current_video, "project_type", "single") == "manual":
                target_tool = str(getattr(current_video, "manual_target_tool", "") or "")
                if target_tool:
                    from haizflow.pipeline.manual_tools import run_manual_tool_sync

                    video_store.log_to_video(video_id, f"Manual tool requested: {target_tool}.")
                    if target_tool == "translation":
                        run_manual_tool_sync(video_id, target_tool, on_translation_published=self.on_translation_published)
                    else:
                        run_manual_tool_sync(video_id, target_tool)
                    return
                stop_after = str(getattr(current_video, "manual_target_stage", "") or "")
                if not stop_after:
                    raise RuntimeError("Choose a Manual tool before starting processing.")
                video_store.log_to_video(video_id, f"Manual run requested through stage: {stop_after}.")
            from haizflow.pipeline.process_video import process_video_sync

            if stop_after:
                process_video_sync(video_id, stop_after=stop_after)
            else:
                process_video_sync(video_id)
        except Exception as exc:
            if video_id not in host._deleted_video_ids:
                if is_cancelled(video_id) or is_paused(video_id):
                    state = "paused" if is_paused(video_id) else "cancelled"
                    video_store.update_video(video_id, status=state, error=None, step=state)
                else:
                    message = f"Desktop worker failed before pipeline could start: {exc}"
                    video_store.log_to_video(video_id, message)
                    video_store.update_video(video_id, status="failed", error=str(exc), step="failed")
        finally:
            from haizflow.services import processing_runs

            processing_runs.finish(video_id)

    def prepare_batch_models(self, video_id: str) -> None:
        """Queue speculative batch warm-up without importing inference in Core."""

        video = video_store.get_video(video_id)
        if video is None:
            return
        context = {
            "device": str(getattr(self._host, "_settings_processing_device", "cpu") or "cpu"),
            "model": str(getattr(video, "speech_recognition_model", "small") or "small"),
            "translation_model": str(getattr(video, "translation_model", "auto") or "auto"),
            "source_language": str(getattr(video, "source_language", "auto") or "auto"),
            "language": str(getattr(video, "target_language", "") or ""),
        }
        self._host._smart_warmup.request("recognition", context, priority=8)
        video_store.log_to_video(video_id, "Recognition model queued for background preparation.")

    def on_video_log(self, video_id: str, line: str) -> None:
        host = self._host
        if video_id == host._selected_video_id:
            host._log_queue.put(("video_log", video_id, line))

    def drain_log_queue(self) -> None:
        with self._wake_lock:
            self._wake_pending = False
        host = self._host
        pending_lines = []
        while True:
            try:
                item = host._log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple) and len(item) == 3 and item[0] == "video_log":
                _kind, video_id, line = item
                if video_id == host._selected_video_id:
                    pending_lines.append(line)
                continue
            if not isinstance(item, str):
                # The queue is shared by worker callbacks.  Ignore malformed
                # payloads instead of crashing the GUI timer.
                continue
            if item.startswith("__QUEUE_STARTED__:"):
                notice = getattr(host, "_project_failure_notice", None)
                if notice is not None:
                    notice.started(item.partition(":")[2])
                host.refreshVideos()
                host.selectedVideoChanged.emit()
                host.processingChanged.emit()
                host._refresh_batch_model()
                host.batchChanged.emit()
            elif item.startswith("__TRANSLATION_PUBLISHED__:"):
                video_id = item.partition(":")[2]
                if video_id == str(host._selected_video_id or ""):
                    published_video = video_store.get_video(video_id)
                    key = self._translation_preview_key(published_video)
                    if key and self._reconcile_manual_preview(published_video, translation=True):
                        self._previewed_translation = key
            elif item.startswith("__QUEUE_FINISHED__:"):
                finished_video_id = item.partition(":")[2]
                host.refreshVideos()
                finished_video = video_store.get_video(finished_video_id)
                from haizflow.core.vieneu_voices import unsupported_language_notice

                language = str(getattr(finished_video, "subtitle_language", "") or "")
                if (finished_video_id == str(host._selected_video_id or "") and finished_video
                        and language
                        and unsupported_language_notice(getattr(host, "_tts_provider", ""), language)
                        and str(getattr(host, "_tts_provider", "")).startswith("vieneu")
                        and str(getattr(finished_video, "tts_provider", "")).startswith("omnivoice")):
                    host._tts_provider, host._tts_voice = finished_video.tts_provider, finished_video.tts_voice
                    host.ttsProviderChanged.emit()
                    host.ttsVoiceChanged.emit()
                    host.ttsProviderOptionsChanged.emit()
                    host.ttsVoiceOptionsChanged.emit()
                    from haizflow.desktop.presenters import language_label

                    vi = getattr(host, "_settings_language", "vi") == "vi"
                    label = language_label(language, "vi" if vi else "en")
                    host.appAlertRequested.emit("Đã đổi công cụ giọng đọc" if vi else "Speech backend changed",
                        f"Phụ đề vừa tạo là {label.lower()}. VieNeu đã được chuyển sang OmniVoice để tạo giọng." if vi
                        else f"The new subtitles are in {label}. VieNeu was switched to OmniVoice for speech generation.", "warning")
                key = self._translation_preview_key(finished_video)
                if key and key == self._previewed_translation:
                    manual_preview_ready = True
                else:
                    manual_preview_ready = self._reconcile_manual_preview(finished_video, translation=bool(key))
                if self._previewed_translation and self._previewed_translation[0] == finished_video_id:
                    self._previewed_translation = None
                if finished_video_id == str(host._selected_video_id or ""):
                    host.selectedVideoChanged.emit()
                host._refresh_batch_model()
                host.batchChanged.emit()
                ready = getattr(host, "manualToolPreviewReady", None)
                if (manual_preview_ready and ready is not None
                        and finished_video_id == str(host._selected_video_id or "")):
                    ready.emit(finished_video_id)
                # Render completion is not external export completion.
            elif item == "__QUEUE_IDLE__":
                if host._processing_queue.has_work:
                    continue
                host._batch_running = False
                host._batch_stop_requested = False
                host.refreshVideos()
                host.processingChanged.emit()
                host.batchChanged.emit()
                identifiers = getattr(host, "_batch_summary_ids", [])
                if identifiers:
                    from haizflow.services.batch_feedback import completion_notice, results

                    summary = results([video_store.get_video(key) for key in identifiers])
                    if summary["total"] and not summary["waiting"]:
                        host._batch_summary_ids = []
                        host.appAlertRequested.emit(*completion_notice(summary, host._settings_language))
            elif item == "__QUEUE_CHANGED__":
                host.refreshVideos()
                host.selectedVideoChanged.emit()
                host.batchChanged.emit()
            elif item == "__THUMBNAILS_READY__":
                host._thumbnail_refresh_running = False
                host.refreshVideos()
            elif item == "__VIDEO_DIMENSIONS_READY__":
                host.poll_videos()
        changed = False
        file_followed = False
        # Worker processes write the same durable log but their in-process
        # event listeners do not reach Qt. Follow the file while the task runs
        # instead of discovering all Whisper lines at the completion boundary.
        video_id = str(host._selected_video_id or "")
        if video_id:
            try:
                path = video_store.get_video_logs_path(video_id)
                stat = os.stat(path)
                revision = (video_id, stat.st_mtime_ns, stat.st_size)
                if revision != self._disk_log_revision or pending_lines:
                    tail = ActivityLogBuffer()
                    tail.replace(ActivityLogBuffer.read_tail(path))
                    self._disk_log_revision = revision
                    if tail.text != host._log_buffer.text:
                        self.replace_logs(tail.text)
                        changed = True
                file_followed = True
            except OSError:
                pass
        else:
            self._disk_log_revision = None
        # A delayed Qt callback may describe a line already read from disk.
        # Treat the durable file as authoritative, rather than appending it twice.
        if not file_followed and pending_lines:
            changed = self.append_logs(pending_lines) or changed
        if changed:
            host.logsChanged.emit()

    @staticmethod
    def read_video_logs(video_id: str) -> str:
        return ActivityLogBuffer.read_tail(video_store.get_video_logs_path(video_id))

    def replace_logs(self, text: str) -> None:
        host = self._host
        host._log_buffer.replace(text)
        host._logs = host._log_buffer.text
        host.activity_events.replace_text(text)

    def clear_logs(self) -> None:
        host = self._host
        self._disk_log_revision = None
        host._log_buffer.clear()
        host._logs = ""
        host.activity_events.clear()

    def append_logs(self, lines) -> bool:
        host = self._host
        normalized_lines = list(lines)
        if not host._log_buffer.append(normalized_lines):
            return False
        host.activity_events.append_lines(normalized_lines)
        host._logs = host._log_buffer.text
        return True
