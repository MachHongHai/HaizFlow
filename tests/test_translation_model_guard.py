"""Live-model contract changes are simulated; never use real keys or inference."""
import io
import json
from copy import deepcopy
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from haizflow.services import api_translation as api
from haizflow.services import translation_catalog_cache as cache
from haizflow.services import translation_connections as connections
from haizflow.services import translation_model_guard as guard

_real_check_endpoints = guard._check_endpoints


def profile(model="vendor/new:free", provider="openrouter"):
    return {"provider": provider, "model": model, "format": "json_schema",
            "base_url": "https://openrouter.ai/api/v1", "id": "a" * 32}


def row(model="vendor/new:free", **changes):
    return {"id": model, "name": "New model", "endpoints": ["/api/v1/chat/completions"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "supported_parameters": ["max_tokens", "response_format"],
            "pricing": {"prompt": "0", "completion": "0"},
            "context_length": 16384, "top_provider": {"max_completion_tokens": 4096}, **changes}


def endpoint(**changes):
    return {"model_id": "vendor/new:free", "status": 0, "context_length": 16384,
            "max_completion_tokens": 4096, "supported_parameters": ["max_tokens", "response_format"],
            "pricing": {"prompt": "0", "completion": "0"}, **changes}


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    from haizflow.services import translation_privacy, translation_reasoning_catalog

    monkeypatch.setattr(cache, "_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(cache, "_BUNDLED", tmp_path / "absent.json")
    monkeypatch.setattr(translation_privacy, "_PATH", tmp_path / "privacy.json")
    monkeypatch.setattr(translation_reasoning_catalog, "_PATH", tmp_path / "reasoning.json")
    monkeypatch.setattr(connections, "_PATH", tmp_path / "profiles.json")
    monkeypatch.setattr(connections.secure_credentials, "write_secret", lambda *_a, **_k: None)
    monkeypatch.setattr(connections.secure_credentials, "read_secret", lambda *_a: "SYNTHETIC-PRIVATE-KEY")
    monkeypatch.setattr("haizflow.pipeline.process_registry.check_cancellation", lambda *_args: None)
    monkeypatch.setattr(api, "check_cancellation", lambda *_args: None)
    monkeypatch.setattr(api, "log_to_video", Mock())
    monkeypatch.setattr(api.gemini_translation, "check_cancellation", lambda *_args: None)
    monkeypatch.setattr(api.gemini_translation, "log_to_video", Mock())
    # Most cases isolate the model-metadata stage. Serving-endpoint checks and
    # the production two-GET flow are exercised explicitly below.
    monkeypatch.setattr(guard, "_check_endpoints", lambda option, **_kwargs: option)


def test_preflight_queries_exact_official_model_without_key_or_user_content(monkeypatch):
    send = Mock(return_value={"data": row()})
    monkeypatch.setattr(api, "_json_request", send)
    result = guard.prepare({**profile(), "base_url": "https://attacker.invalid"})
    assert result["value"] == "vendor/new:free" and result["output_format"] == "json_object"
    assert result["parameters"] == ["max_tokens", "response_format"]
    assert result["reasoning_supported"] is False
    assert send.call_args.args == ("https://openrouter.ai/api/v1/model/vendor/new%3Afree", "")
    assert send.call_args.kwargs == {"timeout": 12}


@pytest.mark.parametrize("provider", ["openai", "deepseek", "custom"])
def test_other_providers_do_not_receive_router_specific_preflight(monkeypatch, provider):
    send = Mock()
    monkeypatch.setattr(api, "_json_request", send)
    assert guard.prepare(profile(provider=provider)) is None
    send.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"endpoints": ["/api/v1/batches"]}, {"endpoints": ["/api/v1/responses"]}, {"endpoints": None},
    {"endpoints": []}, {"supported_parameters": []},
    {"supported_parameters": ["max_tokens"]}, {"architecture": {"input_modalities": ["image"], "output_modalities": ["text"]}},
    {"architecture": {"input_modalities": ["text"], "output_modalities": ["audio"]}},
    {"expiration_date": "2020-01-01"}, {"pricing": {"prompt": "0.01", "completion": "0.01"}},
    {"pricing": None}, {"id": "vendor/silently-switched"},
    {"context_length": None}, {"context_length": "16384"},
    {"top_provider": {"max_completion_tokens": None}},
    {"top_provider": {"max_completion_tokens": -1}},
])
def test_incompatible_or_changed_model_stops_before_any_inference(monkeypatch, changes):
    send = Mock(return_value={"data": row(**changes)})
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="chưa gửi nội dung dịch"):
        guard.prepare(profile())
    assert send.call_count == 1 and len(send.call_args.args) == 2


