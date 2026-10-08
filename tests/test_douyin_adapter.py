import http.cookiejar
import json
import logging
import threading
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, urlsplit

import pytest

from haizflow.services.douyin_adapter import DouyinAdapter, DouyinSession
from haizflow.services.douyin_classification import DouyinError, Outcome, classify
from haizflow.services.douyin_signing import DETAIL_PATH, POSTS_PATH, DouyinSigner, SignedRequest
from haizflow.services.douyin_transport import BrowserProfile, DouyinTransport, Response, validate_douyin_address
from haizflow.services.video_download import DownloadCancelled, VideoMetadata, download_audio, download_video
from haizflow.vendor.douyin_abogus import ABogus, decode, structure_error
from haizflow.vendor.douyin_sm3 import sm3_hexdigest

ID = "7683481325270177898"


def response(payload=None, *, status=200, body=None, url="https://www.douyin.com/"):
    return Response(status, body if body is not None else json.dumps(payload).encode(), url, {})


def detail(media="https://cdn.example/video.mp4"):
    return {"status_code": 0, "aweme_detail": {"aweme_id": ID, "desc": "captcha tutorial",
        "video": {"duration": 7000, "play_addr": {"url_list": [media]}}}}


class FakeTransport:
    def __init__(self, profile=None, replies=()):
        self.profile = profile or BrowserProfile()
        self.cookies = {"UIFID_TEMP": "visitor-secret", "s_v_web_id": "fp-secret", "msToken": "token-secret"}
        self.cookie_jar = http.cookiejar.CookieJar()
        self.replies = list(replies)
        self.calls = []
        self.closed = False

    def get(self, url, headers=None, cancel_event=None):
        self.calls.append((url, headers, cancel_event))
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("cancelled")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def import_cookies(self, cookies, *, replace=False):
        if replace:
            self.cookies.clear()
        self.cookies.update({c["name"]: c["value"] for c in cookies})

    def close(self):
        self.closed = True


def adapter_with(*replies, ready=True):
    transport = FakeTransport(replies=replies)
    session = DouyinSession(lambda profile: transport)
    session.ready = ready
    return DouyinAdapter(session), transport


@pytest.fixture(autouse=True)
def no_network_wait():
    with patch("haizflow.services.video_download._wait_for_retry"):
        yield


def test_modal_and_direct_video_reuse_the_same_session():
    adapter, transport = adapter_with(response(body=b"app shell"), response(detail()), response(detail()), ready=False)
    adapter.inspect(f"https://www.douyin.com/jingxuan?modal_id={ID}")
    adapter.inspect(f"https://www.douyin.com/video/{ID}")
    assert len(transport.calls) == 3  # bootstrap exactly once
    assert adapter.session.generation == 1
    for url, headers, _ in transport.calls[1:]:
        params = parse_qs(urlsplit(url).query)
        assert params["aweme_id"] == [ID]
        assert params["msToken"] == ["token-secret"]
        assert params["uifid"] == ["visitor-secret"]
        assert headers["uifid"] == "visitor-secret"


def test_video_channel_and_audio_inspection_share_owned_session_without_recreation():
    posts = {"aweme_list": [{"aweme_id": ID, "desc": "Video", "author": {"nickname": "Creator"},
                            "video": {"play_addr": {"url_list": ["https://cdn.example/video.mp4"]}}}],
             "has_more": 0, "max_cursor": 0}
    adapter, transport = adapter_with(response(detail()), response(posts), response(detail()))
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
                             "height": 1080, "language": "zh-CN", "cores": 8, "memory": 8},
             "cookies": []}
    adapter.session.profile = BrowserProfile.from_browser(state["fingerprint"])
    backend = Mock()
    backend.sign.return_value = SignedRequest("https://www.douyin.com/detail", {}, "browser-sdk"), state
    adapter.session.browser = backend
    from haizflow.services.douyin_adapter import get_douyin_adapter
    with patch("haizflow.services.douyin_adapter._adapter", adapter), \
         patch("haizflow.services.douyin_browser.create_anonymous_state") as create:
        get_douyin_adapter().inspect(f"https://www.douyin.com/video/{ID}")
        get_douyin_adapter({}).profile_posts("https://www.douyin.com/user/creator", limit=1)
        get_douyin_adapter().inspect(f"https://www.douyin.com/jingxuan?modal_id={ID}")
    create.assert_not_called()
    backend.close.assert_not_called()
    assert adapter.session.generation == 1 and adapter.session.transport is transport
    assert [call.args[0] for call in backend.sign.call_args_list] == [DETAIL_PATH, POSTS_PATH, DETAIL_PATH]
    assert all(not call.kwargs["refresh"] for call in backend.sign.call_args_list)


