"""Model discovery uses GET only, isolates drafts and never falls back to inference."""
import json
import threading
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from haizflow.services import api_translation as api
from haizflow.services import translation_model_catalog as catalog


def router(model, **extra):
    return {"id": model, "name": "Readable " + model,
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "supported_parameters": ["structured_outputs"], **extra}


def test_presets_are_explicit_independent_and_translation_only():
    assert catalog.presets("openai")[0]["value"] == "gpt-6-luna"
    assert catalog.presets("deepseek")[0]["value"] == "deepseek-flash"
    assert catalog.presets("custom") == catalog.presets("openrouter") == []
    options = catalog.presets("openai")
    options[0]["value"] = "changed"
    assert catalog.presets("openai")[0]["value"] == "gpt-6-luna"


def test_openai_list_is_filtered_without_paid_inference(monkeypatch):
    request = Mock(return_value={"data": [{"id": value} for value in (
        "gpt-6-luna", "gpt-4.1-mini", "gpt-3.5-turbo", "gpt-4", "whisper-1",
        "gpt-4o-audio-preview", "gpt-image-1", "o3", "gpt-6-search", "gpt-4o-2024-05-13")]})
    monkeypatch.setattr(api, "_json_request", request)
    rows, state = catalog.fetch_models("openai", "secret", "https://attacker.invalid")
    assert state == "ready"
    assert {row["value"] for row in rows} == {"gpt-6-luna", "gpt-4.1-mini", "o3"}
    assert request.call_args.args == ("https://api.openai.com/v1/models", "secret")
    assert "payload" not in request.call_args.kwargs
    assert "secret" not in json.dumps(rows)


def test_router_paginates_filters_json_support_and_sanitizes(monkeypatch):
    first = [router(f"vendor/model-{index}") for index in range(100)]
    second = [router("vendor/final", name="<b>Not HTML</b>"), router("vendor/audio"),
              router("openrouter/auto"), router("vendor/no-schema", supported_parameters=["response_format"]),
              router("vendor/image-only", architecture={"input_modalities": ["text"], "output_modalities": ["image"]}),
              router("bad id"), None, router("vendor/expired", expiration_date="2000-01-01")]
    request = Mock(side_effect=[{"data": first}, {"data": second}])
    monkeypatch.setattr(api, "_json_request", request)
    rows, state = catalog.fetch_models("openrouter", "secret")
    assert state == "ready" and len(rows) == 101
    assert rows[0] == {"value": "vendor/final", "label": "<b>Not HTML</b>", "pricing_kind": "unknown",
                       "output_format": "json_schema"}
    assert "offset=100" in request.call_args.args[0]
    assert "supported_parameters=" not in request.call_args.args[0]


@pytest.mark.parametrize("parameters,pricing,outputs,expected", [
    (["response_format"], {"prompt": "0", "completion": "0"}, ["text"], "json_object"),
    (["structured_outputs", "response_format"], {"prompt": "0", "completion": "0"}, ["text"], "json_schema"),
    (["response_format"], {"prompt": "0.01", "completion": "0"}, ["text"], None),
    (["response_format"], None, ["text"], None),
    ([], {"prompt": "0", "completion": "0"}, ["text"], None),
    (["response_format"], {"prompt": "0", "completion": "0"}, ["text", "audio"], None),
])
def test_free_json_mode_is_supported_without_guessing_paid_or_audio_capabilities(
        parameters, pricing, outputs, expected):
    row = router("vendor/model:free", supported_parameters=parameters, pricing=pricing,
                 architecture={"input_modalities": ["text"], "output_modalities": outputs})
    option = catalog._option("openrouter", row)
    assert (option or {}).get("output_format") == expected


@pytest.mark.parametrize("model", ["deepseek/deepseek-r1:free", "deepseek/deepseek-r1-0528:free"])
def test_retired_free_models_cannot_reappear_even_with_stale_capability_metadata(model):
    assert catalog._option("openrouter", router(model, pricing={"prompt": "0", "completion": "0"})) is None


@pytest.mark.parametrize("model", ["google/gemma-2-27b-it", "bytedance/ui-tars-1.5-7b",
                                 "inference-net/schematron-v2-small", "typesafe/jev-router"])