@pytest.mark.parametrize("model", ["bad id", "vendor/model:batch", "vendor/model:batch:nitro", "no-author",
                                 "vendor/../models", "vendor/./model", "vendor//model"])
def test_obviously_invalid_models_do_not_even_fetch_metadata(monkeypatch, model):
    send = Mock()
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="Model ID"):
        guard.prepare(profile(model))
    send.assert_not_called()


@pytest.mark.parametrize("status", [401, 403, 404, 410, 429, 500, 503])
def test_preflight_http_errors_are_sanitized_and_not_retried(monkeypatch, status):
    send = Mock(side_effect=HTTPError("https://private.invalid", status, "PRIVATE ERROR", {}, io.BytesIO(b"private")))
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError) as caught:
        guard.prepare(profile())
    assert send.call_count == 1 and "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("answer", [{}, [], {"data": None}, {"data": []},
                                  {"data": row(), "error": {"code": 401}},
                                  {"data": row(), "error": {"code": 429}}])
def test_malformed_or_http200_error_metadata_is_never_used(monkeypatch, answer):
    send = Mock(return_value=answer)
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError):
        guard.prepare(profile())
    assert send.call_count == 1


def test_cancelled_preflight_never_sends_a_request(monkeypatch):
    stopped = RuntimeError("TEST CANCELLED")
    monkeypatch.setattr("haizflow.pipeline.process_registry.check_cancellation", Mock(side_effect=stopped))
    send = Mock()
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError) as caught:
        guard.prepare(profile())
    assert caught.value is stopped
    send.assert_not_called()


def test_preflight_rejects_a_free_alias_that_becomes_paid(monkeypatch):
    model = "vendor/preview"
    cache.store([{"value": model, "pricing_kind": "free"}], "ready")
    send = Mock(return_value={"data": row(model, pricing={"prompt": "0.01", "completion": "0.01"},
                                         supported_parameters=["max_tokens", "structured_outputs"])})
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="không còn miễn phí"):
        guard.prepare(profile(model))
    assert send.call_count == 1


def test_translation_pins_live_protocol_for_all_chunks_despite_background_cache_changes(monkeypatch):
    monkeypatch.setattr(guard, "_check_endpoints", _real_check_endpoints)
    model = "vendor/new:free"
    identifier = connections.add("openrouter", "A", "synthetic", model)
    calls = []
    def send(url, key, payload=None, **kwargs):
        calls.append((url, key, deepcopy(payload)))
        if payload is None:
            assert key == ""
            if url.endswith("/endpoints"):
                return {"data": {"endpoints": [endpoint()]}}
            return {"data": row(model)}
        assert key == "SYNTHETIC-PRIVATE-KEY" and payload["model"] == model
        assert "reasoning" not in payload  # No stale OpenRouter or OpenAI fallback knobs.
        assert payload["response_format"] == {"type": "json_object"}
        assert "max_tokens" not in payload
        assert payload["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0}
        assert len(payload["messages"]) == 2  # Do not inherit a stale Gemma-only prompt layout.
        entries, _end = json.JSONDecoder().raw_decode(payload["messages"][1]["content"])
        cache.store([{"value": model, "output_format": "json_schema", "prompt_format": "user_only",
                      "max_completion_tokens": 123, "reasoning_supported": True,
                      "reasoning_capabilities": {"mandatory": True, "values": ["high"]}}], "ready")
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"translations": [
            {"id": item["id"], "text": f"Câu {item['id']}."} for item in reversed(entries)]})}}]}
    monkeypatch.setattr(api, "_json_request", send)
    result = api.translate_texts([f"Sentence {i}." for i in range(25)], model="api:" + identifier,
                                source_language="en", target_language="vi", video_id="")
    assert result == [f"Câu {i}." for i in range(25)]
    assert len(calls) == 4 and sum(payload is None for _url, _key, payload in calls) == 2


@pytest.mark.parametrize("endpoints", [
    [], None, "invalid", [None], [endpoint(model_id="vendor/wrong")], [endpoint(model_id=[])], [endpoint(status=-1)],
    [endpoint(supported_parameters=["max_tokens"])],
    [endpoint(pricing={"prompt": "0.01", "completion": "0"})], [endpoint(pricing={})],
])
def test_no_matching_serving_endpoint_stops_before_inference(monkeypatch, endpoints):
    from haizflow.services.translation_model_catalog import _option

    send = Mock(return_value={"data": {"endpoints": endpoints}})
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="chưa có endpoint khả dụng"):
        _real_check_endpoints(_option("openrouter", row()))
    assert send.call_args.args == ("https://openrouter.ai/api/v1/models/vendor/new%3Afree/endpoints", "")
    assert send.call_count == 1


