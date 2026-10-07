"""Legacy CLI entry point and Douyin channel metadata normalization.

Desktop scans now share DouyinAdapter directly. No fabricated token, browser
profile extraction, urllib transport or second signing strategy lives here.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from haizflow.services.douyin_transport import validate_douyin_address as _validated_douyin_url

__all__ = ["_validated_douyin_url", "_candidate", "inspect_profile"]

def _cover_url(video: dict) -> str:
    for key in ("cover", "origin_cover", "dynamic_cover"):
        value = video.get(key)
        if not isinstance(value, dict):
            continue
        urls = value.get("url_list") or []
        if isinstance(urls, list):
            for url in urls:
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    return url
    return ""


def _candidate(aweme: dict) -> dict | None:
    # Photo notes and slideshows are not valid inputs for the video pipeline.
    if aweme.get("images"):
        return None
    video_value = aweme.get("video")
    if not isinstance(video_value, dict):
        return None
    video: dict = video_value
    play_address = video.get("play_addr")
    if not isinstance(play_address, dict):
        return None
    play_urls = play_address.get("url_list") or []
    if not isinstance(play_urls, list) or not any(
        isinstance(url, str) and url.startswith(("http://", "https://"))
        for url in play_urls
    ):
        return None
    remote_id = str(aweme.get("aweme_id") or "").strip()
    if not remote_id:
        return None
    author_value = aweme.get("author")
    author: dict = author_value if isinstance(author_value, dict) else {}
    statistics_value = aweme.get("statistics")
    statistics: dict = statistics_value if isinstance(statistics_value, dict) else {}
    timestamp = aweme.get("create_time")
    try:
        published_at = (
            datetime.fromtimestamp(float(timestamp), timezone.utc).strftime("%Y%m%d")
            if timestamp is not None
            else ""
        )
    except (TypeError, ValueError, OSError):
        published_at = ""
    try:
        duration = int(video.get("duration") or aweme.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    duration //= 1000
    raw_view_count = statistics.get("play_count")
    try:
        view_count = int(raw_view_count) if raw_view_count is not None else None
    except (TypeError, ValueError):
        view_count = None
    return {
        "remote_video_id": remote_id,
        "source_url": f"https://www.douyin.com/video/{remote_id}",
        "title": str(aweme.get("desc") or f"Video {remote_id}").strip(),
        "platform": "Douyin",
        "uploader": str(author.get("nickname") or "").strip(),
        "duration_seconds": max(0, duration),
        "published_at": published_at,
        "view_count": view_count,
        "thumbnail_url": _cover_url(video),
    }



def inspect_profile(payload: dict) -> dict:
    from haizflow.services.douyin_adapter import get_douyin_adapter
    adapter = get_douyin_adapter(payload)
    budget = payload.get("scan_scope") if payload.get("ranking") == "popular" else payload.get("limit", 20)
    name, candidates = adapter.profile_posts(str(payload.get("url") or ""), limit=int(budget or 1000))
    return {"channel_name": name, "candidates": candidates}


def main() -> int:
    try:
        response = inspect_profile(json.loads(sys.stdin.read()))
    except (OSError, ValueError, RuntimeError) as exc:
        response = {"error": str(exc)}
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
