"""Offline translation-only adapters: never spend user credits or touch real credentials."""
import io
import json
import threading
from unittest.mock import Mock
from urllib import error

import pytest

from haizflow.core.translation_models import is_api_model, is_cloud_model, translation_provider
from haizflow.services import api_translation as api
from haizflow.services import translation_connections as connections


@pytest.fixture
def store(tmp_path, monkeypatch):
    secrets = {}
    monkeypatch.setattr(connections, "_PATH", tmp_path / "connections.json")
    monkeypatch.setattr(connections.secure_credentials, "read_secret", lambda target: secrets.get(target, ""))
    monkeypatch.setattr(connections.secure_credentials, "write_secret",
                        lambda target, value, **_kwargs: secrets.__setitem__(target, value))
    monkeypatch.setattr(connections.secure_credentials, "delete_secret", lambda target: secrets.pop(target, None))
    monkeypatch.setattr(api, "check_cancellation", lambda _id: None)
    monkeypatch.setattr(api, "log_to_video", Mock())
    monkeypatch.setattr(api.gemini_translation, "log_to_video", Mock())
    monkeypatch.setattr(api.gemini_translation, "check_cancellation", lambda _id: None)
    return secrets


@pytest.mark.parametrize("provider", list(connections.PROVIDERS))
def test_connections_are_translation_only_and_never_persist_or_return_keys(store, provider):
    identifier = connections.add(provider, "Dịch", "private-secret", "vendor/model", "https://example.com/v1")
    choice = "api:" + identifier
    assert is_api_model(choice) and is_cloud_model(choice) and translation_provider(choice) == "api"
    row, key = connections.resolve(choice, with_key=True)
    assert key == "private-secret" and row["model"] == "vendor/model"
    assert "private-secret" not in connections._PATH.read_text("utf-8")
    assert "private-secret" not in json.dumps(connections.list_connections())
    assert connections.remove(identifier)
    assert not store
    with pytest.raises(ValueError, match="đã bị xóa"):
        connections.resolve(choice)


@pytest.mark.parametrize("url", ["http://example.com/v1", "https://key@example.com", "https://example.com?key=secret",
                                 "https://example.com/#secret", "file:///v1", "https://example.com/../v1",
                                 "https://example.com/%2e%2e/v1", "https://example.com:0/v1", "https://example.com/\nx"])
def test_custom_endpoints_reject_credential_injection_and_unsafe_urls(url):
    with pytest.raises(ValueError):
        connections.normalized_url(url)


def test_local_http_is_explicitly_allowed_and_official_endpoints_cannot_be_overridden(store):
    assert connections.normalized_url("http://127.0.0.1:1234/v1/") == "http://127.0.0.1:1234/v1"
    identifier = connections.add("openai", "A", "key", "chosen-model", "https://wrong.example/v1")
    assert connections.resolve("api:" + identifier)["base_url"] == "https://api.openai.com/v1"


@pytest.mark.parametrize("model", ["~author/model-latest", "@preset/subtitle", "vendor/Model-2026-11-02"])
def test_model_identifiers_preserve_provider_aliases_and_case(store, model):
    choice = "api:" + connections.add("openrouter", "A", "private", model)
    assert connections.resolve(choice)["model"] == model


def test_atomic_profile_save_failure_rolls_back_secret_and_previous_index(store, monkeypatch):
    connections.add("deepseek", "A", "first-key", "model-a")
    before = connections._PATH.read_bytes()
    monkeypatch.setattr(connections, "_save", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        connections.add("openai", "B", "second-key", "model-b")
    assert connections._PATH.read_bytes() == before and list(store.values()) == ["first-key"]


def test_distinct_profiles_preserve_models_case_and_have_distinct_cache_signatures(store):
    a = "api:" + connections.add("openrouter", "A", "key1", "Vendor/Model-A")
    b = "api:" + connections.add("openrouter", "B", "key2", "Vendor/Model-B")
    assert connections.resolve(a)["model"] == "Vendor/Model-A"
    assert connections.signature_parts(a) != connections.signature_parts(b)
    assert "key1" not in str(connections.signature_parts(a))
    from haizflow.core.hardware import translation_model_signature_parts
    from haizflow.schemas.video import VideoConfig
    from haizflow.services.gemini_context import guidance
    assert translation_model_signature_parts(a) == connections.signature_parts(a)
    config = VideoConfig(translation_model=a, translator_provider="api", gemini_translation_style="natural")
    assert config.model_dump()["translation_model"] == a and guidance(config)["translation_style"] == "natural"


def _chat(rows):
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"translations": rows})}}]}


