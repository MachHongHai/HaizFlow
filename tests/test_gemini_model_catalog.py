"""All Gemini entry points use the same curated, model-specific contract."""

import pytest
import io
import json
from unittest.mock import Mock
from urllib.error import HTTPError

from haizflow.core.gemini_models import FREE_TIER_MODELS, MODEL_LABELS, PAID_ONLY_MODELS, THINKING_LEVELS, model_options
from haizflow.core.translation_models import GEMINI_MODELS, is_cloud_model, translation_provider
from haizflow.schemas.video import VideoConfig, VideoInfo
from haizflow.services import batch_settings, gemini_translation, translation_api_policy, video_store


def test_current_catalog_is_shared_and_excludes_media_redirects_and_legacy():
    assert set(MODEL_LABELS) == GEMINI_MODELS == set(THINKING_LEVELS)
    assert gemini_translation.MODELS == MODEL_LABELS
    assert {row["value"] for row in model_options()} == GEMINI_MODELS
    assert FREE_TIER_MODELS | PAID_ONLY_MODELS == GEMINI_MODELS
    assert not FREE_TIER_MODELS & PAID_ONLY_MODELS
    assert {row["value"] for row in model_options() if row["pricing_kind"] == "free"} == FREE_TIER_MODELS
    assert {row["value"] for row in model_options() if row["pricing_kind"] == "paid"} == PAID_ONLY_MODELS
    assert {"gemini-4-hydrogen", "gemini-4-argon", "gemini-4-carbon", "gemini-3.6-flash",
            "gemini-3.1-pro-preview", "gemini-3-flash-preview"} <= GEMINI_MODELS
    assert not {"gemini-3.5-flash", "gemini-3.7-flash", "gemini-2.5-flash", "gemini-flash-latest",
                "gemini-3.8-flash-tts", "gemini-omni-1.2-flash"} & GEMINI_MODELS


@pytest.mark.parametrize("model", MODEL_LABELS)
@pytest.mark.parametrize("kind", ["single", "manual", "batch"])
def test_models_survive_project_and_batch_persistence(model, kind):
    config = VideoConfig(project_type=kind, translation_model=model)
    record = VideoInfo(**config.model_dump(), video_id="fixture", original_filename="fixture.mp4", status="pending",
                       created_at="2026-11-15T00:00:00Z", updated_at="2026-11-15T00:00:00Z")
    restored, _ = video_store._migrate_video_metadata(record.model_dump(mode="json"))
    assert restored["translation_model"] == model and restored["translator_provider"] == "gemini"
    assert batch_settings.config_for(batch_settings.values_for(record)).translation_model == model
    assert is_cloud_model(model) and translation_provider(model) == "gemini"


@pytest.mark.parametrize("model", MODEL_LABELS)
def test_documented_efforts_are_exact_and_lowest_is_default(model):
    expected = ["low", "medium", "high"]
    if model in {"gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3-flash-preview"}:
        expected.insert(0, "minimal")
    if model == "gemini-4-hydrogen":
        expected.append("xhigh")
    assert translation_api_policy.capabilities("gemini", model) == {
        "parameter": "thinkingLevel", "values": expected, "default": expected[0]}
    for effort in expected:
        payload = gemini_translation._payload_for_chunk([(0, "Hello.")], model=model, source_language="English",
                    target_language="Vietnamese", reasoning_effort=effort)
        settings = payload["generationConfig"]
        assert settings["thinkingConfig"] == {"thinkingLevel": effort, "includeThoughts": False}
        assert "maxOutputTokens" not in settings
        assert not {"temperature", "topP", "topK"} & settings.keys()
    with pytest.raises(ValueError, match="thinkingLevel"):
        gemini_translation._payload_for_chunk([(0, "Hello.")], model=model, source_language="English",
                                            target_language="Vietnamese", reasoning_effort="max")


def test_mcp_discovery_includes_models_and_reasoning_without_network(monkeypatch):
    from haizflow.mcp.options import model_page

    monkeypatch.setattr(gemini_translation, "active_key", lambda: pytest.fail("Discovery must not read keys"))
    result = model_page("gemini", "", "", 0, 50, False, True)
    assert result["total"] == len(MODEL_LABELS)
    assert result["pricing_basis"] == "free_tier_availability"
    assert "billing-enabled" in result["billing_notice"]
    assert {row["model"] for row in result["items"]} == GEMINI_MODELS
    hydrogen = next(row for row in result["items"] if row["model"] == "gemini-4-hydrogen")
    assert hydrogen["reasoning"]["values"] == ["low", "medium", "high", "xhigh"]
    assert hydrogen["pricing_kind"] == "free"
    free = model_page("gemini", "", "", 0, 50, True)
    assert {row["model"] for row in free["items"]} == FREE_TIER_MODELS
    assert all(row["pricing_kind"] == "free" for row in free["items"])


@pytest.mark.parametrize("fault", [
    {"message": "Quota exceeded: generate_content_free_tier_input_token_count, limit: 0, model: gemini-4-carbon"},
    {"details": [{"violations": [{"quotaMetric": "generate_content_free_tier_input_token_count", "quotaValue": "0"}]}]},
])
def test_zero_free_quota_explains_billing_without_retry_or_key_leak(monkeypatch, fault):
    fault = {**fault, "unused": "private-fixture-key"}
    body = io.BytesIO(json.dumps({"error": fault}).encode())
    failure = HTTPError("https://generativelanguage.googleapis.com", 429, "limited", {}, body)
    send = Mock(side_effect=failure)
    monkeypatch.setattr(gemini_translation, "_open_request", send)
    monkeypatch.setattr(gemini_translation, "_retry_delay", lambda *_args: pytest.fail("No retry for zero quota"))
    with pytest.raises(RuntimeError, match="không có hạn mức miễn phí") as caught:
        gemini_translation._request_chunk([(0, "Hello.")], key="private-fixture-key", model="gemini-4-carbon",
                                          source_language="English", target_language="Vietnamese")
    assert "Billing" in str(caught.value) and "private-fixture-key" not in str(caught.value)
    assert send.call_count == 1 and body.closed


@pytest.mark.parametrize("fault", [
    {"message": "Quota exceeded: generate_content_free_tier_requests, limit: 15"},
    {"message": "generate_content_free_tier_requests, limit: 15\npaid_tier_requests, limit: 0"},
    {"details": [{"violations": [{"quotaMetric": "generate_content_paid_input", "quotaValue": "0"}]}]},
    None, [], "invalid",
])
def test_other_429_causes_are_not_misreported_as_zero_free_quota(fault):
    error = HTTPError("https://generativelanguage.googleapis.com", 429, "limited", {},
                      io.BytesIO(json.dumps({"error": fault}).encode()))
    try:
        assert not gemini_translation._zero_free_quota(error)
    finally:
        error.close()
