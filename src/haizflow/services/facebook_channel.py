"""Read the public video collection exposed in a Facebook page response.

No login automation, private API, browser process or unrelated recommendations.
Only the initial all_videos connection is used; pagination is not fabricated.
"""

from __future__ import annotations

import json
import threading
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from haizflow.services.video_download import DownloadCancelled, _load_yt_dlp, _youtube_dl_options

MAX_PAGE_BYTES = 4 * 1024 * 1024


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.payloads = []
        self.title = ""
        self._json = False
        self._title = False
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._json = dict(attrs).get("type") == "application/json"
            self._parts = []
        elif tag == "title":
            self._title = True

    def handle_data(self, data):
        if self._json:
            self._parts.append(data)
        elif self._title:
            self.title += data

    def handle_endtag(self, tag):
        if tag == "script" and self._json:
            self._json = False
            try:
                self.payloads.append(json.loads("".join(self._parts)))
            except (ValueError, RecursionError):
                pass
        elif tag == "title":
            self._title = False


def page_video_entries(html: str, limit: int) -> tuple[str, list[dict]]:
    parser = _PageParser()
    parser.feed(html)
    stack = list(reversed(parser.payloads))
    entries = []
    seen = set()
    while stack and len(entries) < limit:
        obj = stack.pop()
        if isinstance(obj, dict):
            connection = obj.get("all_videos")
            if isinstance(connection, dict):
                for edge in connection.get("edges") or []:
                    node = edge.get("node") if isinstance(edge, dict) else None
                    if not isinstance(node, dict) or node.get("__typename") != "Video":
                        continue
                    video_id = str(node.get("id") or "")
                    if not video_id.isdigit() or video_id in seen or node.get("is_live_streaming"):
                        continue
                    seen.add(video_id)
                    entries.append({"id": video_id,
                                    "url": f"https://www.facebook.com/watch/?v={video_id}"})
                    if len(entries) >= limit:
                        break
            stack.extend(reversed(list(obj.values())))
        elif isinstance(obj, list):
            stack.extend(reversed(obj))
    return parser.title.removesuffix(" | Facebook").strip(), entries


def inspect_page(url: str, auth: dict, limit: int, cancel_event: threading.Event) -> dict:
    if cancel_event.is_set():
        raise DownloadCancelled("Channel inspection cancelled.")
    parsed = urlparse(url)
    if parsed.path == "/profile.php":
        query = parse_qs(parsed.query)
        query["sk"] = ["videos"]
        page_url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    else:
        path = parsed.path.rstrip("/")
        if not path.endswith("/videos"):
            path = path.removesuffix("/reels") + "/videos"
        page_url = urlunparse(parsed._replace(path=path, query="", fragment=""))
    from yt_dlp.networking import Request

    options = _youtube_dl_options(auth, impersonate=True)
    # A single bounded page read, not yt-dlp's generic embedded-video scan.
    with _load_yt_dlp().YoutubeDL(options) as downloader:
        with downloader.urlopen(Request(page_url)) as response:
            host = (urlparse(response.url).hostname or "").lower()
            if host != "facebook.com" and not host.endswith(".facebook.com"):
                raise RuntimeError("Facebook redirected to an unsupported page.")
            chunks = []
            total = 0
            while True:
                if cancel_event.is_set():
                    raise DownloadCancelled("Channel inspection cancelled.")
                chunk = response.read(min(65536, MAX_PAGE_BYTES - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PAGE_BYTES:
                    raise RuntimeError("The Facebook page response is too large.")
                chunks.append(chunk)
    html = b"".join(chunks).decode("utf-8", errors="replace")
    name, entries = page_video_entries(html, max(1, limit))
    if not entries:
        raise RuntimeError("Facebook did not expose public page videos. Use individual video links or explicitly supplied cookies.")
    return {"title": name, "entries": entries}
