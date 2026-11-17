"""Cost controls never rename models or assume a custom server's capabilities."""
import pytest

from haizflow.core.translation_models import normalize_translation_model
from haizflow.services.translation_api_policy import capabilities, request_limits, request_options


@pytest.mark.parametrize("model,effort", [
    ("gpt-6-luna", "none"), ("gpt-6-luna-2026-10-01", "none"),
    ("gpt-6.1-terra", "none"), ("gpt-6-sol", "none"),
    ("gpt-6.1-sol", "low"), ("gpt-6-astra", "low"),
    ("gpt-5.6-sol", "none"), ("gpt-5.1", "none"),
    ("gpt-5-2025-08-07", "minimal"), ("o3", "low"), ("o4-mini", "low")])
def test_documented_openai_effort_is_lowest_compatible(model, effort):
    assert request_options("openai", model) == {"reasoning": {"effort": effort}}


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-pro", "deepseek-v4-flash"])
def test_current_deepseek_models_do_not_default_to_high_thinking(model):
    assert request_options("deepseek", model) == {"thinking": {"type": "disabled"}}


@pytest.mark.parametrize("model,effort", [
    ("openai/gpt-6-luna", "none"), ("openai/gpt-6-astra", "low"),
    ("deepseek/deepseek-flash:free", "none"), ("openai/o3", "low"),
    ("deepseek/deepseek-v4.1-flash", "none"), ("deepseek/deepseek-v4.1-flash-1017", "none"),
    ("deepseek/deepseek-v4-pro", "none")])
def test_openrouter_uses_compatible_reasoning_control_not_exclusion_alone(model, effort, monkeypatch):
    from haizflow.services import translation_catalog_cache, translation_reasoning_catalog

    # Exercise curated fallback, independently of cached/bundled public metadata.
    monkeypatch.setattr(translation_reasoning_catalog, "get", lambda _model: None)
    monkeypatch.setattr(translation_catalog_cache, "protocol_for", lambda _model: {})
    assert request_options("openrouter", model) == {"reasoning": {"effort": effort, "exclude": True}}


@pytest.mark.parametrize("provider,model", [
    ("custom", "gpt-6-luna"), ("custom", "deepseek-flash"), ("openai", "gpt-4.1-mini"),
    ("openai", "Future/Unknown-Model"), ("openai", "gpt-6-astra-pro"),
    ("openrouter", "Unknown/Reasoner"), ("deepseek", "unknown-model")])
def test_unknown_capabilities_are_not_guessed(provider, model):
    assert request_options(provider, model) == {}


@pytest.mark.parametrize("pricing", ["free", "paid"])
@pytest.mark.parametrize("ceiling", [8192, 32768])
def test_mandatory_high_uses_provider_budget_without_changing_reasoning(pricing, ceiling):
    protocol = {"reasoning_supported": True, "pricing_kind": pricing,
                "max_completion_tokens": ceiling, "context_length": 131072,
                "reasoning_capabilities": {"mandatory": True, "values": ["high"], "default": "high"}}
    options = request_options("openrouter", "vendor/mandatory-high", protocol=protocol)
    limits = request_limits("openrouter", "vendor/mandatory-high", 2048, protocol=protocol)
    assert options == {"reasoning": {"effort": "high", "exclude": True}}
    assert limits["max_tokens"] is None
    assert limits["reasoning_active"] and limits["mandatory"]


def test_mandatory_default_must_not_increase_budget_when_optional_reasoning_is_disabled():
    protocol = {"reasoning_supported": True, "max_completion_tokens": 32768,
                "reasoning_capabilities": {"mandatory": False, "values": ["none", "high"], "default": "none"}}
    assert request_limits("openrouter", "vendor/optional", 2048, protocol=protocol)["max_tokens"] is None


@pytest.mark.parametrize("pricing", ["free", "paid"])
def test_mandatory_reasoner_without_effort_uses_provider_default(pricing):
    protocol = {"reasoning_supported": True, "pricing_kind": pricing,
                "max_completion_tokens": 65536, "context_length": 131072,
                "reasoning_capabilities": {"mandatory": True, "values": [], "default": ""}}
    assert request_options("openrouter", "vendor/mandatory", protocol=protocol) == {"reasoning": {"exclude": True}}
    assert request_limits("openrouter", "vendor/mandatory", 2048, protocol=protocol)["max_tokens"] is None
    protocol["max_completion_tokens"] = 8192
    assert request_limits("openrouter", "vendor/mandatory", 2048, protocol=protocol)["max_tokens"] is None


@pytest.mark.parametrize("model", ["deepseek/deepseek-r1", "deepseek/deepseek-r1-0528",
                                 "deepseek/deepseek-r1-0528:free"])
def test_r1_mandatory_reasoning_does_not_invent_an_effort_control(model):
    info = capabilities("openrouter", model)
    assert info["mandatory"] and info["values"] == []
    assert request_options("openrouter", model) == {"reasoning": {"exclude": True}}
    for effort in ("none", "low", "high"):
        with pytest.raises(ValueError):
            request_options("openrouter", model, effort)
    limits = request_limits("openrouter", model, 3060)
    assert limits["max_tokens"] is None and limits["sentences"] == 12
    assert request_limits("openrouter", model, 32768)["max_tokens"] is None


def test_only_builtin_translation_enums_are_case_normalized():
    choice = "api:" + "a" * 32 + ":Vendor/MixedCase:free#prompt"
    assert normalize_translation_model(choice) == choice
    assert normalize_translation_model(" Q4 ") == "q4"
    assert normalize_translation_model(None) == "auto"