def test_endpoint_validation_includes_selected_reasoning_parameters(monkeypatch):
    from haizflow.services.translation_model_catalog import _option

    option = _option("openrouter", row(supported_parameters=["max_tokens", "response_format", "reasoning"],
                                       reasoning={"mandatory": False}))
    send = Mock(return_value={"data": {"endpoints": [endpoint()]}})
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="chưa có endpoint"):
        _real_check_endpoints(option, reasoning_effort="enabled")
    assert send.call_count == 1


@pytest.mark.parametrize("paid", [False, True])
def test_provider_default_needs_json_support_but_not_output_cap_support(monkeypatch, paid):
    model = "vendor/new" if paid else "vendor/new:free"
    pricing = {"prompt": "0.01" if paid else "0", "completion": "0"}
    parameters = ["structured_outputs"] if paid else ["response_format"]
    monkeypatch.setattr(guard, "_check_endpoints", _real_check_endpoints)
    send = Mock(side_effect=[{"data": row(model, supported_parameters=parameters, pricing=pricing)},
                            {"data": {"endpoints": [endpoint(model_id=model,
                                supported_parameters=parameters, pricing=pricing)]}}])
    monkeypatch.setattr(api, "_json_request", send)
    protocol = guard.prepare(profile(model))
    assert protocol["parameters"] == parameters
    assert protocol["max_completion_tokens"] == 4096
    assert send.call_count == 2
    assert all(call.args[1] == "" and len(call.args) == 2 for call in send.call_args_list)


def test_capacity_metadata_is_safe_for_every_matching_serving_provider(monkeypatch):
    from haizflow.services.translation_model_catalog import _option

    send = Mock(return_value={"data": {"endpoints": [endpoint(), endpoint(context_length=8192,
        max_completion_tokens=2048), endpoint(status=-1, max_completion_tokens=64)]}})
    monkeypatch.setattr(api, "_json_request", send)
    result = _real_check_endpoints(_option("openrouter", row()))
    assert result["context_length"] == 8192 and result["max_completion_tokens"] == 2048


def test_documented_canonical_model_alias_does_not_change_the_requested_model(monkeypatch):
    monkeypatch.setattr(guard, "_check_endpoints", _real_check_endpoints)
    send = Mock(side_effect=[{"data": row(canonical_slug="vendor/new-20261115")},
                            {"data": {"endpoints": [endpoint(model_id="vendor/new-20261115")]}}])
    monkeypatch.setattr(api, "_json_request", send)
    assert guard.prepare(profile())["value"] == "vendor/new:free"
    assert send.call_count == 2


def test_removed_reasoning_control_stops_before_post_and_keeps_project_choice(monkeypatch):
    monkeypatch.setattr(guard, "_check_endpoints", _real_check_endpoints)
    identifier = connections.add("openrouter", "A", "synthetic", "vendor/new:free")
    choice = "api:" + identifier
    send = Mock(return_value={"data": row()})
    monkeypatch.setattr(api, "_json_request", send)
    with pytest.raises(RuntimeError, match="reasoning"):
        api.translate_texts(["PRIVATE SUBTITLE"], model=choice, source_language="en", target_language="vi",
                            video_id="", reasoning_effort="enabled")
    assert send.call_count == 1 and len(send.call_args.args) == 2
    assert "PRIVATE SUBTITLE" not in repr(send.call_args)
    assert connections.get_connection(identifier)["model"] == "vendor/new:free"


def test_mandatory_internal_reasoning_without_a_supported_control_is_not_sent_as_a_parameter():
    from haizflow.services.translation_api_policy import capabilities, request_limits, request_options
    from haizflow.services.translation_model_catalog import _option

    protocol = _option("openrouter", row(reasoning={"mandatory": True}))
    assert capabilities("openrouter", "vendor/new:free", protocol=protocol)["mandatory"]
    assert request_options("openrouter", "vendor/new:free", protocol=protocol) == {}
    limits = request_limits("openrouter", "vendor/new:free", 2048, protocol=protocol)
    assert limits["reasoning_active"] and limits["timeout"] == 240 and limits["max_tokens"] is None
    with pytest.raises(ValueError):
        request_options("openrouter", "vendor/new:free", "high", protocol=protocol)


@pytest.mark.parametrize("initial,texts", [(None, []), (["Đã dịch."], ["Done."])])
def test_no_network_for_empty_or_fully_cached_translation(monkeypatch, initial, texts):
    identifier = connections.add("openrouter", "A", "synthetic", "vendor/new:free")
    send = Mock()
    monkeypatch.setattr(api, "_json_request", send)
    assert api.translate_texts(texts, model="api:" + identifier, source_language="en", target_language="vi",
                               video_id="", initial_translations=initial) == (initial or [])
    send.assert_not_called()