def test_short_link_redirect_is_normalized_in_same_session():
    adapter, transport = adapter_with(response(body=b"", url=f"https://www.douyin.com/jingxuan?modal_id={ID}"),
                                      response(detail()))
    assert adapter.inspect("https://v.douyin.com/share/")["aweme_id"] == ID
    assert len(transport.calls) == 2


@pytest.mark.parametrize("status,body,expected,retry", [
    (200, b"", Outcome.RISK, True), (200, b"{}", Outcome.RISK, True),
    (200, b'{"status_code":0}', Outcome.RISK, True),
    (403, b"Blocked by ArgusSecurityPlugin Uifid Not Found", Outcome.SIGNATURE, True),
    (403, b"sign invalid", Outcome.SIGNATURE, True),
    (429, b"busy", Outcome.RATE_LIMIT, True), (503, b"busy", Outcome.NETWORK, True),
    (200, b"{broken json", Outcome.UPSTREAM, False),
    (200, b'{"status_code":2053}', Outcome.UNAVAILABLE, False),
    (200, b'{"aweme_detail":null,"filter_detail":{"filter_reason":"status_self_see"}}', Outcome.UNAVAILABLE, False),
    (200, b"<html>CAPTCHA</html>", Outcome.CHALLENGE, False),
    (451, b"blocked", Outcome.UNAVAILABLE, False),
])
def test_response_classification(status, body, expected, retry):
    verdict = classify(response(status=status, body=body))
    assert verdict.outcome == expected
    assert verdict.retryable == retry


def test_successful_user_content_is_not_scanned_for_challenge_words():
    assert classify(response(detail())).outcome == Outcome.SUCCESS
    payload = detail()
    payload["filter_detail"] = {"detail_msg": "public item with filter diagnostics"}
    assert classify(response(payload)).outcome == Outcome.SUCCESS


def test_signer_receives_and_seals_one_coherent_session_context():
    profile = BrowserProfile()
    cookies = {"UIFID_TEMP": "visitor", "s_v_web_id": "verify", "msToken": "real-token"}
    signed = DouyinSigner().sign(DETAIL_PATH, {"aweme_id": ID}, cookies, profile)
    params = parse_qs(urlsplit(signed.url).query)
    assert signed.mode == "a_bogus+websign"
    assert params["fp"] == params["verifyFp"] == ["verify"]
    assert params["msToken"] == ["real-token"]
    assert params["uifid"] == ["visitor"]
    assert structure_error(params["a_bogus"][0]) is None
    assert decode(params["a_bogus"][0])["browser_info"].endswith("1920|1080|Win32")
    assert len(params["x-secsdk-web-signature"][0]) == 32
    assert cookies == {"UIFID_TEMP": "visitor", "s_v_web_id": "verify", "msToken": "real-token"}


def test_signer_never_invents_a_visitor_or_token():
    signed = DouyinSigner().sign(DETAIL_PATH, {"aweme_id": ID}, {}, BrowserProfile())
    query = parse_qs(urlsplit(signed.url).query)
    assert "msToken" not in query and "uifid" not in query and "x-secsdk-web-signature" not in query


def test_web_signature_covers_the_exact_encoded_query():
    with patch("haizflow.services.douyin_signing.ABogus") as algorithm, \
         patch("haizflow.services.douyin_signing.time.time", return_value=1700000000):
        algorithm.return_value.get_value.return_value = "fixed-bogus"
        signed = DouyinSigner().sign(DETAIL_PATH, {"aweme_id": ID},
            {"UIFID_TEMP": "visitor", "s_v_web_id": "verify", "msToken": "real-token"}, BrowserProfile())
    # Independently calculated MD5 of the protocol fixture, not an output round-trip.
    assert signed.headers["x-secsdk-web-expire"] == "1700000000"
    assert signed.headers["x-secsdk-web-signature"] == "748242245919650f1f72867d09584590"
    query = parse_qs(urlsplit(signed.url).query)
    assert query["x-secsdk-web-signature"] == [signed.headers["x-secsdk-web-signature"]]


def test_sm3_known_standard_vector_and_abogus_structure():
    assert sm3_hexdigest(b"abc") == "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    value = ABogus(BrowserProfile().ua).get_value("aid=6383&aweme_id=" + ID, now_ms=1791417600123)
    assert structure_error(value) is None
    assert decode(value)["now_ms"] == 1791417600123


