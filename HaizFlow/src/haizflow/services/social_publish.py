"""Persistent Zernio social-publishing queues owned by HaizFlow projects."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from haizflow.services import zernio

STATE_FILE_NAME = ".haizflow-social-publish.json"
LEGACY_STATE_FILE_NAME = ".haizflow-tiktok-publish.json"
STATE_SCHEMA_VERSION = 5
MAX_POST_TEXT_UTF16 = 2200
_STATE_LOCK = threading.RLock()
_HASHTAG_SEPARATOR = re.compile(r"[\s,;]+", re.UNICODE)
_HASHTAG_CLEANUP = re.compile(r"[^\w]", re.UNICODE)
_CAPTION_HASHTAG = re.compile(r"(?<!\w)#([\w]+)", re.UNICODE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "default_caption": "",
        "default_hashtags": "",
        "selected_account_id": "",
        "selected_platform": "tiktok",
        "privacy_level": "",
        "allow_comment": True,
        "allow_duet": True,
        "allow_stitch": True,
        "publish_now": True,
        "share_to_feed": True,
        "ai_generated": False,
        "first_comment": "",
        "items": [],
    }


def empty_state() -> dict[str, Any]:
    """Return a fresh publishing state for controller initialization."""
    return _empty_state()


def state_path(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), STATE_FILE_NAME)


def backup_state_path(project_root: str) -> str:
    return f"{state_path(project_root)}.bak"


def legacy_state_path(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), LEGACY_STATE_FILE_NAME)


def legacy_backup_state_path(project_root: str) -> str:
    return f"{legacy_state_path(project_root)}.bak"


def media_directory(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), "publishing", "media")


def thumbnail_directory(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), "publishing", "thumbnails")


def utf16_length(value: str) -> int:
    return len(str(value or "").encode("utf-16-le")) // 2


def _truncate_utf16(value: str, limit: int) -> str:
    text = str(value or "")
    if limit <= 0:
        return ""
    while text and utf16_length(text) > limit:
        text = text[:-1]
    return text.rstrip()


def normalize_caption(value: str) -> str:
    lines = [" ".join(line.split()) for line in str(value or "").replace("\r", "").split("\n")]
    return _truncate_utf16("\n".join(line for line in lines if line), MAX_POST_TEXT_UTF16)


def normalize_hashtags(value: str) -> str:
    tags: list[str] = []
    seen: set[str] = set()
    for token in _HASHTAG_SEPARATOR.split(str(value or "").strip()):
        cleaned = _HASHTAG_CLEANUP.sub("", token.lstrip("#")).strip("_")
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        tags.append(f"#{cleaned}")
    return " ".join(tags)


def compose_post_text(caption: str, hashtags: str) -> str:
    """Build one social caption without exceeding the conservative shared limit."""
    normalized_caption = normalize_caption(caption)
    normalized_tags = normalize_hashtags(hashtags)
    caption_tags = {
        match.group(1).casefold()
        for match in _CAPTION_HASHTAG.finditer(normalized_caption)
    }
    accepted_tags: list[str] = []
    for tag in normalized_tags.split():
        if tag.lstrip("#").casefold() in caption_tags:
            continue
        candidate_tags = " ".join((*accepted_tags, tag))
        if utf16_length(candidate_tags) > MAX_POST_TEXT_UTF16:
            break
        accepted_tags.append(tag)
    tags_text = " ".join(accepted_tags)
    separator = "\n" if normalized_caption and tags_text else ""
    available_caption = MAX_POST_TEXT_UTF16 - utf16_length(f"{separator}{tags_text}")
    caption_text = _truncate_utf16(normalized_caption, available_caption)
    return f"{caption_text}{separator if caption_text else ''}{tags_text}".strip()


def _read_payload(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") not in {1, 2, 3, 4, STATE_SCHEMA_VERSION}:
        return None
    return payload


def load_state(project_root: str) -> dict[str, Any]:
    with _STATE_LOCK:
        payload = next(
            (
                candidate
                for path in (
                    state_path(project_root),
                    backup_state_path(project_root),
                    legacy_state_path(project_root),
                    legacy_backup_state_path(project_root),
                )
                if (candidate := _read_payload(path)) is not None
            ),
            None,
        )
        if payload is None:
            return _empty_state()
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    normalized_items = []
    for order, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        path_value = os.path.abspath(str(item.get("file_path") or "")) if item.get("file_path") else ""
        target_platform = str(item.get("target_platform") or "tiktok").casefold()
        stored_url = str(item.get("platform_post_url") or "")
        url_verified = bool(item.get("platform_post_url_verified", False))
        if (
            int(payload.get("schema_version") or 0) < STATE_SCHEMA_VERSION
            and stored_url
            and target_platform != "tiktok"
            and zernio.public_post_url(stored_url, target_platform)
        ):
            # Older releases did not record URL provenance. Non-TikTok URLs
            # came directly from the API; TikTok URLs could be guessed from a
            # temporary publish identifier and must be resolved again.
            url_verified = True
        normalized_items.append(
            {
                "id": str(item.get("id") or uuid.uuid4()),
                "order": int(item.get("order", order)),
                "file_name": str(item.get("file_name") or os.path.basename(path_value)),
                "file_path": path_value,
                "thumbnail_path": str(item.get("thumbnail_path") or ""),
                "source_path": str(item.get("source_path") or ""),
                "caption": normalize_caption(str(item.get("caption") or "")),
                "hashtags": normalize_hashtags(str(item.get("hashtags") or "")),
                "status": str(item.get("status") or "ready"),
                "error": str(item.get("error") or ""),
                "request_id": str(item.get("request_id") or uuid.uuid4()),
                "zernio_post_id": str(item.get("zernio_post_id") or ""),
                "platform_post_url": stored_url,
                "platform_post_url_verified": url_verified,
                "target_platform": target_platform,
                "duration_seconds": max(0.0, float(item.get("duration_seconds") or 0.0)),
                "video_width": max(0, int(item.get("video_width") or 0)),
                "video_height": max(0, int(item.get("video_height") or 0)),
                "upload_progress": max(0, min(100, int(item.get("upload_progress") or 0))),
                "created_at": str(item.get("created_at") or _now()),
                "updated_at": str(item.get("updated_at") or _now()),
            }
        )
    normalized_items.sort(key=lambda item: (item["order"], item["created_at"]))
    for order, item in enumerate(normalized_items):
        item["order"] = order
        if item["file_path"] and not os.path.isfile(item["file_path"]):
            item["status"] = "missing"
            item["error"] = "Video file is unavailable."
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "default_caption": normalize_caption(str(payload.get("default_caption") or "")),
        "default_hashtags": normalize_hashtags(str(payload.get("default_hashtags") or "")),
        "selected_account_id": str(payload.get("selected_account_id") or ""),
        "selected_platform": str(payload.get("selected_platform") or "tiktok").casefold(),
        "privacy_level": str(payload.get("privacy_level") or ""),
        "allow_comment": bool(payload.get("allow_comment", True)),
        "allow_duet": bool(payload.get("allow_duet", True)),
        "allow_stitch": bool(payload.get("allow_stitch", True)),
        "publish_now": bool(payload.get("publish_now", True)),
        "share_to_feed": bool(payload.get("share_to_feed", True)),
        "ai_generated": bool(payload.get("ai_generated", False)),
        "first_comment": normalize_caption(str(payload.get("first_comment") or "")),
        "items": normalized_items,
    }


def save_state(project_root: str, state: dict[str, Any]) -> None:
    root = os.path.abspath(project_root)
    os.makedirs(root, exist_ok=True)
    payload = {
        "schema_version": STATE_SCHEMA_VERSION,
        "default_caption": normalize_caption(str(state.get("default_caption") or "")),
        "default_hashtags": normalize_hashtags(str(state.get("default_hashtags") or "")),
        "selected_account_id": str(state.get("selected_account_id") or ""),
        "selected_platform": str(state.get("selected_platform") or "tiktok").casefold(),
        "privacy_level": str(state.get("privacy_level") or ""),
        "allow_comment": bool(state.get("allow_comment", True)),
        "allow_duet": bool(state.get("allow_duet", True)),
        "allow_stitch": bool(state.get("allow_stitch", True)),
        "publish_now": bool(state.get("publish_now", True)),
        "share_to_feed": bool(state.get("share_to_feed", True)),
        "ai_generated": bool(state.get("ai_generated", False)),
        "first_comment": normalize_caption(str(state.get("first_comment") or "")),
        "items": list(state.get("items") or []),
    }
    path = state_path(root)
    temporary_path = ""
    with _STATE_LOCK:
        try:
            handle, temporary_path = tempfile.mkstemp(prefix=".publish-", suffix=".json", dir=root)
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as output:
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            if _read_payload(path) is not None:
                shutil.copy2(path, backup_state_path(root))
            os.replace(temporary_path, path)
            temporary_path = ""
            for legacy_path in (legacy_state_path(root), legacy_backup_state_path(root)):
                try:
                    os.remove(legacy_path)
                except FileNotFoundError:
                    pass
        finally:
            if temporary_path:
                try:
                    os.remove(temporary_path)
                except FileNotFoundError:
                    pass


def append_items(project_root: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    with _STATE_LOCK:
        state = load_state(project_root)
        state["items"].extend(items)
        for order, item in enumerate(state["items"]):
            item["order"] = order
        save_state(project_root, state)
        return state


def update_item(project_root: str, item_id: str, **changes: Any) -> dict[str, Any] | None:
    with _STATE_LOCK:
        state = load_state(project_root)
        item = next((candidate for candidate in state["items"] if candidate["id"] == item_id), None)
        if item is None:
            return None
        content_changed = False
        if "caption" in changes:
            changes["caption"] = normalize_caption(str(changes["caption"] or ""))
            content_changed = changes["caption"] != item.get("caption")
        if "hashtags" in changes:
            changes["hashtags"] = normalize_hashtags(str(changes["hashtags"] or ""))
            content_changed = content_changed or changes["hashtags"] != item.get("hashtags")
        if content_changed:
            # A changed caption is a new logical post. Preserve the request ID
            # for an unchanged retry so an ambiguous network failure cannot
            # duplicate a post, but rotate it when the content itself changes.
            changes["request_id"] = str(uuid.uuid4())
            changes["zernio_post_id"] = ""
            changes["platform_post_url"] = ""
            changes["platform_post_url_verified"] = False
            changes["upload_progress"] = 0
        item.update(changes)
        item["updated_at"] = _now()
        save_state(project_root, state)
        return item


def remove_item(project_root: str, item_id: str) -> dict[str, Any] | None:
    with _STATE_LOCK:
        state = load_state(project_root)
        removed = next((candidate for candidate in state["items"] if candidate["id"] == item_id), None)
        if removed is None:
            return None
        state["items"] = [candidate for candidate in state["items"] if candidate["id"] != item_id]
        for order, item in enumerate(state["items"]):
            item["order"] = order
        save_state(project_root, state)
        return removed


def update_defaults(
    project_root: str,
    caption: str,
    hashtags: str,
    *,
    apply_to_ready_items: bool = False,
    apply_to_empty_items: bool = True,
) -> dict[str, Any]:
    with _STATE_LOCK:
        state = load_state(project_root)
        state["default_caption"] = normalize_caption(caption)
        state["default_hashtags"] = normalize_hashtags(hashtags)
        for item in state["items"]:
            if item["status"] in {"uploading", "publishing", "published", "posted", "scheduled"}:
                continue
            item_is_empty = not item.get("caption") and not item.get("hashtags")
            if apply_to_ready_items or (apply_to_empty_items and item_is_empty):
                item["caption"] = state["default_caption"]
                item["hashtags"] = state["default_hashtags"]
                item["status"] = "ready"
                item["error"] = ""
                item["request_id"] = str(uuid.uuid4())
                item["zernio_post_id"] = ""
                item["platform_post_url"] = ""
                item["platform_post_url_verified"] = False
                item["upload_progress"] = 0
                item["updated_at"] = _now()
        save_state(project_root, state)
        return state


def update_publish_settings(project_root: str, **changes: Any) -> dict[str, Any]:
    allowed = {
        "selected_account_id",
        "selected_platform",
        "privacy_level",
        "allow_comment",
        "allow_duet",
        "allow_stitch",
        "publish_now",
        "share_to_feed",
        "ai_generated",
        "first_comment",
    }
    with _STATE_LOCK:
        state = load_state(project_root)
        for key, value in changes.items():
            if key not in allowed:
                continue
            if key.startswith("allow_") or key in {"publish_now", "share_to_feed", "ai_generated"}:
                state[key] = bool(value)
            elif key == "first_comment":
                state[key] = normalize_caption(str(value or ""))
            else:
                state[key] = str(value or "")
        save_state(project_root, state)
        return state


def new_item(file_path: str, thumbnail_path: str, order: int, caption: str, hashtags: str) -> dict[str, Any]:
    now = _now()
    return {
        "id": str(uuid.uuid4()),
        "order": int(order),
        "file_name": Path(file_path).name,
        "file_path": os.path.abspath(file_path),
        "thumbnail_path": os.path.abspath(thumbnail_path) if thumbnail_path else "",
        "source_path": "",
        "caption": normalize_caption(caption),
        "hashtags": normalize_hashtags(hashtags),
        "status": "ready",
        "error": "",
        "request_id": str(uuid.uuid4()),
        "zernio_post_id": "",
        "platform_post_url": "",
        "platform_post_url_verified": False,
        "target_platform": "",
        "duration_seconds": 0.0,
        "video_width": 0,
        "video_height": 0,
        "upload_progress": 0,
        "created_at": now,
        "updated_at": now,
    }


def summarize(project_root: str) -> dict[str, Any]:
    state = load_state(project_root)
    items = state["items"]
    posted = sum(1 for item in items if item["status"] in {"published", "posted"})
    if not items:
        status = "empty"
    elif posted == len(items):
        status = "done"
    elif any(item["status"] in {"uploading", "publishing", "scheduled", "draft"} for item in items):
        status = "processing"
    elif any(item["status"] in {"failed", "missing", "partial"} for item in items):
        status = "failed"
    else:
        status = "ready"
    first_thumbnail = next(
        (item["thumbnail_path"] for item in items if item.get("thumbnail_path") and os.path.isfile(item["thumbnail_path"])),
        "",
    )
    return {
        "item_count": len(items),
        "posted_count": posted,
        "progress": round(posted * 100 / len(items)) if items else 0,
        "status": status,
        "thumbnail_path": first_thumbnail,
    }


def cleanup_orphaned_media(project_root: str) -> int:
    """Remove interrupted copies and files no longer referenced by the queue."""
    has_valid_state = (
        _read_payload(state_path(project_root)) is not None
        or _read_payload(backup_state_path(project_root)) is not None
        or _read_payload(legacy_state_path(project_root)) is not None
        or _read_payload(legacy_backup_state_path(project_root)) is not None
    )
    state = load_state(project_root)
    referenced = {
        os.path.normcase(os.path.abspath(path))
        for item in state["items"]
        for path in (item.get("file_path"), item.get("thumbnail_path"))
        if path
    }
    removed = 0
    for directory in (media_directory(project_root), thumbnail_directory(project_root)):
        if not os.path.isdir(directory):
            continue
        for entry in os.scandir(directory):
            if not entry.is_file(follow_symlinks=False):
                continue
            path = os.path.abspath(entry.path)
            if os.path.normcase(path) in referenced:
                continue
            if not has_valid_state and not entry.name.lower().endswith(".part"):
                continue
            try:
                os.remove(path)
                removed += 1
            except FileNotFoundError:
                pass
    return removed


def migrate_project_layout(project_root: str) -> dict[str, Any]:
    """Migrate a publishing project without deleting any user-owned content.

    Only the two known legacy directories are removed, and only when empty.
    A successful write of the new social state happens before legacy state
    files are retired, so a failed migration remains recoverable.
    """
    root = os.path.abspath(project_root)
    state = load_state(root)
    current_payload = _read_payload(state_path(root))
    legacy_exists = any(
        os.path.isfile(path)
        for path in (legacy_state_path(root), legacy_backup_state_path(root))
    )
    if (
        current_payload is None
        or current_payload.get("schema_version") != STATE_SCHEMA_VERSION
        or legacy_exists
    ):
        save_state(root, state)
    for directory_name in ("exports", "videos"):
        directory = os.path.join(root, directory_name)
        try:
            os.rmdir(directory)
        except (FileNotFoundError, OSError):
            pass
    return state
