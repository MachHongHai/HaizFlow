"""The opt-in audit must never send paid/fallback traffic or save user consent."""
import io
import json
from pathlib import Path
import runpy
from unittest.mock import Mock
from urllib.error import HTTPError

from haizflow.services import api_translation, translation_privacy


def audit():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "audit-openrouter-free.py"))


def profile():
    return {"id": "a" * 32, "provider": "openrouter", "base_url": "https://openrouter.ai/api/v1",
            "model": "vendor/old", "format": "json_schema"}


def option(model="vendor/audit:free"):
    return {"value": model, "output_format": "json_schema", "pricing_kind": "free"}


def answer():
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
        "translations": [{"id": 0, "text": "Cảm ơn mẹ."}, {"id": 1, "text": "Tôi không biết."}]})}}]}


def test_audit_uses_production_language_names_zero_price_and_never_saves_consent(monkeypatch):
    def send(url, key, payload, **kwargs):
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert key == "synthetic-key"
        assert payload["model"] == "vendor/audit:free" and "models" not in payload
        assert payload["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0}
        assert payload["provider"]["data_collection"] == "allow"
        assert "English into natural Vietnamese" in payload["messages"][0]["content"]
        assert kwargs["timeout"] <= 75
        return answer()
    monkeypatch.setattr(api_translation, "_json_request", send)
    grant = Mock()
    monkeypatch.setattr(translation_privacy, "grant", grant)
    result = audit()["check"](profile(), "synthetic-key", option(), allow_collection=True)
    assert result["usable"] and result["requests"] == 1
    assert "synthetic-key" not in json.dumps(result)
    grant.assert_not_called()


def test_audit_suppresses_automatic_post_retries(monkeypatch):
    send = Mock(side_effect=HTTPError("https://openrouter.ai/api/v1/chat/completions", 503,
                                     "Unavailable", {}, io.BytesIO(b"{}")))
    monkeypatch.setattr(api_translation, "_json_request", send)
    result = audit()["check"](profile(), "synthetic-key", option())
    assert not result["usable"] and result["requests"] == 1
    assert result["http_status"] == 503 and send.call_count == 1


def test_explicit_probe_can_recheck_hidden_route_without_changing_production_policy(monkeypatch):
    from haizflow.services.translation_model_catalog import _UNAVAILABLE_OPENROUTER_MODELS
    model = "google/gemma-4-26b-a4b-it:free"
    send = Mock(return_value=answer())
    monkeypatch.setattr(api_translation, "_json_request", send)
    check = audit()["check"]
    assert not check(profile(), "synthetic-key", option(model))["usable"]
    send.assert_not_called()
    assert check(profile(), "synthetic-key", option(model), probe_unavailable=True)["usable"]
    assert model in _UNAVAILABLE_OPENROUTER_MODELS


def test_audit_refuses_nonofficial_post_destination(monkeypatch):
    send = Mock()
    monkeypatch.setattr(api_translation, "_json_request", send)
    result = audit()["check"]({**profile(), "base_url": "https://example.invalid/v1"},
                              "synthetic-key", option())
    assert not result["usable"] and result["requests"] == 0
    send.assert_not_called()
