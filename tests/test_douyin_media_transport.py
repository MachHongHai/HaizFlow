"""Exercise Douyin media requests through real yt-dlp/curl, without Douyin I/O."""
import http.cookiejar
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yt_dlp
from yt_dlp.networking._curlcffi import CurlCFFIRH
from yt_dlp.utils import ExtractorError

from haizflow.schemas.channel_import import ChannelImportRequest, ChannelVideoCandidate
from haizflow.services import video_download
from haizflow.services.channel_import import download_candidate
from haizflow.services.douyin_transport import BrowserProfile
from haizflow.services.douyin_video import HaizFlowDouyinIE, media_impersonate_target

VIDEO_ID = "7683481325270177898"
VIDEO_URL = f"https://www.douyin.com/video/{VIDEO_ID}"


@pytest.mark.parametrize("major,expected", [(136, "chrome-136"), (145, "chrome-145"), (157, "chrome-150")])
def test_media_target_matches_metadata_transport_and_keeps_original_ua(major, expected):
    profile = BrowserProfile(major=major, version=f"{major}.0.0.0")
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as downloader:
        before = downloader.params.get("impersonate")
        assert media_impersonate_target(profile, downloader) == expected
        assert downloader.params.get("impersonate") == before
    assert profile.transport_mode == expected.replace("-", "")
    assert f"Chrome/{major}." in profile.ua


@pytest.mark.parametrize("available", [False, None])
def test_missing_handler_reports_actionable_error_not_keyerror(available):
    downloader = Mock()
    downloader._impersonate_target_available.return_value = available
    with pytest.raises(ExtractorError, match="Chrome 150.*cập nhật"):
        media_impersonate_target(BrowserProfile(major=157), downloader)


def test_unknown_browser_version_does_not_silently_rotate_to_another_profile():
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as downloader:
        with pytest.raises(ExtractorError, match="Chrome 999"):
            media_impersonate_target(BrowserProfile(major=999), downloader)


@pytest.mark.parametrize("entrypoint", ["video", "channel", "audio"])
@pytest.mark.parametrize("retry_profile", [False, True])
@pytest.mark.parametrize("cached_director", [False, True])
def test_real_media_download_uses_supported_request_target(
    tmp_path, monkeypatch, entrypoint, retry_profile, cached_director,
):
    payload = b"media-bytes" * 8192
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            requests.append(dict(self.headers))
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    profile = BrowserProfile(major=157, version="157.0.0.0")
    jar = http.cookiejar.CookieJar()
    jar.set_cookie(http.cookiejar.Cookie(
        0, "session-test", "private-value", None, False, ".douyin.com", True, True,
        "/", True, True, None, True, None, None, {}, False,
    ))
    adapter = SimpleNamespace(
        inspect=Mock(return_value={"aweme_id": VIDEO_ID}),
        session=SimpleNamespace(
            lock=threading.RLock(), profile=profile,
            transport=SimpleNamespace(cookie_jar=jar),
        ),
    )
    instances = []
    real_downloader = yt_dlp.YoutubeDL
    options_for = video_download._youtube_dl_options

    def downloader_factory(options):
        options = {**options_for(impersonate=retry_profile), **options, "proxy": ""}
        if retry_profile:
            options["impersonate"] = options_for(impersonate=True)["impersonate"]
        downloader = real_downloader(options)
        # A curl-only director exposes the original unsupported-global-target
        # KeyError instead of allowing unrelated handlers to mask it. Exercise
        # both lazy construction and handlers cached before extraction.
        previous = downloader.__dict__.pop("_request_director", None)
        if previous is not None:
            previous.close()
        build_director = downloader.build_request_director
        downloader.build_request_director = lambda _handlers, preferences=None: build_director(
            [CurlCFFIRH], preferences)
        if cached_director:
            _ = downloader._request_director
        instances.append((downloader, downloader.params.get("impersonate")))
        return downloader

    def parse(_self, detail):
        return {
            "id": detail["aweme_id"], "title": "Clip", "duration": 7,
            "formats": [{
                "url": f"http://127.0.0.1:{server.server_port}/media.mp4",
                "ext": "mp4", "protocol": "http", "vcodec": "h264", "acodec": "aac",
                "height": 720, "filesize": len(payload),
            }],
        }

    monkeypatch.setattr("haizflow.services.douyin_adapter.get_douyin_adapter", lambda _auth=None: adapter)
    monkeypatch.setattr(video_download, "_load_yt_dlp", lambda: SimpleNamespace(YoutubeDL=downloader_factory))
    monkeypatch.setattr(HaizFlowDouyinIE, "_parse_aweme_video_app", parse)
    monkeypatch.setattr(video_download, "_validate_processable_video", Mock())
    monkeypatch.setattr(
        video_download, "_normalize_downloaded_audio",
        lambda source, target, _cancel: target.write_bytes(source.read_bytes()),
    )
    cancel = threading.Event()
    try:
        if entrypoint == "channel":
            candidate = ChannelVideoCandidate(remote_video_id=VIDEO_ID, source_url=VIDEO_URL,
                                               title="Clip", platform="Douyin", duration_seconds=7)
            request = ChannelImportRequest(url="https://www.douyin.com/user/test", platform="douyin")
            output = download_candidate(candidate, request, str(tmp_path), None, cancel)
        elif entrypoint == "audio":
            output = video_download.download_audio(VIDEO_URL, tmp_path / "audio.m4a", cancel_event=cancel)
        else:
            metadata = video_download.VideoMetadata(VIDEO_URL, "Clip", "Douyin", 7, "", "")
            output = video_download.download_video(metadata, str(tmp_path), cancel_event=cancel)
        assert Path(output).read_bytes() == payload
        assert len(instances) == 1  # No error-masking retry or profile rotation.
        for downloader, initial_target in instances:
            assert downloader.params.get("impersonate") == initial_target
        assert requests and all(headers["User-Agent"] == profile.ua for headers in requests)
        assert all(headers["Referer"] == "https://www.douyin.com/" for headers in requests)
        assert all("Cookie" not in headers for headers in requests)
        assert not list(tmp_path.glob("*.source.*"))
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
