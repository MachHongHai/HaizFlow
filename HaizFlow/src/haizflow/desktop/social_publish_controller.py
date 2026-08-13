"""Project-backed social publishing through Zernio's official REST API."""

from __future__ import annotations

import os
import queue
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from haizflow.desktop.external_links import open_external_url
from haizflow.desktop.localization import QFileDialog, QMessageBox, native_media_dialog_directory
from haizflow.desktop.media import create_video_thumbnail_path, normalize_video_path, thumbnail_source
from haizflow.services import project_store, secure_credentials, social_publish as tiktok_publish, video_store, zernio
from haizflow.utils.ffmpeg import get_video_dimensions, get_video_duration


ZERNIO_CREDENTIAL_TARGET = "HaizFlow/Zernio/APIKey"
ZERNIO_SIGN_UP_URL = "https://zernio.com/signup"
ZERNIO_SIGN_IN_URL = "https://zernio.com/signin"
ZERNIO_API_KEYS_URL = "https://zernio.com/dashboard/api-keys"
ZERNIO_POSTING_DOCS_URL = "https://docs.zernio.com/platforms"
ZERNIO_TIKTOK_DOCS_URL = ZERNIO_POSTING_DOCS_URL  # Backward-compatible import.
PUBLISH_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm"})
TIKTOK_MAX_VIDEO_BYTES = 4_000_000_000
SUPPORTED_PLATFORMS = ("tiktok", "youtube", "facebook", "instagram")
PLATFORM_LABELS = {
    "tiktok": "TikTok",
    "youtube": "YouTube Shorts",
    "facebook": "Facebook Reels",
    "instagram": "Instagram Reels",
}
_API_KEY_PATTERN = re.compile(r"^sk_[0-9a-fA-F]{64}$")
_POLLABLE_POST_STATUSES = frozenset({"uploading", "publishing", "pending", "processing", "queued"})
_SUCCESS_POST_STATUSES = frozenset({"published", "posted"})
_FAILED_POST_STATUSES = frozenset({"failed", "partial", "cancelled", "deleted"})
_POST_STATUS_POLL_SECONDS = 3.0
_POST_STATUS_POLL_TIMEOUT_SECONDS = 180.0
_OAUTH_ACCOUNT_POLL_SECONDS = 1.0
_OAUTH_ACCOUNT_POLL_TIMEOUT_SECONDS = 30.0
_ACCOUNT_BACKGROUND_REFRESH_SECONDS = 5.0
_CREATOR_INFO_CACHE_SECONDS = 300.0
_ZERNIO_FREE_CONNECTED_ACCOUNTS = 2
_ZERNIO_BILLING_ERROR_MARKERS = (
    "http 402",
    "billing",
    "payment",
    "subscription",
    "account limit",
    "connection limit",
    "quota",
    "authorization url",
)


