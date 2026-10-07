import io
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.schemas.channel_import import ChannelImportRequest
from haizflow.services import facebook_channel, video_download
from haizflow.services.channel_import import normalize_remote_url, scan_channel, validate_channel_url


VIDEO_LINKS = {
    "YouTube": "https://www.youtube.com/watch?v=demo",
    "TikTok": "https://www.tiktok.com/@creator/video/123",
    "Douyin": "https://www.douyin.com/jingxuan?modal_id=7683481325270177898",
    "Bilibili": "https://www.bilibili.com/video/BV1xx411c7mD",
    "Instagram": "https://www.instagram.com/reel/example/",
    "Facebook": "https://www.facebook.com/watch/?v=123",
    "X": "https://twitter.com/creator/status/123",
    "Reddit": "https://www.reddit.com/r/demo/comments/abc/title/",
    "Streamable": "https://streamable.com/demo",
}


@pytest.mark.parametrize("platform,url", VIDEO_LINKS.items())
def test_each_remaining_video_source_is_routed(platform, url):
    assert video_download.validate_video_url(url)[1] == platform
    with patch.object(video_download, "_load_yt_dlp"), patch.object(
        video_download, "_inspect_video_info", return_value={"title": "Clip", "duration": 20}
    ) as inspect:
        assert video_download.inspect_video_url(url).platform == platform
    assert inspect.call_count == 1


@pytest.mark.parametrize("platform,url", VIDEO_LINKS.items())
def test_each_remaining_audio_source_uses_shared_routing(tmp_path, platform, url):
    source = tmp_path / "audio.source.mp4"
    target = tmp_path / "audio.m4a"
    source.write_bytes(b"source")
    downloader = Mock()
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    module = SimpleNamespace(YoutubeDL=Mock(return_value=downloader))
    with patch.object(video_download, "_load_yt_dlp", return_value=module), patch.object(
        video_download, "_extract_video_info", return_value={}
    ) as extract, patch.object(video_download, "_downloaded_audio_path", return_value=source), patch.object(
        video_download, "_normalize_downloaded_audio", side_effect=lambda *_: target.write_bytes(b"audio")
    ):
        assert video_download.download_audio(url, str(target)) == str(target)
    assert video_download.validate_video_url(extract.call_args.args[1])[1] == platform
    assert module.YoutubeDL.call_args.args[0]["format"] == "bestaudio/best"
    assert not source.exists()


@pytest.mark.parametrize("url", ["https://vimeo.com/123", "https://dai.ly/abc", "https://www.dailymotion.com/video/abc",
                                  "https://www.twitch.tv/creator", "https://clips.twitch.tv/abc", "https://vk.com/video-123_456"])
def test_removed_sources_are_rejected_in_all_download_modes(url):
    with pytest.raises(ValueError):
        video_download.validate_video_url(url)
    with pytest.raises(ValueError):
        validate_channel_url(url)


def test_facebook_profile_identity_and_video_keys_are_preserved():
    assert validate_channel_url("https://www.facebook.com/profile.php?id=123&ref=tracking")[0] == "https://www.facebook.com/profile.php?id=123"
    assert normalize_remote_url("https://www.facebook.com/watch/?v=123&ref=tracking") != normalize_remote_url("https://www.facebook.com/watch/?v=456")


@pytest.mark.parametrize("url", ["https://user:secret@facebook.com/NASA", "https://facebook.com:123/NASA",
                                  "https://facebook.com/", "https://facebook.com/NASA/videos/123",
                                  "https://facebook.com/profile.php", "https://facebook.com.evil.example/NASA"])
def test_channel_urls_reject_invalid_or_individual_sources(url):
    with pytest.raises(ValueError):
        validate_channel_url(url)


def page_html(*nodes):
    payload = {"data": {"all_videos": {"edges": [{"node": node} for node in nodes]}}}
    # Unrelated/recommended/comment video must not become a channel candidate.
    payload["recommended"] = {"__typename": "Video", "id": "999"}
    return '<title>Page | Facebook</title><script type="application/json">' + json.dumps(payload) + '</script>'


def test_facebook_reads_only_the_page_collection_and_deduplicates():
    html = page_html({"__typename": "Video", "id": "123"}, {"__typename": "Photo", "id": "456"},
                     {"__typename": "Video", "id": "123"}, {"__typename": "Video", "id": "789", "is_live_streaming": True},
                     {"__typename": "Video", "id": "321"})
    name, entries = facebook_channel.page_video_entries(html, 10)
    assert name == "Page"
    assert [row["id"] for row in entries] == ["123", "321"]
    assert len(facebook_channel.page_video_entries(html, 1)[1]) == 1


def response_for(html, url="https://www.facebook.com/NASA/videos"):
    response = io.BytesIO(html.encode())
    response.url = url
    return response


def test_facebook_fetch_uses_existing_auth_browser_transport_and_video_tab():
    downloader = Mock()
    downloader.urlopen.return_value = response_for(page_html({"__typename": "Video", "id": "123"}))
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    module = SimpleNamespace(YoutubeDL=Mock(return_value=downloader))
    with patch.object(facebook_channel, "_load_yt_dlp", return_value=module):
        info = facebook_channel.inspect_page("https://www.facebook.com/profile.php?id=123", {"cookie_file": "explicit.txt"}, 2, threading.Event())
    assert info["entries"][0]["id"] == "123"
    assert downloader.urlopen.call_args.args[0].url.endswith("profile.php?id=123&sk=videos")
    options = module.YoutubeDL.call_args.args[0]
    assert options["cookiefile"] == "explicit.txt"
    assert str(options["impersonate"]) == "chrome"


