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