class SocialPublishController:
    def __init__(self, host):
        self._host = host
        self._project_key = ""
        self._project_root = ""
        self._state = tiktok_publish.empty_state()
        self._busy = False
        self._account_syncing = False
        self._background_account_refreshing = False
        self._creator_syncing = False
        self._account_generation = 0
        self._creator_generation = 0
        self._status = ""
        self._events: queue.Queue[dict] = queue.Queue()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._account_worker_thread: threading.Thread | None = None
        self._background_account_worker_thread: threading.Thread | None = None
        self._creator_worker_thread: threading.Thread | None = None
        self._creator_cache: dict[str, tuple[float, dict]] = {}
        self._project_sources: list[dict] = []
        self._accounts: list[dict] = []
        self._profiles: list[dict] = []
        self._profile_id = ""
        self._profile_name = ""
        self._api_key_cache: str | None = None
        self._api_key_verified = False
        self._privacy_levels: list[str] = []
        self._interaction_settings = {"comment": False, "duet": False, "stitch": False}
        self._creator_info_loaded = False
        self._can_post_more = True
        self._auto_continue = False
        self._consent_confirmed = False
        self._oauth_sync_pending = False
        self._oauth_account_ids_before: set[str] = set()
        self._oauth_sync_deadline = 0.0
        self._oauth_sync_next = 0.0
        self._account_refresh_next = 0.0
        self._post_status_poll_deadline = 0.0
        self._post_status_poll_next = 0.0
        self._post_status_refreshing = False
        self._publish_signal_snapshot: tuple | None = None
        self._account_signal_snapshot: tuple | None = None
        self._option_signal_snapshot: tuple | None = None

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def account_syncing(self) -> bool:
        return self._account_syncing

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
    def api_key_verified(self) -> bool:
        return self.api_key_configured and self._api_key_verified

    @property
    def connected_account_count(self) -> int:
        return len(self._accounts)

    @property
    def profile_count(self) -> int:
        return len(self._profiles)

    @property
    def connection_profile_name(self) -> str:
        return self._profile_name

    @property
    def oauth_sync_pending(self) -> bool:
        return self._oauth_sync_pending

    @property
    def account_ready(self) -> bool:
        # Keep the last verified account usable in the UI while a background
        # refresh is running. Publishing itself is still guarded by
        # ``_account_syncing`` in ``_ensure_ready_to_publish``.
        return bool(
            self.selected_account_index >= 0
            and self._creator_info_loaded
            and self._privacy_levels
            and self._can_post_more
        )

    @property
    def can_post_more(self) -> bool:
        # ``True`` is the neutral value until TikTok creator information has
        # loaded.  A false value must only mean that TikTok explicitly reports
        # the account's daily posting limit has been reached.
        return self._can_post_more

    @property
    def account_names(self) -> list[str]:
        return [self._account_label(account) for account in self._accounts]

    @property
    def account_platforms(self) -> list[str]:
        return [self._account_platform(account) for account in self._accounts]

    @property
    def selected_platform(self) -> str:
        index = self.selected_account_index
        if 0 <= index < len(self._accounts):
            return self._account_platform(self._accounts[index])
        return str(self._state.get("selected_platform") or "tiktok")

    @property
    def selected_platform_label(self) -> str:
        return PLATFORM_LABELS.get(self.selected_platform, self.selected_platform.title())

    @property
    def selected_account_name(self) -> str:
        index = self.selected_account_index
        return self._account_label(self._accounts[index]) if 0 <= index < len(self._accounts) else ""

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
    def share_to_feed(self) -> bool:
        return bool(self._state.get("share_to_feed", True))

    @property
    def ai_generated(self) -> bool:
        return bool(self._state.get("ai_generated", False))

    @property
    def first_comment(self) -> str:
        return str(self._state.get("first_comment") or "")

    @property
    def comment_available(self) -> bool:
        return self._creator_info_loaded and bool(self._interaction_settings["comment"])

    @property
    def duet_available(self) -> bool:
        return self._creator_info_loaded and bool(self._interaction_settings["duet"])

    @property
    def stitch_available(self) -> bool:
        return self._creator_info_loaded and bool(self._interaction_settings["stitch"])

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
            self._stop_post_status_poll()
        self._project_key = str(project_key or "")
        self._project_root = os.path.abspath(project_root) if project_root else ""
        if not self._busy and self._project_root:
            tiktok_publish.migrate_project_layout(self._project_root)
            tiktok_publish.cleanup_orphaned_media(self._project_root)
        self._reload()
        if self._pending_post_ids():
            self._schedule_post_status_poll(immediate=True)
        # Verify a securely stored key and restore the connected-account state
        # as soon as the publishing project opens.  Users should not need to
        # press Refresh on every app launch just to make the page usable.
        if self.api_key_configured and not self._busy:
            self.reconcile_accounts()

    def detach_project(self) -> None:
        self._project_key = ""
        self._project_root = ""
        self._state = tiktok_publish.empty_state()
        self._accounts = []
        self._profiles = []
        self._profile_name = ""
        self._privacy_levels = []
        self._api_key_verified = False
        self._interaction_settings = {"comment": False, "duet": False, "stitch": False}
        self._creator_info_loaded = False
        self._can_post_more = True
        self._account_syncing = False
        self._background_account_refreshing = False
        self._creator_syncing = False
        self._account_generation += 1
        self._creator_generation += 1
        self._account_worker_thread = None
        self._background_account_worker_thread = None
        self._creator_worker_thread = None
        self._creator_cache.clear()
        self._account_refresh_next = 0.0
        self._consent_confirmed = False
        self._stop_oauth_sync()
        self._stop_post_status_poll()
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
        self._host.tiktok_publish_items.set_items(
            [self._model_item(item) for item in self._state.get("items") or []]
        )

    def _model_item(self, item: dict) -> dict:
        target_platform = str(item.get("target_platform") or "tiktok")
        if (
            str(item.get("status") or "") in {"ready", "failed", "missing"}
            and not item.get("zernio_post_id")
        ):
            target_platform = self.selected_platform
        return {
            **item,
            "post_text": tiktok_publish.compose_post_text(item["caption"], item["hashtags"]),
            "thumbnail_source": thumbnail_source(item.get("thumbnail_path") or ""),
            "target_platform": target_platform,
            # Never expose a guessed, media, or dashboard URL as an "Open post"
            # action. TikTok can report success before its permalink is ready.
            "platform_post_url": (
                zernio.public_post_url(item.get("platform_post_url"), target_platform)
                if item.get("platform_post_url_verified") else ""
            ),
        }

    def _update_item_state(self, item_id: str, **changes) -> dict | None:
        current = next(
            (item for item in self._state.get("items") or [] if item.get("id") == item_id),
            None,
        )
        if current is not None and all(current.get(key) == value for key, value in changes.items()):
            return current
        updated = tiktok_publish.update_item(self._project_root, item_id, **changes)
        if updated is None:
            return None
        for index, item in enumerate(self._state.get("items") or []):
            if item.get("id") == item_id:
                self._state["items"][index] = updated
                break
        if not self._host.tiktok_publish_items.update_item(item_id, self._model_item(updated)):
            self._sync_model()
        return updated

    def _emit_changed(self) -> None:
        publish_snapshot = (
            self._busy,
            self._status,
            self.default_caption,
            self.default_hashtags,
            self.count,
            self.posted_count,
            self.project_source_selected_count,
            self._consent_confirmed,
        )
        account_snapshot = (
            self._account_syncing,
            self.api_key_configured,
            self.api_key_verified,
            self.connected_account_count,
            self.profile_count,
            self.connection_profile_name,
            self._oauth_sync_pending,
            self.account_ready,
            self.can_post_more,
            tuple(self.account_names),
            tuple(self.account_platforms),
            self.selected_platform,
            self.selected_platform_label,
            self.selected_account_index,
            self.selected_account_name,
        )
        option_snapshot = (
            tuple(self._privacy_levels),
            self.privacy_level,
            self.publish_now,
            self.allow_comment,
            self.allow_duet,
            self.allow_stitch,
            self.share_to_feed,
            self.ai_generated,
            self.first_comment,
            self.comment_available,
            self.duet_available,
            self.stitch_available,
        )

        if publish_snapshot != self._publish_signal_snapshot:
            self._publish_signal_snapshot = publish_snapshot
            signal = getattr(self._host, "socialPublishStateChanged", None)
            if signal is not None:
                signal.emit()
        if account_snapshot != self._account_signal_snapshot:
            self._account_signal_snapshot = account_snapshot
            signal = getattr(self._host, "zernioAccountsChanged", None)
            if signal is not None:
                signal.emit()
        if option_snapshot != self._option_signal_snapshot:
            self._option_signal_snapshot = option_snapshot
            signal = getattr(self._host, "zernioPostOptionsChanged", None)
            if signal is not None:
                signal.emit()

        self._host.tiktokPublishChanged.emit()

    def save_api_key(self, value: str) -> bool:
        if self._busy or self._account_syncing or self._creator_syncing:
            return False
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
        self._api_key_cache = key
        self._accounts = []
        self._profiles = []
        self._profile_id = ""
        self._profile_name = ""
        self._api_key_verified = False
        self._privacy_levels = []
        self._interaction_settings = {"comment": False, "duet": False, "stitch": False}
        self._creator_info_loaded = False
        self._can_post_more = True
        self._creator_cache.clear()
        self._stop_oauth_sync()
        self._stop_post_status_poll()
        self._status = "Zernio API key saved. Verifying the connection..."
        self._emit_changed()
        return self.refresh_accounts()

    def clear_api_key(self) -> bool:
        if self._busy or self._account_syncing or self._creator_syncing:
            return False
        try:
            secure_credentials.delete_secret(ZERNIO_CREDENTIAL_TARGET)
        except OSError as exc:
            self._status = f"Could not remove the Zernio API key: {exc}"
            self._emit_changed()
            return False
        self._api_key_cache = ""
        self._accounts = []
        self._profiles = []
        self._privacy_levels = []
        self._interaction_settings = {"comment": False, "duet": False, "stitch": False}
        self._creator_info_loaded = False
        self._can_post_more = True
        self._creator_cache.clear()
        self._profile_id = ""
        self._profile_name = ""
        self._api_key_verified = False
        self._stop_oauth_sync()
        self._stop_post_status_poll()
        if self._project_root and os.path.isdir(self._project_root):
            self._state = tiktok_publish.update_publish_settings(
                self._project_root,
                selected_account_id="",
                privacy_level="",
            )
        self._status = "Zernio API key removed."
        self._emit_changed()
        return True

    def connect_tiktok(self) -> bool:
        return self.connect_platform("tiktok")

    def connect_platform(self, platform: str) -> bool:
        name = str(platform or "").strip().casefold()
        if name not in SUPPORTED_PLATFORMS:
            self._status = "Choose a supported publishing platform."
            self._emit_changed()
            return False
        return self._start_account_worker("connect", name)

    def _open_zernio_page(self, url: str, success: str, failure: str) -> bool:
        opened = open_external_url(url)
        self._status = (
            success
            if opened else failure
        )
        self._emit_changed()
        return opened

    def open_zernio_sign_up(self) -> bool:
        return self._open_zernio_page(
            ZERNIO_SIGN_UP_URL,
            "Zernio account registration opened in your browser.",
            "Could not open Zernio registration. Copy https://zernio.com/signup into your browser.",
        )

    def open_zernio_sign_in(self) -> bool:
        return self._open_zernio_page(
            ZERNIO_SIGN_IN_URL,
            "Zernio sign-in opened in your browser.",
            "Could not open Zernio sign-in. Copy https://zernio.com/signin into your browser.",
        )

    def open_zernio_api_keys(self) -> bool:
        return self._open_zernio_page(
            ZERNIO_API_KEYS_URL,
            "Zernio API keys opened in your browser.",
            "Could not open Zernio API keys. Copy https://zernio.com/dashboard/api-keys into your browser.",
        )

    def open_zernio_posting_docs(self) -> bool:
        return self._open_zernio_page(
            ZERNIO_POSTING_DOCS_URL,
            "Zernio social posting documentation opened in your browser.",
            "Could not open the Zernio Posting API documentation.",
        )

    def open_zernio_dashboard(self) -> bool:
        """Backward-compatible alias for older QML caches."""
        return self.open_zernio_api_keys()

    def refresh_accounts(self) -> bool:
        return self._start_account_worker("refresh")

    def reconcile_accounts(self) -> bool:
        """Refresh connected accounts without blocking or repainting the page."""
        return self._start_account_worker("refresh", silent=True)

    def disconnect_account(self, index: int) -> bool:
        if index < 0 or index >= len(self._accounts):
            return False
        account_id = self._object_id(self._accounts[index])
        if not account_id:
            return False
        return self._start_account_worker("disconnect", account_id=account_id)

    def _start_account_worker(
        self,
        action: str,
        platform: str = "",
        account_id: str = "",
        silent: bool = False,
    ) -> bool:
        if self._busy:
            return False
        if silent and (self._background_account_refreshing or self._account_syncing):
            return False
        if not silent and self._account_syncing:
            return False
        key = self._api_key()
        if not key:
            if not silent:
                self._status = "Add a Zernio API key first."
                self._emit_changed()
            return False
        if silent:
            self._background_account_refreshing = True
            generation = self._account_generation
        else:
            self._account_generation += 1
            generation = self._account_generation
            self._account_syncing = True
        platform_name = str(platform or "").strip().casefold()
        if silent:
            pass
        elif action == "connect":
            self._status = f"Connecting {PLATFORM_LABELS.get(platform_name, platform_name.title())} through Zernio"
        elif action == "disconnect":
            self._status = "Disconnecting the social account"
        else:
            self._status = "Syncing social connections"
        self._account_refresh_next = time.monotonic() + _ACCOUNT_BACKGROUND_REFRESH_SECONDS
        if not silent:
            self._emit_changed()
        worker = threading.Thread(
            target=self._account_worker,
            args=(
                action,
                key,
                self._project_key,
                platform_name,
                len(self._accounts),
                generation,
                bool(silent),
                str(self._profile_id or "").strip(),
                str(self._profile_name or "").strip(),
                list(self._profiles),
                str(account_id or "").strip(),
            ),
            name=f"haizflow-zernio-{action}",
            daemon=True,
        )
        if silent:
            self._background_account_worker_thread = worker
        else:
            self._account_worker_thread = worker
        worker.start()
        return True

    def _account_worker(
        self,
        action: str,
        key: str,
        project_key: str,
        platform: str = "",
        connected_account_count: int = 0,
        generation: int = 0,
        silent: bool = False,
        cached_profile_id: str = "",
        cached_profile_name: str = "",
        cached_profiles: list[dict] | None = None,
        account_id: str = "",
    ) -> None:
        api_key_verified = False
        try:
            client = zernio.ZernioClient(key)
            if action == "connect":
                # A verified profile is stable across account disconnects. Use
                # it directly so opening OAuth needs one request instead of a
                # profile-list round trip followed by the authorization call.
                # If it was deleted on Zernio, refresh once and retry below.
                profiles = list(cached_profiles or [])
                profile_id = str(cached_profile_id or "")
                profile_name = str(cached_profile_name or "Zernio profile")
                if profile_id:
                    try:
                        auth_url = client.get_connect_url(profile_id, platform)
                        api_key_verified = True
                    except zernio.ZernioError as exc:
                        normalized_error = str(exc).casefold()
                        stale_profile = (
                            "http 404" in normalized_error
                            or (
                                "profile" in normalized_error
                                and any(marker in normalized_error for marker in ("not found", "missing", "invalid"))
                            )
                        )
                        if not stale_profile:
                            raise
                        profile_id = ""
                if not profile_id:
                    profiles = client.list_profiles()
                    api_key_verified = True
                    profile = self._connection_profile(profiles)
                    if not profile:
                        profile = client.create_profile("HaizFlow", "Social publishing from HaizFlow")
                        profiles = [profile]
                    profile_id = self._object_id(profile)
                    if not profile_id:
                        raise zernio.ZernioError("Zernio did not return a profile ID.")
                    profile_name = str(profile.get("name") or "Zernio profile")
                    auth_url = client.get_connect_url(profile_id, platform)
                if not auth_url:
                    raise zernio.ZernioError("Zernio did not return an authorization URL.")
                self._events.put({
                    "type": "oauth",
                    "project_key": project_key,
                    "profile_id": profile_id,
                    "profile_name": profile_name,
                    "profiles": profiles,
                    "url": auth_url,
                    "platform": platform,
                    "generation": int(generation),
                    "silent": bool(silent),
                })
                return
            profiles = client.list_profiles()
            api_key_verified = True
            profile = self._connection_profile(profiles)
            if not profile:
                profile = client.create_profile("HaizFlow", "Social publishing from HaizFlow")
                profiles = [profile]
            profile_id = self._object_id(profile)
            if not profile_id:
                raise zernio.ZernioError("Zernio did not return a profile ID.")
            profile_name = str(profile.get("name") or "Zernio profile")
            if action == "disconnect":
                client.disconnect_account(account_id)
            # Accounts connected in the Zernio dashboard may belong to any
            # profile visible to this API key.  Restricting this request to the
            # profile used for new HaizFlow OAuth connections made those valid
            # accounts disappear from the desktop UI.
            accounts = client.list_accounts(platforms=SUPPORTED_PLATFORMS)
            self._events.put({
                "type": "accounts",
                "project_key": project_key,
                "profile_id": profile_id,
                "profile_name": profile_name,
                "profiles": profiles,
                "accounts": accounts,
                "generation": int(generation),
                "silent": bool(silent),
                "message": (
                    "Social account disconnected."
                    if action == "disconnect" else ""
                ),
            })
        except (OSError, ValueError, zernio.ZernioError) as exc:
            message = str(exc)
            if action == "connect":
                message = self._connection_error_message(message, connected_account_count)
            self._events.put({
                "type": "error",
                "project_key": project_key,
                "message": message,
                "api_key_verified": api_key_verified,
                "generation": int(generation),
                "silent": bool(silent),
            })

    @staticmethod
    def _connection_error_message(message: str, connected_account_count: int) -> str:
        normalized = str(message or "").casefold()
        if (
            connected_account_count >= _ZERNIO_FREE_CONNECTED_ACCOUNTS
            and any(marker in normalized for marker in _ZERNIO_BILLING_ERROR_MARKERS)
        ):
            return (
                "Zernio includes the first 2 connected accounts for free. "
                "Connecting another account may require billing in Zernio. "
                f"Zernio response: {message}"
            )
        return message

    def select_account(self, index: int) -> bool:
        if index < 0 or index >= len(self._accounts) or not self._ensure_publish_project():
            return False
        account_id = self._object_id(self._accounts[index])
        if not account_id:
            return False
        platform = self._account_platform(self._accounts[index])
        previous_account_id = str(self._state.get("selected_account_id") or "")
        previous_platform = self.selected_platform
        if (
            account_id == previous_account_id
            and platform == previous_platform
            and self._creator_info_loaded
        ):
            return True
        self._state = tiktok_publish.update_publish_settings(
            self._project_root,
            selected_account_id=account_id,
            selected_platform=platform,
        )
        if platform != previous_platform:
            self._sync_model()
        if platform == "tiktok":
            cached = self._cached_creator_info(account_id)
            if cached is not None:
                self._invalidate_creator_sync()
                self._apply_creator_info(cached)
                self._status = "TikTok account is ready for publishing."
                self._emit_changed()
                return True
            return self._start_creator_info_worker(account_id)
        self._configure_non_tiktok_account(platform)
        self._status = f"{PLATFORM_LABELS.get(platform, platform.title())} connection is ready."
        self._emit_changed()
        return True

    def _cached_creator_info(self, account_id: str) -> dict | None:
        cached = self._creator_cache.get(str(account_id or ""))
        if cached is None:
            return None
        cached_at, payload = cached
        if time.monotonic() - cached_at > _CREATOR_INFO_CACHE_SECONDS:
            self._creator_cache.pop(str(account_id or ""), None)
            return None
        return dict(payload)

    def _apply_creator_info(self, payload: dict) -> None:
        self._privacy_levels = list(payload.get("levels") or [])
        interactions = payload.get("interactions") or {}
        self._interaction_settings = {
            "comment": bool(interactions.get("comment", False)),
            "duet": bool(interactions.get("duet", False)),
            "stitch": bool(interactions.get("stitch", False)),
        }
        self._creator_info_loaded = True
        self._can_post_more = bool(payload.get("can_post_more", True))
        selected = str(self._state.get("privacy_level") or "")
        if self._privacy_levels and selected not in self._privacy_levels:
            selected = (
                "PUBLIC_TO_EVERYONE"
                if "PUBLIC_TO_EVERYONE" in self._privacy_levels
                else self._privacy_levels[0]
            )
        changes = {
            "privacy_level": selected,
            "allow_comment": bool(self.allow_comment and self.comment_available),
            "allow_duet": bool(self.allow_duet and self.duet_available),
            "allow_stitch": bool(self.allow_stitch and self.stitch_available),
        }
        if any(self._state.get(key) != value for key, value in changes.items()):
            self._state = tiktok_publish.update_publish_settings(
                self._project_root,
                **changes,
            )

    def _invalidate_creator_sync(self) -> None:
        """Invalidate a creator-info response that belongs to an old selection."""
        self._creator_generation += 1
        self._creator_syncing = False
        self._creator_worker_thread = None

    def _configure_non_tiktok_account(self, platform: str) -> None:
        self._invalidate_creator_sync()
        self._creator_info_loaded = True
        self._can_post_more = True
        self._interaction_settings = {"comment": False, "duet": False, "stitch": False}
        self._privacy_levels = ["public", "unlisted", "private"] if platform == "youtube" else ["public"]
        selected = str(self._state.get("privacy_level") or "")
        if selected not in self._privacy_levels:
            selected = self._privacy_levels[0]
            self._state = tiktok_publish.update_publish_settings(
                self._project_root,
                privacy_level=selected,
            )

    def _start_creator_info_worker(self, account_id: str) -> bool:
        if self._busy:
            return False
        key = self._api_key()
        if not key:
            return False
        self._creator_generation += 1
        generation = self._creator_generation
        self._creator_syncing = True
        self._privacy_levels = []
        self._interaction_settings = {"comment": False, "duet": False, "stitch": False}
        self._creator_info_loaded = False
        self._can_post_more = True
        self._status = "Loading TikTok publishing options"
        self._emit_changed()
        self._creator_worker_thread = threading.Thread(
            target=self._creator_info_worker,
            args=(key, account_id, self._project_key, generation),
            name="haizflow-zernio-creator-info",
            daemon=True,
        )
        self._creator_worker_thread.start()
        return True

    def _creator_info_worker(
        self,
        key: str,
        account_id: str,
        project_key: str,
        generation: int,
    ) -> None:
        try:
            info = zernio.ZernioClient(key).get_tiktok_creator_info(account_id)
            levels = info.get("privacyLevels") or info.get("privacy_levels") or []
            if not isinstance(levels, list):
                levels = []
            interactions = info.get("interactionSettings") or {}
            self._events.put({
                "type": "creator",
                "project_key": project_key,
                "account_id": account_id,
                "generation": generation,
                "levels": [str(value) for value in levels if str(value)],
                "interactions": interactions if isinstance(interactions, dict) else {},
                "can_post_more": bool(info.get("canPostMore", True)),
            })
        except (OSError, ValueError, zernio.ZernioError) as exc:
            self._events.put({
                "type": "creator_error",
                "project_key": project_key,
                "account_id": account_id,
                "generation": generation,
                "message": str(exc),
            })

    def set_publish_settings(
        self,
        privacy_level: str,
        publish_now: bool,
        allow_comment: bool,
        allow_duet: bool,
        allow_stitch: bool,
        share_to_feed: bool = True,
        ai_generated: bool = False,
        first_comment: str = "",
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
            allow_comment=bool(
                allow_comment and (self.comment_available if self._creator_info_loaded else True)
            ),
            allow_duet=bool(
                allow_duet and (self.duet_available if self._creator_info_loaded else True)
            ),
            allow_stitch=bool(
                allow_stitch and (self.stitch_available if self._creator_info_loaded else True)
            ),
            share_to_feed=bool(share_to_feed),
            ai_generated=bool(ai_generated),
            first_comment=first_comment,
        )
        self._emit_changed()
        return True

    def browse_videos(self) -> None:
        if not self._ensure_publish_project():
            return
        paths, _ = QFileDialog.getOpenFileNames(
            None,
            "Choose videos to publish",
            native_media_dialog_directory(),
            "Social video files (*.mp4 *.mov *.webm);;All files (*.*)",
        )
        if paths:
            self.add_videos(paths)

    def browse_folder(self) -> None:
        if not self._ensure_publish_project():
            return
        folder = QFileDialog.getExistingDirectory(
            None,
            "Choose a folder of videos to publish",
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
            QMessageBox.warning(None, "Social publishing", "This folder contains no supported videos.")
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
        duplicate_count = 0
        seen = {
            os.path.normcase(os.path.abspath(str(item.get("source_path") or "")))
            for item in self._state.get("items") or []
            if item.get("source_path")
        }
        for value in paths:
            path = normalize_video_path(value)
            path_key = os.path.normcase(os.path.abspath(path))
            if path_key in seen:
                duplicate_count += 1
                continue
            seen.add(path_key)
            if self._supported_file(path):
                valid.append((path, str((display_names or {}).get(path) or Path(path).name)))
        if not valid:
            if duplicate_count:
                self._status = "The selected videos are already in this publishing queue."
                self._emit_changed()
                return False
            QMessageBox.warning(None, "Social publishing", "Choose an MP4, MOV, or WebM video smaller than 4 GB.")
            return False
        self._busy = True
        self._cancel.clear()
        self._status = "Adding videos to the publishing project"
        self._emit_changed()
        self._worker = threading.Thread(
            target=self._import_worker,
            args=(self._project_key, self._project_root, valid, self.default_caption, self.default_hashtags, self.count),
            name="haizflow-social-import",
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
                    raise ValueError("Videos must be between 3 seconds and 10 minutes long.")
                width, height = get_video_dimensions(destination, timeout_seconds=20.0)
                create_video_thumbnail_path(destination, thumbnail_path, cancel_event=self._cancel)
                item = tiktok_publish.new_item(
                    destination, thumbnail_path if os.path.isfile(thumbnail_path) else "",
                    starting_order + offset, caption, hashtags,
                )
                item["id"] = item_id
                item["file_name"] = display_name
                item["source_path"] = os.path.abspath(source)
                item["duration_seconds"] = round(float(duration), 3)
                item["video_width"] = int(width)
                item["video_height"] = int(height)
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
        self._consent_confirmed = False
        self._sync_model()
        self._emit_changed()
        self._host.refreshVideos()
        return True

    def update_item(self, row: int, caption: str, hashtags: str) -> bool:
        item = self._host.tiktok_publish_items.item_at(row)
        if (
            not item
            or not self._ensure_publish_project()
            or item["status"] in {"uploading", "publishing", "published", "posted", "scheduled"}
        ):
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
            "platform": self.selected_platform,
            "privacy_level": self._state["privacy_level"],
            "publish_now": self.publish_now,
            "allow_comment": self.allow_comment,
            "allow_duet": self.allow_duet,
            "allow_stitch": self.allow_stitch,
            "share_to_feed": self.share_to_feed,
            "ai_generated": self.ai_generated,
            "first_comment": self.first_comment,
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
        if self._account_syncing or self._creator_syncing:
            self._status = "Wait for the selected platform to finish loading."
        elif not self._api_key():
            self._status = "Add a Zernio API key first."
        elif not self._state.get("selected_account_id"):
            self._status = "Connect and select a social account first."
        elif not self._state.get("privacy_level"):
            self._status = "Choose a visibility option for the selected connection."
        elif not self._can_post_more:
            self._status = "The selected account has reached its current posting limit."
        elif not self._consent_confirmed:
            self._status = "Review the queued posts and confirm consent before uploading."
        elif not os.path.isfile(item.get("file_path") or ""):
            self._status = "The selected video file is unavailable."
        elif error := self._platform_video_error(item):
            self._status = error
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
            content = tiktok_publish.compose_post_text(item["caption"], item["hashtags"])
            title = next((line.strip() for line in content.splitlines() if line.strip()), Path(item["file_path"]).stem)
            result = client.create_video_post(
                platform=settings["platform"],
                account_id=settings["account_id"],
                content=content,
                media_url=public_url,
                privacy_level=settings["privacy_level"],
                publish_now=settings["publish_now"],
                request_id=item["request_id"],
                title=title,
                allow_comment=settings["allow_comment"],
                allow_duet=settings["allow_duet"],
                allow_stitch=settings["allow_stitch"],
                share_to_feed=settings["share_to_feed"],
                ai_generated=settings["ai_generated"],
                first_comment=settings["first_comment"],
            )
            post = result.get("post") if isinstance(result.get("post"), dict) else result.get("existingPost")
            if not isinstance(post, dict):
                post = result
            post_id = self._object_id(post)
            post_result = zernio.post_result(post, settings["platform"])
            status = post_result["status"] or ("publishing" if settings["publish_now"] else "draft")
            # The create response may briefly expose an internal/legacy status
            # even though Zernio already accepted this logical post. Do not
            # make the card publishable again while that remote post exists.
            if (
                settings["publish_now"]
                and post_id
                and status not in _SUCCESS_POST_STATUSES
                and status not in _FAILED_POST_STATUSES
            ):
                status = "publishing"
            self._events.put({
                "type": "publish_finished", "project_key": project_key, "item_id": item["id"],
                "post_id": post_id, "status": status, "url": post_result["url"],
                "error": post_result["error"], "platform": settings["platform"],
            })
        except zernio.ZernioCancelled as exc:
            self._events.put({"type": "publish_finished", "project_key": project_key, "item_id": item["id"], "status": "ready", "error": str(exc)})
        except (OSError, ValueError, zernio.ZernioError) as exc:
            self._events.put({"type": "publish_finished", "project_key": project_key, "item_id": item["id"], "status": "failed", "error": str(exc)})

    def refresh_post_statuses(self) -> bool:
        return self._start_status_worker(only_pending=False)

    def _start_status_worker(self, *, only_pending: bool) -> bool:
        posts = [
            (item["id"], item.get("zernio_post_id") or "", item.get("target_platform") or "tiktok")
            for item in self._state.get("items") or []
        ]
        if only_pending:
            posts = [
                (item["id"], item.get("zernio_post_id") or "", item.get("target_platform") or "tiktok")
                for item in self._state.get("items") or []
                if self._item_needs_status_poll(item)
            ]
        posts = [(item_id, post_id, platform) for item_id, post_id, platform in posts if post_id]
        if self._post_status_refreshing or not posts or not self._api_key():
            return False
        self._post_status_refreshing = True
        if not only_pending:
            self._status = "Refreshing post statuses"
            self._emit_changed()
        worker = threading.Thread(
            target=self._status_worker,
            args=(self._api_key(), self._project_key, posts),
            name="haizflow-zernio-status",
            daemon=True,
        )
        worker.start()
        return True

    def _status_worker(self, key: str, project_key: str, posts: list[tuple[str, str, str]]) -> None:
        updates = []
        try:
            client = zernio.ZernioClient(key)
            for item_id, post_id, platform in posts:
                post = client.get_post(post_id)
                result = zernio.post_result(post, platform)
                updates.append({
                    "item_id": item_id,
                    "status": result["status"],
                    "url": result["url"],
                    "error": result["error"],
                })
            self._events.put({"type": "statuses", "project_key": project_key, "updates": updates})
        except (OSError, ValueError, zernio.ZernioError) as exc:
            self._events.put({"type": "status_error", "project_key": project_key, "message": str(exc)})

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
            event_changed = True
            if kind == "oauth":
                generation = int(event.get("generation") or 0)
                if generation != self._account_generation:
                    continue
                self._account_syncing = False
                self._account_worker_thread = None
                self._api_key_verified = True
                self._profile_id = str(event.get("profile_id") or "")
                self._profile_name = str(event.get("profile_name") or "")
                self._profiles = list(event.get("profiles") or [])
                opened = open_external_url(str(event.get("url") or ""))
                if opened:
                    self._start_oauth_sync()
                    platform = str(event.get("platform") or "")
                    self._status = f"Finish connecting {PLATFORM_LABELS.get(platform, platform.title())} in the browser."
                else:
                    self._stop_oauth_sync()
                    self._status = "Could not open the Zernio authorization page."
            elif kind == "accounts":
                silent = bool(event.get("silent"))
                generation = int(event.get("generation") or 0)
                if silent:
                    self._background_account_refreshing = False
                    self._background_account_worker_thread = None
                else:
                    self._account_syncing = False
                    self._account_worker_thread = None
                if generation != self._account_generation:
                    continue
                self._api_key_verified = True
                self._profile_id = str(event.get("profile_id") or "")
                self._profile_name = str(event.get("profile_name") or "")
                self._profiles = list(event.get("profiles") or [])
                previous_accounts = self._accounts
                self._accounts = self._deduplicate_accounts(event.get("accounts") or [])
                available_account_ids = {
                    self._object_id(account)
                    for account in self._accounts
                    if self._object_id(account)
                }
                self._creator_cache = {
                    account_id: cached
                    for account_id, cached in self._creator_cache.items()
                    if account_id in available_account_ids
                }
                accounts_changed = (
                    self._account_visible_signature(previous_accounts)
                    != self._account_visible_signature(self._accounts)
                )
                current_account_ids = {
                    self._object_id(account) for account in self._accounts if self._object_id(account)
                }
                if self._oauth_sync_pending and (
                    current_account_ids - self._oauth_account_ids_before
                ):
                    self._stop_oauth_sync()
                selected_id = str(self._state.get("selected_account_id") or "")
                selected_changed = False
                platform_changed = False
                if self._accounts and not any(self._object_id(item) == selected_id for item in self._accounts):
                    selected_id = self._object_id(self._accounts[0])
                    selected_changed = True
                    platform = self._account_platform(self._accounts[0])
                    platform_changed = self._state.get("selected_platform") != platform
                    self._state = tiktok_publish.update_publish_settings(
                        self._project_root,
                        selected_account_id=selected_id,
                        selected_platform=platform,
                    )
                elif not self._accounts and selected_id:
                    selected_id = ""
                    selected_changed = True
                    self._privacy_levels = []
                    self._interaction_settings = {"comment": False, "duet": False, "stitch": False}
                    self._creator_info_loaded = False
                    self._can_post_more = True
                    self._invalidate_creator_sync()
                    self._state = tiktok_publish.update_publish_settings(
                        self._project_root,
                        selected_account_id="",
                        selected_platform="",
                        privacy_level="",
                    )
                elif selected_id:
                    selected_account = next(
                        (item for item in self._accounts if self._object_id(item) == selected_id),
                        {},
                    )
                    platform = self._account_platform(selected_account)
                    if self._state.get("selected_platform") != platform:
                        platform_changed = True
                        self._state = tiktok_publish.update_publish_settings(
                            self._project_root,
                            selected_platform=platform,
                        )
                # Ready queue cards derive their target badge from the active
                # publishing platform. Keep them in sync when account refresh
                # auto-selects a newly connected account.
                if accounts_changed or selected_changed or platform_changed:
                    self._sync_model()
                if not silent or event.get("message"):
                    self._status = str(event.get("message") or "") or (
                        f"{len(self._accounts)} publishing account(s) available."
                        if self._accounts else
                        "No supported publishing account is available."
                    )
                if selected_id:
                    selected_index = self.selected_account_index
                    platform = self._account_platform(self._accounts[selected_index]) if selected_index >= 0 else "tiktok"
                    if platform == "tiktok" and (
                        selected_changed
                        or (not self._creator_info_loaded and not self._creator_syncing)
                    ):
                        cached = self._cached_creator_info(selected_id)
                        if cached is not None:
                            self._invalidate_creator_sync()
                            self._apply_creator_info(cached)
                        else:
                            self._start_creator_info_worker(selected_id)
                    elif platform != "tiktok" and (
                        selected_changed or not self._creator_info_loaded
                    ):
                        self._configure_non_tiktok_account(platform)
                event_changed = (
                    not silent or accounts_changed or selected_changed or platform_changed
                )
            elif kind == "creator":
                generation = int(event.get("generation") or 0)
                account_id = str(event.get("account_id") or "")
                if (
                    generation != self._creator_generation
                    or account_id != str(self._state.get("selected_account_id") or "")
                ):
                    continue
                self._creator_syncing = False
                self._creator_worker_thread = None
                creator_payload = {
                    "levels": list(event.get("levels") or []),
                    "interactions": dict(event.get("interactions") or {}),
                    "can_post_more": bool(event.get("can_post_more", True)),
                }
                self._creator_cache[account_id] = (time.monotonic(), creator_payload)
                self._apply_creator_info(creator_payload)
                self._status = (
                    "TikTok account is ready for publishing."
                    if self._can_post_more else "TikTok reports that this account has reached its posting limit."
                )
            elif kind == "creator_error":
                generation = int(event.get("generation") or 0)
                account_id = str(event.get("account_id") or "")
                if (
                    generation != self._creator_generation
                    or account_id != str(self._state.get("selected_account_id") or "")
                ):
                    continue
                self._creator_syncing = False
                self._creator_worker_thread = None
                self._creator_info_loaded = False
                self._status = str(
                    event.get("message") or "Could not load TikTok publishing options."
                )
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
                self._update_item_state(event["item_id"], upload_progress=event["progress"])
                self._status = f"Uploading video: {event['progress']}%"
            elif kind == "publishing":
                self._update_item_state(event["item_id"], status="publishing", upload_progress=100)
                self._status = "Video uploaded; creating the social post"
            elif kind == "publish_finished":
                self._busy = False
                self._worker = None
                status = str(event.get("status") or "failed")
                self._update_item_state(
                    event["item_id"], status=status,
                    error=str(event.get("error") or ""), zernio_post_id=str(event.get("post_id") or ""),
                    platform_post_url=str(event.get("url") or ""),
                    platform_post_url_verified=bool(event.get("url")),
                    target_platform=str(event.get("platform") or self.selected_platform),
                    upload_progress=100 if status != "ready" else 0,
                )
                if status in _SUCCESS_POST_STATUSES:
                    self._status = f"{PLATFORM_LABELS.get(str(event.get('platform') or ''), 'The platform')} published the video successfully."
                else:
                    self._status = str(event.get("error") or ("Post sent to Zernio." if status != "draft" else "Draft created in Zernio."))
                if event.get("post_id") and (
                    status in _POLLABLE_POST_STATUSES
                    or (status in _SUCCESS_POST_STATUSES and not event.get("url"))
                ):
                    self._schedule_post_status_poll(immediate=True)
                refresh_projects = True
                continue_queue = self._auto_continue and status not in {"ready"}
                if status == "failed":
                    self._auto_continue = False
            elif kind == "statuses":
                self._post_status_refreshing = False
                status_changed = False
                previous_status_text = self._status
                for update in event.get("updates") or []:
                    current = next(
                        (
                            item
                            for item in self._state.get("items") or []
                            if item.get("id") == update["item_id"]
                        ),
                        {},
                    )
                    changes = {
                        "status": update["status"],
                        "error": update.get("error") or "",
                        "platform_post_url": update.get("url") or "",
                        "platform_post_url_verified": bool(update.get("url")),
                    }
                    if any(current.get(key) != value for key, value in changes.items()):
                        status_changed = True
                    self._update_item_state(
                        update["item_id"], **changes,
                    )
                pending = self._pending_post_ids()
                if pending:
                    self._schedule_post_status_poll()
                    waiting_for_link = any(
                        str(item.get("status") or "").casefold() in _SUCCESS_POST_STATUSES
                        and not bool(item.get("platform_post_url_verified"))
                        for item in self._state.get("items") or []
                    )
                    self._status = (
                        "The platform published the video; waiting for its public link."
                        if waiting_for_link else
                        f"Waiting for the platforms to finish {len(pending)} post(s)."
                    )
                else:
                    self._stop_post_status_poll()
                    self._status = "Social post statuses are up to date."
                refresh_projects = refresh_projects or status_changed
                event_changed = status_changed or self._status != previous_status_text
            elif kind == "status_error":
                self._post_status_refreshing = False
                self._stop_post_status_poll()
                self._status = str(event.get("message") or "Could not refresh Zernio post statuses.")
            elif kind == "error":
                silent = bool(event.get("silent"))
                generation = int(event.get("generation") or 0)
                if silent:
                    self._background_account_refreshing = False
                    self._background_account_worker_thread = None
                else:
                    self._account_syncing = False
                    self._account_worker_thread = None
                if generation != self._account_generation:
                    continue
                if "api_key_verified" in event and not silent:
                    self._api_key_verified = bool(event.get("api_key_verified"))
                if not silent:
                    self._status = str(event.get("message") or "Zernio request failed.")
                event_changed = not silent
            changed = changed or event_changed
        if changed:
            self._emit_changed()
        if refresh_projects:
            project_store.touch_project_by_key(self._project_key)
            self._host.refreshVideos()
        if continue_queue and not self._busy:
            self.publish_next(continue_queue=True)
        self._poll_oauth_accounts()
        self._poll_connected_accounts()
        self._poll_post_statuses()

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
        if not item:
            return False
        platform = str(item.get("target_platform") or self.selected_platform or "tiktok")
        raw_url = str(item.get("platform_post_url") or "")
        url = (
            zernio.public_post_url(raw_url, platform)
            if item.get("platform_post_url_verified") else ""
        )
        if url:
            return bool(open_external_url(url))
        if raw_url:
            self._update_item_state(
                item["id"], platform_post_url="", platform_post_url_verified=False
            )
        if item.get("zernio_post_id") and self._api_key():
            self._status = "The post is published; retrieving its public link."
            self._emit_changed()
            self._schedule_post_status_poll(immediate=True)
            self._start_status_worker(only_pending=False)
        return False

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
        self._stop_post_status_poll()

    def _api_key(self) -> str:
        environment_key = str(os.environ.get("ZERNIO_API_KEY") or "").strip()
        if environment_key:
            return environment_key
        if self._api_key_cache is not None:
            return self._api_key_cache
        try:
            self._api_key_cache = secure_credentials.read_secret(ZERNIO_CREDENTIAL_TARGET)
        except OSError:
            self._api_key_cache = ""
        return self._api_key_cache

    def _stop_oauth_sync(self) -> None:
        self._oauth_sync_pending = False
        self._oauth_account_ids_before.clear()
        self._oauth_sync_deadline = 0.0
        self._oauth_sync_next = 0.0

    def _start_oauth_sync(self) -> None:
        now = time.monotonic()
        self._oauth_sync_pending = True
        self._oauth_account_ids_before = {
            self._object_id(account) for account in self._accounts if self._object_id(account)
        }
        self._oauth_sync_deadline = now + _OAUTH_ACCOUNT_POLL_TIMEOUT_SECONDS
        self._oauth_sync_next = now + _OAUTH_ACCOUNT_POLL_SECONDS

    def _poll_oauth_accounts(self) -> None:
        if (
            not self._oauth_sync_pending
            or self._busy
            or self._account_syncing
            or not self._project_key
        ):
            return
        now = time.monotonic()
        if now >= self._oauth_sync_deadline:
            self._stop_oauth_sync()
            self._status = "Connection finished. Open the platform picker to refresh accounts."
            self._emit_changed()
            return
        if now >= self._oauth_sync_next:
            self._oauth_sync_next = now + _OAUTH_ACCOUNT_POLL_SECONDS
            self._start_account_worker("refresh", silent=True)

    def _poll_connected_accounts(self) -> None:
        """Quietly reconcile connections changed in the Zernio dashboard."""
        if (
            self._oauth_sync_pending
            or self._busy
            or self._account_syncing
            or self._background_account_refreshing
            or not self._project_key
            or not self.api_key_configured
        ):
            return
        now = time.monotonic()
        if now < self._account_refresh_next:
            return
        self._account_refresh_next = now + _ACCOUNT_BACKGROUND_REFRESH_SECONDS
        self._start_account_worker("refresh", silent=True)

    def _pending_post_ids(self) -> list[str]:
        return [
            str(item.get("zernio_post_id") or "")
            for item in self._state.get("items") or []
            if item.get("zernio_post_id")
            and self._item_needs_status_poll(item)
        ]

    @staticmethod
    def _item_needs_status_poll(item: dict) -> bool:
        status = str(item.get("status") or "").casefold()
        platform = str(item.get("target_platform") or "tiktok")
        has_public_url = bool(item.get("platform_post_url_verified")) and bool(
            zernio.public_post_url(item.get("platform_post_url"), platform)
        )
        if status in _SUCCESS_POST_STATUSES:
            return not has_public_url
        if status in _FAILED_POST_STATUSES or status == "draft":
            return False
        # Any other state attached to an existing remote post is transitional,
        # including new statuses introduced by Zernio after this app release.
        return bool(item.get("zernio_post_id"))

    def _schedule_post_status_poll(self, *, immediate: bool = False) -> None:
        now = time.monotonic()
        if self._post_status_poll_deadline <= now:
            self._post_status_poll_deadline = now + _POST_STATUS_POLL_TIMEOUT_SECONDS
        self._post_status_poll_next = now if immediate else now + _POST_STATUS_POLL_SECONDS

    def _poll_post_statuses(self) -> None:
        if (
            not self._post_status_poll_next
            or self._busy
            or self._post_status_refreshing
            or not self._project_key
        ):
            return
        now = time.monotonic()
        if now >= self._post_status_poll_deadline:
            self._stop_post_status_poll()
            self._status = "The platform is still processing the post. Use Refresh status later."
            self._emit_changed()
            return
        if now >= self._post_status_poll_next:
            self._post_status_poll_next = now + _POST_STATUS_POLL_SECONDS
            if not self._start_status_worker(only_pending=True):
                self._stop_post_status_poll()

    def _stop_post_status_poll(self) -> None:
        self._post_status_poll_deadline = 0.0
        self._post_status_poll_next = 0.0
        self._post_status_refreshing = False

    def _connection_profile(self, profiles: list[dict]) -> dict:
        if not profiles:
            return {}
        if self._profile_id:
            selected = next(
                (profile for profile in profiles if self._object_id(profile) == self._profile_id),
                None,
            )
            if selected:
                return selected
        named = next(
            (profile for profile in profiles if str(profile.get("name") or "").casefold() == "haizflow"),
            None,
        )
        if named:
            return named
        default = next(
            (profile for profile in profiles if bool(profile.get("isDefault") or profile.get("is_default"))),
            None,
        )
        return default or profiles[0]

    @classmethod
    def _deduplicate_accounts(cls, accounts) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        for account in accounts:
            if not isinstance(account, dict):
                continue
            account_id = cls._object_id(account)
            if not account_id or account_id in seen:
                continue
            seen.add(account_id)
            result.append(account)
        platform_order = {platform: index for index, platform in enumerate(SUPPORTED_PLATFORMS)}
        result.sort(key=lambda account: (
            platform_order.get(cls._account_platform(account), len(platform_order)),
            cls._account_label(account).casefold(),
            cls._object_id(account),
        ))
        return result

    @classmethod
    def _account_visible_signature(cls, accounts: list[dict]) -> tuple[tuple[str, str, str], ...]:
        """Fields that can change the platform picker or active publishing target."""
        return tuple(
            (
                cls._object_id(account),
                cls._account_platform(account),
                cls._account_label(account),
            )
            for account in accounts
        )

    def _ensure_publish_project(self) -> bool:
        if self._host._project_type == "publish" and self._project_key and self._project_root:
            return True
        QMessageBox.information(None, "Social publishing", "Open a social publishing project first.")
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
        username = str(account.get("username") or "").strip()
        display_name = str(account.get("displayName") or account.get("name") or "").strip()
        identity = display_name
        if username and username.casefold().lstrip("@") != display_name.casefold().lstrip("@"):
            identity = f"{display_name} ({username})" if display_name else username
        if not identity and isinstance(account.get("metadata"), dict):
            identity = account["metadata"].get("username") or account["metadata"].get("displayName")
        profile = account.get("profileId") or account.get("profile")
        profile_name = str(profile.get("name") or "").strip() if isinstance(profile, dict) else ""
        platform = SocialPublishController._account_platform(account)
        label = str(identity or SocialPublishController._object_id(account) or "Social account")
        suffix = f" · {profile_name}" if profile_name else ""
        return f"{PLATFORM_LABELS.get(platform, platform.title())} — {label}{suffix}"

    @staticmethod
    def _account_platform(account: dict) -> str:
        value = str(account.get("platform") or "tiktok").strip().casefold() if isinstance(account, dict) else "tiktok"
        return value if value in SUPPORTED_PLATFORMS else "tiktok"

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

    def _platform_video_error(self, item: dict) -> str:
        """Validate the requirements that determine short-form post behavior."""
        platform = self.selected_platform
        suffix = Path(str(item.get("file_path") or "")).suffix.casefold()
        duration = float(item.get("duration_seconds") or 0.0)
        width = int(item.get("video_width") or 0)
        height = int(item.get("video_height") or 0)
        if platform in {"facebook", "instagram"} and suffix not in {".mp4", ".mov"}:
            return f"{PLATFORM_LABELS[platform]} requires an MP4 or MOV video."
        if platform == "youtube":
            if duration > 180.0:
                return "YouTube Shorts must be 3 minutes or shorter."
            if width > 0 and height > 0 and width >= height:
                return "YouTube Shorts requires a vertical video."
        elif platform == "facebook" and duration > 60.0:
            return "Facebook Reels must be 60 seconds or shorter."
        elif platform == "instagram" and duration > 90.0:
            return "Instagram Reels must be 90 seconds or shorter."
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