def test_transport_profile_matches_ua_tls_and_redirect_headers():
    with patch("curl_cffi.requests.Session") as factory:
        client = factory.return_value
        client.get.return_value = Mock(status_code=200, content=b"{}", headers={})
        transport = DouyinTransport(BrowserProfile())
        transport.get("https://www.douyin.com/", {"uifid": "visitor"})
        factory.assert_called_once_with(impersonate="chrome136", default_headers=False)
        kwargs = client.get.call_args.kwargs
        assert "Chrome/136.0.0.0" in kwargs["headers"]["User-Agent"]
        assert kwargs["headers"]["sec-ch-ua-platform"] == '"Windows"'
        assert kwargs["verify"] is True and kwargs["allow_redirects"] is False


def test_redirect_outside_douyin_is_rejected_before_request():
    with patch("curl_cffi.requests.Session") as factory:
        factory.return_value.get.return_value = Mock(status_code=302, headers={"location": "https://evil.example/"})
        with pytest.raises(ValueError):
            DouyinTransport(BrowserProfile()).get("https://v.douyin.com/share/")
        assert factory.return_value.get.call_count == 1


@pytest.mark.parametrize("url", ["https://u:p@douyin.com/", "file:///x", "https://douyin.com.evil/",
                                "https://douyin.com:bad/", "https://douyin.com:8888/"])
def test_transport_rejects_malformed_and_untrusted_addresses(url):
    with pytest.raises(ValueError):
        validate_douyin_address(url)


def test_retry_refreshes_session_once_after_empty_response():
    adapter, transport = adapter_with(response(body=b""), response(body=b"home"), response(detail()))
    assert adapter.inspect(f"https://www.douyin.com/video/{ID}")["aweme_id"] == ID
    assert adapter.session.generation == 2
    assert [urlsplit(c[0]).path for c in transport.calls] == [DETAIL_PATH, "/", DETAIL_PATH]


@pytest.mark.parametrize("reply", [response(status=404), response({"status_code": 2053}),
                                 response(body=b"<html>captcha</html>")])
def test_terminal_failures_do_not_retry_or_use_share_fallback(reply):
    adapter, transport = adapter_with(reply)
    with pytest.raises(DouyinError):
        adapter.inspect(f"https://www.douyin.com/video/{ID}")
    assert len(transport.calls) == 1


def test_risk_retry_is_bounded_and_fallback_does_not_change_identity():
    adapter, transport = adapter_with(response(body=b""), response(body=b"home"),
        response(body=b""), response(body=b""), response(body=b"no hydration"))
    with pytest.raises(DouyinError, match="withheld"):
        adapter.inspect(f"https://www.douyin.com/video/{ID}")
    assert len(transport.calls) == 5  # 3 API, 1 warmup, 1 share page
    assert adapter.session.profile == BrowserProfile()


def test_channel_bare_envelope_is_not_treated_as_end_of_feed():
    adapter, transport = adapter_with(response({"status_code": 0}), response(body=b"home"),
        response({"status_code": 0}), response({"status_code": 0}))
    with pytest.raises(DouyinError, match="withheld"):
        adapter.profile_posts("https://www.douyin.com/user/creator", limit=20)
    assert len(transport.calls) == 4


def test_channel_pagination_uses_same_signer_and_fixes_short_duration():
    item = detail()["aweme_detail"]
    item["author"] = {"nickname": "Creator"}
    second = {**item, "aweme_id": "7683481325270177899"}
    adapter, transport = adapter_with(
        response({"status_code": 0, "aweme_list": [item], "has_more": 1, "max_cursor": 42}),
        response({"status_code": 0, "aweme_list": [second], "has_more": 0, "max_cursor": 42}))
    name, videos = adapter.profile_posts("https://www.douyin.com/user/creator", limit=2)
    assert name == "Creator" and len(videos) == 2
    assert videos[0]["duration_seconds"] == 7
    for url, headers, _ in transport.calls:
        assert urlsplit(url).path == POSTS_PATH
        assert headers["uifid"] == "visitor-secret"
    assert parse_qs(urlsplit(transport.calls[1][0]).query)["max_cursor"] == ["42"]