@pytest.mark.parametrize("model,expected", [
    ("google/gemma-4-26b-a4b-it:free", "json_object"),
    ("google/gemma-4-31b-it:free", "json_object"),
    ("recursive/flint-v1.0:free", "json_object"),
    ("liquid/lfm-2.5-2.6b:free", "json_schema"),
    ("unknown/unlisted:free", "json_schema"),
])
def test_free_model_uses_advertised_json_protocol_without_model_fallback(store, monkeypatch, model, expected):
    from haizflow.services import translation_catalog_cache as cache

    monkeypatch.setattr(cache, "_PATH", cache._PATH.parent / "missing-protocol-test.json")
    choice = "api:" + connections.add("openrouter", "Free", "private", model)
    send = Mock(return_value=_chat([{"id": 0, "text": "Xin chào."}]))
    monkeypatch.setattr(api, "_json_request", send)
    assert api.translate_texts(["Hello."], model=choice, source_language="en", target_language="vi",
                               video_id="") == ["Xin chào."]
    payload = send.call_args.args[2]
    assert payload["model"] == model and "models" not in payload
    assert payload["response_format"]["type"] == expected
    assert payload["provider"]["require_parameters"] is True
    assert payload["provider"]["data_collection"] == "deny"
    if expected == "json_object":
        assert '"translations":[{"id":0,"text":' in payload["messages"][0]["content"]
    assert send.call_count == 1


@pytest.mark.parametrize("rows", [
    [{"id": 0, "text": "Một câu."}],
    [{"id": 0, "text": "Một."}, {"id": 0, "text": "Hai."}],
    [{"id": 0, "text": "Một."}, {"id": 1, "text": ""}],
])
def test_free_json_mode_retains_complete_subtitle_validation(store, monkeypatch, rows):
    from haizflow.services import translation_catalog_cache as cache

    monkeypatch.setattr(cache, "format_for", lambda _model: "json_object")
    choice = "api:" + connections.add("openrouter", "Free", "private", "vendor/model:free")
    send, saved = Mock(return_value=_chat(rows)), Mock()
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="chưa hoàn tất"):
        api.translate_texts(["One.", "Two."], model=choice, source_language="en", target_language="vi",
                            video_id="", result_callback=saved)
    assert send.call_count == 1
    saved.assert_not_called()


@pytest.mark.parametrize("body_error", [False, True])
def test_unavailable_r1_free_explains_endpoint_error_without_retry_or_paid_fallback(store, monkeypatch, body_error):
    choice = "api:" + connections.add("openrouter", "R1 free", "private", "deepseek/deepseek-r1:free")
    send = Mock(side_effect=error.HTTPError("https://private", 404, "private secret", {}, io.BytesIO(b"secret")))
    if body_error:
        send = Mock(return_value={"error": {"code": 404, "message": "private secret"}})
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="không có endpoint khả dụng") as caught:
        api.translate_texts(["Hello."], model=choice, source_language="en", target_language="vi", video_id="")
    assert "404" in str(caught.value) and "secret" not in str(caught.value)
    assert send.call_count == 1
    payload = send.call_args.args[2]
    assert payload["model"] == "deepseek/deepseek-r1:free" and "models" not in payload


def test_r1_batching_keeps_context_and_leaves_room_for_visible_translation(store, monkeypatch):
    choice = "api:" + connections.add("openrouter", "R1 test", "private", "deepseek/deepseek-r1-0528")
    received, contexts, budgets = [], [], []

    def send(_url, _key, payload, **options):
        entries, _end = json.JSONDecoder().raw_decode(payload["messages"][1]["content"])
        ids = [row["id"] for row in entries]
        received.append(ids)
        contexts.append(payload["messages"][1]["content"])
        budgets.append(payload["max_tokens"])
        assert options == {"timeout": 240}
        assert payload["reasoning"] == {"exclude": True}  # Not a fictitious Low/High setting.
        return _chat([{"id": index, "text": f"Bản dịch câu {index}."} for index in ids])

    monkeypatch.setattr(api, "_json_request", send)
    saved = Mock()
    result = api.translate_texts([f"Source sentence {i}." for i in range(40)], model=choice,
        source_language="English", target_language="Vietnamese", video_id="fixture",
        translation_glossary="Giữ thống nhất tên nhân vật.", result_callback=saved)
    assert [len(batch) for batch in received] == [12, 12, 12, 4]
    assert [index for batch in received for index in batch] == list(range(40))
    assert all(10240 <= limit <= 32768 for limit in budgets)
    assert all("Giữ thống nhất tên nhân vật." in context for context in contexts)
    assert "accepted_examples" in contexts[1] and "Bản dịch câu 0." in contexts[1]
    assert len(result) == 40 and saved.call_count == 4


