import io
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.services import social_channel as social
from haizflow.services.video_download import DownloadCancelled


def response(body, url="https://www.instagram.com/api/v1/", status=200):
    stream = io.BytesIO(body.encode() if isinstance(body, str) else json.dumps(body).encode())
    stream.url, stream.status = url, status
    stream.reason = "Test response"
    return stream


def run(platform, url, responses, limit=3, event=None):
    downloader = Mock()
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    downloader.urlopen.side_effect = responses
    module = SimpleNamespace(YoutubeDL=Mock(return_value=downloader))
    with patch.object(social, "_load_yt_dlp", return_value=module):
        result = social.inspect_profile(url, platform, {"cookie_file": "chosen.txt"}, limit, event or threading.Event())
    assert str(module.YoutubeDL.call_args.args[0]["impersonate"]) == "chrome"
    assert module.YoutubeDL.call_args.args[0]["cookiefile"] == "chosen.txt"
    return result, downloader


def ig_node(code="clip", **extra):
    return {"id": code, "shortcode": code, "is_video": True, "video_duration": 10,
            "taken_at_timestamp": 1700000000, **extra}


def ig_profile(nodes, more=False, **extra):
    return {"data": {"user": {"id": "123", "full_name": "Creator", **extra,
            "edge_owner_to_timeline_media": {"edges": [{"node": node} for node in nodes],
                                             "page_info": {"has_next_page": more}}}}}


def test_instagram_reads_owner_videos_and_feed_using_one_session():
    profile = ig_profile([ig_node(), ig_node("photo", is_video=False)], more=True)
    feed = {"items": [{"pk": "second", "code": "reel", "media_type": 2,
                       "taken_at": 1700000001, "video_duration": 9}], "more_available": False}
    result, downloader = run("Instagram", "https://instagram.com/creator", [response(profile), response(feed)])
    assert [row["id"] for row in result["entries"]] == ["clip", "second"]
    assert result["entries"][1]["url"] == "https://www.instagram.com/p/reel/"
    assert downloader.urlopen.call_count == 2
    requests = [call.args[0] for call in downloader.urlopen.call_args_list]
    assert "feed/user/123/" in requests[1].url
    assert all(request.headers["X-IG-App-ID"] == "936619743392459" for request in requests)


def test_instagram_stops_repeating_feed_cursor_and_deduplicates():
    profile = ig_profile([], more=True)
    feed = {"items": [{"pk": "second", "code": "reel", "media_type": 2}],
            "more_available": True, "next_max_id": "same"}
    result, downloader = run("Instagram", "https://instagram.com/creator/reels", [response(profile), response(feed), response(feed)])
    assert len(result["entries"]) == 1 and downloader.urlopen.call_count == 3


def test_instagram_does_not_retry_private_or_login_required():
    for payload in (ig_profile([], is_private=True), {"require_login": True, "status": "fail"}):
        with pytest.raises(RuntimeError, match="private profile|permission required"):
            run("Instagram", "https://instagram.com/creator", [response(payload)])


def x_document(tweets, protected=False):
    payload = {"props": {"pageProps": {"headerProps": {"user": {"name": "Creator", "protected": protected}},
               "timeline": {"entries": [{"type": "tweet", "content": {"tweet": row}} for row in tweets]}}}}
    return "<html><script type='application/json' id='__NEXT_DATA__'>" + json.dumps(payload) + "</script></html>"


def tweet(video_id="123", username="creator", kind="video", **extra):
    return {"id_str": video_id, "user": {"screen_name": username}, "full_text": "Clip",
            "created_at": "Tue Nov 14 22:13:20 +0000 2023",
            "extended_entities": {"media": [{"type": kind, "media_url_https": "https://pbs.twimg.com/a.jpg"}]}, **extra}