def test_cancellation_before_request_and_during_transport_is_preserved():
    adapter, transport = adapter_with()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DownloadCancelled):
        adapter.inspect(f"https://www.douyin.com/video/{ID}", cancel)
    assert not transport.calls
    adapter, transport = adapter_with(DownloadCancelled("cancelled"))
    with pytest.raises(DownloadCancelled):
        adapter.inspect(f"https://www.douyin.com/video/{ID}")
    assert len(transport.calls) == 1


def test_observability_does_not_log_session_values_or_signed_query(caplog):
    adapter, _ = adapter_with(response(detail()))
    with caplog.at_level(logging.INFO):
        adapter.inspect(f"https://www.douyin.com/video/{ID}")
    assert "classification=success" in caplog.text and "generation=1" in caplog.text
    for secret in ("visitor-secret", "token-secret", "fp-secret", "a_bogus=", "?aweme_id"):
        assert secret not in caplog.text


@pytest.mark.parametrize("audio_only", [False, True])
def test_expired_media_refreshes_metadata_and_downloads_new_candidate(tmp_path, caplog, audio_only):
    caplog.set_level(logging.INFO, logger="haizflow.services.douyin_adapter")
    adapter, transport = adapter_with(response(detail("https://cdn.example/old.mp4")),
                                      response(detail("https://cdn.example/new.mp4")))
    urls = []

    class Downloader:
        def __init__(self, options):
            self.params = options
            self.cookiejar = http.cookiejar.CookieJar()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def add_info_extractor(self, ie):
            self.ie = ie
            ie.set_downloader(self)
        def extract_info(self, url, **kwargs):
            info = self.ie._real_extract(url)
            urls.append(info["formats"][0]["url"])
            if len(urls) == 1:
                raise RuntimeError("HTTP Error 403: Forbidden")
            target = tmp_path / "video.mp4"
            target.write_bytes(b"fake valid media")
            return {**info, "filepath": str(target)}
        def prepare_filename(self, info): return info["filepath"]

    def parse(self, data):
        return {"id": data["aweme_id"], "title": "Video", "formats": [
            {"url": data["video"]["play_addr"]["url_list"][0]}]}

    from haizflow.services.douyin_video import HaizFlowDouyinIE
    with patch("haizflow.services.douyin_adapter.get_douyin_adapter", return_value=adapter), \
         patch("haizflow.services.video_download._load_yt_dlp", return_value=Mock(YoutubeDL=Downloader)), \
         patch.object(HaizFlowDouyinIE, "_parse_aweme_video_app", parse), \
         patch("haizflow.services.video_download._validate_processable_video"), \
         patch("haizflow.services.video_download._normalize_downloaded_audio",
               side_effect=lambda source, target, cancel: target.write_bytes(b"valid audio")):
        if audio_only:
            path = download_audio(f"https://www.douyin.com/video/{ID}", tmp_path / "audio.m4a")
        else:
            path = download_video(VideoMetadata(f"https://www.douyin.com/video/{ID}", "Video", "Douyin", 7, "", ""), str(tmp_path))
    assert Path(path).is_file()
    assert urls == ["https://cdn.example/old.mp4", "https://cdn.example/new.mp4"]
    assert len(transport.calls) == 2 and adapter.session.generation == 1
    assert "classification=media_expired http=403" in caplog.text
    assert "https://cdn.example" not in caplog.text


def test_rate_limit_respects_bounded_retry_after_without_changing_identity():
    busy = Response(429, b"busy", "https://www.douyin.com/", {"retry-after": "3600"})
    adapter, transport = adapter_with(busy, response(detail()))
    with patch("haizflow.services.video_download._wait_for_retry") as wait:
        adapter.inspect(f"https://www.douyin.com/video/{ID}")
    wait.assert_called_once_with(None, 8.0)
    assert adapter.session.generation == 1 and len(transport.calls) == 2


def test_browser_refresh_is_explicit_and_replaces_the_session_atomically():
    adapter, transport = adapter_with(response(detail()))
    adapter.inspect(f"https://www.douyin.com/video/{ID}")
    replacement = FakeTransport(replies=[response({"status_code": 5, "aweme_detail": None})])
    adapter.session.transport_factory = lambda p: replacement
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
             "height": 1080, "language": "zh-CN"}, "cookies": [{"name": "UIFID_TEMP", "value": "new", "domain": ".douyin.com"}]}
    backend = Mock()
    backend.sign.return_value = SignedRequest("https://www.douyin.com/detail", {}, "browser-sdk"), state
    state["backend"] = backend
    with patch("haizflow.services.douyin_browser.create_anonymous_state", return_value=state) as browser:
        browser.assert_not_called()
        adapter.create_browser_session()
        browser.assert_called_once_with(None, status_callback=None)
    assert adapter.session.generation == 2 and transport.closed
    assert adapter.session.transport.cookies["UIFID_TEMP"] == "new"


