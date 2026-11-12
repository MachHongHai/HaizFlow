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
    from haizflow.services import translation_reasoning_catalog

    # Exercise curated fallback, independently of cached/bundled public metadata.
    monkeypatch.setattr(translation_reasoning_catalog, "get", lambda _model: None)
    assert request_options("openrouter", model) == {"reasoning": {"effort": effort, "exclude": True}}


@pytest.mark.parametrize("provider,model", [
    ("custom", "gpt-6-luna"), ("custom", "deepseek-flash"), ("openai", "gpt-4.1-mini"),
    ("openai", "Future/Unknown-Model"), ("openai", "gpt-6-astra-pro"),
    ("openrouter", "Unknown/Reasoner"), ("deepseek", "unknown-model")])
def test_unknown_capabilities_are_not_guessed(provider, model):
    assert request_options(provider, model) == {}


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
    assert limits["max_tokens"] == 11252 and limits["sentences"] == 12
    assert request_limits("openrouter", model, 32768)["max_tokens"] == 32768


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
    assert limits["max_tokens"] <= min(maximum or context, context // 2)
    assert limits["characters"] * 4 + 1024 <= limits["max_tokens"]
    assert limits["sentences"] <= 24 and limits["characters"] < 4000


def test_all_seven_free_models_use_real_toggle_or_mandatory_reasoning_metadata(tmp_path, monkeypatch):
    from haizflow.services import translation_catalog_cache as cache
    from haizflow.services import translation_reasoning_catalog as reasoning

    monkeypatch.setattr(cache, "_PATH", tmp_path / "absent-models.json")
    monkeypatch.setattr(reasoning, "_PATH", tmp_path / "absent-reasoning.json")
    rows = [row for row in cache.load() if row.get("pricing_kind") == "free"]
    assert len(rows) == 7
    mandatory = {"recursive/flint-v1.0:free", "liquid/lfm-2.5-2.6b:free", "liquid/lfm-3-1.7b:free"}
    for row in rows:
        model = row["value"]
        info = capabilities("openrouter", model)
        limits = request_limits("openrouter", model, 2156)
        assert limits["max_tokens"] <= row["max_completion_tokens"]
        if model in mandatory:
            assert info["mandatory"] and info["values"] == []
            assert request_options("openrouter", model) == {"reasoning": {"exclude": True}}
            assert limits["reasoning_active"] and limits["max_tokens"] >= 8192
            for effort in ("disabled", "none", "enabled"):
                with pytest.raises(ValueError):
                    request_options("openrouter", model, effort)
        elif model == "stealth/crouton-alpha":
            assert info["mandatory"] and info["parameter"] == "reasoning.effort"
            assert info["default"] == "minimal"
            assert request_options("openrouter", model) == {"reasoning": {"effort": "minimal", "exclude": True}}
            assert limits["reasoning_active"] and limits["max_tokens"] >= 8192
        else:
            assert info["parameter"] == "reasoning.enabled" and info["values"] == ["disabled", "enabled"]
            assert request_options("openrouter", model) == {"reasoning": {"enabled": False, "exclude": True}}
            assert not limits["reasoning_active"] and limits["max_tokens"] == 2156
            assert request_options("openrouter", model, "enabled") == {
                "reasoning": {"enabled": True, "exclude": True}}
            enabled = request_limits("openrouter", model, 2156, "enabled")
            assert enabled["reasoning_active"] and enabled["max_tokens"] >= 10240
            assert enabled["max_tokens"] <= row["max_completion_tokens"] and enabled["sentences"] <= 12


def test_unknown_reasoning_support_reserves_headroom_without_inventing_controls(monkeypatch):
    from haizflow.services import translation_catalog_cache, translation_reasoning_catalog

    monkeypatch.setattr(translation_reasoning_catalog, "get", lambda _: None)
    monkeypatch.setattr(translation_catalog_cache, "protocol_for", lambda _: {"reasoning_supported": True})
    assert request_options("openrouter", "vendor/unknown-reasoner") == {}
    assert request_limits("openrouter", "vendor/unknown-reasoner", 2048)["reasoning_active"]


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