def test_x_reads_only_original_owner_video_tweets_from_initial_embed():
    rows = [tweet(), tweet(), tweet("124", kind="photo"), tweet("125", username="other"),
            tweet("126", retweeted_status={"id_str": "retweet"}), tweet("127", kind="animated_gif")]
    result, downloader = run("X", "https://twitter.com/creator/media",
                             [response("<html>Legacy shell</html>", "https://x.com/creator"),
                              response(x_document(rows), "https://syndication.twitter.com/srv/timeline-profile/screen-name/creator")])
    assert [row["id"] for row in result["entries"]] == ["123", "127"]
    assert result["entries"][0]["url"] == "https://x.com/creator/status/123"
    assert result["entries"][0]["upload_date"] == "20231114"
    assert downloader.urlopen.call_count == 2


def test_x_protected_and_changed_shell_not_successful_empty_timeline():
    for body, match in ((x_document([], True), "private profile"), ("<html>Welcome</html>", "format changed")):
        with pytest.raises(RuntimeError, match=match):
            run("X", "https://x.com/creator", [response("<html>Legacy shell</html>", "https://x.com/creator"),
                                                response(body, "https://syndication.twitter.com/")])


def test_x_public_rendered_timeline_avoids_limited_embed_and_excludes_quotes_and_footer():
    body = '''<script>expanded_url:"https://x.com/creator/status/123/video/1";
        expanded_url:"https://x.com/other/status/124/video/1";
        expanded_url:"https://x.com/creator/status/999/video/1";</script>
        <div id="urt:profile:creator"><ul>
        <li><div data-href="/creator/status/123"><article><video></video></article></div></li>
        <li><div data-href="/creator/status/124"><article><video></video></article></div></li>
        <li><div data-href="/creator/status/125"><article><img src="photo.jpg"></article></div></li>
        </ul></div><div data-href="/creator/status/999"><video></video></div>'''
    result, downloader = run("X", "https://x.com/creator", [response(body, "https://x.com/creator")])
    assert [row["id"] for row in result["entries"]] == ["123"]
    assert downloader.urlopen.call_count == 1


def test_x_empty_valid_timeline_does_not_retry_another_endpoint():
    result, downloader = run("X", "https://x.com/creator", [response('<div id="urt:profile:creator"><ul></ul></div>', "https://x.com/creator")])
    assert not result["entries"] and downloader.urlopen.call_count == 1


def reddit_post(video_id="abc", **extra):
    return {"kind": "t3", "data": {"id": video_id, "permalink": f"/r/demo/comments/{video_id}/title/",
             "is_video": True, "created_utc": 1700000000, "title": "Clip", "author": "Creator",
             "secure_media": {"reddit_video": {"duration": 20, "fallback_url": "https://v.redd.it/a/DASH_720.mp4"}}, **extra}}


def listing(rows, after=None):
    return {"kind": "Listing", "data": {"children": rows, "after": after}}


@pytest.mark.parametrize("profile,endpoint", [("/r/demo", "/r/demo/new.json"),
                                              ("/u/creator", "/user/creator/submitted.json"),
                                              ("/user/creator/submitted", "/user/creator/submitted.json")])
def test_reddit_channel_and_user_read_native_videos_with_bounded_paging(profile, endpoint):
    bodies = [listing([reddit_post(), reddit_post("photo", is_video=False), reddit_post("removed", removed_by_category="deleted")], "t3_abc"),
              listing([reddit_post(), reddit_post("def")])]
    result, downloader = run("Reddit", "https://www.reddit.com" + profile,
                             [response(body, "https://www.reddit.com" + endpoint) for body in bodies])
    assert [row["id"] for row in result["entries"]] == ["abc", "def"]
    assert endpoint in downloader.urlopen.call_args_list[0].args[0].url
    assert "after=t3_abc" in downloader.urlopen.call_args_list[1].args[0].url


