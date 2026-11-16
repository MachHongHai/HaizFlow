import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from haizflow.services import gemini_credentials as checks
from haizflow.services import gemini_translation as gemini
from haizflow.services import zernio


@pytest.mark.parametrize("payload,expected", [({"models": [{"name": "models/gemini-model"}]}, "verified"),
    ({"models": []}, "verified"), ({}, "unsupported-check"), ({"models": ["bad"]}, "unsupported-check"),
    ({"models": [{"name": None}]}, "unsupported-check"),
    ({"models": [], "error": {"code": 401}}, "invalid"),
    ({"error": {"code": 429}}, "rate-limited"),
    ({"error": {"code": 400, "details": [{"reason": "API_KEY_INVALID"}]}}, "invalid")])
def test_gemini_readonly_auth_contract(monkeypatch, payload, expected):
    opener = Mock()
    opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(checks.request, "build_opener", Mock(return_value=opener))
    assert checks.check_key("synthetic-gemini-key") == expected
    outgoing = opener.open.call_args.args[0]
    assert outgoing.get_method() == "GET" and outgoing.data is None
    assert outgoing.get_header("X-goog-api-key") == "synthetic-gemini-key"
    assert "synthetic-gemini-key" not in outgoing.full_url and "generateContent" not in outgoing.full_url
    assert outgoing.get_header("Cache-control") == "no-cache"
    assert opener.open.call_count == 1 and opener.open.call_args.kwargs["timeout"] == 15


@pytest.mark.parametrize("status,expected", [(401, "invalid"), (403, "permissions"), (429, "rate-limited"),
                                          (500, "unavailable"), (302, "unavailable"), (404, "unsupported-check")])
def test_gemini_http_errors_are_not_success(monkeypatch, status, expected):
    opener = Mock()
    opener.open.side_effect = HTTPError("https://private", status, "private", {}, io.BytesIO(b"private"))
    monkeypatch.setattr(checks.request, "build_opener", Mock(return_value=opener))
    assert checks.check_key("synthetic") == expected


@pytest.mark.parametrize("raw", [b"not json", b"x" * (checks._MAX_BYTES + 1)], ids=["malformed", "oversized"])
def test_gemini_broken_response_is_not_success(monkeypatch, raw):
    opener = Mock()
    opener.open.return_value = io.BytesIO(raw)
    monkeypatch.setattr(checks.request, "build_opener", Mock(return_value=opener))
    assert checks.check_key("synthetic") == "unavailable"


def test_gemini_timeout_is_not_success(monkeypatch):
    opener = Mock()
    opener.open.side_effect = URLError("private")
    monkeypatch.setattr(checks.request, "build_opener", Mock(return_value=opener))
    assert checks.check_key("synthetic") == "unavailable"


def test_gemini_verification_uses_named_keys_without_changing_active_key(tmp_path, monkeypatch):
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    from haizflow.desktop.translation_api_controller import TranslationApiController

    app = QGuiApplication.instance() or QGuiApplication([])
    monkeypatch.setattr(gemini, "_KEYS_PATH", tmp_path / "keys.json")
    secrets = {}
    monkeypatch.setattr(gemini.secure_credentials, "read_secret", lambda target: secrets.get(target, ""))
    monkeypatch.setattr(gemini.secure_credentials, "write_secret",
                        lambda target, value, **_kwargs: secrets.__setitem__(target, value))
    first = gemini.add_named_key("First", "first-key")
    second = gemini.add_named_key("Second", "second-key")
    host = QObject()
    controller = TranslationApiController(host)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def check(key):
        assert threading.current_thread() is not threading.main_thread()
        calls.append(key)
        entered.set()
        release.wait(2)
        return "invalid" if key == "first-key" else "verified"
    monkeypatch.setattr(checks, "check_key", check)
    assert controller.verifyGemini(first) and entered.wait(1)
    assert controller.geminiBusy and not controller.verifyGemini(second)
    release.set()
    for _ in range(100):
        app.processEvents()
        if not controller.geminiBusy:
            break
        QTest.qWait(10)
    assert not controller.geminiBusy and calls == ["first-key"]
    profiles = {row["id"]: row for row in controller.geminiProfiles}
    assert profiles[first]["check_result"] == "invalid" and profiles[second]["check_result"] == ""
    assert gemini.active_key() == "second-key"
    assert controller.verifyGemini()
    for _ in range(100):
        app.processEvents()
        if not controller.geminiBusy:
            break
        QTest.qWait(10)
    assert not controller.geminiBusy
    assert calls == ["first-key", "first-key", "second-key"]
    assert gemini.active_key() == "second-key"
    controller.invalidateGemini(second)
    assert next(row for row in controller.geminiProfiles if row["id"] == second)["check_result"] == ""
    with pytest.raises(ValueError):
        gemini.key_value("unknown-key")


@pytest.mark.parametrize("payload", [{}, {"data": {}}, {"profiles": ["bad"]},
    {"error": {"code": 401}}, {"error": "bad", "type": "authentication_error"},
    {"data": {"error": "bad", "type": "permission_error"}}, {"success": False}])
def test_zernio_malformed_or_http200_errors_cannot_verify_key(monkeypatch, payload):
    monkeypatch.setattr(zernio, "urlopen", Mock(side_effect=lambda *_args, **_kwargs:
        io.BytesIO(json.dumps(payload).encode())))
    with pytest.raises(zernio.ZernioError):
        zernio.ZernioClient("synthetic").list_profiles()


def test_zernio_valid_empty_profiles_are_not_an_error(monkeypatch):
    monkeypatch.setattr(zernio, "urlopen", Mock(side_effect=lambda *_args, **_kwargs:
        io.BytesIO(b'{"profiles":[]}')))
    assert zernio.ZernioClient("synthetic").list_profiles() == []


def test_zernio_authenticated_redirect_does_not_leak_key():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_GET(self):
            calls.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/credential-sink")
            self.end_headers()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    try:
        client = zernio.ZernioClient("synthetic", base_url=f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(zernio.ZernioError) as caught:
            client.list_profiles()
        assert caught.value.status == 302
        assert len(calls) == 1 and "/credential-sink" not in calls
    finally:
        server.shutdown()
        server.server_close()