@pytest.mark.parametrize("finish,content,reasoning,expected", [
    ("length", None, 3060, "reasoning_budget_exhausted"),
    ("stop", "", 3060, "reasoning_budget_exhausted"),
    ("length", '{"translations":[', 2000, "token_limit"),
])
def test_r1_reasoning_exhaustion_is_precise_safe_and_never_paid_retried(
        store, monkeypatch, finish, content, reasoning, expected):
    choice = "api:" + connections.add("openrouter", "R1", "private", "deepseek/deepseek-r1-0528")
    answer = {"choices": [{"finish_reason": finish, "message": {
        "content": content, "reasoning": "PRIVATE REASONING TEXT"}}],
        "usage": {"prompt_tokens": 1398, "completion_tokens": 3060,
                  "completion_tokens_details": {"reasoning_tokens": reasoning}}}
    send, saved = Mock(return_value=answer), Mock()
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="giới hạn token") as caught:
        api.translate_texts(["One."], model=choice, source_language="en", target_language="vi",
                            video_id="fixture", result_callback=saved)
    assert send.call_count == 1
    saved.assert_not_called()
    logs = str(api.log_to_video.call_args_list)
    assert f"response={expected}" in logs and f"finish={finish}" in logs
    assert "max_tokens=10240" in logs
    assert "PRIVATE REASONING TEXT" not in logs and "PRIVATE REASONING TEXT" not in str(caught.value)


def test_r1_resume_preserves_completed_rows_and_never_retranslates_them(store, monkeypatch):
    choice = "api:" + connections.add("openrouter", "R1", "private", "deepseek/deepseek-r1-0528")
    seen = []

    def send(_url, _key, payload, **_kwargs):
        entries, _end = json.JSONDecoder().raw_decode(payload["messages"][1]["content"])
        ids = [row["id"] for row in entries]
        seen.extend(ids)
        return _chat([{"id": index, "text": f"Mới {index}."} for index in ids])

    monkeypatch.setattr(api, "_json_request", send)
    initial = [f"Đã lưu {i}." for i in range(24)] + [None] * 16
    result = api.translate_texts([f"Sentence {i}." for i in range(40)], model=choice,
        source_language="en", target_language="vi", video_id="", initial_translations=initial)
    assert seen == list(range(24, 40)) and result[:24] == initial[:24]


def test_r1_failed_batch_keeps_checkpoint_and_old_subtitles_until_resume(store, tmp_path, monkeypatch):
    from haizflow.services import translation

    choice = "api:" + connections.add("openrouter", "R1", "private", "deepseek/deepseek-r1-0528")
    source, output, progress = (tmp_path / name for name in ("source.json", "result.json", "progress.json"))
    segments = [{"start": i * 3, "end": i * 3 + 2, "text": f"Source sentence {i}.", "language": "en"}
                for i in range(27)]
    source.write_text(json.dumps(segments), "utf-8")
    output.write_text("previous-result", "utf-8")
    monkeypatch.setattr(translation, "log_to_video", Mock())
    monkeypatch.setattr(translation, "shutdown_hymt2_worker", Mock())
    monkeypatch.setattr(translation, "_suspicious_translation_indexes", lambda *_args: set())
    received, failing = [], [True]

    def send(_url, _key, payload, **_kwargs):
        entries, _end = json.JSONDecoder().raw_decode(payload["messages"][1]["content"])
        ids = [row["id"] for row in entries]
        received.append(ids)
        if failing[0] and len(received) == 2:
            return {"choices": [{"finish_reason": "length", "message": {"content": None}}],
                    "usage": {"completion_tokens": 10240,
                              "completion_tokens_details": {"reasoning_tokens": 10240}}}
        return _chat([{"id": index, "text": f"Bản dịch câu {index}."} for index in ids])

    monkeypatch.setattr(api, "_json_request", send)
    options = dict(provider="api", translation_model=choice, checkpoint_path=str(progress))
    with pytest.raises(RuntimeError, match="suy luận"):
        translation.translate_segments(str(source), str(output), "fixture", **options)
    assert output.read_text("utf-8") == "previous-result"
    assert len([value for value in json.loads(progress.read_text("utf-8"))["translations"] if value]) == 12
    assert len(received) == 2  # No paid automatic retry of the failed batch.
    received.clear()
    failing[0] = False
    translation.translate_segments(str(source), str(output), "fixture", **options)
    assert received == [list(range(12, 24)), [24, 25, 26]]
    result = json.loads(output.read_text("utf-8"))
    assert [(row["start"], row["end"]) for row in result] == [(row["start"], row["end"]) for row in segments]
    assert not progress.exists()


