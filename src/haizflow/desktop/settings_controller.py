"""Persistent desktop settings operations kept outside the QML facade."""

from __future__ import annotations

from haizflow.core.hardware import (
    basic_hardware_capabilities,
    clear_runtime_profile_cache,
    recommended_processing_device,
    validate_processing_device,
)
from haizflow.desktop.localization import QMessageBox, _set_ui_language
from haizflow.services import desktop_settings


class SettingsController:
    def __init__(self, host):
        self._host = host

    def apply(self, theme, language, processing_device) -> bool:
        host = self._host
        theme = "graphite"
        processing_device = str(processing_device).lower()
        pipeline_active = host._pipeline_is_active()
        if processing_device != host._settings_processing_device and not (pipeline_active or host._device_switching):
            clear_runtime_profile_cache()
        capabilities = getattr(host, "_hardware_capabilities", None) or basic_hardware_capabilities()
        compatible, compatibility_message = validate_processing_device(
            processing_device,
            capabilities,
        )
        if not compatible:
            QMessageBox.warning(None, "Processing device", compatibility_message)
            return False
        history_before = {
            "language": str(host._settings_language),
            "processing_device": str(host._settings_processing_device),
        }
        device_changed = processing_device != host._settings_processing_device
        try:
            settings = desktop_settings.save_settings(
                {
                    "theme": theme,
                    "language": language,
                    "processing_device": processing_device,
                    "processing_device_origin": "manual",
                    "keep_models_warm": bool(getattr(host, "_keep_models_warm", True)),
                    "manual_project_cache_gib": int(getattr(host, "_manual_project_cache_gib", 4)),
                    "manual_global_cache_gib": int(getattr(host, "_manual_global_cache_gib", 16)),
                }
            )
        except OSError as exc:
            QMessageBox.warning(None, "Settings", f"Cannot save settings: {exc}")
            return False
        host._settings_theme = settings["theme"]
        host._settings_language = settings["language"]
        host._settings_processing_device = settings["processing_device"]
        host._processing_device_origin = settings["processing_device_origin"]
        # Test doubles and one-version migration adapters may return only the
        # legacy keys. Preserve the active values until the normalized store
        # supplies the new resource settings.
        host._keep_models_warm = bool(settings.get("keep_models_warm", getattr(host, "_keep_models_warm", True)))
        host._manual_project_cache_gib = int(
            settings.get("manual_project_cache_gib", getattr(host, "_manual_project_cache_gib", 4))
        )
        host._manual_global_cache_gib = int(
            settings.get("manual_global_cache_gib", getattr(host, "_manual_global_cache_gib", 16))
        )
        _set_ui_language(host._settings_language)
        activity_events = getattr(host, "activity_events", None)
        if activity_events is not None:
            activity_events.set_language(host._settings_language)
        if device_changed and (pipeline_active or host._device_switching):
            host._pending_processing_device = host._settings_processing_device
            host._status_message = "Settings applied. The current video keeps its processing device."
        else:
            host._status_message = "Settings applied"
        host.settingsChanged.emit()
        options_changed = getattr(host, "speechRecognitionModelOptionsChanged", None)
        if options_changed:
            options_changed.emit()
        host.languageOptionsChanged.emit()
        voice_options_changed = getattr(host, "ttsVoiceOptionsChanged", None)
        if voice_options_changed:
            voice_options_changed.emit()
        host.statusMessageChanged.emit()
        if device_changed and not (pipeline_active or host._device_switching):
            host._switch_processing_device(host._settings_processing_device)
        record = getattr(host, "_record_app_settings_change", None)
        if callable(record):
            record(
                history_before,
                {
                    "language": str(host._settings_language),
                    "processing_device": str(host._settings_processing_device),
                },
            )
        return True

    def reset(self) -> None:
        host = self._host
        history_before = {
            "language": str(host._settings_language),
            "processing_device": str(host._settings_processing_device),
        }
        pipeline_active = host._pipeline_is_active()
        capabilities = getattr(host, "_hardware_capabilities", None) or basic_hardware_capabilities()
        try:
            settings = desktop_settings.reset_settings()
            settings["processing_device"] = recommended_processing_device(capabilities)
            settings["processing_device_origin"] = "detected"
            settings = desktop_settings.save_settings(settings)
        except OSError as exc:
            QMessageBox.warning(None, "Settings", f"Cannot restore defaults: {exc}")
            return
        host._settings_theme = settings["theme"]
        host._settings_language = settings["language"]
        _set_ui_language(host._settings_language)
        activity_events = getattr(host, "activity_events", None)
        if activity_events is not None:
            activity_events.set_language(host._settings_language)
        device_changed = settings["processing_device"] != host._settings_processing_device
        host._settings_processing_device = settings["processing_device"]
        host._processing_device_origin = settings["processing_device_origin"]
        host._keep_models_warm = settings["keep_models_warm"]
        host._manual_project_cache_gib = settings["manual_project_cache_gib"]
        host._manual_global_cache_gib = settings["manual_global_cache_gib"]
        if device_changed and (pipeline_active or host._device_switching):
            host._pending_processing_device = host._settings_processing_device
            host._status_message = "Settings reset. The processing device changes after the current video."
        else:
            host._status_message = "Settings reset to defaults"
        host.settingsChanged.emit()
        options_changed = getattr(host, "speechRecognitionModelOptionsChanged", None)
        if options_changed:
            options_changed.emit()
        host.languageOptionsChanged.emit()
        voice_options_changed = getattr(host, "ttsVoiceOptionsChanged", None)
        if voice_options_changed:
            voice_options_changed.emit()
        host.statusMessageChanged.emit()
        if device_changed and not (pipeline_active or host._device_switching):
            host._switch_processing_device(host._settings_processing_device)
        record = getattr(host, "_record_app_settings_change", None)
        if callable(record):
            record(
                history_before,
                {
                    "language": str(host._settings_language),
                    "processing_device": str(host._settings_processing_device),
                },
            )

    def set_keep_models_warm(self, enabled: bool) -> None:
        host = self._host
        enabled = bool(enabled)
        if enabled == bool(getattr(host, "_keep_models_warm", True)):
            return
        settings = desktop_settings.load_settings()
        settings["keep_models_warm"] = enabled
        saved = desktop_settings.save_settings(settings)
        host._keep_models_warm = saved["keep_models_warm"]
        host.settingsChanged.emit()
        warmup = getattr(host, "_smart_warmup", None)
        if warmup is None:
            return
        if enabled:
            warmup.start()
            warmup.request_project_prediction()
        else:
            warmup.release("setting")

    def set_manual_cache_limits(self, project_gib: int, global_gib: int) -> None:
        host = self._host
        settings = desktop_settings.load_settings()
        settings["manual_project_cache_gib"] = project_gib
        settings["manual_global_cache_gib"] = max(project_gib, global_gib)
        saved = desktop_settings.save_settings(settings)
        host._manual_project_cache_gib = saved["manual_project_cache_gib"]
        host._manual_global_cache_gib = max(
            saved["manual_global_cache_gib"],
            host._manual_project_cache_gib,
        )
        host.settingsChanged.emit()
