"""TikTok publishing workflow for local desktop projects."""

from __future__ import annotations

import os
import queue
import shutil
import threading
import uuid
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from haizflow.desktop.external_links import close_managed_chrome, open_managed_chrome_url
from haizflow.desktop.localization import QFileDialog, QMessageBox, native_media_dialog_directory
from haizflow.desktop.media import (
    create_video_thumbnail_path,
    normalize_video_path,
    thumbnail_source,
)
from haizflow.services import project_store, tiktok_publish, tiktok_studio, video_store


TIKTOK_STUDIO_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
TIKTOK_STUDIO_URL = "https://www.tiktok.com/tiktokstudio"
PUBLISH_VIDEO_EXTENSIONS = frozenset({".mp4", ".webm"})
TIKTOK_MAX_VIDEO_BYTES = 10_000_000_000


class TikTokPublishController:
    def __init__(self, host):
        self._host = host
        self._project_key = ""
        self._project_root = ""
        self._state = {
            "default_caption": "",
            "default_hashtags": "",
            "items": [],
        }
        self._busy = False
        self._status = ""
        self._events: queue.Queue[dict] = queue.Queue()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._project_sources: list[dict] = []

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def status(self) -> str:
        return self._status

    @property
    def default_caption(self) -> str:
        return str(self._state.get("default_caption") or "")

    @property
    def default_hashtags(self) -> str:
        return str(self._state.get("default_hashtags") or "")

    @property
    def count(self) -> int:
        return len(self._state.get("items") or [])

    @property
    def posted_count(self) -> int:
        return sum(1 for item in self._state.get("items") or [] if item["status"] == "posted")

    @property
    def awaiting_count(self) -> int:
        return sum(
            1 for item in self._state.get("items") or []
            if item["status"] == "awaiting_confirmation"
        )

    def has_project_work(self, project_key: str) -> bool:
        return bool(self._busy and self._project_key == str(project_key or ""))

    def can_switch_project(self, project_key: str) -> bool:
        target = str(project_key or "")
        return not self._busy or not self._project_key or self._project_key == target

    def attach_project(self, project_key: str, project_root: str) -> None:
        next_key = str(project_key or "")
        next_root = os.path.abspath(project_root) if project_root else ""
        if not self._busy and next_root:
            tiktok_publish.cleanup_orphaned_media(next_root)
        self._project_key = next_key
        self._project_root = next_root
        self._reload()

    def detach_project(self) -> None:
        self._project_key = ""
        self._project_root = ""
        self._state = {"default_caption": "", "default_hashtags": "", "items": []}
        self._host.tiktok_publish_items.set_items([])
        self._emit_changed()

    def _reload(self) -> None:
        if not self._project_root or not os.path.isdir(self._project_root):
            self._state = {"default_caption": "", "default_hashtags": "", "items": []}
        else:
            self._state = tiktok_publish.load_state(self._project_root)
        self._sync_model()
        self._emit_changed()

    def _sync_model(self) -> None:
        presented = []
        for item in self._state.get("items") or []:
            presented.append(
                {
                    **item,
                    "post_text": tiktok_publish.compose_post_text(item["caption"], item["hashtags"]),
                    "thumbnail_source": thumbnail_source(item.get("thumbnail_path") or ""),
                }
            )
        self._host.tiktok_publish_items.set_items(presented)

    def _emit_changed(self) -> None:
        self._host.tiktokPublishChanged.emit()

    def browse_videos(self) -> None:
        if not self._ensure_publish_project():
            return
        paths, _ = QFileDialog.getOpenFileNames(
            None,
            "Choose videos to publish on TikTok",
            native_media_dialog_directory(),
            "TikTok video files (*.mp4 *.webm);;All files (*.*)",
        )
        if paths:
            self.add_videos(paths)

    def browse_folder(self) -> None:
        if not self._ensure_publish_project():
            return
        folder = QFileDialog.getExistingDirectory(
            None,
            "Choose a folder of videos to publish on TikTok",
            native_media_dialog_directory(),
            QFileDialog.Option.ShowDirsOnly,
        )
        if not folder:
            return
        try:
            paths = [
                str(path.resolve())
                for path in sorted(Path(folder).iterdir(), key=lambda value: value.name.lower())
                if path.is_file() and self._supported_file(str(path))
            ]
        except OSError:
            paths = []
        if not paths:
            QMessageBox.warning(None, "TikTok publishing", "This folder contains no supported videos.")
            return
        self.add_videos(paths)

    def prepare_login(self) -> bool:
        """Open TikTok Studio in HaizFlow's persistent browser-owned session."""
        opened = open_managed_chrome_url(
            TIKTOK_STUDIO_URL,
            tiktok_publish.browser_session_directory(),
            new_window=True,
        )
        self._status = (
            "TikTok Studio opened in HaizFlow's saved session. Sign in once; "
            "Chrome will keep the login for future app sessions."
            if opened
            else "Google Chrome is required to prepare the saved TikTok session."
        )
        self._emit_changed()
        return opened

    def clear_login_session(self) -> bool:
        if self._busy:
            QMessageBox.information(None, "TikTok publishing", "Wait for the current TikTok task to finish.")
            return False
        if QMessageBox.question(
            None,
            "Clear TikTok login",
            "Close HaizFlow's TikTok browser and remove its saved login? Publishing projects and videos are kept.",
        ) != QMessageBox.StandardButton.Yes:
            return False
        self._busy = True
        self._status = "Clearing the saved TikTok login"
        self._emit_changed()
        project_key = self._project_key
        self._worker = threading.Thread(
            target=self._clear_login_session_worker,
            args=(project_key,),
            name="haizflow-tiktok-session-clear",
            daemon=True,
        )
        self._worker.start()
        return True

    def _clear_login_session_worker(self, project_key: str) -> None:
        error = ""
        removed = False
        session_directory = tiktok_publish.browser_session_directory()
        try:
            if not close_managed_chrome(session_directory):
                raise RuntimeError("Close the HaizFlow TikTok browser and try again.")
            removed = tiktok_publish.clear_browser_session_data()
        except (OSError, RuntimeError) as exc:
            error = str(exc)
        self._events.put(
            {
                "type": "session_cleared",
                "project_key": project_key,
                "removed": removed,
                "error": error,
            }
        )

    def refresh_project_sources(self) -> None:
        candidates: list[dict] = []
        batch_groups: dict[str, dict] = {}
        for video in video_store.list_videos():
            if video.project_type not in {"single", "batch"} or video.status != "done":
                continue
            output_path = self._output_path(video)
            if not self._supported_file(output_path):
                continue
            width = int(getattr(video, "video_width", 0) or 0)
            height = int(getattr(video, "video_height", 0) or 0)
            project_name = video.project_name or Path(video.original_filename).stem
            source = {
                "output_path": output_path,
                "display_name": f"{project_name} — {video.original_filename}",
            }
            if video.project_type == "batch":
                group_key = str(
                    getattr(video, "project_key", "")
                    or getattr(video, "project_id", "")
                    or project_name
                )
                candidate = batch_groups.get(group_key)
                if candidate is None:
                    candidate = {
                        "video_id": f"batch:{group_key}",
                        "project_name": project_name,
                        "project_type": "batch",
                        "file_name": "",
                        "output_paths": [],
                        "thumbnail_source": thumbnail_source((video.files or {}).get("thumbnail") or ""),
                        "video_size": "",
                        "video_count": 0,
                        "selected": False,
                    }
                    batch_groups[group_key] = candidate
                    candidates.append(candidate)
                candidate["output_paths"].append(source)
                count = len(candidate["output_paths"])
                candidate["video_count"] = count
                continue
            candidates.append(
                {
                    "video_id": video.video_id,
                    "project_name": project_name,
                    "project_type": "single",
                    "file_name": video.original_filename,
                    "output_paths": [source],
                    "thumbnail_source": thumbnail_source((video.files or {}).get("thumbnail") or ""),
                    "video_size": f"{width} x {height}" if width and height else "",
                    "video_count": 1,
                    "selected": False,
                }
            )
        self._project_sources = candidates
        self._host.tiktok_project_sources.set_items(candidates)
        self._emit_changed()

    def set_project_source_selected(self, row: int, selected: bool) -> bool:
        if not self._host.tiktok_project_sources.set_selected(row, selected):
            return False
        self._project_sources[row]["selected"] = bool(selected)
        self._emit_changed()
        return True

    def add_selected_project_videos(self) -> bool:
        selected = [item for item in self._project_sources if item["selected"]]
        if not selected:
            return False
        sources = [source for item in selected for source in item["output_paths"]]
        labels = {source["output_path"]: source["display_name"] for source in sources}
        return self.add_videos([source["output_path"] for source in sources], labels)

    def add_videos(self, paths, display_names: dict[str, str] | None = None) -> bool:
        if not self._ensure_publish_project():
            return False
        if self._busy:
            QMessageBox.information(None, "TikTok publishing", "Wait for the current video import to finish.")
            return False
        valid: list[tuple[str, str]] = []
        rejected: list[str] = []
        seen: set[str] = set()
        for value in paths:
            path = normalize_video_path(value)
            if path in seen:
                continue
            seen.add(path)
            if self._supported_file(path):
                label = str((display_names or {}).get(path) or Path(path).name)
                valid.append((path, label))
            else:
                rejected.append(Path(path).name or path)
        if not valid:
            QMessageBox.warning(
                None,
                "TikTok publishing",
                "Choose an MP4 or WebM video smaller than 10 GB.",
            )
            return False
        if rejected:
            self._status = f"Skipped {len(rejected)} unsupported or unavailable file(s)."
        self._busy = True
        self._cancel.clear()
        project_key = self._project_key
        project_root = self._project_root
        caption = self.default_caption
        hashtags = self.default_hashtags
        starting_order = self.count
        self._emit_changed()
        self._worker = threading.Thread(
            target=self._import_worker,
            args=(project_key, project_root, valid, caption, hashtags, starting_order),
            name="haizflow-tiktok-import",
            daemon=True,
        )
        self._worker.start()
        return True

    def _import_worker(
        self,
        project_key: str,
        project_root: str,
        sources: list[tuple[str, str]],
        caption: str,
        hashtags: str,
        starting_order: int,
    ) -> None:
        imported = 0
        errors: list[str] = []
        media_dir = tiktok_publish.media_directory(project_root)
        thumbnails_dir = tiktok_publish.thumbnail_directory(project_root)
        os.makedirs(media_dir, exist_ok=True)
        os.makedirs(thumbnails_dir, exist_ok=True)
        for offset, (source, display_name) in enumerate(sources):
            if self._cancel.is_set():
                break
            item_id = str(uuid.uuid4())
            suffix = Path(source).suffix.lower()
            destination = os.path.join(media_dir, f"{item_id}{suffix}")
            temporary = f"{destination}.part"
            thumbnail_path = os.path.join(thumbnails_dir, f"{item_id}.jpg")
            try:
                shutil.copy2(source, temporary)
                if self._cancel.is_set():
                    raise InterruptedError("Video import was cancelled.")
                os.replace(temporary, destination)
                create_video_thumbnail_path(
                    destination,
                    thumbnail_path,
                    cancel_event=self._cancel,
                )
                item = tiktok_publish.new_item(
                    destination,
                    thumbnail_path if os.path.isfile(thumbnail_path) else "",
                    starting_order + offset,
                    caption,
                    hashtags,
                )
                item["id"] = item_id
                item["file_name"] = display_name
                tiktok_publish.append_items(project_root, [item])
                imported += 1
                self._events.put({"type": "progress", "project_key": project_key, "imported": imported, "total": len(sources)})
            except InterruptedError:
                for candidate in (temporary, destination, thumbnail_path):
                    try:
                        os.remove(candidate)
                    except FileNotFoundError:
                        pass
                break
            except (OSError, RuntimeError, ValueError) as exc:
                errors.append(f"{Path(source).name}: {exc}")
                for candidate in (temporary, destination, thumbnail_path):
                    try:
                        os.remove(candidate)
                    except FileNotFoundError:
                        pass
        self._events.put(
            {
                "type": "finished",
                "project_key": project_key,
                "imported": imported,
                "total": len(sources),
                "errors": errors,
                "cancelled": self._cancel.is_set(),
            }
        )

    def drain_events(self) -> None:
        changed = False
        refresh_projects = False
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event.get("project_key") != self._project_key:
                continue
            if event["type"] == "progress":
                self._status = f"Adding video {event['imported']} / {event['total']}"
                changed = True
            elif event["type"] == "session_cleared":
                self._busy = False
                self._worker = None
                error = str(event.get("error") or "")
                if error:
                    self._status = error
                elif event.get("removed"):
                    self._status = "Saved TikTok login removed. Sign in to use another account."
                else:
                    self._status = "No saved TikTok login was found."
                changed = True
            elif event["type"] == "studio_progress":
                self._status = str(event.get("message") or "Preparing TikTok Studio")
                changed = True
            elif event["type"] == "studio_finished":
                self._busy = False
                self._worker = None
                attached = bool(event.get("video_attached"))
                caption_filled = bool(event.get("caption_filled"))
                error = str(event.get("error") or "")
                tiktok_publish.update_item(
                    self._project_root,
                    str(event.get("item_id") or ""),
                    status="awaiting_confirmation" if attached else "ready",
                    error=error,
                )
                if attached and caption_filled:
                    self._status = "Video, caption, and hashtags are ready in TikTok Studio. Review and publish there."
                elif attached:
                    self._status = "Video added to TikTok Studio. Caption remains on the clipboard for manual paste."
                else:
                    self._status = error or "TikTok Studio could not be prepared automatically."
                self._reload()
                project_store.touch_project_by_key(self._project_key)
                refresh_projects = True
                changed = True
            elif event["type"] == "finished":
                self._busy = False
                self._worker = None
                if event["cancelled"]:
                    self._status = "Video import stopped."
                elif event["errors"]:
                    self._status = f"Added {event['imported']} video(s); {len(event['errors'])} failed."
                else:
                    self._status = f"Added {event['imported']} video(s)."
                self._reload()
                project_store.touch_project_by_key(self._project_key)
                refresh_projects = True
                changed = True
        if changed:
            self._emit_changed()
        if refresh_projects:
            self._host.refreshVideos()

    def save_defaults(self, caption: str, hashtags: str, apply_to_existing: bool) -> bool:
        if not self._ensure_publish_project():
            return False
        self._state = tiktok_publish.update_defaults(
            self._project_root,
            caption,
            hashtags,
            apply_to_ready_items=bool(apply_to_existing),
        )
        self._sync_model()
        self._emit_changed()
        self._host.refreshVideos()
        return True

    def update_item(self, row: int, caption: str, hashtags: str) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item or not self._ensure_publish_project():
            return False
        status = "posted" if item["status"] == "posted" else "ready"
        updated = tiktok_publish.update_item(
            self._project_root,
            item["id"],
            caption=caption,
            hashtags=hashtags,
            status=status,
            error="",
        )
        if updated is None:
            return False
        self._reload()
        return True

    def prepare_item(self, row: int) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item or not self._ensure_publish_project():
            return False
        if self._busy:
            QMessageBox.information(None, "TikTok publishing", "Wait for the current TikTok task to finish.")
            return False
        path = item["file_path"]
        if not os.path.isfile(path):
            tiktok_publish.update_item(
                self._project_root,
                item["id"],
                status="missing",
                error="Video file is unavailable.",
            )
            self._reload()
            return False
        post_text = tiktok_publish.compose_post_text(item["caption"], item["hashtags"])
        QGuiApplication.clipboard().setText(post_text)
        browser_opened = open_managed_chrome_url(
            TIKTOK_STUDIO_UPLOAD_URL,
            tiktok_publish.browser_session_directory(),
        )
        if not browser_opened:
            tiktok_publish.update_item(
                self._project_root,
                item["id"],
                status="ready",
                error="Could not open TikTok Studio automatically.",
            )
            self._status = "Google Chrome is required to prepare the saved TikTok session."
            self._reload()
            return False

        tiktok_publish.update_item(self._project_root, item["id"], status="preparing", error="")
        self._busy = True
        self._cancel.clear()
        self._status = "Opening TikTok Studio and adding the video"
        self._reload()
        self._worker = threading.Thread(
            target=self._prepare_worker,
            args=(self._project_key, item["id"], path, post_text),
            name="haizflow-tiktok-studio",
            daemon=True,
        )
        self._worker.start()
        return True

    def _prepare_worker(
        self,
        project_key: str,
        item_id: str,
        video_path: str,
        post_text: str,
    ) -> None:
        result = tiktok_studio.prepare_upload(
            tiktok_publish.browser_session_directory(),
            video_path,
            post_text,
            cancel_event=self._cancel,
            progress=lambda message: self._events.put(
                {"type": "studio_progress", "project_key": project_key, "message": message}
            ),
        )
        self._events.put(
            {
                "type": "studio_finished",
                "project_key": project_key,
                "item_id": item_id,
                "video_attached": result.video_attached,
                "caption_filled": result.caption_filled,
                "error": result.error,
            }
        )

    def prepare_next(self) -> bool:
        for row, item in enumerate(self._state.get("items") or []):
            if item["status"] not in {"posted", "missing"}:
                return self.prepare_item(row)
        QMessageBox.information(None, "TikTok publishing", "There are no remaining videos to prepare.")
        return False

    def mark_posted(self, row: int) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item or not self._ensure_publish_project():
            return False
        if tiktok_publish.update_item(self._project_root, item["id"], status="posted", error="") is None:
            return False
        project_store.touch_project_by_key(self._project_key)
        self._reload()
        self._host.refreshVideos()
        return True

    def confirm_and_prepare_next(self, row: int) -> bool:
        if not self.mark_posted(row):
            return False
        for next_row, item in enumerate(self._state.get("items") or []):
            if item["status"] not in {"posted", "missing"}:
                return self.prepare_item(next_row)
        self._status = "All queued videos are marked as posted."
        self._emit_changed()
        return True

    def mark_ready(self, row: int) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item or not self._ensure_publish_project():
            return False
        if tiktok_publish.update_item(self._project_root, item["id"], status="ready", error="") is None:
            return False
        self._reload()
        self._host.refreshVideos()
        return True

    def copy_caption(self, row: int) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item:
            return False
        QGuiApplication.clipboard().setText(item["post_text"])
        self._status = "Caption and hashtags copied."
        self._emit_changed()
        return True

    def remove_item(self, row: int) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item or not self._ensure_publish_project():
            return False
        if QMessageBox.question(
            None,
            "Remove publishing item",
            f"Remove '{item['file_name']}' from this publishing project and delete its project-owned copy?",
        ) != QMessageBox.StandardButton.Yes:
            return False
        removed = tiktok_publish.remove_item(self._project_root, item["id"])
        if removed is None:
            return False
        for key in ("file_path", "thumbnail_path"):
            path = str(removed.get(key) or "")
            if self._is_owned_file(path):
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
        self._reload()
        self._host.refreshVideos()
        return True

    def shutdown(self) -> None:
        self._cancel.set()

    @property
    def project_source_selected_count(self) -> int:
        return sum(1 for item in self._project_sources if item["selected"])

    def _ensure_publish_project(self) -> bool:
        if self._host._project_type == "publish" and self._project_key and self._project_root:
            return True
        QMessageBox.information(None, "TikTok publishing", "Open a TikTok publishing project first.")
        return False

    def _is_owned_file(self, path: str) -> bool:
        if not path or not self._project_root:
            return False
        candidate = os.path.abspath(path)
        publishing_root = os.path.abspath(project_store.project_publishing_dir_for_key(self._project_key))
        try:
            return os.path.commonpath([publishing_root, candidate]) == publishing_root and candidate != publishing_root
        except ValueError:
            return False

    @staticmethod
    def _supported_file(path: str) -> bool:
        if not path or Path(path).suffix.lower() not in PUBLISH_VIDEO_EXTENSIONS:
            return False
        try:
            return os.path.isfile(path) and 0 < os.path.getsize(path) < TIKTOK_MAX_VIDEO_BYTES
        except OSError:
            return False

    @staticmethod
    def _output_path(video) -> str:
        files = video.files or {}
        for key in ("final_video", "output_video"):
            candidate = str(files.get(key) or "")
            if candidate and os.path.isfile(candidate):
                return os.path.abspath(candidate)
        legacy = os.path.join(video_store.get_video_dir(video.video_id), "output", "final.mp4")
        return os.path.abspath(legacy) if os.path.isfile(legacy) else ""
