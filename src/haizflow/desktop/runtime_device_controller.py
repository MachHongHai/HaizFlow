"""Runtime, model warm-up, shutdown, and hardware-device orchestration."""

from __future__ import annotations

import queue
import shutil
import threading

from haizflow.core.events import unsubscribe_log
from haizflow.core.hardware import (
    configure_processing_device,
    detect_hardware_capabilities,
    processing_device_preference,
    recommended_processing_device,
    validate_processing_device,
)
from haizflow.core.runtime_probe import probe_runtime
from haizflow.desktop.localization import QMessageBox
from haizflow.pipeline.process_registry import pause_video
from haizflow.services import desktop_settings, video_store
from haizflow.services.model_bootstrap import ModelProgress
from haizflow.services.translation import shutdown_hymt2_worker


class RuntimeDeviceController:
    """Owns runtime transitions; the QML singleton remains the stable facade."""

    def __init__(self, host, *, unsubscribe=None, pause=None, shutdown_translation=None, detect_hardware=None):
        self._host = host
        self._unsubscribe = unsubscribe or unsubscribe_log
        self._pause = pause or pause_video
        self._shutdown_translation = shutdown_translation or shutdown_hymt2_worker
        self._detect_hardware = detect_hardware or detect_hardware_capabilities

    def _set_runtime_state(self, state: str) -> None:
        host = self._host
        host._runtime_state = state
        signal = getattr(host, "runtimeStateChanged", None)
        if signal:
            signal.emit()

    def _confirm_application_close(self) -> bool:
        host = self._host
        background_work = (
            host._processing_queue.has_work
            or host._url_importer.busy
            or host._channel_importer.busy
            or (getattr(host, "_media_downloader", None) and host._media_downloader.hasWork)
            or getattr(host, "_media_import_busy", False)
            or getattr(host, "_model_setup_state", "ready") in {"checking", "downloading", "verifying"}
        )
        if not background_work:
            host._close_confirmed = True
            return True
        answer = QMessageBox.question(
            None,
            "Exit HaizFlow",
            "HaizFlow is still processing or downloading data.\n\n"
            "Exit now? The active video will be paused, active downloads will be cancelled, "
            "and queued videos will remain available for later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        host._close_confirmed = answer == QMessageBox.StandardButton.Yes
        return host._close_confirmed

    def shutdown(self):
        host = self._host
        if host._shutdown_started:
            return
        host._shutdown_started = True
        background_shutdown_event = getattr(host, "_background_shutdown_event", None)
        if background_shutdown_event:
            background_shutdown_event.set()
        model_setup_cancel_event = getattr(host, "_model_setup_cancel_event", None)
        if model_setup_cancel_event:
            model_setup_cancel_event.set()
        host._initial_model_warmup_done.set()
        self._unsubscribe(host._on_video_log)

        active_video_id = host._processing_queue.active_video_id
        active_video = video_store.get_video(active_video_id) if active_video_id else None
        if active_video and active_video.status in {"pending", "processing"}:
            resume_step = active_video.resume_step or active_video.step or "processing"
            if resume_step in {"pending", "queued", "paused"}:
                resume_step = "starting"
            self._pause(active_video_id)
            video_store.update_video(
                active_video_id,
                status="paused",
                error=None,
                step="paused",
                resume_step=resume_step,
                step_detail=f"Paused during application exit ({resume_step})",
                estimated_remaining_seconds=None,
            )
            video_store.log_to_video(
                active_video_id,
                "Application exit requested. Active subprocesses were stopped and the video was paused.",
            )

        for video_id in host._processing_queue.pending_ids():
            queued_video = video_store.get_video(video_id)
            if queued_video and queued_video.status == "pending":
                video_store.update_video(
                    video_id,
                    step="queued",
                    step_detail="Waiting to be started after the application exited",
                )

        host._url_importer.shutdown()
        host._channel_importer.shutdown()
        media_downloader = getattr(host, "_media_downloader", None)
        if media_downloader:
            media_downloader.shutdown()
        project_import = getattr(host, "_project_import", None)
        if project_import:
            project_import.shutdown()
        dimension_probe = getattr(host, "_dimension_probe", None)
        if dimension_probe:
            dimension_probe.shutdown()
        manual_subtitles = getattr(host, "_manual_subtitles", None)
        if manual_subtitles:
            manual_subtitles.close()
        subtitle_overlay = getattr(host, "_subtitle_overlay", None)
        if subtitle_overlay:
            subtitle_overlay.close()
        manual_audio = getattr(host, "_manual_audio", None)
        if manual_audio:
            manual_audio.close()
        for directory in getattr(host, "_edit_history_asset_directories", set()):
            shutil.rmtree(directory, ignore_errors=True)
        getattr(host, "_edit_history_asset_directories", set()).clear()
        for background_thread in (
            getattr(host, "_thumbnail_refresh_thread", None),
            getattr(host, "_startup_maintenance_thread", None),
        ):
            if background_thread and background_thread.is_alive():
                background_thread.join(timeout=2.0)
        queue_stopped = host._processing_queue.shutdown(timeout_seconds=10.0)
        self._shutdown_translation(permanent=True)
        if not queue_stopped:
            queue_stopped = host._processing_queue.shutdown(timeout_seconds=2.0)

        warmup_thread = host._warmup_thread
        if warmup_thread and warmup_thread.is_alive():
            warmup_thread.join(timeout=1.0)
        if (
            queue_stopped
            and not (warmup_thread and warmup_thread.is_alive())
            and getattr(host, "_smart_warmup", None) is None
        ):
            try:
                from haizflow.pipeline.transcribe import release_warm_whisperx_model

                release_warm_whisperx_model()
            except (ImportError, ModuleNotFoundError):
                pass
        if getattr(type(host), "_qml_instance", None) is host:
            type(host)._qml_instance = None

    def _warm_models(self):
        host = self._host
        with host._model_runtime_lock:
            host._warm_models_unlocked()

    @staticmethod
    def _queue_model_setup(host, progress: ModelProgress | None = None, **values) -> None:
        if progress is not None:
            values = {
                "state": progress.state,
                "component": progress.component,
                "detail": progress.detail,
                "completed_bytes": progress.completed_bytes,
                "total_bytes": progress.total_bytes,
            }
        host._model_setup_events.put(values)

    def _resolve_startup_processing_device(self) -> str:
        """Probe CUDA off the GUI thread before choosing the model runtime."""
        host = self._host
        probe_lock = getattr(host, "_hardware_probe_lock", None)
        if probe_lock is not None:
            with probe_lock:
                host._hardware_probe_running = True
        try:
            capabilities = self._detect_hardware()
        finally:
            if probe_lock is not None:
                with probe_lock:
                    host._hardware_probe_running = False

        requested_device = str(getattr(host, "_settings_processing_device", "cpu") or "cpu")
        origin = str(getattr(host, "_processing_device_origin", "detected") or "detected")
        device_valid, device_message = validate_processing_device(requested_device, capabilities)
        if origin == "detected":
            selected_device = recommended_processing_device(capabilities)
        elif device_valid:
            selected_device = requested_device
        else:
            selected_device = "cpu"
            origin = "detected"

        settings_changed = selected_device != requested_device or origin != getattr(
            host, "_processing_device_origin", origin
        )
        host._hardware_capabilities = capabilities
        host._settings_processing_device = selected_device
        host._processing_device_origin = origin
        host._active_processing_device = selected_device
        host._startup_hardware_resolved = True
        configure_processing_device(selected_device)

        if settings_changed:
            try:
                desktop_settings.save_settings(
                    {
                        "theme": host._settings_theme,
                        "language": host._settings_language,
                        "processing_device": selected_device,
                        "processing_device_origin": origin,
                    }
                )
            except OSError:
                pass

        status_message = ""
        if not device_valid and selected_device == "cpu" and requested_device == "gpu":
            status_message = f"Saved GPU setting is unavailable: {device_message} Switched to CPU."
            host._status_message = status_message
        events = getattr(host, "_hardware_probe_events", None)
        if events is not None:
            events.put(
                {
                    "kind": "startup",
                    "capabilities": capabilities,
                    "settings_changed": settings_changed,
                    "status_message": status_message,
                }
            )
        return selected_device

    def _warm_models_at_startup(self):
        host = self._host
        try:
            if hasattr(host, "_hardware_probe_events") and not getattr(host, "_startup_hardware_resolved", False):
                self._resolve_startup_processing_device()
            smart = getattr(host, "_smart_warmup", None)
            if smart is not None:
                smart.request_startup_prediction()
            self._set_runtime_state("ready")
        except Exception as exc:
            host._runtime_probe_error = str(exc)
            host._status_message = f"Không thể kiểm tra bộ xử lý: {exc}"
            self._set_runtime_state("ready")
            host.statusMessageChanged.emit()
        finally:
            host._initial_model_warmup_done.set()

    def retryModelSetup(self):
        host = self._host
        resource_packs = getattr(host, "_resource_packs", None)
        if resource_packs is not None:
            resource_packs.model.refresh()
            resource_packs.changed.emit()
        smart = getattr(host, "_smart_warmup", None)
        if smart is not None:
            smart.request_startup_prediction()

    def cancelModelSetup(self):
        return

    def _warm_models_unlocked(self):
        host = self._host
        smart = getattr(host, "_smart_warmup", None)
        if smart is not None:
            smart.request_startup_prediction()
        self._set_runtime_state("ready")

    def _switch_processing_device(self, preference: str):
        host = self._host
        previous_device = host._active_processing_device
        host._model_setup_cancel_event = threading.Event()
        host._model_setup_target_device = preference
        engine_pack = "engine-cuda128-py313" if preference == "gpu" else "engine-cpu-py313"
        resource_packs = getattr(host, "_resource_packs", None)
        if resource_packs is not None and resource_packs.manager.status(engine_pack) == "missing":
            host._settings_processing_device = previous_device
            host.appAlertRequested.emit(
                "Thiếu bộ xử lý",
                "Cài gói bộ xử lý phù hợp trong Cài đặt → Gói cài đặt trước khi đổi thiết bị.",
                "info",
            )
            host.settingsChanged.emit()
            return
        host._device_switching = True
        self._set_runtime_state("warming")
        host._status_message = "Switching processing device"
        host.processingChanged.emit()
        host.statusMessageChanged.emit()

        def restore_previous_setting():
            host._settings_processing_device = previous_device
            host._pending_processing_device = ""
            try:
                desktop_settings.save_settings(
                    {
                        "theme": host._settings_theme,
                        "language": host._settings_language,
                        "processing_device": previous_device,
                        "processing_device_origin": host._processing_device_origin,
                    }
                )
            except OSError:
                pass

        def switch_models():
            try:
                probe = probe_runtime(preference)
                if not probe.ok:
                    active_device = host._active_processing_device
                    host._settings_processing_device = active_device
                    host._pending_processing_device = ""
                    try:
                        desktop_settings.save_settings(
                            {
                                "theme": host._settings_theme,
                                "language": host._settings_language,
                                "processing_device": active_device,
                                "processing_device_origin": host._processing_device_origin,
                            }
                        )
                    except OSError:
                        pass
                    host._status_message = f"Cannot switch to {preference.upper()}: {probe.message}"
                    self._set_runtime_state("ready")
                    # The current runtime is still usable. Close any setup UI
                    # opened for the rejected switch instead of trapping the
                    # user behind a stale checking screen.
                    self._queue_model_setup(
                        host,
                        state="ready",
                        component="",
                        detail="Models are ready",
                    )
                    host.settingsChanged.emit()
                    host.statusMessageChanged.emit()
                    return
                with host._model_runtime_lock:
                    smart = getattr(host, "_smart_warmup", None)
                    if smart is not None:
                        smart.quiesce_for_device_switch()
                    else:
                        self._shutdown_translation()
                    configure_processing_device(preference)
                    host._active_processing_device = preference
                    host._settings_processing_device = preference
                    try:
                        desktop_settings.save_settings(
                            {
                                "theme": host._settings_theme,
                                "language": host._settings_language,
                                "processing_device": preference,
                                "processing_device_origin": host._processing_device_origin,
                            }
                        )
                    except OSError:
                        pass
                    host._runtime_probe_error = ""
                    if host._pending_processing_device == preference:
                        host._pending_processing_device = ""
                    host._warm_models_unlocked()
                host.settingsChanged.emit()
                host.hardwareChanged.emit()
                options_changed = getattr(host, "speechRecognitionModelOptionsChanged", None)
                if options_changed:
                    options_changed.emit()
                if host._runtime_state == "ready":
                    host._model_setup_target_device = ""
                    self._queue_model_setup(
                        host,
                        state="ready",
                        component="",
                        detail="Models are ready",
                    )
            except Exception as exc:
                restore_previous_setting()
                host._status_message = f"Processing device switch failed: {exc}"
                self._set_runtime_state("ready")
                host.settingsChanged.emit()
                host.statusMessageChanged.emit()
            finally:
                host._device_switching = False
                host.processingChanged.emit()

        threading.Thread(target=switch_models, name="processing-device-switch", daemon=True).start()

    def _pipeline_is_active(self) -> bool:
        host = self._host
        """Return whether a video is currently inside the serial worker."""
        return bool(host._processing_queue.active_video_id)

    def _activate_pending_device_for_next_video(self, video_id: str) -> None:
        host = self._host
        """Switch only between two queued videos, never during a pipeline."""
        preference = host._pending_processing_device
        if preference not in {"cpu", "gpu"}:
            return

        if preference == processing_device_preference():
            host._pending_processing_device = ""
            return

        compatible, message = validate_processing_device(preference)
        if not compatible:
            preference = "cpu"
            host._settings_processing_device = "cpu"
            host._processing_device_origin = "detected"
            try:
                desktop_settings.save_settings(
                    {
                        "theme": host._settings_theme,
                        "language": host._settings_language,
                        "processing_device": "cpu",
                        "processing_device_origin": "detected",
                    }
                )
            except OSError:
                pass
            video_store.log_to_video(
                video_id, f"Requested GPU runtime is no longer safe: {message} Falling back to CPU."
            )

        probe = probe_runtime(preference)
        if not probe.ok and preference == "gpu":
            video_store.log_to_video(video_id, f"GPU runtime validation failed: {probe.message} Falling back to CPU.")
            preference = "cpu"
            probe = probe_runtime("cpu")
            host._settings_processing_device = "cpu"
            host._processing_device_origin = "detected"
            try:
                desktop_settings.save_settings(
                    {
                        "theme": host._settings_theme,
                        "language": host._settings_language,
                        "processing_device": "cpu",
                        "processing_device_origin": "detected",
                    }
                )
            except OSError:
                pass
        if not probe.ok:
            host._runtime_probe_error = probe.message
            video_store.log_to_video(video_id, f"Processing runtime validation failed: {probe.message}")
            return

        try:
            with host._model_runtime_lock:
                if preference != processing_device_preference():
                    smart = getattr(host, "_smart_warmup", None)
                    if smart is not None:
                        smart.quiesce_for_device_switch()
                    else:
                        self._shutdown_translation()
                    configure_processing_device(preference)
            host._active_processing_device = preference
            host._runtime_probe_error = ""
            host._pending_processing_device = ""
            video_store.log_to_video(video_id, f"Using the updated {preference.upper()} runtime for this video.")
        except Exception as exc:
            video_store.log_to_video(video_id, f"Could not apply the updated processing device: {exc}")

    def _apply_live_hardware(self, capabilities) -> None:
        """Apply a completed worker probe on the Qt GUI thread."""
        host = self._host
        recommended_device = recommended_processing_device(capabilities)
        # The pipeline can force a single video onto CPU after a GPU fault. Once
        # the queue is idle, persist that runtime choice so Settings never
        # claims that GPU is active while the app is actually using CPU.
        runtime_fallback_device = processing_device_preference()
        runtime_fallback_pending = (
            not host._pending_processing_device and runtime_fallback_device != host._settings_processing_device
        )
        should_fallback_to_cpu = host._settings_processing_device == "gpu" and recommended_device == "cpu"
        should_follow_recommendation = (
            host._processing_device_origin == "detected" and recommended_device != host._settings_processing_device
        )
        runtime_needs_switch = runtime_fallback_pending or should_fallback_to_cpu or should_follow_recommendation
        if capabilities != host._hardware_capabilities:
            host._hardware_capabilities = capabilities
            host.hardwareChanged.emit()
            options_changed = getattr(host, "speechRecognitionModelOptionsChanged", None)
            if options_changed:
                options_changed.emit()
        if host._pipeline_is_active():
            return
        if host._pending_processing_device:
            if not host._device_switching:
                host._switch_processing_device(host._pending_processing_device)
            return
        if not runtime_needs_switch or host._device_switching:
            return
        host._apply_detected_processing_device(
            runtime_fallback_device if runtime_fallback_pending else recommended_device
        )

    def _refresh_live_hardware(self):
        """Schedule Settings telemetry without importing Torch on the GUI thread."""
        host = self._host
        if not host._hardware_telemetry_active or host._shutdown_started:
            return
        with host._hardware_probe_lock:
            if host._hardware_probe_running:
                return
            host._hardware_probe_running = True

        def probe() -> None:
            try:
                capabilities = self._detect_hardware()
                host._hardware_probe_events.put({"kind": "telemetry", "capabilities": capabilities})
            except Exception as exc:
                host._hardware_probe_events.put({"kind": "error", "message": str(exc)})
            finally:
                with host._hardware_probe_lock:
                    host._hardware_probe_running = False

        threading.Thread(target=probe, name="hardware-live-probe", daemon=True).start()

    def drain_hardware_events(self) -> None:
        """Transfer hardware worker results to Qt without redundant repaints."""
        host = self._host
        events = getattr(host, "_hardware_probe_events", None)
        if events is None:
            return
        while True:
            try:
                event = events.get_nowait()
            except queue.Empty:
                break
            kind = event.get("kind")
            if kind == "telemetry":
                self._apply_live_hardware(event["capabilities"])
            elif kind == "startup":
                host._hardware_capabilities = event["capabilities"]
                refresh_turbo = getattr(host, "_refresh_whisper_turbo_model_ready", None)
                if refresh_turbo:
                    refresh_turbo()
                host.hardwareChanged.emit()
                options_changed = getattr(host, "speechRecognitionModelOptionsChanged", None)
                if options_changed:
                    options_changed.emit()
                if event.get("settings_changed"):
                    host.settingsChanged.emit()
                if event.get("status_message"):
                    host.statusMessageChanged.emit()

    def setHardwareTelemetryActive(self, active: bool):
        host = self._host
        """Only refresh dynamic telemetry while the Settings dialog needs it."""
        host._hardware_telemetry_active = bool(active)
        if host._hardware_telemetry_active:
            host._refresh_live_hardware()

    def _apply_detected_processing_device(self, device: str):
        host = self._host
        """Persist a safe device chosen from live hardware telemetry."""
        if device not in {"cpu", "gpu"}:
            device = "cpu"
        host._settings_processing_device = device
        host._processing_device_origin = "detected"
        try:
            desktop_settings.save_settings(
                {
                    "theme": host._settings_theme,
                    "language": host._settings_language,
                    "processing_device": device,
                    "processing_device_origin": "detected",
                }
            )
        except OSError:
            pass
        host.settingsChanged.emit()
        host._switch_processing_device(device)

    def _set_warmup_status(self, detail: str):
        host = self._host
        host._status_message = detail
        host.statusMessageChanged.emit()
        if host._model_setup_state != "ready":
            self._queue_model_setup(
                host,
                state="warming",
                component="",
                detail=detail,
            )
