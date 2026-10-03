"""Model policies independent of project names, hardware, or installed models."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.core.model_choices import gpu_choice_blocked, project_model_defaults, recognition_context
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
    assert warm._requests[0].context == {"model": "small", "device": "gpu"}
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
