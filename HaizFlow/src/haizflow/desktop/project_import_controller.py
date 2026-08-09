"""Project media import and channel-download commands behind the QML facade."""

from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from queue import Empty
from pathlib import Path

from haizflow.config import TMP_DIR
from haizflow.desktop.localization import QFileDialog, QMessageBox, native_media_dialog_directory
from haizflow.desktop.media import collect_batch_video_paths, create_video_thumbnail_path, normalize_video_path
from haizflow.core.paths import app_data_dir
from haizflow.schemas.video import SubtitleStyle, VideoConfig
from haizflow.services import project_store, video_store
from haizflow.services.channel_import import normalize_remote_url
from haizflow.services.desktop_videos import create_desktop_video, set_desktop_background_music
from haizflow.services.video_download import DownloadCancelled, _load_yt_dlp, _youtube_dl_options, validate_video_url


class ProjectImportController:
    """Owns media acquisition without exposing another QML API surface."""

    _VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}

    def __init__(self, host, *, create_video=None):
        self._host = host
        self._create_video = create_video or create_desktop_video
        self._storage_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._tasks: dict[int, dict] = {}
        self._task_threads: dict[int, threading.Thread] = {}
        self._next_task_id = 0
        self._background_music_cancel = threading.Event()
        self._background_music_thread: threading.Thread | None = None
        self._background_music_task: dict | None = None

    def _media_dialog_directory(self) -> str:
        """Start imports in the user's normal Explorer media locations.

        A selected source is read-only until HaizFlow copies it into the
        project workspace, so this does not weaken portable runtime storage.
        """
        native_directory = native_media_dialog_directory()
        if native_directory:
            return native_directory
        candidates = (
            os.path.dirname(str(getattr(self._host, "videoPath", "") or "")),
            str(getattr(self._host, "_project_directory", "") or ""),
        )
        for candidate in candidates:
            if candidate and os.path.isdir(candidate):
                return os.path.abspath(candidate)
        fallback = app_data_dir()
        fallback.mkdir(parents=True, exist_ok=True)
        return str(fallback.resolve())

    def _can_import_in_background(self) -> bool:
        """Keep the small controller doubles used by unit tests synchronous."""
        return hasattr(self._host, "_media_import_events")

    def _config_for_project_import(self, *, force_batch: bool = False) -> VideoConfig:
        """Build an import snapshot without leaking a per-video batch override.

        The shared editor intentionally shows an individual video's settings
        while that batch card is open.  New imports must nevertheless inherit
        the batch baseline (the most common saved configuration), not whichever
        custom card happened to be visited last.
        """
        host = self._host
        config = host._build_config().model_copy(deep=True)
        is_batch = force_batch or str(getattr(host, "_project_type", "")) == "batch"
        if not is_batch or not getattr(host, "_batch_video_ids", None):
            return config

        values = host._batch_settings_values()
        style_payload = dict(values.get("subtitleStyle") or {})
        manual_layout = bool(style_payload.pop("manual", False))
        remove_original_subtitles = bool(values.get("removeOriginalSubtitles", True))
        return config.model_copy(update={
            "mode": "review" if values.get("workflowMode") == "review" else "A",
            "target_language": str(values.get("targetLanguage") or "vi"),
            "tts_voice": str(values.get("ttsVoice") or ""),
            "enable_audio_separation": bool(values.get("enableAudioSeparation", False)),
            "original_video_volume": int(values.get("originalVolume", 60)),
            "background_music_volume": int(values.get("backgroundMusicVolume", 30)),
            "tts_volume": int(values.get("ttsVolume", 100)),
            "watermark_text": str(values.get("watermarkText") or ""),
            "remove_original_subtitles": remove_original_subtitles,
            "subtitle_style": SubtitleStyle(**style_payload),
            "subtitle_layout_override": manual_layout and not remove_original_subtitles,
            "background_music_path": str(values.get("backgroundMusicPath") or ""),
            "project_type": "batch",
        })

    def _queue_import(self, jobs: list[dict], context: dict) -> bool:
        """Run disk/FFmpeg work outside the QML thread and marshal results back."""
        host = self._host
        if not self._can_import_in_background():
            return False
        self._next_task_id += 1
        task_id = self._next_task_id
        self._tasks[task_id] = context
        host._media_import_busy = True
        host._media_import_total += len(jobs)
        host._media_import_status = "Adding video files in the background…"
        host.mediaImportChanged.emit()
        worker = threading.Thread(
            target=self._run_import_task,
            args=(task_id, jobs),
            name=f"haizflow-media-import-{task_id}",
            daemon=True,
        )
        self._task_threads[task_id] = worker
        worker.start()
        return True

    def _run_import_task(self, task_id: int, jobs: list[dict]) -> None:
        created_ids: list[str] = []
        errors: list[str] = []
        for job in jobs:
            if self._shutdown_event.is_set():
                errors.append(f"{os.path.basename(job['path'])}: import cancelled")
                break
            try:
                with self._storage_lock:
                    if job["operation"] == "replace":
                        video = video_store.replace_video_input(
                            job["video_id"], job["path"], media_source=job.get("media_source")
                        )
                        if video is None:
                            raise RuntimeError("The video was removed before its replacement completed.")
                        video.video_width, video.video_height = 0, 0
                    else:
                        kwargs = dict(job.get("create_kwargs") or {})
                        video = self._create_video(job["path"], job["config"], **kwargs)
                    if video is None:
                        raise RuntimeError("The imported video could not be loaded from storage.")
                    self._assign_thumbnail_in_worker(video)
                created_ids.append(video.video_id)
            except Exception as exc:  # The GUI reports the individual file after the batch finishes.
                errors.append(f"{os.path.basename(job['path'])}: {exc}")
            finally:
                self._host._media_import_events.put({
                    "type": "progress", "task_id": task_id, "completed": 1,
                })
        self._host._media_import_events.put({
            "type": "finished", "task_id": task_id, "created_ids": created_ids, "errors": errors,
        })

    def _assign_thumbnail_in_worker(self, video) -> None:
        input_path = (video.files or {}).get("video_input")
        if not isinstance(input_path, str) or not input_path.strip():
            raise RuntimeError("Video metadata is missing its input-video path.")
        thumbnail = create_video_thumbnail_path(
            input_path,
            os.path.join(video_store.get_video_dir(video.video_id), "thumbnail.jpg"),
            cancel_event=self._shutdown_event,
        )
        if thumbnail:
            video.files["thumbnail"] = thumbnail
            video_store.save_video(video)

    def drain_background_events(self) -> None:
        """Apply import results on the QObject's owning (GUI) thread."""
        host = self._host
        if not self._can_import_in_background():
            return
        changed = False
        while True:
            try:
                event = host._media_import_events.get_nowait()
            except Empty:
                break
            if event.get("type") == "background_music_finished":
                self._finish_background_music_download(event)
                changed = True
                continue
            if event.get("type") == "progress":
                host._media_import_completed += int(event.get("completed", 0))
                changed = True
                continue
            context = self._tasks.pop(int(event["task_id"]), None)
            self._task_threads.pop(int(event["task_id"]), None)
            if context:
                self._apply_finished_import(
                    context, list(event.get("created_ids") or []), list(event.get("errors") or [])
                )
            changed = True
        if not self._tasks:
            host._media_import_busy = False
            host._media_import_total = 0
            host._media_import_completed = 0
            host._media_import_status = ""
            changed = True
        if changed:
            host.mediaImportChanged.emit()

    def _finish_background_music_download(self, event: dict) -> None:
        host = self._host
        task = self._background_music_task
        if not task or event.get("task_id") != task.get("task_id"):
            return
        self._background_music_thread = None
        self._background_music_task = None
        host._background_music_import_busy = False
        temporary_directory = str(event.get("temporary_directory") or "")
        try:
            error = str(event.get("error") or "")
            if error:
                host._background_music_import_status = error
                return
            if task.get("target") == "batch":
                project_key_value = str(task.get("project_key") or "")
                project = project_store.get_project(project_key_value)
                if not project or project_store.normalize_project_type(project.get("project_type")) != "batch":
                    host._background_music_import_status = "The batch project is no longer available."
                    return
                source_path = str(event.get("path") or "")
                suffix = os.path.splitext(source_path)[1].lower() or ".m4a"
                assets_directory = os.path.join(project_store.project_root_for_key(project_key_value), ".batch-assets")
                os.makedirs(assets_directory, exist_ok=True)
                destination = os.path.join(assets_directory, f"background_music{suffix}")
                temporary_destination = f"{destination}.tmp"
                try:
                    shutil.copy2(source_path, temporary_destination)
                    os.replace(temporary_destination, destination)
                finally:
                    try:
                        os.remove(temporary_destination)
                    except FileNotFoundError:
                        pass
                for candidate in Path(assets_directory).glob("background_music.*"):
                    if os.path.normcase(os.path.abspath(candidate)) != os.path.normcase(os.path.abspath(destination)):
                        try:
                            candidate.unlink()
                        except OSError:
                            pass
                host._background_music_import_status = "Background music imported"
                host.batchBackgroundMusicDraftReady.emit(destination)
                return
            selected = video_store.get_video(str(task.get("video_id") or ""))
            if not selected:
                host._background_music_import_status = "The selected video is no longer available."
                return
            if host._processing_queue.contains(selected.video_id):
                host._background_music_import_status = "Pause or finish this video before changing its background music."
                return
            source_path = str(event.get("path") or "")
            stored_path = set_desktop_background_music(selected, source_path)
            if host._selected_video_id == selected.video_id:
                host._background_music_path = stored_path
                host.selectedVideoChanged.emit()
                host.backgroundMusicChanged.emit()
                preview = getattr(host, "_audio_preview", None)
                if preview is not None:
                    preview.invalidate()
            host.refreshVideos()
            host._background_music_import_status = "Background music imported"
        except (OSError, RuntimeError, ValueError) as exc:
            host._background_music_import_status = str(exc)
        finally:
            if temporary_directory:
                shutil.rmtree(temporary_directory, ignore_errors=True)
            host.backgroundMusicImportChanged.emit()

    def import_background_music_link(self, url: str) -> bool:
        host = self._host
        value = str(url or "").strip()
        if not value:
            host._background_music_import_status = "Paste a background music link first."
            host.backgroundMusicImportChanged.emit()
            return False
        if host._background_music_import_busy:
            return False
        if not host._selected_video_id:
            host._background_music_import_status = "Select a video before importing background music."
            host.backgroundMusicImportChanged.emit()
            return False
        if host._processing_queue.contains(host._selected_video_id):
            host._background_music_import_status = "Pause or finish this video before changing its background music."
            host.backgroundMusicImportChanged.emit()
            return False
        try:
            normalized_url, _platform = validate_video_url(value)
        except ValueError as exc:
            host._background_music_import_status = str(exc)
            host.backgroundMusicImportChanged.emit()
            return False

        task_id = uuid.uuid4().hex
        self._background_music_cancel = threading.Event()
        self._background_music_task = {
            "task_id": task_id,
            "target": "video",
            "video_id": host._selected_video_id,
            "url": normalized_url,
        }
        host._background_music_import_busy = True
        host._background_music_import_status = "Downloading background music"
        host.backgroundMusicImportChanged.emit()
        self._background_music_thread = threading.Thread(
            target=self._run_background_music_download,
            args=(dict(self._background_music_task), self._background_music_cancel),
            name="haizflow-background-music-download",
            daemon=True,
        )
        self._background_music_thread.start()
        return True

    def import_batch_background_music_link(self, url: str) -> bool:
        host = self._host
        value = str(url or "").strip()
        if not value:
            host._background_music_import_status = "Paste a background music link first."
            host.backgroundMusicImportChanged.emit()
            return False
        if host._background_music_import_busy:
            return False
        project = project_store.get_project(host._selected_project_key)
        if not project or project_store.normalize_project_type(project.get("project_type")) != "batch":
            host._background_music_import_status = "Open a batch project before importing background music."
            host.backgroundMusicImportChanged.emit()
            return False
        try:
            normalized_url, _platform = validate_video_url(value)
        except ValueError as exc:
            host._background_music_import_status = str(exc)
            host.backgroundMusicImportChanged.emit()
            return False

        task_id = uuid.uuid4().hex
        self._background_music_cancel = threading.Event()
        self._background_music_task = {
            "task_id": task_id,
            "target": "batch",
            "project_key": host._selected_project_key,
            "url": normalized_url,
        }
        host._background_music_import_busy = True
        host._background_music_import_status = "Downloading background music"
        host.backgroundMusicImportChanged.emit()
        self._background_music_thread = threading.Thread(
            target=self._run_background_music_download,
            args=(dict(self._background_music_task), self._background_music_cancel),
            name="haizflow-batch-background-music-download",
            daemon=True,
        )
        self._background_music_thread.start()
        return True

    def cancel_background_music_link_import(self) -> None:
        if self._background_music_thread and self._background_music_thread.is_alive():
            self._background_music_cancel.set()
            self._host._background_music_import_status = "Cancelling background music download"
            self._host.backgroundMusicImportChanged.emit()

    def _run_background_music_download(self, task: dict, cancel_event: threading.Event) -> None:
        temporary_directory = os.path.join(TMP_DIR, "background-music", str(task["task_id"]))
        output_path = os.path.join(temporary_directory, "background.m4a")
        event = {
            "type": "background_music_finished",
            "task_id": task["task_id"],
            "temporary_directory": temporary_directory,
            "path": "",
            "error": "",
        }
        try:
            os.makedirs(temporary_directory, exist_ok=True)
            if cancel_event.is_set():
                raise DownloadCancelled("Background music download cancelled.")
            yt_dlp = _load_yt_dlp()

            def progress_hook(progress: dict) -> None:
                if cancel_event.is_set():
                    raise DownloadCancelled("Background music download cancelled.")

            options = _youtube_dl_options()
            options.update({
                "outtmpl": str(Path(output_path).with_suffix(".%(ext)s")),
                "format": "bestaudio/best",
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
                "progress_hooks": [progress_hook],
                "nopart": True,
                "overwrites": True,
            })
            with yt_dlp.YoutubeDL(options) as downloader:
                downloader.extract_info(task["url"], download=True)
            if cancel_event.is_set():
                raise DownloadCancelled("Background music download cancelled.")
            produced = Path(output_path)
            if not produced.is_file():
                candidates = list(Path(temporary_directory).glob("background.*"))
                produced = max(candidates, key=lambda item: item.stat().st_mtime) if candidates else Path()
            if not produced.is_file() or produced.stat().st_size <= 0:
                raise RuntimeError("The link did not produce a playable audio file.")
            event["path"] = str(produced)
        except Exception as exc:
            event["error"] = str(exc)
        self._host._media_import_events.put(event)

    def _apply_finished_import(self, context: dict, created_ids: list[str], errors: list[str]) -> None:
        host = self._host
        errors = list(context.get("invalid_names") or []) + errors
        operation = context["operation"]
        project_key = context.get("project_key", "")
        if operation == "batch":
            if project_key == host._selected_project_key and host._project_type == "batch":
                self._prepend_batch_import(created_ids)
                host._refresh_batch_model()
                host.batchChanged.emit()
        elif operation == "create" and created_ids:
            video = video_store.get_video(created_ids[0])
            if video and project_key == host._selected_project_key:
                if context.get("as_batch"):
                    self._prepend_batch_import(created_ids)
                    host._refresh_batch_model()
                    host.batchChanged.emit()
                else:
                    host._select_video(video)
        elif operation == "replace" and created_ids:
            video = video_store.get_video(created_ids[0])
            if video:
                destination = (video.files or {}).get("video_input")
                if not isinstance(destination, str) or not destination.strip():
                    errors.append("Replacement metadata is missing its input-video path.")
                    destination = ""
                update_open_view = host._selected_video_id == video.video_id
                if update_open_view and destination:
                    host._set_video_path(destination, refresh_thumbnail=True)
                video_store.log_to_video(video.video_id, f"Input video replaced with: {video.original_filename}")
                if update_open_view:
                    host._replace_logs(host._read_video_logs(video.video_id))
                    host.videoThumbnailChanged.emit()
                    host.selectedVideoChanged.emit()
                    host.logsChanged.emit()
                host._log_queue.put("__QUEUE_CHANGED__")
        if created_ids:
            host.refreshVideos()
        if context.get("url_import"):
            message = "" if created_ids else "The video was downloaded but could not be added to the project."
            host._url_importer.complete_import(bool(created_ids), message)
        if context.get("channel_import"):
            host._channel_importer.complete_video(
                context["session_id"], context["remote_id"], bool(created_ids),
                "" if created_ids else (errors[0] if errors else "The video could not be added to the project."),
            )
        if errors and not context.get("channel_import") and not context.get("url_import"):
            QMessageBox.warning(None, "Some videos were skipped", self.batch_rejection_message(errors))

    def shutdown(self, timeout_seconds: float = 5.0) -> bool:
        """Stop accepting work and wait a bounded time for atomic imports to settle."""
        self._shutdown_event.set()
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        current_thread = threading.current_thread()
        for worker in tuple(self._task_threads.values()):
            if worker is current_thread or not worker.is_alive():
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            worker.join(timeout=remaining)
        self._background_music_cancel.set()
        music_worker = self._background_music_thread
        if music_worker and music_worker is not current_thread and music_worker.is_alive():
            remaining = deadline - time.monotonic()
            if remaining > 0:
                music_worker.join(timeout=remaining)
        return (
            not any(worker.is_alive() for worker in self._task_threads.values())
            and not (music_worker and music_worker.is_alive())
        )

    def download_inspected_video(self) -> None:
        host = self._host
        if not host.hasOpenProject:
            host._url_importer.complete_import(False, "Open or create a project before downloading a video.")
            return
        if host._project_type == "single" and host.isSelectedVideoProcessing:
            host._url_importer.complete_import(False, "Pause or finish the current video before replacing it.")
            return
        host._url_import_target = {
            "project_key": host._selected_project_key,
            "project_name": host._project_name,
            "project_directory": host._project_directory,
            "project_type": host._project_type,
            "selected_video_id": host._selected_video_id,
            "config": self._config_for_project_import(force_batch=host._project_type == "batch"),
            "media_source": {
                "type": "video_url",
                "platform": host._url_importer.platform,
                "source_url": host._url_importer.url,
                "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        }
        if not host._url_importer.start_download(host._selected_project_root()):
            host._url_import_target = None

    def handle_url_download_ready(self, path, _workspace, mode) -> None:
        host = self._host
        target = host._url_import_target
        host._url_import_target = None
        if self._can_import_in_background():
            if self._queue_downloaded_video(path, mode, target):
                return
            host._url_importer.complete_import(False, "The video was downloaded but could not be added to the project.")
            return
        imported = self.import_downloaded_video(path, mode, target)
        message = "" if imported else "The video was downloaded but could not be added to the project."
        host._url_importer.complete_import(imported, message)

    def _queue_downloaded_video(self, path: str, mode: str, target) -> bool:
        host = self._host
        if not target:
            if mode == "batch":
                return self._queue_batch_paths([path], url_import=True)
            if host._selected_video_id:
                return self._queue_replace(host._selected_video_id, path, None, url_import=True)
            return self._queue_project_video(path, url_import=True)
        target_video_id = target.get("selected_video_id")
        if mode != "batch" and target_video_id:
            return self._queue_replace(target_video_id, path, target.get("media_source"), url_import=True)
        config = target.get("config")
        known_project_keys = {project.get("key") for project in project_store.list_projects()}
        if not isinstance(config, VideoConfig) or target.get("project_key") not in known_project_keys:
            return False
        return self._queue_import([{
            "operation": "create", "path": path, "config": config.model_copy(deep=True),
            "create_kwargs": {
                "project_name": str(target.get("project_name") or ""),
                "project_directory": str(target.get("project_directory") or ""),
                "project_key_value": str(target.get("project_key") or ""),
                "media_source": target.get("media_source"),
            },
        }], {"operation": "create", "project_key": str(target.get("project_key") or ""),
             "as_batch": mode == "batch", "url_import": True})

    def import_downloaded_video(self, path: str, mode: str, target) -> bool:
        host = self._host
        if not target:
            if mode == "batch":
                previous_count = host.batchCount
                self.import_batch_videos([path])
                return host.batchCount > previous_count
            if host._selected_video_id:
                return self.replace_video(host._selected_video_id, path)
            return self.import_video(path)

        target_video_id = target.get("selected_video_id")
        if mode != "batch" and target_video_id:
            return self.replace_video(target_video_id, path, target.get("media_source"))
        config = target.get("config")
        if not isinstance(config, VideoConfig):
            return False
        if target.get("project_key") not in {project.get("key") for project in project_store.list_projects()}:
            QMessageBox.warning(None, "Import video", "The destination project no longer exists.")
            return False
        try:
            kwargs: dict[str, object] = {
                "project_name": str(target.get("project_name") or ""),
                "project_directory": str(target.get("project_directory") or ""),
                "project_key_value": str(target.get("project_key") or ""),
            }
            if target.get("media_source"):
                kwargs["media_source"] = target["media_source"]
            video = self._create_video(path, config, **kwargs)
            self._assign_thumbnail(video)
        except Exception as exc:
            QMessageBox.warning(None, "Import video", str(exc))
            return False

        if target.get("project_key") == host._selected_project_key:
            if mode == "batch":
                self._prepend_batch_import([video.video_id])
                host._refresh_batch_model()
                host.batchChanged.emit()
            else:
                host._select_video(video)
        host.refreshVideos()
        return True

    def current_project_media_keys(self) -> set[str]:
        host = self._host
        keys: set[str] = set()
        for video in video_store.list_videos():
            if not video.project_directory or host._video_project_key(video) != host._selected_project_key:
                continue
            source = getattr(video, "media_source", None)
            platform = str(getattr(source, "platform", "") or "").strip().lower()
            remote_id = str(getattr(source, "remote_video_id", "") or "").strip().lower()
            source_url = str(getattr(source, "source_url", "") or "").strip().lower()
            if platform and remote_id:
                keys.add(f"{platform}:{remote_id}")
            if source_url:
                keys.update((source_url, normalize_remote_url(source_url)))
        return keys

    def prepare_channel_import(self) -> bool:
        host = self._host
        if not host.hasOpenProject or host._project_type != "batch":
            QMessageBox.information(None, "Channel import", "Open or create a batch project before importing a channel.")
            return False
        host._channel_importer.attach_project(
            host._selected_project_key, host._selected_project_root(), self.current_project_media_keys()
        )
        return True

    def start_channel_downloads(self) -> bool:
        host = self._host
        if not self.prepare_channel_import() or host._channel_importer.selectedCount <= 0:
            return False
        session_id = host._channel_importer.sessionId
        if not session_id:
            return False
        self.remember_channel_import_target(session_id)
        if not host._channel_importer.start_downloads(2):
            host._channel_import_targets.pop(session_id, None)
            return False
        return True

    def remember_channel_import_target(self, session_id: str) -> None:
        host = self._host
        host._channel_import_targets[session_id] = {
            "project_key": host._selected_project_key,
            "project_name": host._project_name,
            "project_directory": host._project_directory,
            "project_type": "batch",
            "config": self._config_for_project_import(force_batch=True),
            "channel_url": host._channel_importer.channelUrl,
            "channel_name": host._channel_importer.channelName,
        }

    def retry_channel_video(self, row: int) -> bool:
        host = self._host
        if not self.prepare_channel_import():
            return False
        session_id = host._channel_importer.sessionId
        if not session_id:
            return False
        self.remember_channel_import_target(session_id)
        if not host._channel_importer.retry(int(row)):
            host._channel_import_targets.pop(session_id, None)
            return False
        return True

    def handle_channel_video_ready(self, path, _workspace, candidate_payload, project_key, session_id) -> None:
        host = self._host
        project_key = str(project_key or "")
        target = host._channel_import_targets.get(session_id)
        candidate = dict(candidate_payload or {})
        remote_id = str(candidate.get("remote_video_id") or "")
        if not target or target.get("project_key") != project_key:
            host._channel_importer.complete_video(session_id, remote_id, False, "The destination project is no longer available.")
            return
        if project_key not in {project.get("key") for project in project_store.list_projects()}:
            host._channel_importer.complete_video(session_id, remote_id, False, "The destination project was deleted.")
            return
        source = {
            "type": "channel", "platform": str(candidate.get("platform") or ""),
            "remote_video_id": remote_id, "source_url": str(candidate.get("source_url") or ""),
            "channel_url": str(target.get("channel_url") or ""),
            "channel_name": str(target.get("channel_name") or candidate.get("uploader") or ""),
            "import_session_id": session_id,
            "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if self._can_import_in_background():
            queued = self._queue_import([{
                "operation": "create", "path": path, "config": target["config"].model_copy(deep=True),
                "create_kwargs": {
                    "project_name": str(target.get("project_name") or ""),
                    "project_directory": str(target.get("project_directory") or ""),
                    "media_source": source, "move_input": True, "project_key_value": project_key,
                },
            }], {"operation": "create", "project_key": project_key, "as_batch": True,
                 "channel_import": True, "session_id": session_id, "remote_id": remote_id})
            if queued:
                return
            host._channel_importer.complete_video(session_id, remote_id, False, "Unable to queue the imported video.")
            return
        try:
            video = self._create_video(
                path, target["config"].model_copy(deep=True),
                project_name=str(target.get("project_name") or ""),
                project_directory=str(target.get("project_directory") or ""),
                media_source=source, move_input=True, project_key_value=project_key,
            )
            self._assign_thumbnail(video)
        except Exception as exc:
            host._channel_importer.complete_video(session_id, remote_id, False, str(exc))
            return
        if project_key == host._selected_project_key and host._project_type == "batch":
            self._prepend_batch_import([video.video_id])
            host._refresh_batch_model()
            host.batchChanged.emit()
        host.refreshVideos()
        host._channel_importer.complete_video(session_id, remote_id, True)

    def finish_channel_import_target(self, session_id: str) -> None:
        self._host._channel_import_targets.pop(str(session_id), None)

    def browse_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            None, "Choose input video", self._media_dialog_directory(),
            "Video files (*.mp4 *.mov *.mkv);;All files (*.*)",
        )
        if path:
            self.import_video(path, replace_selected=True)

    def browse_background_music(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Choose background music",
            self._media_dialog_directory(),
            "Audio or video files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma *.mp4 *.mov *.mkv *.webm *.avi);;All files (*.*)",
        )
        if path:
            self.set_background_music(path)

    def choose_batch_background_music(self) -> str:
        """Choose a batch music source without mutating any video draft."""
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Choose background music for the batch",
            self._media_dialog_directory(),
            "Audio or video files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma *.mp4 *.mov *.mkv *.webm *.avi);;All files (*.*)",
        )
        if not path:
            return ""
        path = os.path.abspath(path)
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            QMessageBox.warning(None, "Background music", "Choose an available audio or video file.")
            return ""
        return path

    def set_background_music(self, path: str) -> bool:
        host = self._host
        source_path = os.path.abspath(str(path or "").strip()) if path else ""
        if source_path and (not os.path.isfile(source_path) or os.path.getsize(source_path) <= 0):
            QMessageBox.warning(None, "Background music", "Choose an available audio or video file.")
            return False
        selected = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if selected:
            if host._processing_queue.contains(selected.video_id):
                QMessageBox.information(None, "Background music", "Pause or finish this video before changing its background music.")
                return False
            try:
                stored_path = set_desktop_background_music(selected, source_path)
            except (OSError, RuntimeError, ValueError) as exc:
                QMessageBox.warning(None, "Background music", str(exc))
                return False
            host._background_music_path = stored_path
            host.refreshVideos()
            host.selectedVideoChanged.emit()
        else:
            host._background_music_path = source_path
        host.backgroundMusicChanged.emit()
        preview = getattr(host, "_audio_preview", None)
        if preview is not None:
            preview.invalidate()
        return True

    def browse_project_directory(self, project_type: str = "single") -> None:
        host = self._host
        os.makedirs(host._project_directory, exist_ok=True)
        title = (
            "Choose download output location"
            if project_store.normalize_project_type(project_type) == "download"
            else "Choose project storage location"
        )
        path = QFileDialog.getExistingDirectory(None, title, host._project_directory)
        if path:
            host._project_directory = os.path.abspath(path)
            host.projectSetupChanged.emit()

    def _reset_new_project_setup(self) -> None:
        """Restore project-local defaults before the first import of a project."""
        host = self._host
        defaults = {
            "_workflow_mode": "A",
            "_target_language": "vi",
            "_tts_voice": "vi-VN-HoaiMyNeural",
            "_enable_audio_separation": False,
            "_original_volume": 60,
            "_background_music_volume": 30,
            "_tts_volume": 100,
            "_watermark_text": "",
            "_remove_original_subtitles": True,
            "_subtitle_style": SubtitleStyle(),
            "_subtitle_layout_override": False,
            "_background_music_path": "",
        }
        changed_signals = {
            "_workflow_mode": "workflowModeChanged",
            "_target_language": "targetLanguageChanged",
            "_tts_voice": "ttsVoiceChanged",
            "_enable_audio_separation": "enableAudioSeparationChanged",
            "_original_volume": "originalVolumeChanged",
            "_background_music_volume": "backgroundMusicVolumeChanged",
            "_tts_volume": "ttsVolumeChanged",
            "_watermark_text": "watermarkTextChanged",
            "_remove_original_subtitles": "subtitleSettingsChanged",
            "_subtitle_style": "subtitleSettingsChanged",
            "_subtitle_layout_override": "subtitleSettingsChanged",
            "_background_music_path": "backgroundMusicChanged",
        }
        voice_changed = getattr(host, "_tts_voice", None) != defaults["_tts_voice"]
        for attribute, value in defaults.items():
            if getattr(host, attribute, None) == value:
                continue
            setattr(host, attribute, value)
            signal = getattr(host, changed_signals[attribute], None)
            if signal:
                signal.emit()
        if voice_changed:
            signal = getattr(host, "ttsVoiceOptionsChanged", None)
            if signal:
                signal.emit()

        # A late event from a preview or music-link download belonging to the
        # previous project must never populate the new project's setup.
        self.cancel_background_music_link_import()
        preview = getattr(host, "_audio_preview", None)
        if preview:
            preview.invalidate()

    def prepare_project(self, project_name: str, project_directory: str, project_type: str) -> bool:
        host = self._host
        project_name, project_directory = project_name.strip(), project_directory.strip()
        if not project_name:
            QMessageBox.warning(None, "Project name", "Enter a project name.")
            return False
        if not project_directory:
            QMessageBox.warning(None, "Project storage location", "Choose a location for this project.")
            return False
        normalized_type = project_store.normalize_project_type(project_type)
        if (
            normalized_type == "download"
            and not host._media_downloader.can_switch_project("__new_download_project__")
        ):
            QMessageBox.information(
                None,
                "Download project",
                "Wait for the current channel task to finish or cancel it before creating another download project.",
            )
            return False
        host._project_name, host._project_directory = project_name, os.path.abspath(project_directory)
        host._project_type = normalized_type
        try:
            project = project_store.create_project(host._project_name, host._project_directory, host._project_type)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(None, "Project storage location", f"Cannot create the project at this location: {exc}")
            return False
        host._selected_project_key = project["key"]
        self._reset_new_project_setup()
        if host._project_type == "download":
            host._media_downloader.attach_project(project["key"], project["project_root"])
        host.videoPath = ""
        host._selected_video_id, host._batch_video_ids = None, []
        host._refresh_batch_model()
        host._clear_logs()
        host.projectSetupChanged.emit()
        host.selectedVideoChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        host.projectPrepared.emit()
        return True

    def import_video(self, path: str, *, replace_selected: bool = False) -> bool:
        host = self._host
        if replace_selected and host._selected_video_id:
            return self.replace_video(host._selected_video_id, path)
        normalized = normalize_video_path(path)
        if not os.path.isfile(normalized):
            QMessageBox.warning(None, "Invalid video", "The dropped file is unavailable.")
            return False
        if os.path.splitext(normalized)[1].lower() not in self._VIDEO_EXTENSIONS:
            QMessageBox.warning(None, "Unsupported file", "Choose an MP4, MOV, or MKV video file.")
            return False
        if not host.hasOpenProject:
            host._selected_video_id = None
            host.videoPath = normalized
            host.selectedVideoChanged.emit()
            return True
        if self._can_import_in_background():
            return self._queue_project_video(normalized)
        try:
            video = self._create_video(
                normalized, self._config_for_project_import(), project_name=host._project_name,
                project_directory=host._project_directory, project_key_value=host._selected_project_key,
            )
            host._assign_project_thumbnail(video)
        except Exception as exc:
            QMessageBox.critical(None, "Cannot import video", str(exc))
            return False
        host._select_video(video)
        host.refreshVideos()
        return True

    def replace_video(self, video_id: str | None, path: str, media_source=None) -> bool:
        host = self._host
        video = video_store.get_video(video_id) if video_id else None
        normalized = normalize_video_path(path)
        if not video:
            return False
        if video.status == "processing" or host._processing_queue.active_video_id == video.video_id:
            QMessageBox.information(None, "Replace video", "Pause or finish this video before replacing it.")
            return False
        if not os.path.isfile(normalized) or os.path.splitext(normalized)[1].lower() not in self._VIDEO_EXTENSIONS:
            QMessageBox.warning(None, "Invalid video", "Choose an MP4, MOV, or MKV video file.")
            return False
        if host._processing_queue.discard(video.video_id):
            host._update_queue_positions()
        if self._can_import_in_background():
            return self._queue_replace(video.video_id, normalized, media_source)
        try:
            video = video_store.replace_video_input(video.video_id, normalized, media_source=media_source)
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(None, "Replace video", str(exc))
            return False
        if video is None:
            QMessageBox.warning(None, "Replace video", "The video was removed before its replacement completed.")
            return False
        destination = (video.files or {}).get("video_input")
        if not isinstance(destination, str) or not destination.strip():
            QMessageBox.warning(None, "Replace video", "Replacement metadata is missing its input-video path.")
            return False
        video.video_width, video.video_height = 0, 0
        thumbnail = host._create_video_thumbnail_path(destination, host._video_thumbnail_path(video.video_id))
        if thumbnail:
            video.files["thumbnail"] = thumbnail
        video_store.save_video(video)
        update_open_view = host._selected_video_id == video.video_id
        if update_open_view:
            host._set_video_path(destination, refresh_thumbnail=True)
        video_store.log_to_video(video.video_id, f"Input video replaced with: {video.original_filename}")
        if update_open_view:
            host._replace_logs(host._read_video_logs(video.video_id))
            host.videoThumbnailChanged.emit()
            host.selectedVideoChanged.emit()
            host.logsChanged.emit()
        host.refreshVideos()
        host._log_queue.put("__QUEUE_CHANGED__")
        return True

    def browse_batch_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            None, "Choose videos for batch processing", self._media_dialog_directory(),
            "Video files (*.mp4 *.mov *.mkv);;All files (*.*)",
        )
        if paths:
            self.import_batch_videos(paths)

    def browse_batch_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            None, "Choose a folder of videos for batch processing", self._media_dialog_directory(),
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self.import_batch_videos([folder])

    def import_batch_videos(self, paths) -> None:
        host = self._host
        valid_paths, invalid_names = collect_batch_video_paths(paths)
        if not valid_paths:
            if invalid_names:
                QMessageBox.warning(None, "Some videos were skipped", self.batch_rejection_message(invalid_names))
            else:
                QMessageBox.warning(None, "No supported videos", "Choose MP4, MOV, or MKV video files.")
            return
        if self._can_import_in_background():
            self._queue_batch_paths(valid_paths, invalid_names=invalid_names)
            return
        created_ids, errors = [], []
        for path in valid_paths:
            try:
                video = self._create_video(
                    path, self._config_for_project_import(force_batch=True), project_name=host._project_name,
                    project_directory=host._project_directory, project_key_value=host._selected_project_key,
                )
                self._assign_thumbnail(video)
                created_ids.append(video.video_id)
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
        self._prepend_batch_import(created_ids)
        host._refresh_batch_model()
        host.refreshVideos()
        host.batchChanged.emit()
        rejected = invalid_names + errors
        if rejected:
            QMessageBox.warning(None, "Some videos were skipped", self.batch_rejection_message(rejected))

    def _prepend_batch_import(self, created_ids) -> None:
        """Persist a newly imported batch group before the existing queue.

        A batch can refresh while any card is processing.  Keeping the order
        in controller memory would therefore reintroduce a timestamp-based
        shuffle after reopening the project.  The integer positions here are
        project-local and intentionally untouched by status/progress writes.
        """
        host = self._host
        new_ids = list(dict.fromkeys(
            str(video_id) for video_id in created_ids
            if video_id and str(video_id) not in host._batch_video_ids
        ))
        if not new_ids:
            return

        def belongs_to_current_batch(video) -> bool:
            return (
                getattr(video, "project_type", "") == "batch"
                and host._video_project_key(video) == host._selected_project_key
            )

        # Assign durable compatibility positions to old batch entries once.
        # Prefer the order currently being viewed, then fall back to creation
        # time for a batch opened for the first time after migration.
        try:
            catalog_videos = video_store.list_videos()
        except (OSError, RuntimeError, ValueError):
            # A project can disappear while an asynchronous channel import is
            # delivering its final result.  The caller still owns the current
            # in-memory queue, so preserve the new card without failing the
            # whole import completion path.
            catalog_videos = []
        all_batch_videos = [video for video in catalog_videos if belongs_to_current_batch(video)]
        by_id = {video.video_id: video for video in all_batch_videos}
        visible_order = {
            video_id: index for index, video_id in enumerate(host._batch_video_ids)
        }
        existing = [video for video in all_batch_videos if video.video_id not in new_ids]
        existing.sort(key=lambda video: (
            0 if video.video_id in visible_order else 1,
            visible_order.get(video.video_id, 0),
            str(getattr(video, "created_at", "")),
        ))
        for index, video in enumerate(existing, start=1):
            if int(getattr(video, "batch_import_order", 0) or 0) <= 0:
                try:
                    refreshed = video_store.update_video(video.video_id, batch_import_order=index * 1000)
                except (OSError, RuntimeError, ValueError):
                    refreshed = None
                if refreshed:
                    by_id[video.video_id] = refreshed

        existing_orders = [
            int(getattr(by_id[video.video_id], "batch_import_order", 0) or 0)
            for video in existing
            if int(getattr(by_id[video.video_id], "batch_import_order", 0) or 0) > 0
        ]
        first_order = min(existing_orders, default=1000)
        # Keep room before the first item indefinitely.  A very active batch
        # can receive many one-by-one imports, so compact its project-local
        # positions before they would reach the zero compatibility sentinel.
        if existing and first_order <= len(new_ids):
            for index, video in enumerate(existing, start=1):
                try:
                    refreshed = video_store.update_video(video.video_id, batch_import_order=index * 1000)
                except (OSError, RuntimeError, ValueError):
                    refreshed = None
                if refreshed:
                    by_id[video.video_id] = refreshed
            first_order = 1000
        for offset, video_id in enumerate(new_ids, start=1):
            try:
                video_store.update_video(
                    video_id,
                    batch_import_order=first_order - len(new_ids) + offset - 1,
                )
            except (OSError, RuntimeError, ValueError):
                # The project can be deleted between importing and this UI
                # update.  Do not turn a completed background task into an
                # exception merely because its target no longer exists.
                pass

        # Importing a later group places that group at the top.  Its internal
        # order remains the order in which the user selected the files.
        host._batch_video_ids = new_ids + [
            video_id for video_id in host._batch_video_ids if video_id not in new_ids
        ]

    def _queue_project_video(self, path: str, *, url_import: bool = False) -> bool:
        host = self._host
        return self._queue_import([{
            "operation": "create", "path": path, "config": self._config_for_project_import(),
            "create_kwargs": {
                "project_name": host._project_name, "project_directory": host._project_directory,
                "project_key_value": host._selected_project_key,
            },
        }], {"operation": "create", "project_key": host._selected_project_key, "url_import": url_import})

    def _queue_batch_paths(self, paths, *, invalid_names=None, url_import: bool = False) -> bool:
        host = self._host
        valid_paths = list(paths)
        if not valid_paths:
            return False
        jobs = [{
            "operation": "create", "path": path, "config": self._config_for_project_import(force_batch=True),
            "create_kwargs": {
                "project_name": host._project_name, "project_directory": host._project_directory,
                "project_key_value": host._selected_project_key,
            },
        } for path in valid_paths]
        context = {
            "operation": "batch", "project_key": host._selected_project_key,
            "url_import": url_import, "invalid_names": list(invalid_names or []),
        }
        return self._queue_import(jobs, context)

    def _queue_replace(self, video_id: str, path: str, media_source, *, url_import: bool = False) -> bool:
        host = self._host
        video = video_store.get_video(video_id)
        if not video:
            return False
        return self._queue_import([{
            "operation": "replace", "video_id": video_id, "path": path, "media_source": media_source,
        }], {"operation": "replace", "project_key": host._selected_project_key, "url_import": url_import})

    def batch_rejection_message(self, rejected) -> str:
        host = self._host
        shown = [str(item) for item in rejected][:12]
        remaining = len(rejected) - len(shown)
        if remaining:
            shown.append(f"... và {remaining} mục khác" if host._settings_language == "vi" else f"... and {remaining} more")
        heading = (
            f"{len(rejected)} mục không được hỗ trợ hoặc không thể đọc:"
            if host._settings_language == "vi"
            else f"{len(rejected)} unsupported or unreadable item(s):"
        )
        return f"{heading}\n\n" + "\n".join(shown)

    def _assign_thumbnail(self, video) -> None:
        host = self._host
        input_path = (video.files or {}).get("video_input")
        if not isinstance(input_path, str) or not input_path.strip():
            raise RuntimeError("Video metadata is missing its input-video path.")
        thumbnail = host._create_video_thumbnail_path(input_path, host._video_thumbnail_path(video.video_id))
        if thumbnail:
            video.files["thumbnail"] = thumbnail
            video_store.save_video(video)