def test_unsuitable_or_confirmed_incompatible_models_are_not_recommended(model):
    assert catalog._option("openrouter", router(model)) is None


def test_catalogue_keeps_bounded_protocol_metadata_for_compatible_models():
    option = catalog._option("openrouter", router("vendor/gemma-chat", context_length=8192,
        top_provider={"max_completion_tokens": 2048}, architecture={"input_modalities": ["text"],
        "output_modalities": ["text"], "instruct_type": "gemma"}))
    assert {field: option[field] for field in ("context_length", "max_completion_tokens", "prompt_format")} == {
        "context_length": 8192, "max_completion_tokens": 2048, "prompt_format": "user_only"}


def test_partial_catalog_is_marked_and_repeated_page_is_bounded(monkeypatch):
    data = {"data": [router(f"model-{index}") for index in range(100)]}
    request = Mock(return_value=data)
    monkeypatch.setattr(api, "_json_request", request)
    rows, state = catalog.fetch_models("openrouter", "secret")
    assert len(rows) == 100 and state == "partial" and request.call_count == 2
    request.side_effect = [data, TimeoutError("secret service body")]
    request.reset_mock()
    rows, state = catalog.fetch_models("openrouter", "secret")
    assert len(rows) == 100 and state == "partial"


@pytest.mark.parametrize("status,state", [
    (401, "auth"), (403, "auth"), (404, "unsupported"), (429, "error"), (503, "error")])
def test_errors_never_expose_bodies_or_retry_inference(monkeypatch, status, state):
    request = Mock(side_effect=HTTPError("https://secret.invalid", status, "private-body", None, None))
    monkeypatch.setattr(api, "_json_request", request)
    assert catalog.fetch_models("custom", "secret", "https://example.com/v1") == ([], state)
    assert request.call_count == 1


def test_invalid_drafts_and_cancel_never_make_network_requests(monkeypatch):
    request = Mock()
    monkeypatch.setattr(api, "_json_request", request)
    assert catalog.fetch_models("custom", "secret", "http://remote.invalid") == ([], "invalid")
    assert catalog.fetch_models("openai", "bad\nkey") == ([], "invalid")
    cancelled = threading.Event()
    cancelled.set()
    assert catalog.fetch_models("openai", "secret", cancelled=cancelled) == ([], "cancelled")
    request.assert_not_called()


@pytest.mark.parametrize("pricing,expected", [
    ({"prompt": "0", "completion": "0"}, "free"),
    ({"prompt": "0.00000001", "completion": "0"}, "paid"),
    ({"prompt": "0", "completion": "0", "request": "0.01"}, "paid"),
    ({"prompt": "0"}, "unknown"),
    ({"prompt": "NaN", "completion": "0"}, "unknown"),
    ({"prompt": "-1", "completion": "0"}, "unknown"),
    (None, "unknown"),
])
def test_openrouter_pricing_label_uses_actual_text_request_prices(pricing, expected):
    option = catalog._option("openrouter", router("vendor/model:free", pricing=pricing))
    assert option["pricing_kind"] == expected  # A :free suffix alone must not override prices.


def test_controller_ignores_late_results_after_draft_changes(monkeypatch):
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    from haizflow.desktop.translation_api_controller import TranslationApiController

    app = QGuiApplication.instance() or QGuiApplication([])
    host = QObject()
    controller = TranslationApiController(host)
    entered, release = threading.Event(), threading.Event()

    def fetch(*_args, **_kwargs):
        entered.set()
        release.wait(2)
        return [{"value": "old-model", "label": "Old account"}], "ready"

    monkeypatch.setattr(catalog, "fetch_models", fetch)
    controller.loadModels("openai", "private-secret", "")
    assert entered.wait(1) and controller.catalogState == "loading"
    old_generation = controller._catalog_generation
    controller.resetModels()
    release.set()
    QTest.qWait(40)
    app.processEvents()
    controller._finish_catalog(old_generation, [{"value": "late"}], "ready")
    assert controller.catalogOptions == [] and controller.catalogState == "idle"
    controller._finish_catalog(controller._catalog_generation, [{"value": "new"}], "ready")
    assert controller.catalogOptions == [{"value": "new"}]
