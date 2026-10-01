"""Persistent desktop settings operations kept outside the QML facade."""

from __future__ import annotations

from haizflow.core.hardware import (
    configure_translation_model,
    recommended_processing_device,
)
from haizflow.desktop.localization import QMessageBox, _set_ui_language
from haizflow.services import desktop_settings


class SettingsController:
    def __init__(self, host):
        self._host = host

    def apply(self, theme, language, translation_model) -> bool:
        host = self._host
        theme = "graphite"
        translation_model = str(translation_model).lower()
        if translation_model not in {"auto", "q4", "full"}:
            return False
        pipeline_active = host._pipeline_is_active()
        model_changed = translation_model != getattr(host, "_settings_translation_model", "auto")
        if model_changed and pipeline_active:
            QMessageBox.warning(None, "Translation model", "Wait until the current task finishes before changing the translation model.")
            return False
        if model_changed and translation_model == "full" and host._settings_processing_device != "gpu":
            QMessageBox.warning(None, "Translation model", "HY-MT2 đầy đủ cần GPU NVIDIA tương thích. Hãy chọn Tự động hoặc Q4.")
            return False
        history_before = {
            "language": str(host._settings_language),
            "translation_model": str(getattr(host, "_settings_translation_model", "auto")),
        }
        try:
            settings = desktop_settings.save_settings(
                {
                    "theme": theme,
                    "language": language,
                    "processing_device": host._settings_processing_device,
                    "processing_device_origin": "detected",
                    "translation_model": translation_model,
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
        host._settings_translation_model = settings.get("translation_model", "auto")
        configure_translation_model(host._settings_translation_model)
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
        host._status_message = "Settings applied"
        host.settingsChanged.emit()
        selected_changed = getattr(host, "selectedVideoChanged", None)
        if history_before["language"] != host._settings_language and selected_changed is not None:
            selected_changed.emit()
        options_changed = getattr(host, "speechRecognitionModelOptionsChanged", None)
        if options_changed:
            options_changed.emit()
        host.languageOptionsChanged.emit()
        voice_options_changed = getattr(host, "ttsVoiceOptionsChanged", None)
        if voice_options_changed:
            voice_options_changed.emit()
        host.statusMessageChanged.emit()
        if model_changed:
            from haizflow.services.translation import shutdown_hymt2_worker

            shutdown_hymt2_worker()
        record = getattr(host, "_record_app_settings_change", None)
        if callable(record):
            record(
                history_before,
                {
                    "language": str(host._settings_language),
                    "translation_model": str(host._settings_translation_model),
                },
            )
        return True

    def reset(self) -> None:
        host = self._host
        if host._pipeline_is_active():
            QMessageBox.warning(None, "Settings", "Wait until the current task finishes before restoring defaults.")
            return
        history_before = {
            "language": str(host._settings_language),
            "translation_model": str(getattr(host, "_settings_translation_model", "auto")),
        }
        pipeline_active = host._pipeline_is_active()
        from haizflow.core.hardware import basic_hardware_capabilities

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
        model_changed = settings["translation_model"] != getattr(host, "_settings_translation_model", "auto")
        host._settings_translation_model = settings["translation_model"]
        configure_translation_model(host._settings_translation_model)
        host._keep_models_warm = settings["keep_models_warm"]
        host._manual_project_cache_gib = settings["manual_project_cache_gib"]
        host._manual_global_cache_gib = settings["manual_global_cache_gib"]
        if device_changed and (pipeline_active or host._device_switching):
            host._pending_processing_device = host._settings_processing_device
            host._status_message = "Settings reset. The processing device changes after the current video."
        else:
            host._status_message = "Settings reset to defaults"
        host.settingsChanged.emit()
        selected_changed = getattr(host, "selectedVideoChanged", None)
        if history_before["language"] != host._settings_language and selected_changed is not None:
            selected_changed.emit()
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
        if model_changed and not pipeline_active:
            from haizflow.services.translation import shutdown_hymt2_worker

            shutdown_hymt2_worker()
        record = getattr(host, "_record_app_settings_change", None)
        if callable(record):
            record(
                history_before,
                {
                    "language": str(host._settings_language),
                    "translation_model": str(host._settings_translation_model),
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
