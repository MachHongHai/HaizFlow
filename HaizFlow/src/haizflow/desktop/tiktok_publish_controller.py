"""Project-backed TikTok publishing through Zernio's official REST API."""

from __future__ import annotations

import os
import queue
import re
import shutil
import threading
import uuid
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from haizflow.desktop.external_links import open_external_url
from haizflow.desktop.localization import QFileDialog, QMessageBox, native_media_dialog_directory
from haizflow.desktop.media import create_video_thumbnail_path, normalize_video_path, thumbnail_source
from haizflow.services import project_store, secure_credentials, tiktok_publish, video_store, zernio
from haizflow.utils.ffmpeg import get_video_duration


ZERNIO_CREDENTIAL_TARGET = "HaizFlow/Zernio/APIKey"
PUBLISH_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm"})
TIKTOK_MAX_VIDEO_BYTES = 4_000_000_000
_API_KEY_PATTERN = re.compile(r"^sk_[0-9a-fA-F]{64}$")


class TikTokPublishController:
    def __init__(self, host):
        self._host = host
        self._project_key = ""
        self._project_root = ""
        self._state = tiktok_publish.empty_state()
        self._busy = False
        self._status = ""
        self._events: queue.Queue[dict] = queue.Queue()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._project_sources: list[dict] = []
        self._accounts: list[dict] = []
        self._profile_id = ""
        self._privacy_levels: list[str] = []
        self._auto_continue = False
        self._consent_confirmed = False

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
        return sum(1 for item in self._state.get("items") or [] if item["status"] in {"published", "posted"})

    @property
    def api_key_configured(self) -> bool:
        return bool(self._api_key())

    @property
    def account_names(self) -> list[str]:
        return [self._account_label(account) for account in self._accounts]

    @property
    def selected_account_index(self) -> int:
        selected = str(self._state.get("selected_account_id") or "")
        return next((index for index, item in enumerate(self._accounts) if self._object_id(item) == selected), -1)

    @property
    def privacy_levels(self) -> list[str]:
        return list(self._privacy_levels)

    @property
    def privacy_level(self) -> str:
        return str(self._state.get("privacy_level") or "")

    @property
    def publish_now(self) -> bool:
        return bool(self._state.get("publish_now", True))

    @property
    def allow_comment(self) -> bool:
        return bool(self._state.get("allow_comment", True))

    @property
    def allow_duet(self) -> bool:
        return bool(self._state.get("allow_duet", True))

    @property
    def allow_stitch(self) -> bool:
        return bool(self._state.get("allow_stitch", True))

    @property
    def consent_confirmed(self) -> bool:
        return self._consent_confirmed

    @property
    def project_source_selected_count(self) -> int:
        return sum(1 for item in self._project_sources if item["selected"])

    def has_project_work(self, project_key: str) -> bool:
        return bool(self._busy and self._project_key == str(project_key or ""))

    def can_switch_project(self, project_key: str) -> bool:
        target = str(project_key or "")
        return not self._busy or not self._project_key or self._project_key == target

    def attach_project(self, project_key: str, project_root: str) -> None:
        if self._project_key != str(project_key or ""):
            self._consent_confirmed = False
        self._project_key = str(project_key or "")
        self._project_root = os.path.abspath(project_root) if project_root else ""
        if not self._busy and self._project_root:
            tiktok_publish.cleanup_orphaned_media(self._project_root)
        self._reload()

    def detach_project(self) -> None:
        self._project_key = ""
        self._project_root = ""
        self._state = tiktok_publish.empty_state()
        self._accounts = []
        self._privacy_levels = []
        self._consent_confirmed = False
        self._host.tiktok_publish_items.set_items([])
        self._emit_changed()

    def _reload(self) -> None:
        if self._project_root and os.path.isdir(self._project_root):
            self._state = tiktok_publish.load_state(self._project_root)
        else:
            self._state = tiktok_publish.empty_state()
        self._sync_model()
        self._emit_changed()

    def _sync_model(self) -> None:
        self._host.tiktok_publish_items.set_items([
            {
                **item,
                "post_text": tiktok_publish.compose_post_text(item["caption"], item["hashtags"]),
                "thumbnail_source": thumbnail_source(item.get("thumbnail_path") or ""),
            }
            for item in self._state.get("items") or []
        ])

    def _emit_changed(self) -> None:
        self._host.tiktokPublishChanged.emit()

    def save_api_key(self, value: str) -> bool:
        key = str(value or "").strip()
        if not _API_KEY_PATTERN.fullmatch(key):
            self._status = "Zernio API key must use the sk_ prefix followed by 64 hexadecimal characters."
            self._emit_changed()
            return False
        try:
            secure_credentials.write_secret(ZERNIO_CREDENTIAL_TARGET, key, username="Zernio API")
        except (OSError, ValueError) as exc:
            self._status = f"Could not save the Zernio API key securely: {exc}"
            self._emit_changed()
            return False
        self._status = "Zernio API key saved in Windows Credential Manager."
        self._emit_changed()
        return self.refresh_accounts()

    def clear_api_key(self) -> bool:
        if self._busy:
            return False
        try:
            secure_credentials.delete_secret(ZERNIO_CREDENTIAL_TARGET)
        except OSError as exc:
            self._status = f"Could not remove the Zernio API key: {exc}"
            self._emit_changed()
            return False
        self._accounts = []
        self._privacy_levels = []
        self._profile_id = ""
        self._status = "Zernio API key removed."
        self._emit_changed()
        return True

    def connect_tiktok(self) -> bool:
        return self._start_account_worker("connect")

    def refresh_accounts(self) -> bool:
        return self._start_account_worker("refresh")

    def _start_account_worker(self, action: str) -> bool:
        if self._busy:
            return False
        key = self._api_key()
        if not key:
            self._status = "Add a Zernio API key first."
            self._emit_changed()
            return False
        self._busy = True
        self._status = "Connecting to Zernio" if action == "connect" else "Refreshing TikTok accounts"
        self._emit_changed()
        self._worker = threading.Thread(
            target=self._account_worker,
            args=(action, key, self._project_key),
            name=f"haizflow-zernio-{action}",
            daemon=True,
        )
        self._worker.start()
        return True

    def _account_worker(self, action: str, key: str, project_key: str) -> None:
        try:
            client = zernio.ZernioClient(key)
            profiles = client.list_profiles()
            profile = profiles[0] if profiles else client.create_profile("HaizFlow", "TikTok publishing from HaizFlow")
            profile_id = self._object_id(profile)
            if not profile_id:
                raise zernio.ZernioError("Zernio did not return a profile ID.")
            if action == "connect":
                auth_url = client.get_connect_url(profile_id)
                if not auth_url:
                    raise zernio.ZernioError("Zernio did not return a TikTok authorization URL.")
                self._events.put({"type": "oauth", "project_key": project_key, "profile_id": profile_id, "url": auth_url})
                return
            accounts = client.list_tiktok_accounts(profile_id)
            self._events.put({"type": "accounts", "project_key": project_key, "profile_id": profile_id, "accounts": accounts})
        except (OSError, ValueError, zernio.ZernioError) as exc:
            self._events.put({"type": "error", "project_key": project_key, "message": str(exc)})

    def select_account(self, index: int) -> bool:
        if index < 0 or index >= len(self._accounts) or not self._ensure_publish_project():
            return False
        account_id = self._object_id(self._accounts[index])
        if not account_id:
            return False
        self._state = tiktok_publish.update_publish_settings(self._project_root, selected_account_id=account_id)
        return self._start_creator_info_worker(account_id)

    def _start_creator_info_worker(self, account_id: str) -> bool:
        if self._busy:
            return False
        key = self._api_key()
        if not key:
            return False
        self._busy = True
        self._status = "Loading TikTok publishing options"
        self._emit_changed()
        self._worker = threading.Thread(
            target=self._creator_info_worker,
            args=(key, account_id, self._project_key),
            name="haizflow-zernio-creator-info",
            daemon=True,
        )
        self._worker.start()
        return True

    def _creator_info_worker(self, key: str, account_id: str, project_key: str) -> None:
        try:
            info = zernio.ZernioClient(key).get_tiktok_creator_info(account_id)
            levels = info.get("privacyLevels") or info.get("privacy_levels") or []
            if not isinstance(levels, list):
                levels = []
            self._events.put({"type": "creator", "project_key": project_key, "levels": [str(v) for v in levels]})
        except (OSError, ValueError, zernio.ZernioError) as exc:
            self._events.put({"type": "error", "project_key": project_key, "message": str(exc)})

    def set_publish_settings(
        self,
        privacy_level: str,
        publish_now: bool,
        allow_comment: bool,
        allow_duet: bool,
        allow_stitch: bool,
    ) -> bool:
        if not self._ensure_publish_project():
            return False
        level = str(privacy_level or "")
        if self._privacy_levels and level not in self._privacy_levels:
            return False
        self._state = tiktok_publish.update_publish_settings(
            self._project_root,
            privacy_level=level,
            publish_now=publish_now,
            allow_comment=allow_comment,
            allow_duet=allow_duet,
            allow_stitch=allow_stitch,
        )
        self._emit_changed()
        return True

    def browse_videos(self) -> None:
        if not self._ensure_publish_project():
            return
        paths, _ = QFileDialog.getOpenFileNames(
            None,
            "Choose videos to publish on TikTok",
            native_media_dialog_directory(),
            "TikTok video files (*.mp4 *.mov *.webm);;All files (*.*)",
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
        paths = [
            str(path.resolve())
            for path in sorted(Path(folder).iterdir(), key=lambda value: value.name.lower())
            if path.is_file() and self._supported_file(str(path))
        ]
        if not paths:
            QMessageBox.warning(None, "TikTok publishing", "This folder contains no supported videos.")
            return
        self.add_videos(paths)

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
            source = {"output_path": output_path, "display_name": f"{project_name} — {video.original_filename}"}
            if video.project_type == "batch":
                group_key = str(getattr(video, "project_key", "") or getattr(video, "project_id", "") or project_name)
                candidate = batch_groups.get(group_key)
                if candidate is None:
                    candidate = {
                        "video_id": f"batch:{group_key}", "project_name": project_name, "project_type": "batch",
                        "file_name": "", "output_paths": [],
                        "thumbnail_source": thumbnail_source((video.files or {}).get("thumbnail") or ""),
                        "video_size": "", "video_count": 0, "selected": False,
                    }
                    batch_groups[group_key] = candidate
                    candidates.append(candidate)
                candidate["output_paths"].append(source)
                candidate["video_count"] = len(candidate["output_paths"])
            else:
                candidates.append({
                    "video_id": video.video_id, "project_name": project_name, "project_type": "single",
                    "file_name": video.original_filename, "output_paths": [source],
                    "thumbnail_source": thumbnail_source((video.files or {}).get("thumbnail") or ""),
                    "video_size": f"{width} x {height}" if width and height else "", "video_count": 1,
                    "selected": False,
                })
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
        sources = [source for item in selected for source in item["output_paths"]]
        if not sources:
            return False
        labels = {source["output_path"]: source["display_name"] for source in sources}
        return self.add_videos([source["output_path"] for source in sources], labels)

    def add_videos(self, paths, display_names: dict[str, str] | None = None) -> bool:
        if not self._ensure_publish_project() or self._busy:
            return False
        valid: list[tuple[str, str]] = []
        seen: set[str] = set()
        for value in paths:
            path = normalize_video_path(value)
            if path in seen:
                continue
            seen.add(path)
            if self._supported_file(path):
                valid.append((path, str((display_names or {}).get(path) or Path(path).name)))
        if not valid:
            QMessageBox.warning(None, "TikTok publishing", "Choose an MP4, MOV, or WebM video smaller than 4 GB.")
            return False
        self._busy = True
        self._cancel.clear()
        self._status = "Adding videos to the publishing project"
        self._emit_changed()
        self._worker = threading.Thread(
            target=self._import_worker,
            args=(self._project_key, self._project_root, valid, self.default_caption, self.default_hashtags, self.count),
            name="haizflow-tiktok-import",
            daemon=True,
        )
        self._worker.start()
        return True

    def _import_worker(self, project_key, project_root, sources, caption, hashtags, starting_order) -> None:
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
            destination = os.path.join(media_dir, f"{item_id}{Path(source).suffix.lower()}")
            temporary = f"{destination}.part"
            thumbnail_path = os.path.join(thumbnails_dir, f"{item_id}.jpg")
            imported_destination = False
            try:
                shutil.copy2(source, temporary)
                if self._cancel.is_set():
                    raise InterruptedError
                os.replace(temporary, destination)
                imported_destination = True
                duration = get_video_duration(destination, timeout_seconds=20.0)
                if duration < 3.0 or duration > 600.0:
                    raise ValueError("TikTok videos must be between 3 seconds and 10 minutes long.")
                create_video_thumbnail_path(destination, thumbnail_path, cancel_event=self._cancel)
                item = tiktok_publish.new_item(
                    destination, thumbnail_path if os.path.isfile(thumbnail_path) else "",
                    starting_order + offset, caption, hashtags,
                )
                item["id"] = item_id
                item["file_name"] = display_name
                tiktok_publish.append_items(project_root, [item])
                imported += 1
                self._events.put({"type": "import_progress", "project_key": project_key, "done": imported, "total": len(sources)})
            except InterruptedError:
                for candidate in (destination, thumbnail_path):
                    try:
                        os.remove(candidate)
                    except OSError:
                        pass
                break
            except (OSError, RuntimeError, ValueError) as exc:
                errors.append(f"{Path(source).name}: {exc}")
                if imported_destination:
                    for candidate in (destination, thumbnail_path):
                        try:
                            os.remove(candidate)
                        except OSError:
                            pass
            finally:
                for candidate in (temporary,):
                    try:
                        os.remove(candidate)
                    except FileNotFoundError:
                        pass
        self._events.put({
            "type": "import_finished", "project_key": project_key, "done": imported,
            "total": len(sources), "errors": errors, "cancelled": self._cancel.is_set(),
        })

    def save_defaults(self, caption: str, hashtags: str, apply_to_existing: bool) -> bool:
        if not self._ensure_publish_project():
            return False
        self._state = tiktok_publish.update_defaults(
            self._project_root, caption, hashtags, apply_to_ready_items=bool(apply_to_existing)
        )
        if apply_to_existing:
            self._consent_confirmed = False
        self._sync_model()
        self._emit_changed()
        self._host.refreshVideos()
        return True

    def update_item(self, row: int, caption: str, hashtags: str) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item or not self._ensure_publish_project() or item["status"] in {"uploading", "publishing"}:
            return False
        updated = tiktok_publish.update_item(
            self._project_root, item["id"], caption=caption, hashtags=hashtags,
            status="ready" if item["status"] not in {"published", "posted"} else item["status"], error="",
        )
        if updated is None:
            return False
        self._consent_confirmed = False
        self._reload()
        return True

    def set_consent_confirmed(self, confirmed: bool) -> None:
        self._consent_confirmed = bool(confirmed)
        self._emit_changed()

    def publish_item(self, row: int, *, continue_queue: bool = False) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item or not self._ensure_ready_to_publish(item):
            return False
        self._auto_continue = bool(continue_queue)
        self._busy = True
        self._cancel.clear()
        self._status = f"Uploading {item['file_name']}"
        tiktok_publish.update_item(self._project_root, item["id"], status="uploading", error="", upload_progress=0)
        self._reload()
        settings = {
            "account_id": self._state["selected_account_id"],
            "privacy_level": self._state["privacy_level"],
            "publish_now": self.publish_now,
            "allow_comment": self.allow_comment,
            "allow_duet": self.allow_duet,
            "allow_stitch": self.allow_stitch,
        }
        self._worker = threading.Thread(
            target=self._publish_worker,
            args=(self._api_key(), self._project_key, dict(item), settings),
            name="haizflow-zernio-publish",
            daemon=True,
        )
        self._worker.start()
        return True

    def publish_next(self, *, continue_queue: bool = False) -> bool:
        for row, item in enumerate(self._state.get("items") or []):
            if item["status"] in {"ready", "failed", "missing"} and os.path.isfile(item["file_path"]):
                return self.publish_item(row, continue_queue=continue_queue)
        self._status = "No videos are waiting to be published."
        self._emit_changed()
        return False

    def publish_all(self) -> bool:
        return self.publish_next(continue_queue=True)

    def _ensure_ready_to_publish(self, item: dict) -> bool:
        if self._busy or not self._ensure_publish_project():
            return False
        if not self._api_key():
            self._status = "Add a Zernio API key first."
        elif not self._state.get("selected_account_id"):
            self._status = "Connect and select a TikTok account first."
        elif not self._state.get("privacy_level"):
            self._status = "Choose one of the privacy levels allowed by this TikTok account."
        elif not self._consent_confirmed:
            self._status = "Review the queued posts and confirm consent before uploading."
        elif not os.path.isfile(item.get("file_path") or ""):
            self._status = "The selected video file is unavailable."
        else:
            return True
        self._emit_changed()
        return False

    def _publish_worker(self, key: str, project_key: str, item: dict, settings: dict) -> None:
        try:
            client = zernio.ZernioClient(key)
            presigned = client.presign_video(item["file_path"])
            upload_url = str(presigned.get("uploadUrl") or "")
            public_url = str(presigned.get("publicUrl") or "")
            if not upload_url or not public_url:
                raise zernio.ZernioError("Zernio did not return complete media upload information.")
            last_progress = -1

            def report(done: int, total: int) -> None:
                nonlocal last_progress
                percent = round(done * 100 / total) if total else 0
                if percent >= last_progress + 2 or percent == 100:
                    last_progress = percent
                    self._events.put({
                        "type": "upload_progress", "project_key": project_key,
                        "item_id": item["id"], "progress": percent,
                    })

            client.upload_file(upload_url, item["file_path"], progress=report, cancelled=self._cancel.is_set)
            if self._cancel.is_set():
                raise zernio.ZernioCancelled("Upload cancelled.")
            self._events.put({"type": "publishing", "project_key": project_key, "item_id": item["id"]})
            result = client.create_tiktok_post(
                account_id=settings["account_id"],
                content=tiktok_publish.compose_post_text(item["caption"], item["hashtags"]),
                media_url=public_url,
                privacy_level=settings["privacy_level"],
                publish_now=settings["publish_now"],
                request_id=item["request_id"],
                allow_comment=settings["allow_comment"],
                allow_duet=settings["allow_duet"],
                allow_stitch=settings["allow_stitch"],
            )
            post = result.get("post") if isinstance(result.get("post"), dict) else result.get("existingPost")
            if not isinstance(post, dict):
                post = result
            post_id = self._object_id(post)
            status = str(post.get("status") or ("publishing" if settings["publish_now"] else "draft")).lower()
            self._events.put({
                "type": "publish_finished", "project_key": project_key, "item_id": item["id"],
                "post_id": post_id, "status": status, "url": self._platform_url(post), "error": "",
            })
        except zernio.ZernioCancelled as exc:
            self._events.put({"type": "publish_finished", "project_key": project_key, "item_id": item["id"], "status": "ready", "error": str(exc)})
        except (OSError, ValueError, zernio.ZernioError) as exc:
            self._events.put({"type": "publish_finished", "project_key": project_key, "item_id": item["id"], "status": "failed", "error": str(exc)})

    def refresh_post_statuses(self) -> bool:
        posts = [(item["id"], item.get("zernio_post_id") or "") for item in self._state.get("items") or []]
        posts = [(item_id, post_id) for item_id, post_id in posts if post_id]
        if self._busy or not posts or not self._api_key():
            return False
        self._busy = True
        self._status = "Refreshing post statuses"
        self._emit_changed()
        self._worker = threading.Thread(
            target=self._status_worker,
            args=(self._api_key(), self._project_key, posts),
            name="haizflow-zernio-status",
            daemon=True,
        )
        self._worker.start()
        return True

    def _status_worker(self, key: str, project_key: str, posts: list[tuple[str, str]]) -> None:
        updates = []
        try:
            client = zernio.ZernioClient(key)
            for item_id, post_id in posts:
                post = client.get_post(post_id)
                updates.append({
                    "item_id": item_id,
                    "status": str(post.get("status") or "publishing").lower(),
                    "url": self._platform_url(post),
                })
            self._events.put({"type": "statuses", "project_key": project_key, "updates": updates})
        except (OSError, ValueError, zernio.ZernioError) as exc:
            self._events.put({"type": "error", "project_key": project_key, "message": str(exc)})

    def drain_events(self) -> None:
        changed = False
        refresh_projects = False
        continue_queue = False
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event.get("project_key") != self._project_key:
                continue
            kind = event["type"]
            if kind == "oauth":
                self._busy = False
                self._profile_id = str(event.get("profile_id") or "")
                opened = open_external_url(str(event.get("url") or ""))
                self._status = "Authorize TikTok in the browser, then click Refresh accounts." if opened else "Could not open the Zernio authorization page."
            elif kind == "accounts":
                self._busy = False
                self._profile_id = str(event.get("profile_id") or "")
                self._accounts = list(event.get("accounts") or [])
                selected_id = str(self._state.get("selected_account_id") or "")
                if self._accounts and not any(self._object_id(item) == selected_id for item in self._accounts):
                    selected_id = self._object_id(self._accounts[0])
                    self._state = tiktok_publish.update_publish_settings(self._project_root, selected_account_id=selected_id)
                self._status = f"Found {len(self._accounts)} connected TikTok account(s)." if self._accounts else "No TikTok account is connected yet."
                if selected_id:
                    self._busy = False
                    self._start_creator_info_worker(selected_id)
            elif kind == "creator":
                self._busy = False
                self._privacy_levels = list(event.get("levels") or [])
                selected = str(self._state.get("privacy_level") or "")
                if self._privacy_levels and selected not in self._privacy_levels:
                    selected = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in self._privacy_levels else self._privacy_levels[0]
                    self._state = tiktok_publish.update_publish_settings(self._project_root, privacy_level=selected)
                self._status = "TikTok account is ready for publishing."
            elif kind == "import_progress":
                self._status = f"Adding video {event['done']} / {event['total']}"
            elif kind == "import_finished":
                self._busy = False
                self._worker = None
                self._consent_confirmed = False
                self._reload()
                errors = list(event.get("errors") or [])
                self._status = f"Added {event['done']} video(s)." if not errors else f"Added {event['done']} video(s); {len(errors)} failed."
                refresh_projects = True
            elif kind == "upload_progress":
                tiktok_publish.update_item(self._project_root, event["item_id"], upload_progress=event["progress"])
                self._status = f"Uploading video: {event['progress']}%"
                self._reload()
            elif kind == "publishing":
                tiktok_publish.update_item(self._project_root, event["item_id"], status="publishing", upload_progress=100)
                self._status = "Video uploaded; creating the TikTok post"
                self._reload()
            elif kind == "publish_finished":
                self._busy = False
                self._worker = None
                status = str(event.get("status") or "failed")
                tiktok_publish.update_item(
                    self._project_root, event["item_id"], status=status,
                    error=str(event.get("error") or ""), zernio_post_id=str(event.get("post_id") or ""),
                    platform_post_url=str(event.get("url") or ""), upload_progress=100 if status != "ready" else 0,
                )
                self._reload()
                self._status = str(event.get("error") or ("Post sent to Zernio." if status != "draft" else "Draft created in Zernio."))
                refresh_projects = True
                continue_queue = self._auto_continue and status not in {"ready"}
                if status == "failed":
                    self._auto_continue = False
            elif kind == "statuses":
                self._busy = False
                self._worker = None
                for update in event.get("updates") or []:
                    tiktok_publish.update_item(
                        self._project_root, update["item_id"], status=update["status"],
                        platform_post_url=update.get("url") or "",
                    )
                self._reload()
                self._status = "Post statuses updated."
                refresh_projects = True
            elif kind == "error":
                self._busy = False
                self._worker = None
                self._status = str(event.get("message") or "Zernio request failed.")
            changed = True
        if changed:
            self._emit_changed()
        if refresh_projects:
            project_store.touch_project_by_key(self._project_key)
            self._host.refreshVideos()
        if continue_queue and not self._busy:
            self.publish_next(continue_queue=True)

    def copy_caption(self, row: int) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item:
            return False
        QGuiApplication.clipboard().setText(item["post_text"])
        self._status = "Caption and hashtags copied."
        self._emit_changed()
        return True

    def open_post(self, row: int) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        return bool(item and item.get("platform_post_url") and open_external_url(item["platform_post_url"]))

    def remove_item(self, row: int) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if not item or not self._ensure_publish_project() or self._busy:
            return False
        if QMessageBox.question(
            None, "Remove publishing item", f"Remove '{item['file_name']}' and its project-owned copy?"
        ) != QMessageBox.StandardButton.Yes:
            return False
        removed = tiktok_publish.remove_item(self._project_root, item["id"])
        if removed is None:
            return False
        self._consent_confirmed = False
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

    def cancel(self) -> None:
        self._auto_continue = False
        self._cancel.set()
        self._status = "Stopping after the current request"
        self._emit_changed()

    def shutdown(self) -> None:
        self._auto_continue = False
        self._cancel.set()

    def _api_key(self) -> str:
        environment_key = str(os.environ.get("ZERNIO_API_KEY") or "").strip()
        if environment_key:
            return environment_key
        try:
            return secure_credentials.read_secret(ZERNIO_CREDENTIAL_TARGET)
        except OSError:
            return ""

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
    def _object_id(value: dict) -> str:
        return str(value.get("_id") or value.get("id") or "") if isinstance(value, dict) else ""

    @staticmethod
    def _account_label(account: dict) -> str:
        identity = account.get("username") or account.get("displayName") or account.get("name")
        if not identity and isinstance(account.get("metadata"), dict):
            identity = account["metadata"].get("username") or account["metadata"].get("displayName")
        return str(identity or TikTokPublishController._object_id(account) or "TikTok account")

    @staticmethod
    def _platform_url(post: dict) -> str:
        direct = str(post.get("platformPostUrl") or post.get("url") or "")
        if direct:
            return direct
        for key in ("platformResults", "platforms", "results"):
            entries = post.get(key)
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict) and entry.get("platformPostUrl"):
                        return str(entry["platformPostUrl"])
        return ""

    @staticmethod
    def _supported_file(path: str) -> bool:
        if not path or Path(path).suffix.lower() not in PUBLISH_VIDEO_EXTENSIONS:
            return False
        try:
            return os.path.isfile(path) and 0 < os.path.getsize(path) <= TIKTOK_MAX_VIDEO_BYTES
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