def test_refresh_reuses_existing_backend_and_failure_does_not_destroy_it():
    adapter, transport = adapter_with(response(detail()))
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
                             "height": 1080, "language": "zh-CN", "cores": 8, "memory": 8},
             "cookies": []}
    adapter.session.profile = BrowserProfile.from_browser(state["fingerprint"])
    backend = Mock()
    backend.sign.side_effect = [RuntimeError("The Douyin browser session could not complete the request."),
                               (SignedRequest("https://www.douyin.com/detail", {}, "browser-sdk"), state)]
    adapter.session.browser = backend
    status = Mock()
    with patch("haizflow.services.douyin_browser.create_anonymous_state") as create:
        with pytest.raises(RuntimeError):
            adapter.create_browser_session(status_callback=status)
        assert adapter.session.browser is backend and adapter.session.transport is transport
        assert adapter.session.generation == 1 and adapter.session.ready
        assert adapter.inspect(f"https://www.douyin.com/video/{ID}")["aweme_id"] == ID
    create.assert_not_called()
    backend.close.assert_not_called()
    assert [call.kwargs["refresh"] for call in backend.sign.call_args_list] == [True, False]
    status.assert_called_once_with("Douyin request succeeded")


def test_successful_refresh_reuses_backend_and_commits_transport_after_validation():
    adapter, transport = adapter_with()
    backend = Mock()
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
                             "height": 1080, "language": "zh-CN"},
             "cookies": [{"name": "UIFID_TEMP", "value": "refreshed", "domain": ".douyin.com"}]}
    backend.sign.return_value = SignedRequest("https://www.douyin.com/detail", {}, "browser-sdk"), state
    adapter.session.browser = backend
    replacement = FakeTransport(replies=[response({"status_code": 5, "aweme_detail": None})])
    adapter.session.transport_factory = Mock(return_value=replacement)
    with patch("haizflow.services.douyin_browser.create_anonymous_state") as create:
        adapter.create_browser_session()
    create.assert_not_called()
    backend.close.assert_not_called()
    assert adapter.session.browser is backend and transport.closed
    assert adapter.session.transport is replacement and adapter.session.generation == 2


def test_terminal_failure_does_not_clear_a_session_warning():
    adapter, _ = adapter_with(response(status=404))
    status = Mock()
    adapter._status_callback = status
    with pytest.raises(DouyinError):
        adapter.inspect(f"https://www.douyin.com/video/{ID}")
    status.assert_not_called()


def test_explicit_cookie_file_is_imported_once_without_mixing_identities(tmp_path):
    file = tmp_path / "guest-cookies.txt"
    file.write_text("# Netscape HTTP Cookie File\n.douyin.com\tTRUE\t/\tTRUE\t0\tUIFID_TEMP\tvisitor\n"
                    ".douyin.com\tTRUE\t/\tTRUE\t0\tsessionid\tnot-imported\n", encoding="utf-8")
    adapter, old = adapter_with()
    replacement = FakeTransport()
    replacement.cookies = {}
    factory = Mock(return_value=replacement)
    adapter.session.transport_factory = factory
    from haizflow.services.douyin_adapter import get_douyin_adapter
    with patch("haizflow.services.douyin_adapter._adapter", adapter):
        first = get_douyin_adapter({"cookie_file": str(file)})
        replacement.cookies["UIFID_TEMP"] = "refreshed-by-server"
        second = get_douyin_adapter({"cookie_file": str(file)})
    assert first is second is adapter
    factory.assert_called_once()
    assert old.closed and adapter.session.generation == 2
    assert replacement.cookies == {"UIFID_TEMP": "refreshed-by-server"}


def test_browser_version_is_adopted_with_matching_native_transport():
    values = {"userAgent": BrowserProfile(version="145.0.7632.6").ua, "platform": "Win32",
              "width": 1920, "height": 1080, "language": "zh-CN", "cores": 12, "memory": 8}
    profile = BrowserProfile.from_browser(values)
    with patch("curl_cffi.requests.Session") as factory:
        transport = DouyinTransport(profile)
        transport.close()
    factory.assert_called_once_with(impersonate="chrome145", default_headers=False)
    assert profile.major == 145 and "Chrome/145.0.7632.6" in profile.ua