def test_saved_project_keeps_api_connection_and_needs_no_local_translation_pack(store, tmp_path):
    import uuid
    from types import SimpleNamespace

    from haizflow.schemas.video import VideoConfig
    from haizflow.services import video_store
    from haizflow.services.processing_resume import configuration_snapshot
    from haizflow.services.resource_packs import ResourcePackManager

    choice = "api:" + connections.add("openrouter", "A", "private", "Vendor/Model-A")
    config = VideoConfig(project_type="manual", project_directory=str(tmp_path), project_name="API fixture",
                         translation_model=choice, translator_provider="api", gemini_translation_style="natural")
    video = video_store.create_video(uuid.uuid4().hex, "fixture.mp4", config)
    loaded = video_store.get_video(video.video_id)
    assert loaded.translation_model == choice and loaded.translator_provider == "api"
    assert ResourcePackManager.required_packs(SimpleNamespace(), "translation", {
        "device": "cpu", "translation_model": choice}) == []
    loaded.manual_target_tool = "translation"
    snapshot = configuration_snapshot(loaded, "cpu")
    assert snapshot["settings"]["gemini_translation_style"] == "natural"
    assert snapshot["settings"]["translation_connection"] == list(connections.signature_parts(choice))
    assert "private" not in json.dumps(snapshot)


@pytest.mark.parametrize("provider", list(connections.PROVIDERS))
def test_provider_payloads_are_only_text_translation_and_preserve_exact_mapping(store, monkeypatch, provider):
    choice = "api:" + connections.add(provider, "A", "private", "Vendor/ChosenModel", "https://example.com/v1")
    rows = [{"id": 0, "text": "Chào em."}, {"id": 1, "text": "Cảm ơn anh."}]
    answer = ({"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps({"translations": rows})}]}]}
        if provider == "openai" else _chat(rows))
    send = Mock(return_value=answer)
    monkeypatch.setattr(api, "_json_request", send)
    values = api.translate_texts(["Hello.", "Thanks."], model=choice, source_language="English",
                                target_language="Vietnamese", video_id="", translation_style="natural",
                                translation_glossary="Hai người là vợ chồng.")
    assert values == ["Chào em.", "Cảm ơn anh."] and send.call_count == 1
    url, key, payload = send.call_args.args
    assert key == "private" and payload["model"] == "Vendor/ChosenModel"
    assert not {"audio", "voice", "tools", "temperature", "models"} & payload.keys()
    if provider == "openai":
        assert url.endswith("/responses") and not payload["store"]
        assert payload["text"]["format"]["strict"] is True
    else:
        assert url.endswith("/chat/completions")
    if provider == "openrouter":
        assert payload["provider"]["require_parameters"] and payload["provider"]["data_collection"] == "deny"


@pytest.mark.parametrize("answer", [_chat([{"id": 0, "text": "one"}]),
                                    _chat([{"id": 0, "text": "one"}, {"id": 0, "text": "two"}]),
                                    {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
                                    {"choices": [None]}, {"choices": [{"finish_reason": "stop", "message": None}]}])
def test_malformed_partial_or_refused_answers_never_get_published_or_paid_retried(store, monkeypatch, answer):
    choice = "api:" + connections.add("deepseek", "A", "private", "model")
    send, saved = Mock(return_value=answer), Mock()
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="chưa hoàn tất"):
        api.translate_texts(["a", "b"], model=choice, source_language="English", target_language="Vietnamese",
                            video_id="", result_callback=saved)
    assert send.call_count == 1
    saved.assert_not_called()


def test_resume_requests_only_missing_rows_and_preserves_style_and_context(store, monkeypatch):
    choice = "api:" + connections.add("deepseek", "A", "key", "model")
    send, saved = Mock(return_value=_chat([{"id": 1, "text": "Chào anh."}])), Mock()
    monkeypatch.setattr(api, "_json_request", send)
    result = api.translate_texts(["Hello", "Hi"], model=choice, source_language="English", target_language="Vietnamese",
                                video_id="", initial_translations=["Xin chào", None], result_callback=saved)
    assert result == ["Xin chào", "Chào anh."]
    saved.assert_called_once_with([1], ["Chào anh."])
    user = send.call_args.args[2]["messages"][1]["content"]
    assert "accepted_examples" in user and "Xin chào" in user


@pytest.mark.parametrize("status", [401, 402, 403, 429])
def test_auth_billing_rate_errors_never_leak_body_or_retry(store, monkeypatch, status):
    choice = "api:" + connections.add("deepseek", "A", "private", "model")
    send = Mock(side_effect=error.HTTPError("https://private", status, "private secret", {}, io.BytesIO(b"secret")))
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError) as caught:
        api.translate_texts(["a"], model=choice, source_language="en", target_language="vi", video_id="")
    assert "secret" not in str(caught.value) and str(status) in str(caught.value)
    assert send.call_count == 1


