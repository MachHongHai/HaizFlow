"""General settings are validated and saved as one explicit operation."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from haizflow.desktop.settings_controller import SettingsController


def host_fixture():
    return SimpleNamespace(
        _settings_language="vi", _settings_processing_device="cpu",
        _processing_device_origin="manual", _keep_models_warm=False,
        _processing_queue=SimpleNamespace(has_work=False), _device_switching=False,
        _hardware_capabilities={}, _ensure_hardware_ready_for_action=Mock(return_value=True),
        _switch_processing_device=Mock(), activity_events=Mock(), _smart_warmup=Mock(),
        settingsChanged=Mock(), languageOptionsChanged=Mock(), ttsVoiceOptionsChanged=Mock(),
        selectedVideoChanged=Mock(), appAlertRequested=Mock(),
    )


def test_general_apply_commits_one_settings_update():
    host = host_fixture()
    with (patch("haizflow.desktop.settings_controller.desktop_settings.save_settings") as save,
          patch("haizflow.desktop.settings_controller._set_ui_language") as language):
        assert SettingsController(host).apply_general("en", "cpu", True)
    save.assert_called_once_with({"language": "en", "processing_device": "cpu",
                                 "processing_device_origin": "manual", "keep_models_warm": True})
    language.assert_called_once_with("en")
    assert host._keep_models_warm
    host._smart_warmup.start.assert_called_once()
    host._switch_processing_device.assert_not_called()


def test_failed_save_leaves_all_active_settings_unchanged():
    host = host_fixture()
    with (patch("haizflow.desktop.settings_controller.desktop_settings.save_settings", side_effect=OSError("disk")),
          patch("haizflow.desktop.settings_controller._set_ui_language") as language):
        assert not SettingsController(host).apply_general("en", "cpu", True)
    assert host._settings_language == "vi"
    assert not host._keep_models_warm
    language.assert_not_called()
    host.settingsChanged.emit.assert_not_called()


def test_device_guard_rejects_entire_draft_before_saving():
    host = host_fixture()
    host._processing_queue.has_work = True
    with patch("haizflow.desktop.settings_controller.desktop_settings.save_settings") as save:
        assert not SettingsController(host).apply_general("en", "gpu", True)
    save.assert_not_called()
    assert host._settings_language == "vi"
    assert host._settings_processing_device == "cpu"


def test_device_switch_starts_before_ui_signal():
    host = host_fixture()
    events = []
    host._switch_processing_device.side_effect = lambda *_: events.append("switch")
    host.settingsChanged.emit.side_effect = lambda: events.append("changed")
    with (patch("haizflow.desktop.settings_controller.desktop_settings.save_settings"),
          patch("haizflow.desktop.settings_controller.validate_processing_device", return_value=(True, "")),
          patch("haizflow.desktop.settings_controller._set_ui_language")):
        assert SettingsController(host).apply_general("vi", "gpu", False)
    assert events == ["switch", "changed"]
