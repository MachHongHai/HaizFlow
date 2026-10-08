"""Bounded first-party profile readers; individual media still uses yt-dlp.

No login automation or browser startup. Cookies, if any, must be supplied by
the user through the existing download settings. X's public embed exposes
only its initial timeline, not a complete account archive.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlencode, urlparse

from haizflow.services.video_download import DownloadCancelled, _load_yt_dlp, _youtube_dl_options

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_PAGES = 10


def _object(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _cancel(event):
    if event.is_set():
        raise DownloadCancelled("Channel inspection cancelled.")


def _failure(platform, kind):
    return RuntimeError(f"{platform} profile: {kind}.")


def _read(downloader, url, platform, event, headers=None):
    from yt_dlp.networking import Request
    from yt_dlp.networking.exceptions import HTTPError, TransportError

    _cancel(event)
    try:
        response = downloader.urlopen(Request(url, headers=headers or {}))
    except HTTPError as exc:
        response = exc.response
    except TransportError as exc:
        _cancel(event)
        raise _failure(platform, "connection failed; check the network") from exc
    with response:
        host = (urlparse(response.url).hostname or "").lower()
        domains = {"Instagram": ("instagram.com",), "X": ("x.com", "twitter.com"), "Reddit": ("reddit.com",)}[platform]
        if not any(host == domain or host.endswith("." + domain) for domain in domains):
            raise _failure(platform, "unexpected redirect")
        status = response.status
        if status == 429:
            raise _failure(platform, "requests limited; try later")
        if status == 404:
            raise _failure(platform, "not found or unavailable")
        chunks, total = [], 0
        while True:
            _cancel(event)
            chunk = response.read(min(65536, MAX_RESPONSE_BYTES - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise _failure(platform, "response too large")
            chunks.append(chunk)
    _cancel(event)
    body = b"".join(chunks).decode("utf-8", errors="replace")
    if status in {401, 403}:
        raise _failure(platform, "login or access permission required")
    if status >= 400:
        raise _failure(platform, "request rejected")
    if not body.strip():
        raise _failure(platform, "empty response; access may be restricted")
    if "/accounts/login" in urlparse(response.url).path:
        raise _failure(platform, "login or access permission required")
    return body


def _json(body, platform):
    try:
        payload = json.loads(body)
    except (ValueError, RecursionError) as exc:
        raise _failure(platform, "page format changed or access restricted") from exc
    if not isinstance(payload, dict):
        raise _failure(platform, "page format changed or access restricted")
    message = str(payload.get("message") or "").lower()
    if payload.get("require_login") or any(word in message for word in ("login_required", "challenge_required", "checkpoint_required")):
        raise _failure(platform, "login or access permission required")
    if payload.get("status") == "fail" or payload.get("error"):
        raise _failure(platform, "request rejected")
    return payload


def _instagram_entry(node, username):
    if not node.get("is_video") and node.get("media_type") != 2:
        return None
    code = str(node.get("shortcode") or node.get("code") or "")
    remote_id = str(node.get("id") or node.get("pk") or code)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", code):
        return None
    caption = _object(node.get("caption")).get("text")
    if not caption:
        edges = _list(_object(node.get("edge_media_to_caption")).get("edges"))
        caption = _object(_object(edges[0]).get("node")).get("text") if edges else ""
    return {"id": remote_id, "url": f"https://www.instagram.com/p/{code}/",
            "title": caption or f"Video {code}", "uploader": username,
            "duration": node.get("video_duration") or 0,
            "timestamp": node.get("taken_at_timestamp") or node.get("taken_at"),
            "view_count": node.get("video_view_count") or node.get("play_count"),
            "thumbnail": node.get("thumbnail_src") or node.get("display_url") or ""}


def _instagram(downloader, username, limit, event):
    headers = {"X-IG-App-ID": "936619743392459",  # public web application ID, not an API key
               "Referer": f"https://www.instagram.com/{username}/", "Accept": "application/json"}
    payload = _json(_read(downloader, "https://www.instagram.com/api/v1/users/web_profile_info/?"
                         + urlencode({"username": username}), "Instagram", event, headers), "Instagram")
    user = _object(_object(payload.get("data")).get("user"))
    if not user:
        raise _failure("Instagram", "page format changed or access restricted")
    if user.get("is_private"):
        raise _failure("Instagram", "private profile")
    connection = _object(user.get("edge_owner_to_timeline_media"))
    if not isinstance(connection.get("edges"), list):
        raise _failure("Instagram", "page format changed or access restricted")
    entries, seen = [], set()
    def append(nodes):
        for node in nodes:
            entry = _instagram_entry(_object(node), username)
            if entry and entry["id"] not in seen:
                seen.add(entry["id"])
                entries.append(entry)
                if len(entries) >= limit:
                    break
    append(_object(edge).get("node") for edge in connection["edges"])
    # Continue only when the profile reports more posts. The first-party feed
    # is read with the very same cookie jar, without inventing GraphQL hashes.
    user_id = str(user.get("id") or "")
    more = bool(_object(connection.get("page_info")).get("has_next_page"))
    cursor, cursors = "", set()
    if more and user_id.isdigit():
        for _ in range(MAX_PAGES):
            if len(entries) >= limit:
                break
            query = {"count": min(50, limit)}
            if cursor:
                query["max_id"] = cursor
            feed = _json(_read(downloader, f"https://www.instagram.com/api/v1/feed/user/{user_id}/?"
                               + urlencode(query), "Instagram", event, headers), "Instagram")
            if not isinstance(feed.get("items"), list):
                raise _failure("Instagram", "page format changed or access restricted")
            append(feed["items"])
            next_cursor = str(feed.get("next_max_id") or "")
            if not feed.get("more_available") or not next_cursor or next_cursor in cursors:
                break
            cursors.add(next_cursor)
            cursor = next_cursor
    return {"title": user.get("full_name") or username, "entries": entries[:limit]}


class _NextData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.body, self.active = [], False

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = dict(attrs).get("id") == "__NEXT_DATA__"

    def handle_data(self, data):
        if self.active:
            self.body.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False


class _XPublicTimeline(HTMLParser):
    """Read rendered owner posts, not arbitrary status links in scripts/footer."""
    def __init__(self, username):
        super().__init__()
        self.username = username.lower()
        self.found = False
        self._depth = self._li_depth = 0
        self._post_id = ""
        self.video_ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            if self._depth:
                self._depth += 1
            elif str(attrs.get("id") or "").lower() == f"urt:profile:{self.username}":
                self._depth = 1
                self.found = True
        if not self._depth:
            return
        if tag == "li":
            self._li_depth += 1
            if self._li_depth == 1:
                self._post_id = ""
        if self._li_depth == 1 and not self._post_id:
            match = re.fullmatch(r"/([A-Za-z0-9_]+)/status/(\d+)", str(attrs.get("data-href") or ""))
            if match and match[1].lower() == self.username:
                self._post_id = match[2]
        if tag == "video" and self._post_id and self._post_id not in self.video_ids:
            self.video_ids.append(self._post_id)

    def handle_endtag(self, tag):
        if not self._depth:
            return
        if tag == "li":
            self._li_depth = max(0, self._li_depth - 1)
            if not self._li_depth:
                self._post_id = ""
        if tag == "div":
            self._depth -= 1


def x_public_entries(body, username, limit):
    parser = _XPublicTimeline(username)
    parser.feed(body)
    if not parser.found:
        return None
    # A quoted video can appear inside an owner's post. Require media belonging
    # to that very post as well as a rendered video element; never evaluate JS.
    own_media = set(re.findall(
        r'"?expanded_url"?\s*:\s*"https://(?:x|twitter)\.com/' + re.escape(username)
        + r'/status/(\d+)/video/\d+"', body.replace("\\/", "/"), flags=re.IGNORECASE))
    if parser.video_ids and not own_media:
        raise _failure("X", "page format changed or access restricted")
    return [{"id": video_id, "url": f"https://x.com/{username}/status/{video_id}",
             "uploader": username}
            for video_id in parser.video_ids if video_id in own_media][:limit]


def _x(downloader, username, limit, event):
    public_body = _read(downloader, f"https://x.com/{username}", "X", event, {"Accept": "text/html"})
    public_entries = x_public_entries(public_body, username, limit)
    _cancel(event)
    if public_entries is not None:
        return {"title": username, "entries": public_entries}
    # Older web responses may not carry the rendered timeline. Keep the public
    # embed as a single bounded fallback, not repeated requests on HTTP 429.
    body = _read(downloader, f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}?showReplies=false",
                 "X", event, {"Referer": f"https://twitter.com/{username}", "Accept": "text/html"})
    parser = _NextData()
    parser.feed(body)
    payload = _json("".join(parser.body), "X")
    page = _object(_object(payload.get("props")).get("pageProps"))
    user = _object(_object(page.get("headerProps")).get("user"))
    if user.get("protected"):
        raise _failure("X", "private profile")
    rows = _object(page.get("timeline")).get("entries")
    if not isinstance(rows, list):
        raise _failure("X", "page format changed or access restricted")
    entries, seen = [], set()
    for row in rows:
        _cancel(event)
        row = _object(row)
        if row.get("type") != "tweet":
            continue
        tweet = _object(_object(row.get("content")).get("tweet"))
        if tweet.get("retweeted_status"):
            continue
        author = _object(tweet.get("user"))
        if str(author.get("screen_name") or "").lower() != username.lower():
            continue
        media = _list(_object(tweet.get("extended_entities")).get("media")) or _list(_object(tweet.get("entities")).get("media"))
        videos = [item for item in media if isinstance(item, dict) and item.get("type") in {"video", "animated_gif"}]
        video_id = str(tweet.get("id_str") or "")
        if not videos or not video_id.isdigit() or video_id in seen:
            continue
        seen.add(video_id)
        try:
            date = datetime.strptime(str(tweet.get("created_at")), "%a %b %d %H:%M:%S %z %Y").strftime("%Y%m%d")
        except ValueError:
            date = ""
        entries.append({"id": video_id, "url": f"https://x.com/{username}/status/{video_id}",
                        "title": tweet.get("full_text") or f"Video {video_id}", "uploader": username,
                        "upload_date": date, "thumbnail": videos[0].get("media_url_https") or ""})
        if len(entries) >= limit:
            break
    return {"title": user.get("name") or username, "entries": entries}


def _reddit(downloader, path, limit, event):
    entries, seen, cursors = [], set(), set()
    cursor = ""
    for _ in range(MAX_PAGES):
        query = {"limit": min(100, limit), "raw_json": 1}
        if cursor:
            query["after"] = cursor
        payload = _json(_read(downloader, "https://www.reddit.com" + path + ".json?" + urlencode(query),
                              "Reddit", event, {"Accept": "application/json"}), "Reddit")
        data = _object(payload.get("data"))
        if payload.get("kind") != "Listing" or not isinstance(data.get("children"), list):
            raise _failure("Reddit", "page format changed or access restricted")
        for child in data["children"]:
            _cancel(event)
            child = _object(child)
            node = _object(child.get("data"))
            if child.get("kind") != "t3" or not node.get("is_video") or node.get("removed_by_category"):
                continue
            video = _object(_object(node.get("secure_media") or node.get("media")).get("reddit_video"))
            video_id = str(node.get("id") or "")
            permalink = str(node.get("permalink") or "")
            if not video.get("fallback_url") or not re.fullmatch(r"[a-z0-9]+", video_id) or not re.match(r"^/r/[^/]+/comments/", permalink):
                continue
            if video_id in seen:
                continue
            seen.add(video_id)
            entries.append({"id": video_id, "url": "https://www.reddit.com" + permalink,
                            "title": node.get("title") or f"Video {video_id}", "uploader": node.get("author") or "",
                            "duration": video.get("duration") or 0, "timestamp": node.get("created_utc"),
                            "thumbnail": node.get("thumbnail") if str(node.get("thumbnail") or "").startswith("https://") else ""})
            if len(entries) >= limit:
                break
        next_cursor = str(data.get("after") or "")
        if len(entries) >= limit or not next_cursor or next_cursor in cursors:
            break
        cursors.add(next_cursor)
        cursor = next_cursor
    return {"title": path.split("/")[2], "entries": entries}


def inspect_profile(url: str, platform: str, auth: dict, limit: int, event: threading.Event) -> dict:
    _cancel(event)
    parts = urlparse(url).path.strip("/").split("/")
    if platform in {"Instagram", "X"}:
        pattern = r"[A-Za-z0-9_.]{1,30}" if platform == "Instagram" else r"[A-Za-z0-9_]{1,15}"
        if len(parts) not in {1, 2} or not re.fullmatch(pattern, parts[0]) or (len(parts) == 2 and parts[1] not in {"reels", "media"}):
            raise _failure(platform, "invalid profile link")
    elif platform == "Reddit":
        if len(parts) not in {2, 3} or parts[0] not in {"r", "user", "u"} or not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", parts[1]):
            raise _failure(platform, "invalid profile link")
        allowed = {"new", "hot", "top"} if parts[0] == "r" else {"submitted"}
        if len(parts) == 3 and parts[2] not in allowed:
            raise _failure(platform, "invalid profile link")
    else:
        raise ValueError("Unsupported profile reader.")
    limit = min(1000, max(1, limit))
    with _load_yt_dlp().YoutubeDL(_youtube_dl_options(auth, impersonate=True)) as downloader:
        if platform == "Instagram":
            return _instagram(downloader, parts[0], limit, event)
        if platform == "X":
            return _x(downloader, parts[0], limit, event)
        path = (f"/r/{parts[1]}/new" if parts[0] == "r" else f"/user/{parts[1]}/submitted")
        return _reddit(downloader, path, limit, event)