def test_reddit_cursor_loop_and_page_cap_do_not_loop_forever():
    empty = listing([], "same")
    result, downloader = run("Reddit", "https://reddit.com/r/demo", [response(empty, "https://www.reddit.com/") for _ in range(2)])
    assert result["entries"] == [] and downloader.urlopen.call_count == 2
    with patch.object(social, "MAX_PAGES", 2):
        result, downloader = run("Reddit", "https://reddit.com/r/demo", [response(listing([], "cursor" + str(i)), "https://www.reddit.com/") for i in range(2)])
        assert result["entries"] == [] and downloader.urlopen.call_count == 2


@pytest.mark.parametrize("status,match", [(429, "requests limited"), (403, "permission required"),
                                         (404, "not found"), (500, "request rejected")])
def test_http_status_is_classified_once_without_blind_retry(status, match):
    downloader = Mock()
    downloader.urlopen.return_value = response("blocked", "https://www.reddit.com/", status)
    with pytest.raises(RuntimeError, match=match):
        social._read(downloader, "https://www.reddit.com/r/demo/new.json", "Reddit", threading.Event())
    assert downloader.urlopen.call_count == 1


def test_http_exception_response_is_also_classified():
    from yt_dlp.networking.exceptions import HTTPError
    downloader = Mock()
    downloader.urlopen.side_effect = HTTPError(response("blocked", "https://syndication.twitter.com/", 429))
    with pytest.raises(RuntimeError, match="requests limited"):
        social._read(downloader, "https://syndication.twitter.com/", "X", threading.Event())


@pytest.mark.parametrize("body", ["", "<html>Blocked</html>", "null", "[]", "{broken"])
def test_empty_html_and_malformed_payload_are_not_valid_reddit_listings(body):
    with pytest.raises(RuntimeError, match="empty response|format changed"):
        run("Reddit", "https://reddit.com/r/demo", [response(body, "https://www.reddit.com/")])


def test_cancellation_and_size_limits_apply_during_reads():
    downloader = Mock()
    event = threading.Event()
    stream = response("x" * 100, "https://www.reddit.com/")
    original = stream.read
    def read(size):
        value = original(size)
        event.set()
        return value
    stream.read = read
    downloader.urlopen.return_value = stream
    with pytest.raises(DownloadCancelled):
        social._read(downloader, stream.url, "Reddit", event)
    downloader.urlopen.return_value = response("x" * 100, "https://www.reddit.com/")
    with patch.object(social, "MAX_RESPONSE_BYTES", 32), pytest.raises(RuntimeError, match="too large"):
        social._read(downloader, "https://www.reddit.com/", "Reddit", threading.Event())


@pytest.mark.parametrize("platform,url", [("X", "https://x.com/home" + "/status/123"),
                                         ("Instagram", "https://instagram.com/p/clip"),
                                         ("Reddit", "https://reddit.com/r/demo/comments/abc")])
def test_invalid_profile_does_not_make_network_request(platform, url):
    with patch.object(social, "_load_yt_dlp") as loader, pytest.raises(RuntimeError, match="invalid profile"):
        social.inspect_profile(url, platform, {}, 2, threading.Event())
    loader.assert_not_called()


def test_foreign_redirect_is_not_parsed():
    downloader = Mock()
    downloader.urlopen.return_value = response({}, "https://reddit.com.evil.example/")
    with pytest.raises(RuntimeError, match="unexpected redirect"):
        social._read(downloader, "https://www.reddit.com/", "Reddit", threading.Event())


def test_network_failure_is_readable_and_late_cancellation_takes_priority():
    from yt_dlp.networking.exceptions import TransportError
    downloader = Mock()
    event = threading.Event()
    downloader.urlopen.side_effect = TransportError("DNS failure")
    with pytest.raises(RuntimeError, match="connection failed"):
        social._read(downloader, "https://www.reddit.com/", "Reddit", event)
    def cancel_then_fail(_request):
        event.set()
        raise TransportError("DNS failure")
    downloader.urlopen.side_effect = cancel_then_fail
    with pytest.raises(DownloadCancelled):
        social._read(downloader, "https://www.reddit.com/", "Reddit", event)