def test_channel_scan_respects_budget_when_upstream_ignores_count():
    posts = [{"aweme_id": str(n), "desc": "video", "author": {"nickname": "Creator"},
              "video": {"duration": 1200, "play_addr": {"url_list": ["https://cdn.example/video.mp4"]}}}
             for n in range(10)]
    adapter, transport = adapter_with(response({"aweme_list": posts, "has_more": 1, "max_cursor": 99}))
    _, videos = adapter.profile_posts("https://www.douyin.com/user/creator", limit=2)
    assert len(videos) == 2 and len(transport.calls) == 1


def test_sdk_signed_url_is_sent_unchanged_with_scoped_browser_state(caplog):
    adapter, transport = adapter_with(response(detail()))
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
             "height": 1080, "language": "zh-CN"},
             "cookies": [{"name": "UIFID_TEMP", "value": "browser-visitor", "domain": ".douyin.com"}]}
    exact = f"https://www.douyin.com{DETAIL_PATH}?aweme_id={ID}&msToken=sealed%2B&a_bogus=signed"
    backend = Mock()
    backend.sign.return_value = SignedRequest(exact, {"uifid": "browser-visitor"}, "browser-sdk"), state
    adapter.session.browser = backend
    with caplog.at_level(logging.INFO):
        assert adapter.inspect(f"https://www.douyin.com/video/{ID}")["aweme_id"] == ID
    assert transport.calls[0][0] == exact and len(transport.calls) == 1
    backend.sign.assert_called_once_with(DETAIL_PATH, {"aweme_id": ID}, [], None, refresh=False)
    assert transport.cookies["UIFID_TEMP"] == "browser-visitor"
    assert "signer=browser-sdk" in caplog.text
    assert "browser-visitor" not in caplog.text and "sealed%2B" not in caplog.text


def test_sdk_signature_rejection_refreshes_only_on_bounded_second_attempt():
    adapter, transport = adapter_with(response(status=403, body=b'UIFIDNotFound'), response(detail()))
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
             "height": 1080, "language": "zh-CN", "cores": 8, "memory": 8}, "cookies": []}
    adapter.session.profile = BrowserProfile.from_browser(state["fingerprint"])
    backend = Mock()
    backend.sign.return_value = SignedRequest("https://www.douyin.com/detail", {}, "browser-sdk"), state
    adapter.session.browser = backend
    adapter.inspect(f"https://www.douyin.com/video/{ID}")
    assert [call.kwargs["refresh"] for call in backend.sign.call_args_list] == [False, True]
    assert len(transport.calls) == 2 and adapter.session.generation == 2


def test_cancelled_browser_replacement_closes_new_backend_and_preserves_native_jar():
    adapter, transport = adapter_with()
    backend = Mock()
    cancel = threading.Event()
    def created(*args, **kwargs):
        cancel.set()
        return {"backend": backend}
    with patch("haizflow.services.douyin_browser.create_anonymous_state", side_effect=created), \
         pytest.raises(DownloadCancelled):
        adapter.create_browser_session(cancel)
    backend.close.assert_called_once()
    assert adapter.session.transport is transport and not transport.closed


def test_douyin_ytdlp_never_reads_an_ambient_browser_profile_or_unscoped_cookie_file():
    from haizflow.services.video_download import _inspect_video_info, _ytdlp_auth_for_url
    auth = {"cookie_browser": "chrome", "cookie_file": "explicit-cookies.txt"}
    fake = MagicMock()
    with patch("haizflow.services.video_download._extract_video_info", return_value={}) as extract:
        _inspect_video_info(fake, f"https://www.douyin.com/video/{ID}", auth=auth)
    options = fake.YoutubeDL.call_args.args[0]
    assert "cookiesfrombrowser" not in options and "cookiefile" not in options
    assert extract.call_args.kwargs["auth"] is auth  # adapter validates/imports explicitly
    assert _ytdlp_auth_for_url(auth, "https://www.youtube.com/watch?v=test") is auth


def test_imported_guest_cookies_retain_secure_domain_and_expiry():
    transport = DouyinTransport(BrowserProfile())
    try:
        transport.import_cookies([
            {"name": "guest", "value": "value", "domain": ".douyin.com", "path": "/",
             "secure": True, "httpOnly": True, "expires": 4102444800},
            {"name": "expired", "value": "ignored", "domain": ".douyin.com", "expires": 1},
            {"name": "unrelated", "value": "ignored", "domain": ".evil-douyin.com"}])
        cookies = list(transport.cookie_jar)
        assert len(cookies) == 1 and cookies[0].secure
        assert cookies[0].domain == ".douyin.com" and cookies[0].expires == 4102444800
        assert cookies[0].has_nonstandard_attr("HttpOnly")
    finally:
        transport.close()


