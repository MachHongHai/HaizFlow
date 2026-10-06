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
MOBILE_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
PUBLIC_METADATA_AGENT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


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

    def _real_extract(self, url):
        if (urlparse(url).hostname or "").lower() == "v.douyin.com":
            _page, response = self._download_webpage_handle(url, "share", note="Resolving Douyin share link")
            video_id = video_id_from_url(response.url)
        else:
            video_id = video_id_from_url(url)
        canonical = f"https://www.douyin.com/video/{video_id}"
        result = self._download_json(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/", video_id,
            note="Checking Douyin video", query={"aweme_id": video_id}, fatal=False)
        detail = result.get("aweme_detail") if isinstance(result, dict) else None
        if not isinstance(detail, dict) or not detail:
            # Douyin also serves public video metadata for indexing. Request
            # that representation directly; no account cookies, verification
            # tokens, script execution or external parsing service is needed.
            public_result = self._download_json(
                "https://www.douyin.com/aweme/v1/web/aweme/detail/", video_id,
                note="Reading Douyin public video metadata", query={"aweme_id": video_id},
                headers={"User-Agent": PUBLIC_METADATA_AGENT}, fatal=False)
            detail = public_result.get("aweme_detail") if isinstance(public_result, dict) else None
        if not isinstance(detail, dict) or not detail:
            page = self._download_webpage(
                f"https://www.iesdouyin.com/share/video/{video_id}/", video_id,
                note="Checking Douyin share page", headers={"User-Agent": MOBILE_AGENT}, fatal=False)
            detail = share_page_detail(page or "", video_id)
        if not detail or str(detail.get("aweme_id")) != video_id:
            raise ExtractorError(ACCESS_MESSAGE, expected=True)
        info = self._parse_aweme_video_app(detail)
        if not info.get("formats"):
            raise ExtractorError(ACCESS_MESSAGE, expected=True)
        info.update(webpage_url=canonical, extractor="Douyin", extractor_key="Douyin")
        return info
