"""Model policies independent of project names, hardware, or installed models."""

from types import SimpleNamespace
import queue
import threading
from unittest.mock import Mock, patch

import pytest

from hflow.core.model_choices import gpu_choice_blocked, models_for_device, project_model_defaults, project_recognition_choice, project_translation_choice, recognition_context
from hflow.core.hardware import HardwareCapabilities
from hflow.desktop.project_import_controller import ProjectImportController
from hflow.desktop.qml_controller import HFlowController
from hflow.desktop.settings_controller import SettingsController
from hflow.desktop.runtime_device_controller import RuntimeDeviceController
from hflow.desktop.project_commands_controller import ProjectCommandsController, _batch_values_for_device
from hflow.desktop.project_workspace_controller import ProjectWorkspaceController
from hflow.desktop.smart_warmup_controller import SmartWarmupController
from hflow.schemas.video import VideoConfig


@pytest.mark.parametrize("device", ["cpu", "gpu"])
def test_new_project_defaults_match_app_device(device):
    host = SimpleNamespace(_settings_processing_device=device)
    controller = ProjectImportController(host)
    controller.cancel_background_music_link_import = Mock()
    controller._reset_new_project_setup()
    for attribute, value in project_model_defaults(device).items():
        assert getattr(host, attribute) == value
    assert recognition_context(host._speech_recognition_model, device)["device"] == device
    assert host._tts_voice == "vieneu:Hải Đăng"


@pytest.mark.parametrize("device,language,provider", [("gpu", "vi", "vieneu-gpu"),
    ("cpu", "vi", "vieneu"), ("gpu", "en", "omnivoice-gpu"), ("cpu", "zh", "omnivoice")])
def test_voice_defaults_follow_supported_output_language_and_device(device, language, provider):
    assert project_model_defaults(device, target_language=language)["_tts_provider"] == provider


@pytest.mark.parametrize("device", ["cpu", "gpu"])
def test_vieneu_gpu_is_first_picker_entry_but_cpu_mode_cannot_select_it(device):
    host = SimpleNamespace(_settings_processing_device=device, _hardware_capabilities=None)
    options = HFlowController._tts_provider_options_for_language(host, "vi")
    assert options[0]["provider"] == "vieneu-gpu"
    assert options[0]["available"] is (device == "gpu")
    assert options[1]["provider"] == "vieneu" and options[1]["available"]
    for item in HFlowController._tts_provider_options_for_language(host, "en"):
        if item["provider"].startswith("vieneu"):
            assert item["available"] is (not item["provider"].endswith("-gpu") or device == "gpu")


@pytest.mark.parametrize("device, expected", [("gpu", "large-v3-turbo"), ("cpu", "small-cpu")])
def test_legacy_automatic_recognition_follows_device_but_explicit_choices_survive(device, expected):
    assert project_recognition_choice("small", device) == expected
    for explicit in ("small-cpu", "small-gpu", "large-v3-turbo"):
        assert project_recognition_choice(explicit, device) == explicit


def test_four_gb_gpu_defaults_keep_vieneu_on_gpu_without_full_translation():
    choices = project_model_defaults("gpu", total_vram_bytes=4 * 1024**3)
    assert choices == {"_speech_recognition_model": "small-gpu", "_translation_model": "q4",
                       "_tts_provider": "vieneu-gpu"}
    assert project_model_defaults("gpu", total_vram_bytes=8 * 1024**3) == {
        "_speech_recognition_model": "large-v3-turbo", "_translation_model": "full",
        "_tts_provider": "vieneu-gpu"}


@pytest.mark.parametrize("device,vram,expected", [("cpu", 0, "q4"), ("gpu", 4, "q4"),
    ("gpu", 8, "q4"), ("gpu", 24, "full"), ("gpu", None, "q4")])
def test_legacy_translation_auto_resolves_to_visible_model(device, vram, expected):
    memory = None if vram is None else vram * 1024**3
    assert project_translation_choice("auto", device, total_vram_bytes=memory) == expected
    for choice in ("q4", "full", "gemini-3.5-flash-lite"):
        assert project_translation_choice(choice, device, total_vram_bytes=memory) == choice


def gpu_caps(vram):
    return HardwareCapabilities(True, "GPU fixture", vram * 1024**3, vram * 1024**3,
                                16 * 1024**3, 8, True, None)


