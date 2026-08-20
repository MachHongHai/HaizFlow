"""Standalone video and audio downloads for the desktop Downloads page."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import uuid
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from haizflow.config import BIN_DIR, MEDIA_PROCESS_TIMEOUT_SECONDS, TMP_DIR
from haizflow.desktop.channel_import import ChannelImportCoordinator
from haizflow.desktop.localization import QFileDialog, native_media_dialog_directory
from haizflow.desktop.url_import import VideoUrlImportCoordinator
from haizflow.services import project_store
from haizflow.services.video_download import DownloadCancelled, download_video, inspect_video_url
from haizflow.utils.ffmpeg import _binary


class MediaDownloadController(QObject):
    changed = Signal()
    _progress = Signal(int, str)
    _finished = Signal(str)
    _failed = Signal(str)
    _channel_file_saved = Signal(str, str, bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_output_directory = ""
        self._audio_output_directory = ""
        self._channel_output_directory = ""
        self._project_key = ""
        self._project_root = ""
        self._audio_source = ""
        self._state = "idle"
        self._status = ""
        self._progress_value = 0
        self._cancel = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._pending_tasks = deque()
        self._active_task: dict | None = None
        self._channel_starting = False
        self._active_channel_output_directory = ""
        self._channel_importer = ChannelImportCoordinator(self)
        self._video_preview = VideoUrlImportCoordinator(self)
        self._channel_workspace = ""
        self._channel_project_key = ""
        self._progress.connect(self._set_progress)
        self._finished.connect(self._set_finished)
        self._failed.connect(self._set_failed)
        self._channel_file_saved.connect(self._finish_channel_file_save)
        self._channel_importer.changed.connect(self._on_channel_changed)
        self._channel_importer.videoReady.connect(self._save_channel_video)
        self._video_preview.changed.connect(self.changed.emit)

    @Property(str, notify=changed)
    def videoOutputDirectory(self):
        return self._video_output_directory

    @Property(str, notify=changed)
    def audioOutputDirectory(self):
        return self._audio_output_directory

    @Property(str, notify=changed)
    def channelOutputDirectory(self):
        return self._channel_output_directory

    @Property(bool, notify=changed)
    def outputManaged(self):
        return bool(self._project_key and self._project_root)

    @Property(str, notify=changed)
    def projectRoot(self):
        return self._project_root

    # Compatibility for an existing QML cache. New UI uses the explicit
    # destination for its own operation so files cannot land in the wrong folder.
    @Property(str, notify=changed)
    def outputDirectory(self):
        return self._video_output_directory

    @Property(str, notify=changed)
    def audioSource(self):
        return self._audio_source

    @Property(bool, notify=changed)
    def videoPreviewBusy(self):
        return self._video_preview.busy

    @Property(bool, notify=changed)
    def videoPreviewReady(self):
        return self._video_preview.state in {"ready", "retry"}

    @Property(str, notify=changed)
    def videoPreviewUrl(self):
        return self._video_preview.url

    @Property(str, notify=changed)
    def videoPreviewStatus(self):
        return self._video_preview.status

    @Property(str, notify=changed)
    def videoPreviewTitle(self):
        return self._video_preview.title

    @Property(str, notify=changed)
    def videoPreviewPlatform(self):
        return self._video_preview.platform

    @Property(str, notify=changed)
    def videoPreviewUploader(self):
        return self._video_preview.uploader

    @Property(str, notify=changed)
    def videoPreviewDuration(self):
        return self._video_preview.duration

    @Property(str, notify=changed)
    def videoPreviewThumbnail(self):
        return self._video_preview.thumbnailSource

    @Property(bool, notify=changed)
    def busy(self):
        return self._active_task is not None

    @Property(bool, notify=changed)
    def hasWork(self):
        return self.busy or self.channelBusy or bool(self._pending_tasks)

    @Property(bool, notify=changed)
    def currentProjectHasWork(self):
        return self.has_project_work(self._project_key)

    @Property(int, notify=changed)
    def queueCount(self):
        return len(self._pending_tasks)

    @Property(str, notify=changed)
    def queueStatus(self):
        if self._active_task:
            label = self._active_task["label"]
            if self._pending_tasks:
                return f"Running: {label}. {len(self._pending_tasks)} queued."
            return f"Running: {label}."
        if self._pending_tasks:
            return f"{len(self._pending_tasks)} download(s) queued."
        return ""

    @Property(bool, notify=changed)
    def channelBusy(self):
        return self._channel_importer.busy

    @Property(int, notify=changed)
    def channelProgress(self):
        return self._channel_importer.progress

    @Property(str, notify=changed)
    def channelStatus(self):
        return self._channel_importer.status

    @Property(str, notify=changed)
    def channelState(self):
        return self._channel_importer.state

    @Property(int, notify=changed)
    def channelCandidateCount(self):
        return self._channel_importer.candidateCount

    @Property(int, notify=changed)
    def channelSelectedCount(self):
        return self._channel_importer.selectedCount

    @Property(int, notify=changed)
    def channelSelectableCount(self):
        return self._channel_importer.selectableCount

    @Property(str, notify=changed)
    def channelName(self):
        return self._channel_importer.channelName

    @Property(QObject, constant=True)
    def channelCandidateModel(self):
        return self._channel_importer.candidateModel

    @Property(int, notify=changed)
    def progress(self):
        return self._progress_value

    @Property(str, notify=changed)
    def status(self):
        return self._status

    def attach_project(self, project_key: str, project_root: str) -> None:
        key = str(project_key or "").strip()
        root = os.path.abspath(str(project_root or "").strip()) if project_root else ""
        if key == self._project_key and root == self._project_root:
            return
        if not key or not root:
            self._project_key = ""
            self._project_root = ""
            self._video_output_directory = ""
            self._audio_output_directory = ""
            self._channel_output_directory = ""
            self.changed.emit()
            return
        downloads_root = os.path.join(root, "downloads")
        destinations = {
            "channel": os.path.join(downloads_root, "channel"),
            "video": os.path.join(downloads_root, "video"),
            "audio": os.path.join(downloads_root, "audio"),
        }
        for destination in destinations.values():
            os.makedirs(destination, exist_ok=True)
        self._project_key = key
        self._project_root = root
        self._channel_output_directory = destinations["channel"]
        self._video_output_directory = destinations["video"]
        self._audio_output_directory = destinations["audio"]
        self._channel_importer.attach_project(key, root, set())
        self._status = ""
        self.changed.emit()

    def can_switch_project(self, project_key: str) -> bool:
        key = str(project_key or "").strip()
        if not self._project_key or key == self._project_key:
            return True
        tasks = ([self._active_task] if self._active_task else []) + list(self._pending_tasks)
        return not any(
            task
            and str(task.get("project_key") or "") == self._project_key
            and str(task.get("kind") or "").startswith("channel_")
            for task in tasks
        )

    def has_project_work(self, project_key: str) -> bool:
        key = str(project_key or "").strip()
        if not key:
            return False
        tasks = ([self._active_task] if self._active_task else []) + list(self._pending_tasks)
        return any(task and str(task.get("project_key") or "") == key for task in tasks)

    @Slot()
    def chooseVideoOutputDirectory(self):
        folder = QFileDialog.getExistingDirectory(
            None, "Choose video download folder", self._video_output_directory or native_media_dialog_directory()
        )
        if folder:
            self._video_output_directory = os.path.abspath(folder)
            self._status = ""
            self.changed.emit()

    @Slot()
    def chooseAudioOutputDirectory(self):
        folder = QFileDialog.getExistingDirectory(
            None, "Choose audio download folder", self._audio_output_directory or native_media_dialog_directory()
        )
        if folder:
            self._audio_output_directory = os.path.abspath(folder)
            self._status = ""
            self.changed.emit()

    @Slot()
    def chooseChannelOutputDirectory(self):
        folder = QFileDialog.getExistingDirectory(
            None, "Choose channel download folder", self._channel_output_directory or native_media_dialog_directory()
        )
        if folder:
            self._channel_output_directory = os.path.abspath(folder)
            self.changed.emit()

    @Slot()
    def chooseOutputDirectory(self):
        self.chooseVideoOutputDirectory()

    @Slot()
    def chooseAudioSource(self):
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Choose audio or video file",
            native_media_dialog_directory(),
            "Media files (*.mp3 *.m4a *.aac *.wav *.flac *.ogg *.opus *.mp4 *.mov *.mkv *.webm);;All files (*.*)",
        )
        if path:
            self._audio_source = os.path.abspath(path)
            self._status = ""
            self.changed.emit()

    @Slot()
    def cancel(self):
        if not self._active_task:
            return
        if self._active_task["kind"].startswith("channel_"):
            self._channel_importer.cancel()
        else:
            self._cancel.set()
            self._status = "Cancelling download"
            self.changed.emit()

    @Slot()
    def cancelChannel(self):
        self.cancel()

    @Slot(str)
    def inspectVideo(self, url):
        self._video_preview.begin("single")
        self._video_preview.inspect(str(url or ""))

    @Slot()
    def cancelVideoPreview(self):
        self._video_preview.cancel()

    @Slot()
    def clearQueuedDownloads(self):
        if self._pending_tasks:
            self._pending_tasks.clear()
            self.changed.emit()

    @Slot(str)
    def downloadVideo(self, url):
        self._queue_download(url, "video", self._video_output_directory, "video download")

    @Slot(str)
    def downloadAudio(self, url):
        self._queue_download(url, "audio", self._audio_output_directory, "audio download")

    @Slot()
    def extractAudio(self):
        if not self._audio_source or not os.path.isfile(self._audio_source):
            self._reject("Choose an audio or video file first.")
            return
        self._queue_download(self._audio_source, "extract", self._audio_output_directory, "audio extraction")

    @Slot(str, str, str, int, str, int)
    def inspectChannel(self, url, platform, ranking, limit, duration_filter, scan_scope):
        if not str(url or "").strip():
            self._reject("Paste a channel or profile link first.")
            return
        self._enqueue(
            {
                "kind": "channel_scan",
                "label": "channel preview",
                "url": str(url).strip(),
                "platform": str(platform or ""),
                "ranking": str(ranking or "newest"),
                "limit": max(1, min(100, int(limit))),
                "duration_filter": str(duration_filter or "all"),
                "scan_scope": max(0, int(scan_scope)),
                "output": "",
            }
        )

    @Slot(int, bool)
    def setChannelSelected(self, row, selected):
        self._channel_importer.setSelected(int(row), bool(selected))

    @Slot(bool)
    def selectAllChannel(self, selected):
        self._channel_importer.selectAll(bool(selected))

    @Slot()
    def downloadSelectedChannel(self):
        if self._channel_importer.selectedCount <= 0:
            return
        if not self._channel_output_directory or not os.path.isdir(self._channel_output_directory):
            self._reject("Choose a channel download folder before downloading selected videos.")
            return
        self._enqueue(
            {
                "kind": "channel_download",
                "label": "channel download",
                "session_id": self._channel_importer.sessionId,
                "output": self._channel_output_directory,
            }
        )

    @Slot(int, result=bool)
    def retryChannelVideo(self, row):
        candidate = self._channel_importer.candidates.candidate_at(int(row))
        if not candidate or candidate.duplicate or candidate.status != "failed":
            return False
        if not self._channel_output_directory or not os.path.isdir(self._channel_output_directory):
            self._reject("Choose a channel download folder before retrying this video.")
            return False
        self._enqueue(
            {
                "kind": "channel_download",
                "label": "channel video retry",
                "session_id": self._channel_importer.sessionId,
                "candidate_id": candidate.remote_video_id,
                "output": self._channel_output_directory,
            }
        )
        return True

    @Slot(str)
    def setChannelCookieBrowser(self, browser):
        self._channel_importer.setCookieBrowser(str(browser or ""))

    @Slot()
    def browseChannelCookieFile(self):
        self._channel_importer.browseCookieFile()

    @Slot()
    def clearChannelAuthentication(self):
        self._channel_importer.clearAuthentication()

    @Property(str, notify=changed)
    def channelCookieBrowser(self):
        return self._channel_importer.cookieBrowser

    @Property(str, notify=changed)
    def channelCookieFile(self):
        return self._channel_importer.cookieFile

    def _queue_download(self, value: str, mode: str, output_directory: str, label: str):
        if not output_directory or not os.path.isdir(output_directory):
            self._reject("Choose an output folder before downloading.")
            return
        if not str(value or "").strip():
            self._reject("Paste a link first.")
            return
        self._enqueue(
            {
                "kind": mode,
                "label": label,
                "value": str(value).strip(),
                "output": output_directory,
            }
        )

    def _enqueue(self, task: dict) -> None:
        task.setdefault("project_key", self._project_key)
        self._pending_tasks.append(task)
        self._status = f"Queued {task['label']}"
        if task["project_key"]:
            try:
                project_store.touch_project_by_key(task["project_key"])
            except (OSError, RuntimeError, ValueError):
                pass
            host = self.parent()
            if host is not None and hasattr(host, "refreshVideos"):
                host.refreshVideos()
        self.changed.emit()
        self._start_next()

    def _start_next(self) -> None:
        if self._active_task or not self._pending_tasks:
            return
        self._active_task = self._pending_tasks.popleft()
        task = self._active_task
        self._progress_value = 0
        self._cancel = threading.Event()
        self.changed.emit()
        if task["kind"] == "channel_scan":
            self._start_channel_scan(task)
            return
        if task["kind"] == "channel_download":
            self._start_channel_download(task)
            return
        self._state, self._status = "running", f"Preparing {task['label']}"
        self.changed.emit()
        self._worker_thread = threading.Thread(
            target=self._run,
            args=(task["value"], task["kind"], task["output"]),
            daemon=True,
            name="standalone-media-download",
        )
        self._worker_thread.start()

    def _start_channel_scan(self, task: dict) -> None:
        self._channel_project_key = str(task.get("project_key") or "")
        self._channel_workspace = self._project_root if self._channel_project_key else ""
        if not self._channel_project_key or not self._channel_workspace:
            self._channel_project_key = f"standalone-download-{uuid.uuid4()}"
            self._channel_workspace = os.path.join(TMP_DIR, "channel-downloads", uuid.uuid4().hex)
        os.makedirs(self._channel_workspace, exist_ok=True)
        self._active_channel_output_directory = task["output"]
        self._channel_starting = True
        try:
            # Standalone downloads deliberately use public content only. The
            # project import flow keeps its separate opt-in authentication UI.
            self._channel_importer.clearAuthentication()
            self._channel_importer.attach_project(self._channel_project_key, self._channel_workspace, set())
            self._channel_importer.inspect(
                task["url"],
                task["platform"],
                task["ranking"],
                task["limit"],
                task["duration_filter"],
                task["scan_scope"],
            )
        finally:
            self._channel_starting = False
        self._status = "Preparing channel preview"
        self.changed.emit()

    def _start_channel_download(self, task: dict) -> None:
        if task["session_id"] != self._channel_importer.sessionId:
            self._finish_active("Channel selection changed before this queued download could start.")
            return
        self._active_channel_output_directory = task["output"]
        workers = 1 if task.get("candidate_id") else 2
        if not self._channel_importer.start_downloads(workers, task.get("candidate_id", "")):
            self._finish_active("No selected channel videos are available to download.")
            return
        self._status = "Preparing channel download"
        self.changed.emit()

    def _run(self, value: str, mode: str, output_directory: str):
        try:
            output = Path(output_directory)
            if mode == "extract":
                destination = self._unique_path(output / f"{Path(value).stem}.m4a")
                self._extract(value, destination)
            else:
                metadata = inspect_video_url(value, self._cancel)
                workspace = output / ".haizflow-downloads" / uuid.uuid4().hex
                workspace.mkdir(parents=True, exist_ok=True)
                try:
                    if mode == "video":
                        downloaded = download_video(metadata, str(workspace), self._report, self._cancel)
                        destination = self._unique_path(output / Path(downloaded).name)
                        shutil.move(downloaded, destination)
                    else:
                        destination = self._unique_path(output / f"{metadata.title}.m4a")
                        self._download_audio(metadata.url, destination)
                finally:
                    shutil.rmtree(workspace, ignore_errors=True)
            if self._cancel.is_set():
                raise DownloadCancelled("Download cancelled.")
            self._finished.emit(str(destination))
        except Exception as exc:
            self._failed.emit(str(exc))

    def _download_audio(self, url: str, destination: Path):
        import yt_dlp

        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "outtmpl": str(destination.with_suffix(".%(ext)s")),
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
            "progress_hooks": [self._yt_progress],
            "nopart": True,
            "overwrites": True,
        }
        if os.path.isdir(BIN_DIR):
            options["ffmpeg_location"] = BIN_DIR
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.extract_info(url, download=True)
        produced = (
            destination if destination.is_file() else next(destination.parent.glob(f"{destination.stem}.*"), None)
        )
        if not produced or not Path(produced).is_file():
            raise RuntimeError("The link did not produce an audio file.")
        if Path(produced) != destination:
            shutil.move(str(produced), destination)

    def _extract(self, source: str, destination: Path):
        result = subprocess.run(
            [
                _binary("ffmpeg"),
                "-y",
                "-v",
                "error",
                "-i",
                source,
                "-vn",
                "-map",
                "0:a:0?",
                "-c:a",
                "aac",
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=MEDIA_PROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode or not destination.is_file():
            raise RuntimeError((result.stderr or "Could not extract audio from this file.").strip()[:400])

    def _yt_progress(self, event):
        if self._cancel.is_set():
            raise DownloadCancelled("Download cancelled.")
        if event.get("status") == "downloading":
            done = int(event.get("downloaded_bytes") or 0)
            total = int(event.get("total_bytes") or event.get("total_bytes_estimate") or 0)
            self._report(round(done * 100 / total) if total else 0, "Downloading audio")

    def _report(self, progress, detail):
        self._progress.emit(max(0, min(100, int(progress))), str(detail))

    def _unique_path(self, path: Path):
        candidate, index = path, 2
        while candidate.exists():
            candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
            index += 1
        return candidate

    def _reject(self, message):
        self._status = message
        self.changed.emit()

    def _set_progress(self, progress, detail):
        self._progress_value = progress
        self._status = detail
        self.changed.emit()

    def _set_finished(self, destination):
        self._progress_value = 100
        self._finish_active(f"Saved to {destination}")

    def _set_failed(self, message):
        self._finish_active(message)

    def _finish_active(self, status: str) -> None:
        self._active_task = None
        self._state = "done" if status.startswith("Saved to ") else "error"
        self._status = str(status)
        self.changed.emit()
        self._start_next()

    def _on_channel_changed(self) -> None:
        self.changed.emit()
        task = self._active_task
        if not task or self._channel_starting or not task["kind"].startswith("channel_"):
            return
        if self._channel_importer.busy:
            return
        self._finish_active(self._channel_importer.status or "Channel task finished.")

    def _save_channel_video(self, path, _workspace, candidate_payload, _project_key, session_id):
        candidate = dict(candidate_payload or {})
        remote_id = str(candidate.get("remote_video_id") or "")
        source = Path(str(path or ""))
        output = Path(self._active_channel_output_directory)

        def move_file() -> None:
            try:
                if not source.is_file():
                    raise RuntimeError("The channel video download was not found.")
                output.mkdir(parents=True, exist_ok=True)
                destination = self._unique_path(output / source.name)
                shutil.move(str(source), str(destination))
                self._channel_file_saved.emit(str(session_id), remote_id, True, "")
            except Exception as exc:
                self._channel_file_saved.emit(str(session_id), remote_id, False, str(exc))

        threading.Thread(target=move_file, name="save-channel-download", daemon=True).start()

    def _finish_channel_file_save(self, session_id: str, remote_id: str, success: bool, message: str) -> None:
        self._channel_importer.complete_video(session_id, remote_id, success, message)

    def shutdown(self, timeout_seconds: float = 5.0) -> bool:
        self._cancel.set()
        channel_stopped = self._channel_importer.shutdown(timeout_seconds)
        preview_stopped = self._video_preview.shutdown(timeout_seconds)
        worker = self._worker_thread
        if worker and worker.is_alive():
            worker.join(timeout=max(0.0, timeout_seconds))
        return channel_stopped and preview_stopped and not (worker and worker.is_alive())
