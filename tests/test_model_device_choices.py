"""Model policies independent of project names, hardware, or installed models."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.core.model_choices import gpu_choice_blocked, project_model_defaults, project_recognition_choice, recognition_context
from haizflow.core.hardware import HardwareCapabilities
from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.settings_controller import SettingsController
from haizflow.desktop.smart_warmup_controller import SmartWarmupController
from haizflow.schemas.video import VideoConfig


@pytest.mark.parametrize("device", ["cpu", "gpu"])
def test_new_project_defaults_match_app_device(device):
    host = SimpleNamespace(_settings_processing_device=device)
    controller = ProjectImportController(host)
    controller.cancel_background_music_link_import = Mock()
    controller._reset_new_project_setup()
    for attribute, value in project_model_defaults(device).items():
        assert getattr(host, attribute) == value
    assert recognition_context(host._speech_recognition_model, device)["device"] == device


@pytest.mark.parametrize("device, expected", [("gpu", "large-v3-turbo"), ("cpu", "small-cpu")])
def test_legacy_automatic_recognition_follows_device_but_explicit_choices_survive(device, expected):
    assert project_recognition_choice("small", device) == expected
    for explicit in ("small-cpu", "small-gpu", "large-v3-turbo"):
        assert project_recognition_choice(explicit, device) == explicit


def test_opened_legacy_project_warms_same_turbo_choice_as_gpu_ui():
    video = SimpleNamespace(speech_recognition_model="small", manual_target_tool="translation")
    host = SimpleNamespace(_keep_models_warm=True, _settings_processing_device="gpu", _selected_video=lambda: video)
    with patch("haizflow.desktop.smart_warmup_controller.shared_external_engine_pool"):
        warm = SmartWarmupController(host, Mock())
    warm.request_project_prediction()
    assert warm._requests[0].context == {"model": "large-v3-turbo", "device": "gpu"}


def test_gpu_mode_allows_explicit_cpu_model_without_warming_gpu_instead():
    assert recognition_context("small-cpu", "gpu") == {"model": "small", "device": "cpu"}
    assert recognition_context("small-gpu", "gpu") == {"model": "small", "device": "gpu"}
    assert not gpu_choice_blocked("gpu", recognition="small-cpu", translation="q4", voice="omnivoice")


@pytest.mark.parametrize("choice", ["small-gpu", "large-v3-turbo"])
def test_cpu_mode_rejects_gpu_recognition(choice):
    with pytest.raises(ValueError, match="CPU"):
        recognition_context(choice, "cpu")
    assert gpu_choice_blocked("cpu", recognition=choice)


def test_startup_warm_uses_app_mode_not_previous_project_cpu_override():
    host = SimpleNamespace(_keep_models_warm=True, _settings_processing_device="gpu",
                           _speech_recognition_model="small-cpu", _project_type="publish")
    with patch("haizflow.desktop.smart_warmup_controller.shared_external_engine_pool"):
        warm = SmartWarmupController(host, Mock())
    warm.request_startup_prediction()
    assert warm._requests[0].context == {"model": "large-v3-turbo", "device": "gpu"}
    host._project_type = "single"
    warm.request_setup_prediction()
    assert warm._requests[0].context == {"model": "small", "device": "cpu"}


def test_device_change_updates_only_empty_project_defaults():
    host = SimpleNamespace(_settings_processing_device="gpu", _draft_processing_device="cpu",
        _selected_video_id=None, **project_model_defaults("cpu"),
        speechRecognitionModelChanged=Mock(), translationModelChanged=Mock(), ttsProviderChanged=Mock())
    HaizFlowController._sync_project_model_defaults(host)
    assert host._tts_provider == "omnivoice-gpu"
    host._selected_video_id = "saved-video"
    host._settings_processing_device = "cpu"
    HaizFlowController._sync_project_model_defaults(host)
    assert host._tts_provider == "omnivoice-gpu"


def test_processing_device_change_is_blocked_while_busy():
    host = SimpleNamespace(_processing_queue=SimpleNamespace(has_work=True), appAlertRequested=Mock())
    with patch("haizflow.desktop.settings_controller.desktop_settings.save_settings") as save:
        assert not SettingsController(host).set_processing_device("gpu")
        save.assert_not_called()
    host.appAlertRequested.emit.assert_called_once()


def test_manual_device_choice_is_saved_and_warmed_when_already_active():
    host = SimpleNamespace(_processing_queue=SimpleNamespace(has_work=False), _hardware_capabilities=Mock(),
        _active_processing_device="gpu", _settings_processing_device="gpu", settingsChanged=Mock(),
        _smart_warmup=Mock(), _switch_processing_device=Mock())
    with patch("haizflow.desktop.settings_controller.validate_processing_device", return_value=(True, "")), \
         patch("haizflow.desktop.settings_controller.desktop_settings.save_settings") as save:
        assert SettingsController(host).set_processing_device("gpu")
    save.assert_called_once_with({"processing_device": "gpu", "processing_device_origin": "manual"})
    host._smart_warmup.request_setup_prediction.assert_called_once()
    host._switch_processing_device.assert_not_called()


@pytest.mark.parametrize("choice", ["small-cpu", "small-gpu", "large-v3-turbo"])
def test_project_config_roundtrip_preserves_explicit_recognition_device(choice):
    config = VideoConfig(speech_recognition_model=choice)
    restored = VideoConfig.model_validate_json(config.model_dump_json())
    assert restored.speech_recognition_model == choice


def test_no_model_load_is_queued_before_runtime_switch_starts():
    events = []
    host = SimpleNamespace(_processing_queue=SimpleNamespace(has_work=False), _hardware_capabilities=Mock(),
        _active_processing_device="cpu", _settings_processing_device="cpu", settingsChanged=Mock(),
        _switch_processing_device=Mock(side_effect=lambda _: events.append("switch")))
    host.settingsChanged.emit.side_effect = lambda: events.append("settings")
    with patch("haizflow.desktop.settings_controller.validate_processing_device", return_value=(True, "")), \
         patch("haizflow.desktop.settings_controller.desktop_settings.save_settings"):
        assert SettingsController(host).set_processing_device("gpu")
    assert events == ["switch", "settings"]


@pytest.mark.parametrize("device, cuda, vram, ram, pending, expected", [
    ("cpu", True, 8, 16, False, False),
    ("gpu", True, 8, 16, False, True),
    ("gpu", False, 8, 16, False, False),
    ("gpu", True, 4, 16, False, False),
    ("gpu", True, 8, 8, False, False),
    ("gpu", False, 0, 16, True, True),
])
def test_gpu_options_use_resolved_hardware_not_only_saved_preference(device, cuda, vram, ram, pending, expected):
    capabilities = HardwareCapabilities(
        cuda_available=cuda, cuda_name="GPU" if cuda else "", total_vram_bytes=vram * 1024**3,
        free_vram_bytes=vram * 1024**3, total_ram_bytes=ram * 1024**3,
        logical_cpu_count=8, ac_powered=True, battery_percent=None,
    )
    host = SimpleNamespace(_settings_processing_device=device, _settings_language="vi",
                           _startup_hardware_resolved=not pending, _hardware_capabilities=capabilities)
    assert HaizFlowController._project_gpu_available(host) is expected
    choices = HaizFlowController.speechRecognitionModelOptions.fget(host)
    assert choices[0]["available"]
    assert all(choice["available"] is expected for choice in choices[1:])


def test_api_guide_navigates_to_single_owner_before_opening():
    events = []
    host = SimpleNamespace(
        apiKeySettingsRequested=SimpleNamespace(emit=lambda provider: events.append(("navigate", provider))),
        apiKeyGuideRequested=SimpleNamespace(emit=lambda provider: events.append(("guide", provider))),
    )
    HaizFlowController.requestApiKeyGuide(host, "zernio")
    assert events == [("navigate", "zernio"), ("guide", "zernio")]
    HaizFlowController.requestApiKeyGuide(host, "unknown")
    assert len(events) == 2
