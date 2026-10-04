"""Model policies independent of project names, hardware, or installed models."""

from types import SimpleNamespace
import queue
import threading
from unittest.mock import Mock, patch

import pytest

from haizflow.core.model_choices import gpu_choice_blocked, models_for_device, project_model_defaults, project_recognition_choice, recognition_context
from haizflow.core.hardware import HardwareCapabilities
from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.settings_controller import SettingsController
from haizflow.desktop.runtime_device_controller import RuntimeDeviceController
from haizflow.desktop.project_commands_controller import ProjectCommandsController, _batch_values_for_device
from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
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


def model_host():
    return SimpleNamespace(_settings_processing_device="gpu", _draft_processing_device="cpu",
        _selected_video_id=None, **project_model_defaults("cpu"),
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        speechRecognitionModelChanged=Mock(), translationModelChanged=Mock(), ttsProviderChanged=Mock(),
        ttsProviderOptionsChanged=Mock(), ttsVoiceOptionsChanged=Mock(), batchChanged=Mock(), selectedVideoChanged=Mock())


def test_device_change_updates_empty_defaults_and_selected_gpu_models():
    host = model_host()
    HaizFlowController._sync_project_model_defaults(host)
    assert host._tts_provider == "omnivoice-gpu"
    host._selected_video_id = "saved-video"
    host._settings_processing_device = "cpu"
    HaizFlowController._sync_project_model_defaults(host)
    assert host._tts_provider == "omnivoice"
    assert host._speech_recognition_model == "small-cpu"
    assert host._translation_model == "q4"


def test_switch_does_not_change_models_until_runtime_is_confirmed():
    host = model_host()
    host._device_switching = True
    HaizFlowController._sync_project_model_defaults(host)
    assert host._draft_processing_device == "cpu"
    assert host._tts_provider == "omnivoice"
    host._device_switching = False
    host._active_processing_device = "cpu"  # Failed GPU probe restores CPU.
    HaizFlowController._sync_project_model_defaults(host)
    assert host._tts_provider == "omnivoice"


def test_confirmed_cpu_switch_persists_only_model_fields_for_current_owner():
    host = model_host()
    host.__dict__.update(project_model_defaults("gpu"))
    host._settings_processing_device = host._active_processing_device = "cpu"
    host._draft_processing_device = "gpu"
    host._selected_video_id = host._settings_owner_video_id = "video"
    host._audio_preview = Mock()
    host._manual_settings_drafts = {"video": VideoConfig(speech_recognition_model="large-v3-turbo",
        translation_model="full", tts_provider="omnivoice-gpu", watermark_text="Unsaved watermark",
        background_music_volume=15)}
    with patch("haizflow.desktop.qml_controller.video_store.update_video") as save:
        HaizFlowController._sync_project_model_defaults(host)
    save.assert_called_once_with("video", speech_recognition_model="small-cpu",
                                 translation_model="q4", tts_provider="omnivoice")
    host._audio_preview.invalidate.assert_called_once()
    assert recognition_context(host._speech_recognition_model, "cpu") == {"model": "small", "device": "cpu"}
    draft = host._manual_settings_drafts["video"]
    assert draft.speech_recognition_model == "small-cpu"
    assert draft.translation_model == "q4"
    assert draft.tts_provider == "omnivoice"
    assert draft.watermark_text == "Unsaved watermark"
    assert draft.background_music_volume == 15


@pytest.mark.parametrize("device", ["cpu", "gpu"])
def test_cloud_models_and_cpu_overrides_survive_device_sync(device):
    assert models_for_device(device, recognition="small-cpu", translation="gemini-flash",
                             voice="edge") == dict(speech_recognition_model="small-cpu",
                                                   translation_model="gemini-flash", tts_provider="edge")


def test_switch_flag_is_separate_from_video_processing():
    host = SimpleNamespace(_device_switching=True, _processing_queue=SimpleNamespace(has_work=False))
    assert HaizFlowController.isProcessing.fget(host)
    assert HaizFlowController.isSwitchingProcessingDevice.fget(host)
    host._device_switching = False
    assert not HaizFlowController.isSwitchingProcessingDevice.fget(host)


