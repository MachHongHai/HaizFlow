"""Minimal Zernio REST client with streaming presigned uploads."""

from __future__ import annotations

import http.client
import json
import mimetypes
import os
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://zernio.com/api/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
UPLOAD_CHUNK_BYTES = 1024 * 1024


class ZernioError(RuntimeError):
    """A safe, user-facing Zernio error without credentials or signed URLs."""


class ZernioCancelled(ZernioError):
    pass


class ZernioClient:
    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.api_key = str(api_key or "").strip()
        if not self.api_key:
            raise ValueError("A Zernio API key is required.")
        self.base_url = str(base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = max(1.0, float(timeout))

    def list_profiles(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/profiles")
        return _object_list(payload, "profiles")

    def create_profile(self, name: str, description: str = "HaizFlow TikTok publishing") -> dict[str, Any]:
        payload = self._request("POST", "/profiles", {"name": name, "description": description})
        return _object(payload, "profile")

    def get_connect_url(self, profile_id: str) -> str:
        payload = self._request("GET", "/connect/tiktok", query={"profileId": profile_id})
        return str(payload.get("authUrl") or payload.get("url") or payload.get("connectUrl") or "")

    def list_tiktok_accounts(self, profile_id: str = "") -> list[dict[str, Any]]:
        query = {"platform": "tiktok"}
        if profile_id:
            query["profileId"] = profile_id
        payload = self._request("GET", "/accounts", query=query)
        return [item for item in _object_list(payload, "accounts") if str(item.get("platform") or "").lower() == "tiktok"]

    def get_tiktok_creator_info(self, account_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/accounts/{account_id}/tiktok/creator-info",
            query={"mediaType": "video"},
        )

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
            },
        }
        if publish_now:
            body["publishNow"] = True
        return self._request("POST", "/posts", body, headers={"x-request-id": request_id})

    def get_post(self, post_id: str) -> dict[str, Any]:
        return _object(self._request("GET", f"/posts/{post_id}"), "post")

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
            raise ZernioError(_error_message(raw, exc.code)) from exc
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
