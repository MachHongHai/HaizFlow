"""Minimal Zernio REST client with streaming presigned uploads."""

from __future__ import annotations

import http.client
import json
import mimetypes
import os
import re
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://zernio.com/api/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
UPLOAD_CHUNK_BYTES = 1024 * 1024


class ZernioError(RuntimeError):
    """A safe, user-facing Zernio error without credentials or signed URLs."""

    def __init__(self, message: str, *, status: int = 0, payload: Any = None):
        super().__init__(message)
        self.status = int(status or 0)
        self.payload = payload if isinstance(payload, dict) else {}

    @property
    def existing_post_id(self) -> str:
        value = self.payload
        details = value.get("details") if isinstance(value.get("details"), dict) else {}
        candidates = (
            value.get("existingPostId"),
            value.get("existing_post_id"),
            details.get("existingPostId"),
            details.get("existing_post_id"),
            (value.get("error") or {}).get("existingPostId") if isinstance(value.get("error"), dict) else "",
        )
        return next((str(item) for item in candidates if item), "")


class ZernioCancelled(ZernioError):
    pass


class ZernioClient:
    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.api_key = str(api_key or "").strip()
        if not self.api_key:
            raise ValueError("A Zernio API key is required.")
        self.base_url = str(base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = max(1.0, float(timeout))

    def list_profiles(self, *, include_over_limit: bool = True) -> list[dict[str, Any]]:
        query = {"includeOverLimit": "true"} if include_over_limit else None
        payload = self._request("GET", "/profiles", query=query)
        return _object_list(payload, "profiles")

    def create_profile(self, name: str, description: str = "HaizFlow social publishing") -> dict[str, Any]:
        payload = self._request("POST", "/profiles", {"name": name, "description": description})
        return _object(payload, "profile")

    def get_connect_url(self, profile_id: str, platform: str = "tiktok") -> str:
        platform_name = normalize_platform(platform)
        payload = self._request("GET", f"/connect/{platform_name}", query={"profileId": profile_id})
        return str(payload.get("authUrl") or payload.get("url") or payload.get("connectUrl") or "")

    def list_tiktok_accounts(
        self,
        profile_id: str = "",
        *,
        include_over_limit: bool = True,
    ) -> list[dict[str, Any]]:
        return self.list_accounts(
            profile_id,
            platforms=("tiktok",),
            include_over_limit=include_over_limit,
        )

    def list_accounts(
        self,
        profile_id: str = "",
        *,
        platforms: tuple[str, ...] | list[str] | None = None,
        include_over_limit: bool = True,
    ) -> list[dict[str, Any]]:
        query = {"status": "connected"}
        normalized_platforms = tuple(normalize_platform(value) for value in (platforms or ()))
        if len(normalized_platforms) == 1:
            query["platform"] = normalized_platforms[0]
        if include_over_limit:
            query["includeOverLimit"] = "true"
        if profile_id:
            query["profileId"] = profile_id
        payload = self._request("GET", "/accounts", query=query)
        allowed = set(normalized_platforms)
        accounts = _object_list(payload, "accounts")
        if not allowed:
            return accounts
        return [item for item in accounts if str(item.get("platform") or "").strip().casefold() in allowed]

    def get_tiktok_creator_info(self, account_id: str) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"/accounts/{account_id}/tiktok/creator-info",
            query={"mediaType": "video"},
        )
        return normalize_tiktok_creator_info(payload)

    def disconnect_account(self, account_id: str) -> dict[str, Any]:
        """Disconnect one social account from Zernio."""
        normalized_id = str(account_id or "").strip()
        if not normalized_id:
            raise ValueError("A Zernio account ID is required.")
        return self._request("DELETE", f"/accounts/{quote(normalized_id, safe='')}")

    def presign_video(self, file_path: str) -> dict[str, Any]:
        path = os.path.abspath(file_path)
        content_type = mimetypes.guess_type(path)[0] or "video/mp4"
        return self._request(
            "POST",
            "/media/presign",
            {"filename": Path(path).name, "contentType": content_type},
        )

    def upload_file(
        self,
        upload_url: str,
        file_path: str,
        *,
        content_type: str = "",
        progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        source = os.path.abspath(file_path)
        total = os.path.getsize(source)
        parsed = urlsplit(upload_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ZernioError("Zernio returned an invalid media upload URL.")
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(parsed.hostname, parsed.port, timeout=max(self.timeout, 120.0))
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        media_type = content_type or mimetypes.guess_type(source)[0] or "application/octet-stream"
        sent = 0
        try:
            connection.putrequest("PUT", target)
            connection.putheader("Content-Type", media_type)
            connection.putheader("Content-Length", str(total))
            connection.endheaders()
            with open(source, "rb") as handle:
                while True:
                    if cancelled and cancelled():
                        raise ZernioCancelled("Upload cancelled.")
                    chunk = handle.read(UPLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    connection.send(chunk)
                    sent += len(chunk)
                    if progress:
                        progress(sent, total)
            response = connection.getresponse()
            response.read()
            if not 200 <= response.status < 300:
                raise ZernioError(f"Media upload failed (HTTP {response.status}).")
        except (OSError, http.client.HTTPException, socket.timeout) as exc:
            raise ZernioError(f"Could not upload the video: {exc}") from exc
        finally:
            connection.close()

    def create_tiktok_post(
        self,
        *,
        account_id: str,
        content: str,
        media_url: str,
        privacy_level: str,
        publish_now: bool,
        request_id: str,
        allow_comment: bool = True,
        allow_duet: bool = True,
        allow_stitch: bool = True,
        ai_generated: bool = False,
    ) -> Any:
        body: dict[str, Any] = {
            "content": content,
            "mediaItems": [{"type": "video", "url": media_url}],
            "platforms": [{"platform": "tiktok", "accountId": account_id}],
            "tiktokSettings": {
                "privacy_level": privacy_level,
                "allow_comment": bool(allow_comment),
                "allow_duet": bool(allow_duet),
                "allow_stitch": bool(allow_stitch),
                "content_preview_confirmed": True,
                "express_consent_given": True,
                "video_made_with_ai": bool(ai_generated),
            },
        }
        if publish_now:
            body["publishNow"] = True
        return self._request("POST", "/posts", body, headers={"x-request-id": request_id})

    def create_video_post(
        self,
        *,
        platform: str,
        account_id: str,
        content: str,
        media_url: str,
        publish_now: bool,
        request_id: str,
        privacy_level: str = "",
        title: str = "",
        allow_comment: bool = True,
        allow_duet: bool = True,
        allow_stitch: bool = True,
        share_to_feed: bool = True,
        ai_generated: bool = False,
        first_comment: str = "",
    ) -> Any:
        """Create one short-form video post for a supported Zernio connection."""
        platform_name = normalize_platform(platform)
        if platform_name == "tiktok":
            return self.create_tiktok_post(
                account_id=account_id,
                content=content,
                media_url=media_url,
                privacy_level=privacy_level or "PUBLIC_TO_EVERYONE",
                publish_now=publish_now,
                request_id=request_id,
                allow_comment=allow_comment,
                allow_duet=allow_duet,
                allow_stitch=allow_stitch,
                ai_generated=ai_generated,
            )

        platform_data: dict[str, Any]
        if platform_name == "youtube":
            platform_data = {
                "title": (str(title or "").strip() or "HaizFlow video")[:100],
                "visibility": privacy_level if privacy_level in {"public", "private", "unlisted"} else "public",
            }
        elif platform_name == "facebook":
            platform_data = {"contentType": "reel"}
            if title:
                platform_data["title"] = str(title).strip()[:255]
            if first_comment:
                platform_data["firstComment"] = str(first_comment).strip()
        else:
            platform_data = {
                "contentType": "reels",
                "shareToFeed": bool(share_to_feed),
                "isAiGenerated": bool(ai_generated),
            }
            if first_comment:
                platform_data["firstComment"] = str(first_comment).strip()

        body: dict[str, Any] = {
            "content": content,
            "mediaItems": [{"type": "video", "url": media_url}],
            "platforms": [
                {
                    "platform": platform_name,
                    "accountId": account_id,
                    "platformSpecificData": platform_data,
                }
            ],
        }
        if publish_now:
            body["publishNow"] = True
        return self._request("POST", "/posts", body, headers={"x-request-id": request_id})

    def get_post(self, post_id: str) -> dict[str, Any]:
        return _object(self._request("GET", f"/posts/{post_id}"), "post")

    def list_posts(self) -> list[dict[str, Any]]:
        """Return recent posts for status/link recovery after asynchronous publishing."""
        return _object_list(self._request("GET", "/posts"), "posts")

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "HaizFlow/0.1 ZernioClient",
        }
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        request = Request(url, data=data, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raw = exc.read()
            payload = _error_payload(raw)
            raise ZernioError(_error_message(raw, exc.code), status=exc.code, payload=payload) from exc
        except (URLError, OSError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ZernioError(f"Could not reach Zernio: {reason}") from exc
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ZernioError("Zernio returned an unreadable response.") from exc
        if not isinstance(payload, (dict, list)):
            raise ZernioError("Zernio returned an unexpected response.")
        if isinstance(payload, dict):
            data_payload = payload.get("data")
            if isinstance(data_payload, (dict, list)):
                return data_payload
        return payload


def _error_message(raw: bytes, status: int) -> str:
    message = ""
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or error.get("code") or "")
            else:
                message = str(payload.get("message") or error or "")
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    return f"Zernio request failed (HTTP {status}){': ' + message if message else '.'}"


def _error_payload(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _object(payload: Any, key: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    nested = payload.get("data")
    if isinstance(nested, dict):
        return _object(nested, key)
    return payload


def _object_list(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        value = payload
    elif isinstance(payload, dict):
        value = payload.get(key)
        if not isinstance(value, list):
            nested = payload.get("data")
            return _object_list(nested, key) if isinstance(nested, (dict, list)) else []
    else:
        return []
    return [item for item in value if isinstance(item, dict)]


def normalize_tiktok_creator_info(payload: Any) -> dict[str, Any]:
    """Normalize Zernio's creator-info objects into values safe for desktop controls."""
    info = dict(payload) if isinstance(payload, dict) else {}
    raw_levels = info.get("privacyLevels") or info.get("privacy_levels") or []
    levels: list[str] = []
    if isinstance(raw_levels, list):
        for entry in raw_levels:
            value = entry.get("value") if isinstance(entry, dict) else entry
            normalized = str(value or "").strip()
            if normalized and normalized not in levels:
                levels.append(normalized)
    posting_limits = info.get("postingLimits") or info.get("posting_limits") or {}
    if not isinstance(posting_limits, dict):
        posting_limits = {}
    interactions = posting_limits.get("interactionSettings") or posting_limits.get("interaction_settings") or {}
    if not isinstance(interactions, dict):
        interactions = {}
    creator = info.get("creator") if isinstance(info.get("creator"), dict) else {}
    info["privacyLevels"] = levels
    info["interactionSettings"] = {
        "comment": bool(interactions.get("comment", True)),
        "duet": bool(interactions.get("duet", True)),
        "stitch": bool(interactions.get("stitch", True)),
    }
    info["canPostMore"] = bool(creator.get("canPostMore", creator.get("can_post_more", True)))
    return info


SUPPORTED_PUBLISH_PLATFORMS = frozenset({"tiktok", "youtube", "facebook", "instagram"})


def normalize_platform(value: str) -> str:
    platform = str(value or "").strip().casefold()
    if platform not in SUPPORTED_PUBLISH_PLATFORMS:
        raise ValueError(f"Unsupported Zernio platform: {value}")
    return platform


_PUBLIC_POST_URL_KEYS = (
    "platformPostUrl",
    "platform_post_url",
    "publishedUrl",
    "published_url",
    "permalink",
    "permalinkUrl",
    "postUrl",
    "publicUrl",
    "shareUrl",
)


def public_post_url(value: Any, platform: str) -> str:
    """Return *value* only when it is a public post URL for *platform*.

    Zernio media URLs, dashboard URLs, and TikTok's temporary
    ``v_pub_url`` publish identifiers are deliberately not accepted here.
    They are not public post permalinks and opening them can show a different
    or unavailable video.
    """
    platform_name = normalize_platform(platform)
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"}:
        return ""
    host = (parsed.hostname or "").casefold().rstrip(".")
    path = parsed.path or "/"
    if platform_name == "tiktok":
        if host in {"vm.tiktok.com", "vt.tiktok.com"}:
            return candidate if path != "/" else ""
        return (
            candidate
            if host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}
            and (
                re.search(r"/@[^/]+/video/\d+/?$", path, flags=re.IGNORECASE)
                or re.search(r"/(?:t|v)/[^/]+", path, flags=re.IGNORECASE)
            )
            else ""
        )
    if platform_name == "youtube":
        return (
            candidate
            if (host in {"youtu.be", "www.youtu.be"} and path != "/")
            or (
                host in {"youtube.com", "www.youtube.com", "m.youtube.com"}
                and (path.startswith("/watch") or path.startswith("/shorts/") or path.startswith("/live/"))
            )
            else ""
        )
    if platform_name == "instagram":
        return (
            candidate
            if host in {"instagram.com", "www.instagram.com"}
            and re.match(r"/(?:p|reel|reels|tv)/[^/]+", path, flags=re.IGNORECASE)
            else ""
        )
    if platform_name == "facebook":
        return (
            candidate
            if (host in {"fb.watch", "www.fb.watch"} and path != "/")
            or (host in {"facebook.com", "www.facebook.com", "m.facebook.com"} and path != "/")
            else ""
        )
    return ""


def _explicit_public_post_url(container: Any, platform: str) -> str:
    if not isinstance(container, dict):
        return ""
    for key in _PUBLIC_POST_URL_KEYS:
        if url := public_post_url(container.get(key), platform):
            return url
    for nested in container.values():
        if isinstance(nested, dict):
            if url := _explicit_public_post_url(nested, platform):
                return url
        elif isinstance(nested, list):
            for entry in nested:
                if isinstance(entry, dict):
                    if url := _explicit_public_post_url(entry, platform):
                        return url
    return ""


def _platform_result_entry(container: Any, platform: str) -> dict[str, Any]:
    """Locate a platform result across Zernio's wrapped response shapes."""
    if not isinstance(container, dict):
        return {}
    platform_name = normalize_platform(platform)
    direct_platform = str(
        container.get("platform") or container.get("provider") or container.get("network") or ""
    ).casefold()
    if direct_platform == platform_name:
        return container
    for key in ("platforms", "platformResults", "results"):
        entries = container.get(key)
        if isinstance(entries, dict):
            direct = entries.get(platform_name)
            if isinstance(direct, dict):
                return direct
            entries = list(entries.values())
        if isinstance(entries, list):
            for entry in entries:
                if found := _platform_result_entry(entry, platform_name):
                    return found
    for key in ("post", "data", "result", "existingPost"):
        if found := _platform_result_entry(container.get(key), platform_name):
            return found
    return {}


def post_result(post: Any, platform: str) -> dict[str, str]:
    """Return the effective platform status, URL, and error from a Zernio post."""
    platform_name = normalize_platform(platform)
    value = post if isinstance(post, dict) else {}
    platform_entry = _platform_result_entry(value, platform_name)

    status = str(platform_entry.get("status") or value.get("status") or "publishing").casefold()
    url = _explicit_public_post_url(platform_entry, platform_name)
    if not url:
        url = _explicit_public_post_url(value, platform_name)
    error_value = platform_entry.get("error") or value.get("error") or ""
    if isinstance(error_value, dict):
        error_value = error_value.get("message") or error_value.get("code") or ""
    return {"status": status, "url": url, "error": str(error_value or "")}


def tiktok_post_result(post: Any) -> dict[str, str]:
    """Backward-compatible TikTok-specific result helper."""
    return post_result(post, "tiktok")
