"""Douyin URL compatibility and public share-page metadata fallback.

Only read metadata served by Douyin. Do not solve verification challenges,
generate access cookies, or use third-party download APIs.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

from yt_dlp.extractor.tiktok import DouyinIE
from yt_dlp.utils import ExtractorError

ACCESS_MESSAGE = (
    "Douyin did not provide playable video data. Check that the video is public and can be viewed on Douyin."
)


def video_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (parsed.scheme not in {"https", "http"} or parsed.username or parsed.password
            or parsed.port not in {None, 80, 443}
            or not any(host == domain or host.endswith("." + domain)
                       for domain in ("douyin.com", "iesdouyin.com"))):
        raise ExtractorError("The Douyin share link redirected to an unsupported address.", expected=True)
    match = re.fullmatch(r"/(?:share/)?video/([0-9]{10,25})/?", parsed.path)
    values = parse_qs(parsed.query).get("modal_id", [])
    if match:
        return match[1]
    if len(values) == 1 and re.fullmatch(r"[0-9]{10,25}", values[0]):
        return values[0]
    raise ExtractorError("Paste a link to one Douyin video, not a profile or live stream.", expected=True)


def share_page_detail(webpage: str, video_id: str) -> dict | None:
    # JSONDecoder consumes exactly one JSON value, not surrounding JavaScript.
    # Never evaluate downloaded scripts.
    marker = re.search(r"(?:window\.)?_ROUTER_DATA\s*=\s*", webpage)
    if not marker:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(webpage[marker.end():])
    except (ValueError, RecursionError):
        return None
    loaders = data.get("loaderData", {}) if isinstance(data, dict) else {}
    if not isinstance(loaders, dict):
        return None
    for loader in loaders.values():
        if not isinstance(loader, dict):
            continue
        result = loader.get("videoInfoRes")
        if not isinstance(result, dict):
            continue
        items = result.get("item_list") or result.get("aweme_list") or []
        if not isinstance(items, list):
            continue
        for item in items:
            if (isinstance(item, dict) and str(item.get("aweme_id")) == video_id
                    and isinstance(item.get("video"), dict)):
                return item
    return None


class HaizFlowDouyinIE(DouyinIE):
    _VALID_URL = r"https?://(?:(?:www\.)?(?:ies)?douyin\.com/(?:share/)?video/(?P<id>[0-9]+)|v\.douyin\.com/(?P<short>[\w-]+))"

    def __init__(self, downloader=None, *, adapter=None, cancel_event=None):
        super().__init__(downloader)
        self.adapter = adapter
        self.cancel_event = cancel_event

    def _real_extract(self, url):
        from haizflow.services.douyin_adapter import get_douyin_adapter, _session_guard

        adapter = self.adapter or get_douyin_adapter()
        # Freeze the metadata/profile/jar snapshot together. A concurrent explicit
        # session refresh must not pair old media with a new browser identity.
        with _session_guard(adapter.session.lock, self.cancel_event):
            return self._extract_with_session(adapter, url)

    def _extract_with_session(self, adapter, url):
        from copy import copy
        from haizflow.services.douyin_classification import DouyinError, Outcome
        from yt_dlp.networking.impersonate import ImpersonateTarget

        try:
            detail = adapter.inspect(url, self.cancel_event)
        except DouyinError as exc:
            raise ExtractorError(str(exc), expected=True, cause=exc) from exc
        video_id = str(detail["aweme_id"])
        info = self._parse_aweme_video_app(detail)
        if not info.get("formats"):
            raise ExtractorError(str(DouyinError(Outcome.METADATA)), expected=True)
        profile = adapter.session.profile
        headers = {"User-Agent": profile.ua, "Referer": "https://www.douyin.com/"}
        if self._downloader is not None:
            self._downloader.params["impersonate"] = ImpersonateTarget.from_str(f"chrome-{profile.major}")
            # Domain-scoped cookies only; no raw Cookie header on CDN URLs.
            for cookie in adapter.session.transport.cookie_jar:
                domain = cookie.domain.lstrip(".").lower()
                if any(domain == name or domain.endswith("." + name) for name in ("douyin.com", "iesdouyin.com")):
                    self._downloader.cookiejar.set_cookie(copy(cookie))
        for item in info["formats"]:
            item["http_headers"] = headers
        info.update(webpage_url=f"https://www.douyin.com/video/{video_id}", extractor="Douyin",
                    extractor_key="Douyin", http_headers=headers)
        return info