def test_personal_browser_setting_does_not_override_owned_guest_session():
    adapter, transport = adapter_with()
    from haizflow.services.douyin_adapter import get_douyin_adapter
    with patch("haizflow.services.douyin_adapter._adapter", adapter):
        assert get_douyin_adapter({"cookie_browser": "chrome"}) is adapter
    assert adapter.session.transport is transport


def test_same_cookie_file_cannot_overwrite_a_new_explicit_browser_session(tmp_path):
    file = tmp_path / "guest-cookies.txt"
    file.write_text("# Netscape HTTP Cookie File\n.douyin.com\tTRUE\t/\tTRUE\t0\tUIFID_TEMP\tfrom-file\n",
                    encoding="utf-8")
    adapter, _ = adapter_with()
    replacements = [FakeTransport(), FakeTransport(replies=[response({"status_code": 5, "aweme_detail": None})])]
    adapter.session.transport_factory = Mock(side_effect=replacements)
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
             "height": 1080, "language": "zh-CN"},
             "cookies": [{"name": "UIFID_TEMP", "value": "new-guest", "domain": ".douyin.com"}]}
    backend = Mock()
    backend.sign.return_value = SignedRequest("https://www.douyin.com/detail", {}, "browser-sdk"), state
    state["backend"] = backend
    from haizflow.services.douyin_adapter import get_douyin_adapter
    with patch("haizflow.services.douyin_adapter._adapter", adapter), \
         patch("haizflow.services.douyin_browser.create_anonymous_state", return_value=state):
        get_douyin_adapter({"cookie_file": str(file)})
        adapter.create_browser_session()
        get_douyin_adapter({"cookie_file": str(file)})
    assert adapter.session.transport_factory.call_count == 2
    assert adapter.session.transport.cookies["UIFID_TEMP"] == "new-guest"


def test_first_channel_signing_failure_recovers_within_one_preview_call():
    posts = {"aweme_list": [detail()["aweme_detail"]], "has_more": 0, "max_cursor": 0}
    adapter, transport = adapter_with(response(posts))
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
                             "height": 1080, "language": "zh-CN", "cores": 8, "memory": 8},
             "cookies": []}
    adapter.session.profile = BrowserProfile.from_browser(state["fingerprint"])
    backend = Mock()
    backend.sign.side_effect = [DouyinError(Outcome.NETWORK),
                               (SignedRequest("https://www.douyin.com/posts", {}, "browser-sdk"), state)]
    adapter.session.browser = backend
    status = Mock()
    adapter._status_callback = status
    _, videos = adapter.profile_posts("https://www.douyin.com/user/demo", limit=1)
    assert len(videos) == 1 and len(transport.calls) == 1
    assert [c.kwargs["refresh"] for c in backend.sign.call_args_list] == [False, True]
    backend.close.assert_not_called()
    status.assert_called_once_with("Douyin request succeeded")


@pytest.mark.parametrize("reply", [response(body=b""), response(status=403, body=b"sign invalid"),
                                 response({"status_code": 5, "aweme_detail": None, "captcha": "verify_page"})])
def test_browser_creation_requires_endpoint_verification_and_preserves_old_jar(reply):
    adapter, old = adapter_with()
    new = FakeTransport(replies=[reply, reply, reply, reply])
    adapter.session.transport_factory = Mock(return_value=new)
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
                             "height": 1080, "language": "zh-CN", "cores": 8, "memory": 8},
             "cookies": [{"name": "UIFID_TEMP", "value": "candidate", "domain": ".douyin.com"}]}
    backend = Mock()
    backend.sign.return_value = SignedRequest("https://www.douyin.com/detail", {}, "browser-sdk"), state
    state["backend"] = backend
    status = Mock()
    with patch("haizflow.services.douyin_browser.create_anonymous_state", return_value=state), pytest.raises(DouyinError):
        adapter.create_browser_session(status_callback=status)
    assert adapter.session.transport is old and not old.closed
    assert new.closed and adapter.session.browser is None
    backend.close.assert_called_once()
    assert "Douyin session ready" not in [c.args[0] for c in status.call_args_list]