@pytest.mark.parametrize("vram,accepted", [(4, False), (8, True), (24, True)])
def test_translation_picker_rejects_full_on_four_gb_even_without_resource_delegate(vram, accepted):
    host = SimpleNamespace(_translation_model="q4", _settings_processing_device="gpu",
                           _hardware_capabilities=gpu_caps(vram), _startup_hardware_resolved=True,
                           _ensure_hardware_ready_for_action=Mock(return_value=True),
                           _show_app_alert=Mock(), translationModelChanged=Mock())
    HFlowController.translationModel.fset(host, "full")
    assert host._translation_model == ("full" if accepted else "q4")
    assert host._show_app_alert.called is (not accepted)
    assert host.translationModelChanged.emit.called is accepted
    HFlowController.translationModel.fset(host, "auto")
    assert host._translation_model == ("full" if accepted else "q4")


@pytest.mark.parametrize("project_type", ["single", "manual", "batch", None])
@pytest.mark.parametrize("recognition,translation", [("small-gpu", "full"), ("large-v3-turbo", "q4")])
def test_four_gb_preflight_blocks_heavy_models_for_saved_and_new_projects(project_type, recognition, translation):
    host = SimpleNamespace(_settings_processing_device="gpu", _hardware_capabilities=gpu_caps(4),
                           _speech_recognition_model=recognition, _translation_model=translation,
                           _tts_provider="omnivoice-gpu", appAlertRequested=Mock(),
                           _processing_queue=SimpleNamespace(contains=lambda _: False))
    video = SimpleNamespace(video_id="fixture", status="pending", project_type=project_type,
                            speech_recognition_model=recognition, translation_model=translation,
                            tts_provider="omnivoice-gpu") if project_type else None
    with patch("hflow.desktop.project_commands_controller.video_store.update_video") as save:
        assert not ProjectCommandsController._resources_ready(host, video)
    host.appAlertRequested.emit.assert_called_once()
    save.assert_not_called()


def test_batch_apply_blocks_full_before_assets_or_project_mutations():
    host = SimpleNamespace(_selected_project_key="batch", _batch_video_ids=[],
                           _settings_processing_device="gpu", _hardware_capabilities=gpu_caps(4),
                           _processing_queue=SimpleNamespace(contains=lambda _: False), _show_app_alert=Mock())
    controller = ProjectCommandsController(host)
    controller.batch_settings_values = Mock(return_value={"translationModel": "q4"})
    with patch("hflow.services.batch_settings.stage_asset") as stage, \
         patch("hflow.desktop.project_commands_controller.project_store.save_batch_settings") as save:
        assert not controller.apply_batch_settings_values("batch", {"translationModel": "full"})
    host._show_app_alert.assert_called_once()
    stage.assert_not_called()
    save.assert_not_called()


def test_legacy_batch_apply_blocks_full_before_saving_videos():
    host = SimpleNamespace(_settings_processing_device="gpu", _hardware_capabilities=gpu_caps(4),
                           _show_app_alert=Mock(), _speech_recognition_model="small-gpu")
    with patch("hflow.desktop.project_commands_controller.video_store.update_video") as save:
        assert not ProjectCommandsController(host).apply_batch_settings(
            "A", "vi", "omnivoice-gpu", "omnivoice:male", False, 60, translation_model="full")
    host._show_app_alert.assert_called_once()
    save.assert_not_called()


def test_opened_legacy_project_warms_same_turbo_choice_as_gpu_ui():
    video = SimpleNamespace(speech_recognition_model="small", manual_target_tool="translation")
    host = SimpleNamespace(_keep_models_warm=True, _settings_processing_device="gpu", _selected_video=lambda: video)
    with patch("hflow.desktop.smart_warmup_controller.shared_external_engine_pool"):
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
    with patch("hflow.desktop.smart_warmup_controller.shared_external_engine_pool"):
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


def test_device_switch_keeps_a_compatible_native_vieneu_preset():
    host = model_host()
    host._tts_voice = "vieneu:Trúc Ly"
    host.ttsVoiceChanged = Mock()
    HFlowController._sync_project_model_defaults(host)
    assert host._tts_provider == "vieneu-gpu" and host._tts_voice == "vieneu:Trúc Ly"
    host.ttsVoiceChanged.emit.assert_not_called()