def test_model_list_connection_check_is_readonly_and_no_inference_request(store, monkeypatch):
    choice = "api:" + connections.add("openai", "A", "key", "chosen-model")
    send = Mock(return_value={"data": [{"id": "chosen-model"}]})
    monkeypatch.setattr(api, "_json_request", send)
    assert api.check_connection(choice) == "verified"
    assert send.call_args.args == ("https://api.openai.com/v1/models", "key")
    assert send.call_args.kwargs == {"timeout": 15}


def test_actual_http_is_text_only_and_blocks_authenticated_redirects(store):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            calls.append((self.path, self.headers.get("Authorization")))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/credential-sink")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data":[{"id":"test-model"}]}')

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, self.headers.get("Authorization")))
            assert payload["model"] == "test-model" and "audio" not in payload
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(_chat([{"id": 0, "text": "Xin chào."}])).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        choice = "api:" + connections.add("custom", "Local", "test-key", "test-model", base + "/v1")
        assert api.check_connection(choice) == "verified"
        assert api.translate_texts(["Hello"], model=choice, source_language="English",
                                   target_language="Vietnamese", video_id="") == ["Xin chào."]
        with pytest.raises(error.HTTPError) as caught:
            api._json_request(base + "/redirect", "test-key")
        caught.value.close()
        assert all(path != "/credential-sink" for path, _ in calls)
        assert [path for path, _ in calls] == ["/v1/models", "/v1/chat/completions", "/redirect"]
        assert all(auth == "Bearer test-key" for _, auth in calls)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


@pytest.mark.parametrize("override", ["", ":Vendor/Mixed-Case:free"])
def test_interrupted_api_translation_preserves_final_and_resumes_only_missing_cues(
        store, monkeypatch, tmp_path, override):
    from haizflow.services import translation

    choice = "api:" + connections.add("deepseek", "A", "private", "model") + override
    source, output, progress = (tmp_path / name for name in ("source.json", "result.json", "progress.json"))
    segments = [{"start": i * 3, "end": i * 3 + 2, "text": f"Source sentence {i}.", "language": "en"}
                for i in range(27)]
    source.write_text(json.dumps(segments), "utf-8")
    output.write_text("previous-result", "utf-8")
    monkeypatch.setattr(translation, "log_to_video", Mock())
    monkeypatch.setattr(translation, "shutdown_hymt2_worker", Mock())
    monkeypatch.setattr(translation, "_suspicious_translation_indexes", lambda *_args: set())
    received = []

    def request(_url, _key, payload):
        assert payload["model"] == (override[1:] or "model")
        entries, _end = json.JSONDecoder().raw_decode(payload["messages"][1]["content"])
        received.append([row["id"] for row in entries])
        if len(received) == 2:
            raise TimeoutError("lost reply")
        return _chat([{"id": row["id"], "text": f"Bản dịch câu {row['id']}."} for row in entries])

    monkeypatch.setattr(api, "_json_request", request)
    with pytest.raises(RuntimeError, match="quá thời gian"):
        translation.translate_segments(str(source), str(output), "private-test", provider="api",
                                       translation_model=choice, checkpoint_path=str(progress))
    assert output.read_text("utf-8") == "previous-result"
    assert len([value for value in json.loads(progress.read_text("utf-8"))["translations"] if value]) == 24
    received.clear()
    translation.translate_segments(str(source), str(output), "private-test", provider="api",
                                   translation_model=choice, checkpoint_path=str(progress))
    assert received == [[24, 25, 26]]
    result = json.loads(output.read_text("utf-8"))
    assert [(row["start"], row["end"]) for row in result] == [(row["start"], row["end"]) for row in segments]
    assert not progress.exists()