@pytest.mark.parametrize("probe_ok", [True, False])
def test_runtime_switch_commits_cpu_models_only_after_success(probe_ok):
    host = model_host()
    host.__dict__.update(project_model_defaults("gpu"))
    host._settings_processing_device = "cpu"
    host._draft_processing_device = host._active_processing_device = "gpu"
    host._selected_video_id = host._settings_owner_video_id = "video"
    host._pending_processing_device = ""
    host._model_runtime_lock = threading.Lock()
    host._model_setup_events = queue.Queue()
    host._settings_theme = "dark"
    host._settings_language = "vi"
    host._processing_device_origin = "manual"
    host._smart_warmup = Mock()
    host.runtimeStateChanged = host.statusMessageChanged = host.processingChanged = host.hardwareChanged = Mock()
    host._warm_models_unlocked = lambda: setattr(host, "_runtime_state", "ready")
    host.settingsChanged = Mock()
    host.settingsChanged.emit.side_effect = lambda: HaizFlowController._sync_project_model_defaults(host)
    with (patch("haizflow.desktop.runtime_device_controller.threading.Thread") as worker,
          patch("haizflow.desktop.runtime_device_controller.probe_runtime", return_value=SimpleNamespace(ok=probe_ok, message="test")),
          patch("haizflow.desktop.runtime_device_controller.desktop_settings.save_settings"),
          patch("haizflow.desktop.runtime_device_controller.configure_processing_device") as configure,
          patch("haizflow.desktop.qml_controller.video_store.update_video", return_value=None) as save):
        RuntimeDeviceController(host)._switch_processing_device("cpu")
        host.settingsChanged.emit()
        assert host._tts_provider == "omnivoice-gpu"
        save.assert_not_called()
        worker.call_args.kwargs["target"]()
        assert not host._device_switching
        assert host._active_processing_device == ("cpu" if probe_ok else "gpu")
        assert host._tts_provider == ("omnivoice" if probe_ok else "omnivoice-gpu")
        assert configure.called is probe_ok
        assert save.called is probe_ok


def test_cpu_batch_values_do_not_classify_backend_conversion_as_individual_override():
    gpu = dict(speechRecognitionModel="large-v3-turbo", translationModel="full", ttsProvider="omnivoice-gpu",
               targetLanguage="vi", watermarkText="Keep me")
    normalized = _batch_values_for_device(gpu, "cpu")
    assert normalized == {**gpu, "speechRecognitionModel": "small-cpu", "translationModel": "q4", "ttsProvider": "omnivoice"}
    assert gpu["ttsProvider"] == "omnivoice-gpu"


def test_cpu_batch_preflight_persists_cpu_models_before_checking_resources():
    video = SimpleNamespace(video_id="video", status="pending", speech_recognition_model="large-v3-turbo",
                            translation_model="full", tts_provider="omnivoice-gpu")
    converted = SimpleNamespace(**{**vars(video), **models_for_device("cpu", recognition="large-v3-turbo",
                                                                    translation="full", voice="omnivoice-gpu")})
    host = SimpleNamespace(_settings_processing_device="cpu", _processing_queue=SimpleNamespace(contains=lambda _: False))
    with patch("haizflow.desktop.project_commands_controller.video_store.update_video", return_value=converted) as save:
        assert ProjectCommandsController._resources_ready_for_videos(host, [video])
    save.assert_called_once_with("video", speech_recognition_model="small-cpu", translation_model="q4", tts_provider="omnivoice")


@pytest.mark.parametrize("queued", [False, True])
def test_reopening_gpu_project_on_cpu_updates_ui_and_saved_models_without_touching_outputs(queued):
    host = Mock()
    host._settings_processing_device = "cpu"
    host._selected_video_id = host._settings_owner_video_id = None
    host._project_directory = "D:/fixture-projects"
    host._processing_queue = SimpleNamespace(active_video_id="video" if queued else None, contains=lambda _: queued)
    host._normalized_tts_provider.side_effect = lambda _language, provider: provider
    host._normalized_voice_for_language.side_effect = lambda _language, voice, _provider: voice
    host._resolve_video_file.return_value = "D:/fixture-projects/input.mp4"
    host._read_video_logs.return_value = ""
    video = SimpleNamespace(**VideoConfig(speech_recognition_model="large-v3-turbo", translation_model="full",
                                         tts_provider="omnivoice-gpu", tts_voice="omnivoice:clone").model_dump(),
                            video_id="video", status="processing" if queued else "done", original_filename="input.mp4",
                            files={"video_output": "D:/fixture-projects/output.mp4"})
    before = dict(video.files)
    def update(_id, **fields):
        video.__dict__.update(fields)
        return video
    with (patch("haizflow.desktop.project_workspace_controller.project_store.get_project", return_value=None),
          patch("haizflow.desktop.project_workspace_controller.video_store.update_video", side_effect=update) as save):
        ProjectWorkspaceController(host).select_video(video)
    assert host._speech_recognition_model == ("large-v3-turbo" if queued else "small-cpu")
    assert host._translation_model == ("full" if queued else "q4")
    assert host._tts_provider == ("omnivoice-gpu" if queued else "omnivoice")
    assert video.files == before
    if queued:
        save.assert_not_called()
    else:
        save.assert_called_once_with("video", speech_recognition_model="small-cpu", translation_model="q4", tts_provider="omnivoice")


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