@pytest.mark.parametrize("html,url,message", [
    ("<html>login</html>", "https://www.facebook.com/NASA/videos", "did not expose"),
    ("{}", "https://evil.example", "redirected"),
])
def test_facebook_empty_or_redirected_page_is_not_false_success(html, url, message):
    downloader = Mock()
    downloader.urlopen.return_value = response_for(html, url)
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    with patch.object(facebook_channel, "_load_yt_dlp", return_value=SimpleNamespace(YoutubeDL=Mock(return_value=downloader))):
        with pytest.raises(RuntimeError, match=message):
            facebook_channel.inspect_page("https://www.facebook.com/NASA", {}, 2, threading.Event())


def test_facebook_cancelled_before_network():
    cancel = threading.Event()
    cancel.set()
    with patch.object(facebook_channel, "_load_yt_dlp") as loader, pytest.raises(video_download.DownloadCancelled):
        facebook_channel.inspect_page("https://www.facebook.com/NASA", {}, 2, cancel)
    loader.assert_not_called()


def test_facebook_cancelled_while_reading_and_large_page_are_bounded():
    cancel = threading.Event()
    response = response_for(page_html({"__typename": "Video", "id": "123"}))
    original_read = response.read
    def read(size):
        result = original_read(size)
        cancel.set()
        return result
    response.read = read
    downloader = Mock()
    downloader.urlopen.return_value = response
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    with patch.object(facebook_channel, "_load_yt_dlp", return_value=SimpleNamespace(YoutubeDL=Mock(return_value=downloader))):
        with pytest.raises(video_download.DownloadCancelled):
            facebook_channel.inspect_page("https://www.facebook.com/NASA", {}, 2, cancel)
        downloader.urlopen.return_value = response_for("x" * 33)
        with patch.object(facebook_channel, "MAX_PAGE_BYTES", 32), pytest.raises(RuntimeError, match="too large"):
            facebook_channel.inspect_page("https://www.facebook.com/NASA", {}, 2, threading.Event())


def test_bilibili_channel_uses_video_tab_and_does_not_hide_upstream_errors():
    downloader = Mock()
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    downloader.extract_info.side_effect = RuntimeError("Request is rejected by server (352)")
    module = SimpleNamespace(YoutubeDL=Mock(return_value=downloader))
    with patch("haizflow.services.channel_import._load_yt_dlp", return_value=module), pytest.raises(RuntimeError, match="352"):
        scan_channel(ChannelImportRequest(url="https://space.bilibili.com/3985676", platform="bilibili"))
    assert downloader.extract_info.call_args.args[0] == "https://space.bilibili.com/3985676/video"
    options = module.YoutubeDL.call_args.args[0]
    assert options["ignoreerrors"] is False
    assert str(options["impersonate"]) == "chrome"


def test_instagram_upstream_failure_is_explicit_and_does_not_retry():
    downloader = Mock()
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    downloader.extract_info.side_effect = RuntimeError("[instagram:user] creator: Unable to extract data")
    module = SimpleNamespace(YoutubeDL=Mock(return_value=downloader))
    with patch("haizflow.services.channel_import._load_yt_dlp", return_value=module), pytest.raises(RuntimeError, match="Instagram profile downloads are currently unavailable"):
        scan_channel(ChannelImportRequest(url="https://instagram.com/creator", platform="instagram"))
    assert downloader.extract_info.call_count == 1


def test_save_only_can_keep_silent_video_but_project_import_stays_strict():
    with patch.object(video_download, "get_media_stream_types", return_value={"video"}):
        video_download._validate_processable_video("silent.mp4", require_audio=False)
        with pytest.raises(RuntimeError, match="audio track"):
            video_download._validate_processable_video("silent.mp4")
    strict = video_download._download_format_selector("Instagram")
    save_only = video_download._download_format_selector("Instagram", require_audio=False)
    assert save_only.startswith(strict + "/")
    assert strict.endswith("bestaudio[acodec!=none]")
    assert save_only.endswith("/bestvideo[vcodec!=none]")


def test_facebook_channel_uses_page_reader_and_hydrates_before_reporting_ready():
    request = ChannelImportRequest(url="https://www.facebook.com/NASA", platform="facebook", limit=2)
    with patch.object(facebook_channel, "inspect_page", return_value={"title": "NASA", "entries": [
        {"id": "123", "url": "https://www.facebook.com/watch/?v=123"}]}), patch(
        "haizflow.services.channel_import._extract_info_with_platform_retry", return_value={"id": "123", "duration": 40, "title": "Clip"}
    ) as hydrate:
        _, _, rows = scan_channel(request)
    assert rows[0].duration_seconds == 40
    hydrate.assert_called_once()


@pytest.mark.parametrize("platform,url", [("x", "https://x.com/creator"), ("reddit", "https://www.reddit.com/r/demo")])
def test_unsupported_collections_are_explained_not_sent_to_generic_extractor(platform, url):
    with patch("haizflow.services.channel_import._load_yt_dlp") as loader:
        with pytest.raises(RuntimeError, match="channel downloads are not supported"):
            scan_channel(ChannelImportRequest(platform=platform, url=url))
    loader.assert_not_called()