def test_controller_verification_is_async_and_updates_only_its_profile(store, monkeypatch):
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    from haizflow.desktop.translation_api_controller import TranslationApiController

    app = QGuiApplication.instance() or QGuiApplication([])
    host = QObject()
    host._show_app_alert = Mock()
    controller = TranslationApiController(host)
    first = connections.add("deepseek", "A", "unique-private-test-secret", "model")
    second = connections.add("openai", "B", "other", "another-model")
    release, entered = threading.Event(), threading.Event()

    def check(_id, **kwargs):
        assert kwargs == {"model_required": False}
        entered.set()
        release.wait(2)
        return "verified"

    monkeypatch.setattr(api, "check_connection", check)
    assert controller.verify(first) and entered.wait(1)
    assert controller.busy and not controller.verify(second) and not controller.remove(first)
    release.set()
    for _ in range(50):
        app.processEvents()
        if not controller.busy:
            break
        QTest.qWait(10)
    rows = {row["id"]: row for row in controller.profiles}
    assert rows[first]["check_result"] == "verified" and rows[second]["check_result"] == ""
    assert "unique-private-test-secret" not in json.dumps(controller.modelOptions)


def test_project_model_override_is_immutable_and_isolates_progress_signatures(store, monkeypatch):
    from haizflow.core.translation_models import is_api_model

    choice = "api:" + connections.add("openrouter", "Key A", "private", "vendor/default")
    original = connections.resolve(choice)
    variant = choice + ":vendor/Other:free"
    assert is_api_model(variant)
    assert not is_api_model(choice + ":") and not is_api_model(choice + ":bad model")
    profile, key = connections.resolve(variant, with_key=True)
    assert profile == {**original, "model": "vendor/Other:free"} and key == "private"
    assert connections.resolve(choice) == original and len(connections.list_connections()) == 1
    assert connections.signature_parts(choice) != connections.signature_parts(variant)
    from haizflow.schemas.video import VideoConfig

    assert VideoConfig(translation_model=variant).translation_model == variant
    request = Mock(return_value=_chat([{"id": 0, "text": "Xin chào."}]))
    monkeypatch.setattr(api, "_json_request", request)
    assert api.translate_texts(["Hello."], model=variant, source_language="en", target_language="vi",
                              video_id="private-override-test") == ["Xin chào."]
    assert request.call_args.args[2]["model"] == "vendor/Other:free"


def test_key_can_be_saved_without_model_and_cannot_start_inference_until_selected(store, monkeypatch):
    identifier = connections.add("openai", "New key", "private-only-key")
    profile = connections.get_connection(identifier)
    assert profile["model"] == "" and connections.list_connections() == [profile]
    send = Mock(return_value={"data": []})
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(ValueError, match="Chưa chọn model"):
        connections.resolve("api:" + identifier, with_key=True)
    assert api.check_connection("api:" + identifier, model_required=False) == "verified"
    assert send.call_count == 1 and send.call_args.args == ("https://api.openai.com/v1/models", "private-only-key")
    assert connections.resolve("api:" + identifier + ":gpt-6-luna")["model"] == "gpt-6-luna"
    assert connections.get_connection(identifier) == profile


def test_custom_project_format_is_explicit_and_does_not_change_other_projects(store):
    identifier = connections.add("custom", "Private endpoint", "key", base_url="https://example.com/v1")
    base = "api:" + identifier + ":vendor/Model:free"
    assert connections.resolve(base)["format"] == "json_object"
    assert connections.resolve(base + "#prompt")["format"] == "prompt"
    assert connections.signature_parts(base) != connections.signature_parts(base + "#prompt")
    assert connections.get_connection(identifier)["model"] == ""
    official = connections.add("openai", "Official", "key")
    with pytest.raises(ValueError, match="API tùy chỉnh"):
        connections.resolve("api:" + official + ":gpt-6-luna#prompt")


@pytest.mark.parametrize("code,status", [
    (429, 429), ("429", 429), ("insufficient_quota", 429), (402, 402),
    ("invalid_api_key", 401), (503, 503), ("server_error", 500)])