@pytest.mark.parametrize("language", ["en", "zh"])
def test_auto_language_choice_rejects_chinese_and_keeps_english_vieneu(language):
    from hflow.desktop.presenters import voice_options_for_language

    host = SimpleNamespace(_target_language="vi", _tts_provider="vieneu-gpu", _tts_voice="vieneu:Hải Đăng",
        appAlertRequested=Mock(),
        _audio_preview=Mock(), targetLanguageChanged=Mock(), languageOptionsChanged=Mock(),
        ttsVoiceChanged=Mock(), ttsProviderChanged=Mock(), ttsProviderOptionsChanged=Mock(), ttsVoiceOptionsChanged=Mock(),
        _voice_options_for_language=lambda code, provider: voice_options_for_language(code, "vi", provider))
    host._normalized_voice_for_language = HFlowController._normalized_voice_for_language.__get__(host)
    for _ in range(2):
        HFlowController.targetLanguage.fset(host, language)
    assert host._target_language == ("vi" if language == "zh" else "en")
    assert host._tts_provider == "vieneu-gpu" and host._tts_voice == "vieneu:Hải Đăng"
    assert host.appAlertRequested.emit.call_count == (2 if language == "zh" else 0)
    assert host._audio_preview.invalidate.call_count == (0 if language == "zh" else 1)


def test_device_change_updates_empty_defaults_and_selected_gpu_models():
    host = model_host()
    HFlowController._sync_project_model_defaults(host)
    assert host._tts_provider == "vieneu-gpu"
    host._selected_video_id = "saved-video"
    host._settings_processing_device = "cpu"
    HFlowController._sync_project_model_defaults(host)
    assert host._tts_provider == "vieneu"
    assert host._speech_recognition_model == "small-cpu"
    assert host._translation_model == "q4"


def test_switch_does_not_change_models_until_runtime_is_confirmed():
    host = model_host()
    host._device_switching = True
    HFlowController._sync_project_model_defaults(host)
    assert host._draft_processing_device == "cpu"
    assert host._tts_provider == "vieneu"
    host._device_switching = False
    host._active_processing_device = "cpu"  # Failed GPU probe restores CPU.
    HFlowController._sync_project_model_defaults(host)
    assert host._tts_provider == "vieneu"


def test_confirmed_cpu_switch_persists_only_model_fields_for_current_owner():
    host = model_host()
    host.__dict__.update(project_model_defaults("gpu"))
    host._tts_provider = "omnivoice-gpu"  # An existing explicit choice is not replaced by the new default.
    host._settings_processing_device = host._active_processing_device = "cpu"
    host._draft_processing_device = "gpu"
    host._selected_video_id = host._settings_owner_video_id = "video"
    host._audio_preview = Mock()
    host._manual_settings_drafts = {"video": VideoConfig(speech_recognition_model="large-v3-turbo",
        translation_model="full", tts_provider="omnivoice-gpu", watermark_text="Unsaved watermark",
        background_music_volume=15)}
    with patch("hflow.desktop.qml_controller.video_store.update_video") as save:
        HFlowController._sync_project_model_defaults(host)
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
    assert HFlowController.isProcessing.fget(host)
    assert HFlowController.isSwitchingProcessingDevice.fget(host)
    host._device_switching = False
    assert not HFlowController.isSwitchingProcessingDevice.fget(host)


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
    host.settingsChanged.emit.side_effect = lambda: HFlowController._sync_project_model_defaults(host)
    with (patch("hflow.desktop.runtime_device_controller.threading.Thread") as worker,
          patch("hflow.desktop.runtime_device_controller.probe_runtime", return_value=SimpleNamespace(ok=probe_ok, message="test")),
          patch("hflow.desktop.runtime_device_controller.desktop_settings.save_settings"),
          patch("hflow.desktop.runtime_device_controller.configure_processing_device") as configure,
          patch("hflow.desktop.qml_controller.video_store.update_video", return_value=None) as save):
        RuntimeDeviceController(host)._switch_processing_device("cpu")
        host.settingsChanged.emit()
        assert host._tts_provider == "vieneu-gpu"
        save.assert_not_called()
        worker.call_args.kwargs["target"]()
        assert not host._device_switching
        assert host._active_processing_device == ("cpu" if probe_ok else "gpu")
        assert host._tts_provider == ("vieneu" if probe_ok else "vieneu-gpu")
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
    with patch("hflow.desktop.project_commands_controller.video_store.update_video", return_value=converted) as save:
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
    with (patch("hflow.desktop.project_workspace_controller.project_store.get_project", return_value=None),
          patch("hflow.desktop.project_workspace_controller.video_store.update_video", side_effect=update) as save):
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
    with patch("hflow.desktop.settings_controller.desktop_settings.save_settings") as save:
        assert not SettingsController(host).set_processing_device("gpu")
        save.assert_not_called()
    host.appAlertRequested.emit.assert_called_once()