@pytest.mark.parametrize("maximum,context", [(2048, 8192), (4096, 8192), (None, 4096)])
def test_router_small_limits_bound_requests_and_shrink_batches_before_sending(monkeypatch, maximum, context):
    from haizflow.services import translation_catalog_cache

    metadata = {"context_length": context, **({"max_completion_tokens": maximum} if maximum else {})}
    monkeypatch.setattr(translation_catalog_cache, "protocol_for", lambda _model: metadata)
    limits = request_limits("openrouter", "vendor/small-context", 6000)
    assert limits["max_tokens"] is None
    assert limits["characters"] * 4 + 1024 <= min(maximum or context, context // 2)
    assert limits["sentences"] <= 24 and limits["characters"] < 4000


def test_bundled_free_models_keep_advertised_reasoning_and_use_provider_output_defaults(tmp_path, monkeypatch):
    from haizflow.services import translation_catalog_cache as cache
    from haizflow.services import translation_reasoning_catalog as reasoning

    monkeypatch.setattr(cache, "_PATH", tmp_path / "absent-models.json")
    monkeypatch.setattr(reasoning, "_PATH", tmp_path / "absent-reasoning.json")
    rows = [row for row in cache.load() if row.get("pricing_kind") == "free"]
    assert rows
    for row in rows:
        model = row["value"]
        info = capabilities("openrouter", model)
        limits = request_limits("openrouter", model, 2156)
        assert limits["max_tokens"] is None
        if info.get("mandatory"):
            assert "none" not in info["values"] and not info.get("toggle")
            expected = {"exclude": True}
            if info["default"]:
                expected["effort"] = info["default"]
            assert request_options("openrouter", model) == {"reasoning": expected}
            assert limits["reasoning_active"] and limits["sentences"] <= 12
            for effort in ("disabled", "none", "enabled"):
                with pytest.raises(ValueError):
                    request_options("openrouter", model, effort)
        elif info.get("toggle"):
            assert info["parameter"] == "reasoning.enabled" and info["values"] == ["disabled", "enabled"]
            assert request_options("openrouter", model) == {"reasoning": {"enabled": False, "exclude": True}}
            assert not limits["reasoning_active"] and limits["max_tokens"] is None
            assert request_options("openrouter", model, "enabled") == {
                "reasoning": {"enabled": True, "exclude": True}}
            enabled = request_limits("openrouter", model, 2156, "enabled")
            assert enabled["reasoning_active"] and enabled["max_tokens"] is None
            assert enabled["sentences"] <= 12
        else:
            assert info["default"] == "none"
            assert not limits["reasoning_active"] and limits["max_tokens"] is None
            assert request_options("openrouter", model) == {"reasoning": {"effort": "none", "exclude": True}}


@pytest.mark.parametrize("provider,model,effort,active", [
    ("openai", "gpt-6.1-sol", "", True),
    ("openai", "gpt-6.1-sol", "low", True),
    ("openai", "gpt-5", "minimal", True),
    ("openai", "gpt-6-luna", "", False),
    ("openai", "gpt-6-luna", "none", False),
    ("openai", "gpt-6-luna", "high", True),
    ("openai", "gpt-4.1-mini", "", False),
    ("deepseek", "deepseek-flash", "", False),
    ("deepseek", "deepseek-flash", "disabled", False),
    ("deepseek", "deepseek-flash", "low", True),
    ("deepseek", "deepseek-v4-pro", "high", True),
    ("deepseek", "deepseek-v4-pro", "max", True),
    ("custom", "gpt-6.1-sol", "", False),
])
def test_official_provider_reasoning_limits_match_effective_request(provider, model, effort, active):
    limits = request_limits(provider, model, 2048, effort)
    assert limits["reasoning_active"] is active
    assert limits["timeout"] == (240 if active else 90)
    assert (limits["sentences"], limits["characters"]) == ((12, 2000) if active else (24, 4000))
    assert limits["max_tokens"] is None


def test_unknown_reasoning_support_reserves_headroom_without_inventing_controls(monkeypatch):
    from haizflow.services import translation_catalog_cache, translation_reasoning_catalog

    monkeypatch.setattr(translation_reasoning_catalog, "get", lambda _: None)
    monkeypatch.setattr(translation_catalog_cache, "protocol_for", lambda _: {"reasoning_supported": True})
    assert request_options("openrouter", "vendor/unknown-reasoner") == {}
    assert request_limits("openrouter", "vendor/unknown-reasoner", 2048)["reasoning_active"]


def test_selecting_reasoning_effort_does_not_reintroduce_output_caps():
    protocol = {"reasoning_supported": True, "reasoning_capabilities": {
        "mandatory": True, "values": ["low", "high"], "default": "low"}}
    assert request_limits("openrouter", "vendor/low-reasoner", 2048,
                          protocol=protocol)["max_tokens"] is None
    assert request_limits("openrouter", "vendor/low-reasoner", 2048, "high",
                          protocol=protocol)["max_tokens"] is None


def test_batch_application_preserves_project_api_model_case(monkeypatch):
    from types import SimpleNamespace

    from haizflow.core import model_choices
    from haizflow.desktop.project_commands_controller import ProjectCommandsController

    choice = "api:" + "a" * 32 + ":Vendor/MixedCase"
    host = SimpleNamespace(_settings_processing_device="cpu", _speech_recognition_model="small-cpu")

    class ReachedModelPolicy(Exception):
        pass

    def inspect(value, *args, **kwargs):
        assert value == choice
        raise ReachedModelPolicy

    monkeypatch.setattr(model_choices, "project_translation_choice", inspect)
    with pytest.raises(ReachedModelPolicy):
        ProjectCommandsController(host).apply_batch_settings(
            "A", "vi", "edge", "vi-VN-HoaiMyNeural", False, 60, translation_model=choice)