def test_error_after_http_200_is_classified_and_never_paid_retried(store, monkeypatch, code, status):
    choice = "api:" + connections.add("openrouter", "A", "private-key", "vendor/model")
    send = Mock(return_value={"error": {"code": code, "message": "PRIVATE-KEY raw provider details"}})
    monkeypatch.setattr(api, "_json_request", send)
    saved = Mock()
    with pytest.raises(RuntimeError) as caught:
        api.translate_texts(["Hello."], model=choice, source_language="en", target_language="vi",
                            video_id="", result_callback=saved)
    assert str(status) in str(caught.value)
    assert "PRIVATE" not in str(caught.value) and "sai ID" not in str(caught.value)
    assert send.call_count == 1
    saved.assert_not_called()


def test_interrupted_http_body_is_network_error_without_paid_retry(store, monkeypatch):
    from http.client import IncompleteRead

    choice = "api:" + connections.add("custom", "A", "private", "model", "https://example.com/v1")
    send = Mock(side_effect=IncompleteRead(b"PRIVATE reply", 100))
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="mất kết nối") as caught:
        api.translate_texts(["Hello."], model=choice, source_language="en", target_language="vi", video_id="")
    assert "PRIVATE" not in str(caught.value) and send.call_count == 1


@pytest.mark.parametrize("provider", ["gemini", "api"])
def test_similarity_only_never_spends_a_second_cloud_request(store, monkeypatch, tmp_path, provider):
    from haizflow.services import translation

    choice = "gemini-3.5-flash-lite" if provider == "gemini" else (
        "api:" + connections.add("openrouter", "A", "private") + ":Vendor/MixedCase")
    source, output = tmp_path / "source.json", tmp_path / "result.json"
    source.write_text(json.dumps([{"start": 0, "end": 2, "text": "Alice 2026"}]), "utf-8")
    send = Mock(return_value=["Alice 2026"])
    monkeypatch.setattr(api if provider == "api" else api.gemini_translation, "translate_texts", send)
    monkeypatch.setattr(translation, "log_to_video", Mock())
    monkeypatch.setattr(translation, "shutdown_hymt2_worker", Mock())
    monkeypatch.setattr(translation, "_suspicious_translation_indexes", lambda *args: {0})
    result = translation.translate_segments(str(source), str(output), "cost-test", provider=provider,
                                            translation_model=choice, source_language="en")
    assert result[0]["text"] == "Alice 2026" and send.call_count == 1
    assert send.call_args.kwargs["model"] == choice


def test_failed_cloud_recovery_does_not_repeat_a_paid_failure(store, monkeypatch, tmp_path):
    from haizflow.services import translation

    choice = "api:" + connections.add("openrouter", "A", "private") + ":vendor/model"
    source, output = tmp_path / "source.json", tmp_path / "result.json"
    source.write_text(json.dumps([{"start": 0, "end": 2, "text": "Hello."}]), "utf-8")
    send = Mock(side_effect=[["\ufffd"], RuntimeError("HTTP 429 quota")])
    monkeypatch.setattr(api, "translate_texts", send)
    monkeypatch.setattr(translation, "log_to_video", Mock())
    monkeypatch.setattr(translation, "shutdown_hymt2_worker", Mock())
    with pytest.raises(RuntimeError, match="ký tự lỗi"):
        translation.translate_segments(str(source), str(output), "cost-test", provider="api", translation_model=choice)
    assert send.call_count == 2 and not output.exists()  # Initial request + one failed repair, no third paid call.


def test_token_diagnostics_only_log_allowlisted_counts(store):
    api.log_to_video.reset_mock()
    api._log_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 40,
        "completion_tokens_details": {"reasoning_tokens": 5}, "secret": "PRIVATE"}}, "API", "cost-test")
    text = api.log_to_video.call_args.args[1]
    assert "input=100" in text and "output=40" in text and "reasoning=5" in text and "PRIVATE" not in text


def test_real_desktop_model_setter_keeps_opaque_project_model_case(store):
    from types import SimpleNamespace

    from haizflow.desktop.qml_controller import HaizFlowController

    choice = "api:" + connections.add("custom", "A", "private", base_url="https://example.com/v1")
    choice += ":Vendor/MixedCase:free#prompt"
    host = SimpleNamespace(_translation_model="q4", _show_app_alert=Mock(), translationModelChanged=Mock())
    HaizFlowController.translationModel.fset(host, choice)
    assert host._translation_model == choice
    host._show_app_alert.assert_not_called()
    host.translationModelChanged.emit.assert_called_once()