def test_manual_device_choice_is_saved_and_warmed_when_already_active():
    host = SimpleNamespace(_processing_queue=SimpleNamespace(has_work=False), _hardware_capabilities=Mock(),
        _active_processing_device="gpu", _settings_processing_device="gpu", settingsChanged=Mock(),
        _smart_warmup=Mock(), _switch_processing_device=Mock())
    with patch("hflow.desktop.settings_controller.validate_processing_device", return_value=(True, "")), \
         patch("hflow.desktop.settings_controller.desktop_settings.save_settings") as save:
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
    with patch("hflow.desktop.settings_controller.validate_processing_device", return_value=(True, "")), \
         patch("hflow.desktop.settings_controller.desktop_settings.save_settings"):
        assert SettingsController(host).set_processing_device("gpu")
    assert events == ["switch", "settings"]


@pytest.mark.parametrize("device, cuda, vram, ram, pending, expected", [
    ("cpu", True, 8, 16, False, False),
    ("gpu", True, 8, 16, False, True),
    ("gpu", False, 8, 16, False, False),
    ("gpu", True, 4, 16, False, True),
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
    assert HFlowController._project_gpu_available(host) is expected
    choices = HFlowController.speechRecognitionModelOptions.fget(host)
    assert choices[0]["available"]
    assert choices[1]["available"] is expected
    assert choices[2]["available"] is (expected and (pending or vram >= 5))


def test_api_guide_navigates_to_single_owner_before_opening():
    events = []
    host = SimpleNamespace(
        apiKeySettingsRequested=SimpleNamespace(emit=lambda provider: events.append(("navigate", provider))),
        apiKeyGuideRequested=SimpleNamespace(emit=lambda provider: events.append(("guide", provider))),
    )
    HFlowController.requestApiKeyGuide(host, "zernio")
    assert events == [("navigate", "zernio"), ("guide", "zernio")]
    HFlowController.requestApiKeyGuide(host, "unknown")
    assert len(events) == 2


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
@pytest.mark.parametrize("language", ["zh"])
def test_vieneu_language_guard_blocks_manual_before_saving_or_running(provider, language):
    video = SimpleNamespace(video_id="video", project_type="manual", target_language="vi", subtitle_language=language)
    host = SimpleNamespace(_project_type="manual", _selected_video=lambda: video,
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        _normalized_tts_provider=lambda _language, value: value, appAlertRequested=Mock(),
        runManualTool=Mock(), _settings_language="vi")
    with patch("hflow.desktop.qml_controller.video_store.update_video") as save:
        assert not HFlowController.configureAndRunManualVoice(
            host, provider, "vieneu:Hải Đăng", "all", "", "single")
    save.assert_not_called()
    host.runManualTool.assert_not_called()
    host.appAlertRequested.emit.assert_called_once()


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
def test_vieneu_chinese_batch_config_is_rejected_before_staging_assets(provider):
    from hflow.services.batch_settings import config_for
    with pytest.raises(ValueError, match="tiếng Trung"):
        config_for({"targetLanguage": "zh", "ttsProvider": provider,
                    "ttsVoice": "vieneu:Hải Đăng"})
    assert config_for({"targetLanguage": "vi", "ttsProvider": provider,
                       "ttsVoice": "vieneu:Hải Đăng"}).tts_provider == provider


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
def test_stored_unsupported_vieneu_config_blocks_preflight_without_mutation(provider):
    host = SimpleNamespace(_settings_processing_device="cpu", _settings_language="vi",
        appAlertRequested=Mock(), _processing_queue=SimpleNamespace(contains=lambda _: False))
    video = SimpleNamespace(video_id="video", status="pending", target_language="zh", tts_provider=provider)
    with patch("hflow.desktop.project_commands_controller.video_store.update_video") as save:
        assert not ProjectCommandsController._resources_ready_for_videos(host, [video])
    save.assert_not_called()
    host.appAlertRequested.emit.assert_called_once()
