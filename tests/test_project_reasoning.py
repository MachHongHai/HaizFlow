"""Reasoning is project-local, provider-compatible and part of translation identity."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.schemas.video import VideoConfig
from haizflow.services import api_translation as api
from haizflow.services import gemini_context, translation
from haizflow.services import translation_api_policy as policy
from haizflow.services import translation_connections as connections


@pytest.fixture
def credentials(tmp_path, monkeypatch):
    secrets = {}
    monkeypatch.setattr(connections, "_PATH", tmp_path / "connections.json")
    monkeypatch.setattr(connections.secure_credentials, "read_secret", lambda name: secrets.get(name, ""))
    monkeypatch.setattr(connections.secure_credentials, "write_secret",
                        lambda name, key, **kw: secrets.__setitem__(name, key))
    identifier = connections.add("openai", "Private test", "fake-key")
    return "api:" + identifier + ":gpt-6.1-sol"


@pytest.mark.parametrize("provider,model,values", [
    ("openai", "gpt-6.1-sol", ["low", "medium", "high", "xhigh", "max"]),
    ("openai", "gpt-6-luna", ["none", "low", "medium", "high", "xhigh", "max"]),
    ("deepseek", "deepseek-flash", ["low", "high", "max"]),
    ("gemini", "gemini-3.5-flash-lite", ["minimal", "low", "medium", "high"]),
    ("gemini", "gemini-3.8-flash", ["low", "medium", "high"]),
    ("openrouter", "deepseek/deepseek-v4-pro", ["none", "high", "xhigh"]),
    ("custom", "unknown", [])])
def test_official_labels_and_supported_values_only(provider, model, values):
    assert policy.capabilities(provider, model).get("values", []) == values


@pytest.mark.parametrize("provider,model,effort", [
    ("openai", "gpt-6.1-sol", "none"), ("deepseek", "deepseek-flash", "medium"),
    ("openrouter", "deepseek/deepseek-v4-pro", "low"), ("custom", "unknown", "high")])
def test_unsupported_values_reject_before_spending(provider, model, effort):
    with pytest.raises(ValueError, match="reasoning"):
        policy.request_options(provider, model, effort)


def test_deepseek_uses_native_thinking_and_effort_parameters():
    assert policy.request_options("deepseek", "deepseek-flash", "disabled") == {"thinking": {"type": "disabled"}}
    assert policy.request_options("deepseek", "deepseek-flash", "max") == {
        "thinking": {"type": "enabled"}, "reasoning_effort": "max"}


def test_optional_reasoning_enabled_is_a_valid_project_and_batch_value():
    from haizflow.services import batch_settings

    config = VideoConfig(translation_reasoning_effort="enabled")
    assert config.translation_reasoning_effort == "enabled"
    batch = batch_settings.config_for({"translationReasoningEffort": "enabled"})
    assert batch.translation_reasoning_effort == "enabled"


def test_config_metadata_and_batch_defaults_keep_project_reasoning(credentials, tmp_path):
    import uuid

    from haizflow.services import batch_settings, video_store

    config = VideoConfig(project_type="manual", project_directory=str(tmp_path), translation_model=credentials,
                         translator_provider="api", translation_reasoning_effort="high")
    video = video_store.create_video(uuid.uuid4().hex, "fixture.mp4", config)
    assert video_store.get_video(video.video_id).translation_reasoning_effort == "high"
    values = batch_settings.values_for(video)
    assert values["translationReasoningEffort"] == "high"
    assert batch_settings.config_for(values).translation_reasoning_effort == "high"
    assert VideoConfig().translation_reasoning_effort == ""


def test_reasoning_changes_translation_identity_not_voice_or_unset_legacy_snapshot(credentials):
    from haizflow.services.processing_resume import configuration_snapshot

    video = SimpleNamespace(project_type="manual", manual_target_tool="translation", translation_model=credentials,
                            translation_reasoning_effort="", files={})
    before = configuration_snapshot(video, "cpu")
    before_signature = gemini_context.signature_parts(video)
    assert "translation_reasoning_effort" not in before["settings"]
    video.translation_reasoning_effort = "high"
    assert configuration_snapshot(video, "cpu") != before
    assert gemini_context.signature_parts(video) != before_signature
    assert gemini_context.guidance(video)["reasoning_effort"] == "high"
    video.manual_target_tool = "voice"
    voice = configuration_snapshot(video, "cpu")
    video.translation_reasoning_effort = "max"
    assert configuration_snapshot(video, "cpu") == voice


def test_pipeline_passes_selected_reasoning_and_reuses_matching_completed_cues(credentials, tmp_path, monkeypatch):
    source, output, checkpoint = (tmp_path / name for name in ("source.json", "out.json", "progress.json"))
    source.write_text('[{"start":0,"end":2,"text":"Hello."}]', "utf-8")
    for module in (api, api.gemini_translation, translation):
        monkeypatch.setattr(module, "log_to_video", Mock())
        if hasattr(module, "check_cancellation"):
            monkeypatch.setattr(module, "check_cancellation", lambda _: None)
    monkeypatch.setattr(translation, "shutdown_hymt2_worker", Mock())
    monkeypatch.setattr(translation, "_suspicious_translation_indexes", lambda *args: set())
    send = Mock(return_value={"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps({"translations": [{"id": 0, "text": "Xin chào."}]})}]}]})
    monkeypatch.setattr(api, "_json_request", send)
    options = dict(provider="api", translation_model=credentials, checkpoint_path=str(checkpoint),
                   retain_checkpoint=True)
    for effort, count in [("high", 1), ("high", 1), ("low", 2)]:
        translation.translate_segments(str(source), str(output), "fixture", reasoning_effort=effort, **options)
        assert send.call_count == count
        assert send.call_args.args[2]["reasoning"] == {"effort": effort}
    assert send.call_args.args[2]["max_output_tokens"] == 2048  # Low remains bounded, no forced upgrade.


def test_gemini_explicit_thinking_level_reaches_native_payload():
    from haizflow.services.gemini_translation import _payload_for_chunk

    result = _payload_for_chunk([(0, "Hello.")], model="gemini-3.5-flash-lite", source_language="en",
                                target_language="vi", reasoning_effort="high")
    assert result["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "high"
    assert result["generationConfig"]["maxOutputTokens"] == 16384
    with pytest.raises(ValueError):
        _payload_for_chunk([(0, "Hello.")], model="gemini-3.8-flash", source_language="en",
                           target_language="vi", reasoning_effort="minimal")


def test_desktop_selection_is_local_and_model_switch_resets_to_supported_default(credentials):
    from haizflow.desktop.qml_controller import HaizFlowController

    host = SimpleNamespace(_translation_model=credentials, _translation_reasoning_effort="",
        _show_app_alert=Mock(), geminiGuidanceChanged=Mock(), translationModelChanged=Mock())
    HaizFlowController.translationReasoningEffort.fset(host, "high")
    assert host._translation_reasoning_effort == "high"
    HaizFlowController.translationReasoningEffort.fset(host, "none")
    assert host._translation_reasoning_effort == "high" and host._show_app_alert.called
    HaizFlowController.translationModel.fset(host, credentials.replace("gpt-6.1-sol", "gpt-6-luna"))
    assert host._translation_reasoning_effort == ""


def test_openrouter_advertised_capabilities_survive_restart_and_do_not_store_keys(tmp_path, monkeypatch):
    from haizflow.services import translation_reasoning_catalog as catalog

    path = tmp_path / "public-capabilities.json"
    monkeypatch.setattr(catalog, "_PATH", path)
    info = catalog.advertised({"mandatory": True, "supported_efforts": ["none", "medium", "high"],
                               "default_effort": "high", "api_key": "PRIVATE"})
    assert info == {"values": ["medium", "high"], "default": "medium", "mandatory": True}
    catalog.remember([{"value": "vendor/new-model", "reasoning_capabilities": info}])
    assert "PRIVATE" not in path.read_text("utf-8")
    assert policy.capabilities("openrouter", "vendor/new-model")["values"] == ["medium", "high"]
    assert policy.request_options("openrouter", "vendor/new-model", "high") == {
        "reasoning": {"effort": "high", "exclude": True}}
    with pytest.raises(ValueError):
        policy.request_options("openrouter", "vendor/new-model", "none")
    path.write_text("broken file", "utf-8")
    assert policy.capabilities("openrouter", "vendor/new-model") == {}


@pytest.mark.parametrize("supported", ["high", {}, 1])
def test_openrouter_missing_explicit_efforts_never_invents_supported_levels(supported):
    from haizflow.services import translation_reasoning_catalog as catalog

    assert catalog.advertised({"supported_efforts": supported}) is None


def test_openrouter_null_efforts_are_explicit_gateway_support_not_missing_metadata():
    from haizflow.services import translation_reasoning_catalog as catalog

    assert catalog.advertised({"supported_efforts": None})["values"] == list(policy.EFFORTS)
    assert catalog.advertised({}) is None


def test_openrouter_mandatory_reasoning_without_efforts_survives_restart(tmp_path, monkeypatch):
    from haizflow.services import translation_reasoning_catalog as catalog

    monkeypatch.setattr(catalog, "_PATH", tmp_path / "capabilities.json")
    info = catalog.advertised({"mandatory": True})
    assert info == {"values": [], "default": "", "mandatory": True}
    catalog.remember([{"value": "vendor/mandatory-model", "reasoning_capabilities": info}])
    assert catalog.get("vendor/mandatory-model")["mandatory"] is True
    assert policy.request_limits("openrouter", "vendor/mandatory-model", 2048)["max_tokens"] == 10240
    assert policy.request_options("openrouter", "vendor/mandatory-model") == {"reasoning": {"exclude": True}}