def test_optional_token_log_failure_cannot_discard_a_paid_reply(store, monkeypatch):
    choice = "api:" + connections.add("deepseek", "A", "private", "deepseek-flash")
    answer = {**_chat([{"id": 0, "text": "Xin chào."}]), "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
    send, saved = Mock(return_value=answer), Mock()
    monkeypatch.setattr(api, "_json_request", send)
    monkeypatch.setattr(api, "log_to_video", Mock(side_effect=OSError("disk full")))
    assert api.translate_texts(["Hello."], model=choice, source_language="en", target_language="vi",
                               video_id="paid-reply-test", result_callback=saved) == ["Xin chào."]
    saved.assert_called_once_with([0], ["Xin chào."])
    assert send.call_count == 1


@pytest.mark.parametrize("provider,model,expected", [
    ("openai", "gpt-6-luna", {"reasoning": {"effort": "none"}}),
    ("openai", "gpt-6.1-sol", {"reasoning": {"effort": "low"}}),
    ("deepseek", "deepseek-flash", {"thinking": {"type": "disabled"}}),
    ("openrouter", "openai/gpt-6-luna", {"reasoning": {"effort": "none", "exclude": True}}),
    ("custom", "gpt-6-luna", {})])
def test_cost_controls_reach_payload_without_omitting_guidance_or_sentences(
        store, monkeypatch, provider, model, expected):
    choice = "api:" + connections.add(provider, "A", "private", model, "https://example.com/v1")
    rows = [{"id": 0, "text": "Chào em."}, {"id": 1, "text": "Cảm ơn anh."}]
    answer = {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps({"translations": rows})}]}]} if provider == "openai" else _chat(rows)
    send = Mock(return_value=answer)
    monkeypatch.setattr(api, "_json_request", send)
    assert api.translate_texts(["Hello.", "Thanks."], model=choice, source_language="en", target_language="vi",
        video_id="", translation_style="natural", translation_glossary="Alice → An. An và Bình là vợ chồng.") == [
            "Chào em.", "Cảm ơn anh."]
    payload = send.call_args.args[2]
    assert payload["model"] == model and send.call_count == 1
    assert {key: payload[key] for key in ("reasoning", "thinking") if key in payload} == expected
    user = payload["input"][0]["content"] if provider == "openai" else payload["messages"][1]["content"]
    assert "Hello." in user and "Thanks." in user and "vợ chồng" in user and "natural" in user
    assert payload.get("max_output_tokens", payload.get("max_tokens")) == 2048


@pytest.mark.parametrize("provider", ["openai", "deepseek", "openrouter", "custom"])
def test_real_http_cost_and_error_contract_without_any_live_provider(store, monkeypatch, provider):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    state = {"mode": "success", "calls": 0}
    model = {"openai": "gpt-6-luna", "deepseek": "deepseek-flash",
             "openrouter": "openai/gpt-6-luna", "custom": "Vendor/MixedCase"}[provider]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            state["calls"] += 1
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert payload["model"] == model and self.headers["Authorization"] == "Bearer private-test-key"
            if state["mode"] == "broken-chunk":
                self.send_response(200)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(b'100\r\n{"partial":')
                self.close_connection = True
                return
            status = state["mode"] if type(state["mode"]) is int else 200
            if status != 200 or state["mode"] == "body-error":
                body = {"error": {"code": 429 if status == 200 else status, "message": "PRIVATE RAW BODY"}}
            elif provider == "openai":
                body = {"status": "completed", "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": json.dumps({"translations": [{"id": 0, "text": "Xin chào."}]})}]}]}
            else:
                body = _chat([{"id": 0, "text": "Xin chào."}])
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/v1"
        if provider != "custom":
            monkeypatch.setitem(connections.PROVIDERS[provider], "base_url", base)
        choice = "api:" + connections.add(provider, "A", "private-test-key", model, base)
        monkeypatch.setattr(api.gemini_translation, "_retry_delay", Mock())
        assert api.translate_texts(["Hello."], model=choice, source_language="en", target_language="vi",
                                   video_id="") == ["Xin chào."]
        for mode, expected_calls, expected_error in [(401, 1, "401"), (429, 1, "429"), (503, 3, "503"),
                                                    ("body-error", 1, "429"), ("broken-chunk", 1, "mất kết nối")]:
            state.update(mode=mode, calls=0)
            with pytest.raises(RuntimeError, match=expected_error) as caught:
                api.translate_texts(["Hello."], model=choice, source_language="en", target_language="vi", video_id="")
            assert state["calls"] == expected_calls and "PRIVATE" not in str(caught.value)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)