def test_probe_unknown_video_is_not_accepted_as_a_successful_normal_inspection():
    adapter, _ = adapter_with(response({"status_code": 5, "aweme_detail": None}))
    with pytest.raises(DouyinError) as failure:
        adapter.inspect(f"https://www.douyin.com/video/{ID}")
    assert failure.value.outcome == Outcome.METADATA


def test_browser_snapshot_replaces_removed_native_cookies_within_domain_only():
    transport = DouyinTransport(BrowserProfile())
    try:
        transport.import_cookies([
            {"name": "stale", "value": "old", "domain": ".douyin.com"},
            {"name": "other", "value": "preserved", "domain": ".iesdouyin.com"}])
        transport.import_cookies([{"name": "UIFID_TEMP", "value": "current", "domain": ".douyin.com"}], replace=True)
        assert transport.cookies == {"other": "preserved", "UIFID_TEMP": "current"}
    finally:
        transport.close()


def test_exhausted_session_rejection_clears_false_ready_status():
    adapter, _ = adapter_with(*[response(status=403, body=b"sign invalid")] * 3)
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
                             "height": 1080, "language": "zh-CN", "cores": 8, "memory": 8}, "cookies": []}
    adapter.session.profile = BrowserProfile.from_browser(state["fingerprint"])
    backend = Mock()
    backend.sign.return_value = SignedRequest("https://www.douyin.com/posts", {}, "browser-sdk"), state
    adapter.session.browser = backend
    status = Mock()
    adapter._status_callback = status
    with pytest.raises(DouyinError):
        adapter.profile_posts("https://www.douyin.com/user/demo", limit=1)
    assert not adapter.session.ready
    status.assert_called_once_with("Douyin session needs refresh")
    backend.close.assert_not_called()


def test_verified_creation_parks_browser_and_preview_uses_native_signing_only():
    posts = {"aweme_list": [detail()["aweme_detail"]], "has_more": 0, "max_cursor": 0}
    adapter, old = adapter_with()
    new = FakeTransport(replies=[response({"status_code": 5, "aweme_detail": None}),
                                 response(posts), response(detail())])
    adapter.session.transport_factory = Mock(return_value=new)
    backend = Mock()
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
                             "height": 1080, "language": "zh-CN", "cores": 8, "memory": 8},
             "cookies": [{"name": "UIFID_TEMP", "value": "created-guest", "domain": ".douyin.com"}],
             "backend": backend}
    with patch("haizflow.services.douyin_browser.create_anonymous_state", return_value=state) as create:
        adapter.create_browser_session()
        backend.park.assert_called_once_with()
        assert adapter.session.native_verified and old.closed
        _, candidates = adapter.profile_posts("https://www.douyin.com/user/demo", limit=1)
        assert len(candidates) == 1
        adapter.inspect(f"https://www.douyin.com/video/{ID}")
        create.assert_called_once()
    backend.sign.assert_not_called()
    backend.open.assert_not_called()
    assert all("a_bogus=" in c[0] for c in new.calls)


def test_native_session_failure_never_automatically_opens_chromium():
    adapter, transport = adapter_with(response(status=403, body=b"sign invalid"), response(body=b"shell"),
                                      response(status=403, body=b"sign invalid"), response(status=403, body=b"sign invalid"))
    adapter.session.browser = Mock()
    adapter.session.native_verified = True
    with pytest.raises(DouyinError):
        adapter.profile_posts("https://www.douyin.com/user/demo", limit=1)
    adapter.session.browser.sign.assert_not_called()
    adapter.session.browser.open.assert_not_called()
    assert not adapter.session.ready
    assert len(transport.calls) == 4


def test_failed_native_probe_never_parks_browser_or_commits_candidate():
    adapter, old = adapter_with()
    new = FakeTransport(replies=[response({"status_code": 5, "aweme_detail": None, "captcha": "verify_page"})])
    adapter.session.transport_factory = Mock(return_value=new)
    backend = Mock()
    state = {"fingerprint": {"userAgent": BrowserProfile().ua, "platform": "Win32", "width": 1920,
                             "height": 1080, "language": "zh-CN"},
             "cookies": [{"name": "UIFID_TEMP", "value": "guest", "domain": ".douyin.com"}], "backend": backend}
    with patch("haizflow.services.douyin_browser.create_anonymous_state", return_value=state), pytest.raises(DouyinError):
        adapter.create_browser_session()
    backend.park.assert_not_called()
    backend.close.assert_called_once()
    assert adapter.session.transport is old and not adapter.session.native_verified
