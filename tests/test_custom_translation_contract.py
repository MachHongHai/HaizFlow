"""Custom Chat-Completions adapters tested without external accounts or keys."""
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from haizflow.services import api_translation as api
from haizflow.services import translation_connections as connections


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(connections, "_PATH", tmp_path / "connections.json")
    secrets = {}
    monkeypatch.setattr(connections.secure_credentials, "write_secret",
                        lambda target, value, **_kwargs: secrets.__setitem__(target, value))
    monkeypatch.setattr(connections.secure_credentials, "read_secret", lambda target: secrets.get(target, ""))
    monkeypatch.setattr(api, "check_cancellation", lambda *_: None)
    monkeypatch.setattr(api, "log_to_video", Mock())
    monkeypatch.setattr(api.gemini_translation, "check_cancellation", lambda *_: None)
    monkeypatch.setattr(api.gemini_translation, "log_to_video", Mock())
    return secrets


@pytest.mark.parametrize("output_format", ["json_schema", "json_object", "prompt"])
def test_real_custom_http_format_unicode_and_id_contract_without_model_discovery(isolated, output_format):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_GET(self):
            calls.append(("GET", self.path))
            self.send_response(404)  # Discovery is optional on custom servers.
            self.end_headers()
        def do_POST(self):
            calls.append(("POST", self.path))
            assert self.path == "/gateway/v1/chat/completions"
            assert self.headers["Authorization"] == "Bearer synthetic-private"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert payload["model"] == "Vendor/MixedCase:latest"
            assert not {"reasoning", "thinking", "provider", "tools", "audio", "store"} & payload.keys()
            assert "max_tokens" not in payload
            if output_format == "prompt":
                assert "response_format" not in payload
            else:
                assert payload["response_format"]["type"] == output_format
            if output_format != "json_schema":
                assert '{"translations":[{"id":0,"text":"translated subtitle"}]}' in payload["messages"][0]["content"]
            entries, _end = json.JSONDecoder().raw_decode(payload["messages"][1]["content"])
            text = json.dumps({"translations": [{"id": e["id"], "text": f"Câu {e['id']}: 日本語, 한국어, Español."}
                                                 for e in reversed(entries)]}, ensure_ascii=False)
            raw = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": text}}]},
                             ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    try:
        identifier = connections.add("custom", "Local fixture", "synthetic-private", "Vendor/MixedCase:latest",
            f"http://127.0.0.1:{server.server_port}/gateway/v1", output_format)
        choice = "api:" + identifier
        assert api.check_connection(choice, model_required=False) == "unsupported-check"
        output = api.translate_texts([f"Sentence {i}." for i in range(25)], model=choice,
                                     source_language="English", target_language="Vietnamese", video_id="")
        assert output == [f"Câu {i}: 日本語, 한국어, Español." for i in range(25)]
        assert calls == [("GET", "/gateway/v1/models"), ("POST", "/gateway/v1/chat/completions"),
                         ("POST", "/gateway/v1/chat/completions")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 408, 429, 500, 502, 503, 504])
@pytest.mark.parametrize("output_format", ["json_schema", "json_object", "prompt"])
def test_custom_failed_posts_never_retry_or_guess_another_format(isolated, monkeypatch, status, output_format):
    identifier = connections.add("custom", "A", "synthetic-private", "Reasoner-New", "https://example.invalid/v1", output_format)
    send = Mock(side_effect=HTTPError("https://example.invalid", status, "PRIVATE BODY", {}, io.BytesIO(b"secret")))
    monkeypatch.setattr(api, "_json_request", send)
    saved = Mock()
    with pytest.raises(RuntimeError) as caught:
        api.translate_texts(["Hello."], model="api:" + identifier, source_language="English",
                            target_language="Vietnamese", video_id="", result_callback=saved)
    assert send.call_count == 1 and str(status) in str(caught.value)
    assert "PRIVATE" not in str(caught.value) and "synthetic-private" not in str(caught.value)
    saved.assert_not_called()


@pytest.mark.parametrize("suffix", ["/chat/completions", "/responses", "/chat/completions/"])
def test_full_request_endpoint_is_not_silently_treated_as_base_url(isolated, monkeypatch, suffix):
    write = Mock()
    monkeypatch.setattr(connections.secure_credentials, "write_secret", write)
    with pytest.raises(ValueError, match="Base URL"):
        connections.add("custom", "Wrong base", "synthetic", "model", "https://example.invalid/v1" + suffix)
    write.assert_not_called()


def test_custom_failure_keeps_completed_cues_and_does_not_retranslate_them(isolated, monkeypatch):
    identifier = connections.add("custom", "A", "synthetic", "vendor-model", "https://example.invalid/v1", "prompt")
    seen = []
    def send(url, key, payload, **kwargs):
        entries, _end = json.JSONDecoder().raw_decode(payload["messages"][1]["content"])
        seen.extend(e["id"] for e in entries)
        if len(seen) > 24:
            raise HTTPError(url, 503, "private", {}, io.BytesIO(b"private"))
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"translations": [
            {"id": e["id"], "text": f"Câu {e['id']}."} for e in entries]})}}]}
    request = Mock(side_effect=send)
    monkeypatch.setattr(api, "_json_request", request)
    checkpoint = [None] * 25
    def save(indices, values):
        for i, value in zip(indices, values):
            checkpoint[i] = value
    with pytest.raises(RuntimeError, match="503"):
        api.translate_texts([f"Line {i}." for i in range(25)], model="api:" + identifier, source_language="English",
                            target_language="Vietnamese", video_id="", result_callback=save)
    assert request.call_count == 2 and seen == list(range(25))
    assert all(checkpoint[:24]) and checkpoint[24] is None
    seen.clear()
    assert api.translate_texts([f"Line {i}." for i in range(25)], model="api:" + identifier, source_language="English",
        target_language="Vietnamese", video_id="", initial_translations=checkpoint) == [f"Câu {i}." for i in range(25)]
    assert seen == [24]
