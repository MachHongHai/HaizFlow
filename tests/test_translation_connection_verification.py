import io
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from haizflow.services import api_translation as api
from haizflow.services import translation_connections as connections


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(connections, "_PATH", tmp_path / "connections.json")
    keys = {}
    monkeypatch.setattr(connections.secure_credentials, "write_secret",
        lambda target, value, **_kwargs: keys.__setitem__(target, value))
    monkeypatch.setattr(connections.secure_credentials, "read_secret", lambda target: keys.get(target, ""))
    return keys


def test_revoked_router_key_is_not_validated_by_public_models(isolated, monkeypatch):
    identifier = connections.add("openrouter", "Deleted upstream", "revoked-secret")
    def send(url, key, **_kwargs):
        if url.endswith("/models"):
            return {"data": [{"id": "public/model"}]}
        raise HTTPError(url, 401, "Unauthorized", {}, io.BytesIO())
    request = Mock(side_effect=send)
    monkeypatch.setattr(api, "_json_request", request)
    assert api.check_connection("api:" + identifier, model_required=False) == "invalid"
    request.assert_called_once_with("https://openrouter.ai/api/v1/key", "revoked-secret", timeout=15)


def test_router_key_check_is_fresh_single_readonly_request(isolated, monkeypatch):
    identifier = connections.add("openrouter", "A", "secret-a")
    request = Mock(side_effect=[{"data": {"label": "A", "is_free_tier": True}},
                               HTTPError("https://openrouter.ai/api/v1/key", 401, "Unauthorized", {}, io.BytesIO())])
    monkeypatch.setattr(api, "_json_request", request)
    assert api.check_connection("api:" + identifier, model_required=False) == "verified"
    assert api.check_connection("api:" + identifier, model_required=False) == "invalid"
    assert request.call_count == 2
    assert all(len(call.args) == 2 and call.args[0].endswith("/key") for call in request.call_args_list)


def test_connection_only_check_resolves_exact_key_from_project_model_choice(isolated, monkeypatch):
    connections.add("openrouter", "First", "first-secret")
    identifier = connections.add("openrouter", "Second", "second-secret")
    request = Mock(return_value={"data": {"label": "Second"}})
    monkeypatch.setattr(api, "_json_request", request)
    assert api.check_connection("api:" + identifier + ":vendor/model:free", model_required=False) == "verified"
    assert request.call_args.args[1] == "second-secret"


@pytest.mark.parametrize("answer", [{}, {"data": []}, {"data": {}}, {"data": {"id": "model"}},
                                    {"data": [{"id": "model"}]}])
def test_router_rejects_public_or_malformed_auth_response(isolated, monkeypatch, answer):
    identifier = connections.add("openrouter", "A", "secret")
    monkeypatch.setattr(api, "_json_request", Mock(return_value=answer))
    assert api.check_connection("api:" + identifier, model_required=False) == "unsupported-check"


@pytest.mark.parametrize("present", [True, False])
def test_router_auth_and_model_discovery_are_separate(isolated, monkeypatch, present):
    identifier = connections.add("openrouter", "A", "secret", "vendor/model")
    request = Mock(side_effect=[{"data": {"label": "A"}},
                               {"data": [{"id": "vendor/model"}] if present else []}])
    monkeypatch.setattr(api, "_json_request", request)
    assert api.check_connection("api:" + identifier) == ("verified" if present else "model-not-found")
    assert request.call_args_list[0].args == ("https://openrouter.ai/api/v1/key", "secret")
    assert request.call_args_list[1].args == ("https://openrouter.ai/api/v1/models", "")


@pytest.mark.parametrize("status,expected", [(401, "invalid"), (403, "invalid"), (402, "billing-required"),
    (429, "rate-limited"), (404, "unsupported-check"), (302, "unavailable"), (500, "unavailable")])
def test_router_auth_http_errors_are_never_success(isolated, monkeypatch, status, expected):
    identifier = connections.add("openrouter", "A", "secret")
    monkeypatch.setattr(api, "_json_request", Mock(side_effect=HTTPError(
        "https://openrouter.ai/api/v1/key", status, "private response", {}, io.BytesIO())))
    assert api.check_connection("api:" + identifier, model_required=False) == expected


@pytest.mark.parametrize("reject_invalid", [True, False])
def test_custom_public_catalogue_is_only_reachable_not_key_verified(isolated, monkeypatch, reject_invalid):
    identifier = connections.add("custom", "Ollama", "local-secret", base_url="http://localhost:11434/v1")
    def send(_url, key, **_kwargs):
        if key != "local-secret" and reject_invalid:
            raise HTTPError(_url, 401, "Unauthorized", {}, io.BytesIO())
        return {"data": [{"id": "local-model"}]}
    request = Mock(side_effect=send)
    monkeypatch.setattr(api, "_json_request", request)
    assert api.check_connection("api:" + identifier, model_required=False) == (
        "verified" if reject_invalid else "reachable-unverified")
    assert request.call_count == 2
    assert request.call_args_list[1].args[1] != "local-secret"
    assert all(len(call.args) == 2 for call in request.call_args_list)  # GET only, no generation.


def test_two_connections_keep_explicit_key_identity_without_fallback(isolated, monkeypatch):
    from haizflow.services import translation_model_guard

    first = connections.add("openrouter", "Primary", "primary-secret")
    second = connections.add("openrouter", "Backup", "backup-secret")
    monkeypatch.setattr(translation_model_guard, "prepare", lambda *_args, **_kwargs: None)
    run = Mock(return_value=["Xin chào"])
    monkeypatch.setattr(api.gemini_translation, "translate_texts", run)
    for identifier, secret in ((first, "primary-secret"), (second, "backup-secret")):
        choice = "api:" + identifier + ":vendor/model:free"
        api.translate_texts(["Hello"], model=choice, source_language="en", target_language="vi")
        assert run.call_args.kwargs["_key"] == secret
        assert run.call_args.kwargs["model"] == choice
    assert len(connections.list_connections()) == 2


def test_settings_button_rechecks_key_and_replaces_previous_success(isolated, monkeypatch):
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    from haizflow.desktop.translation_api_controller import TranslationApiController

    app = QGuiApplication.instance() or QGuiApplication([])
    identifier = connections.add("openrouter", "A", "private")
    other = connections.add("openrouter", "B", "other-private")
    host = QObject()
    controller = TranslationApiController(host)
    send = Mock(side_effect=[{"data": {"label": "A"}}, HTTPError(
        "https://openrouter.ai/api/v1/key", 401, "Unauthorized", {}, io.BytesIO())])
    monkeypatch.setattr(api, "_json_request", send)
    for expected in ("verified", "invalid"):
        assert controller.verify(identifier)
        for _ in range(100):
            app.processEvents()
            if not controller.busy:
                break
            QTest.qWait(10)
        assert not controller.busy
        profiles = {row["id"]: row for row in controller.profiles}
        assert profiles[identifier]["check_result"] == expected
        assert profiles[other]["check_result"] == ""
    assert send.call_count == 2
