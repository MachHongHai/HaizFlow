"""Mutating project, batch, and video commands behind the QML facade."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from haizflow.desktop.localization import QMessageBox
from haizflow.core.hardware import runtime_profile
from haizflow.pipeline.process_registry import cancel_video, pause_video
from haizflow.services import project_store, video_store
from haizflow.services.desktop_videos import create_desktop_video, set_desktop_background_music
from haizflow.schemas.video import SubtitleStyle


def _subtitle_style_items(video) -> tuple[tuple[str, object], ...]:
    style = getattr(video, "subtitle_style", None) or SubtitleStyle()
    values = style.model_dump() if hasattr(style, "model_dump") else style.dict()
    return tuple(values.items()) + (("manual", bool(getattr(video, "subtitle_layout_override", False))),)


def _validated_review_segments(payload: str) -> list[dict]:
    segments = json.loads(payload)
    if not isinstance(segments, list) or not segments:
        raise ValueError("The review must contain at least one translated segment.")
    for index, item in enumerate(segments, 1):
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            raise ValueError(f"Translation segment {index} must contain text.")
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Translation segment {index} has invalid timestamps.") from exc
        if start < 0 or end <= start:
            raise ValueError(f"Translation segment {index} has an invalid time range.")
    return segments


def _write_json_atomic(path: str, payload) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(prefix=".haizflow-review-", suffix=".json.tmp", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.remove(temporary_path)
        except FileNotFoundError:
            pass
        raise


class ProjectCommandsController:
    def __init__(self, host, *, create_video=None):
        self._host = host
        self._create_video = create_video or create_desktop_video

    def start_batch(self) -> None:
        host = self._host
        pending_ids = [
            video_id
            for video_id in host._batch_video_ids
            if (video := video_store.get_video(video_id)) and video.status == "pending"
        ]
        if not pending_ids:
            QMessageBox.information(None, "Batch queue", "Add at least one video to the queue.")
            return
        host._batch_running = True
        host._batch_stop_requested = False
        if not host._enqueue_videos(pending_ids):
            host._batch_running = False
            QMessageBox.information(None, "Batch queue", "These videos are already waiting or processing.")
            return
        host.batchChanged.emit()

    def resume_batch(self) -> None:
        """Resume paused work and include any newly added pending videos."""
        host = self._host
        resumable_ids = []
        for video_id in host._batch_video_ids:
            video = video_store.get_video(video_id)
            if video and video.status in {"paused", "pending"} and not host._processing_queue.contains(video_id):
                resumable_ids.append(video_id)
        if not resumable_ids:
            QMessageBox.information(None, "Batch queue", "There are no paused videos to resume.")
            return
        host._batch_running = True
        host._batch_stop_requested = False
        queued = host._enqueue_videos(resumable_ids)
        if not queued:
            host._batch_running = False
            QMessageBox.information(None, "Batch queue", "These videos are already waiting or processing.")
            return
        for video_id in resumable_ids:
            if host._processing_queue.contains(video_id):
                video_store.log_to_video(video_id, "Batch resumed from its saved processing state.")
        host.batchChanged.emit()

    def batch_settings_values(self) -> dict[str, object]:
        host = self._host
        videos = [video for video_id in host._batch_video_ids if (video := video_store.get_video(video_id))]
        if not videos:
            return {
                "workflowMode": host._workflow_mode,
                "targetLanguage": host._target_language,
                "speechRecognitionModel": getattr(host, "_speech_recognition_model", "small"),
                "ttsProvider": host._tts_provider,
                "ttsVoice": host._tts_voice,
                "speakerMode": getattr(host, "_speaker_mode", "single"),
                "enableAudioSeparation": host._enable_audio_separation,
                "originalVolume": host._original_volume,
                "backgroundMusicVolume": host._background_music_volume,
                "ttsVolume": host._tts_volume,
                "watermarkText": host._watermark_text,
                "removeOriginalSubtitles": bool(getattr(host, "_remove_original_subtitles", True)),
                "originalSubtitleRemovalMode": str(
                    getattr(host, "_original_subtitle_removal_mode", "patch") or "patch"
                ),
                "subtitleStyle": {
                    **(getattr(host, "_subtitle_style", None) or SubtitleStyle()).model_dump(),
                    "manual": bool(getattr(host, "_subtitle_layout_override", False)),
                },
                "backgroundMusicPath": getattr(host, "_background_music_path", ""),
            }
        common, _count = Counter(
            (
                video.mode,
                video.target_language,
                getattr(video, "speech_recognition_model", "small"),
                getattr(video, "tts_provider", "edge"),
                video.tts_voice,
                getattr(video, "speaker_mode", "single"),
                video.enable_audio_separation,
                video.original_video_volume,
                getattr(video, "background_music_volume", 30),
                getattr(video, "tts_volume", 100),
                getattr(video, "watermark_text", ""),
                bool(getattr(video, "remove_original_subtitles", True)),
                str(getattr(video, "original_subtitle_removal_mode", "patch") or "patch"),
                _subtitle_style_items(video),
            )
            for video in videos
        ).most_common(1)[0]
        (
            workflow_mode,
            target_language,
            speech_recognition_model,
            tts_provider,
            tts_voice,
            speaker_mode,
            audio_separation,
            original_volume,
            background_music_volume,
            tts_volume,
            watermark_text,
            remove_original_subtitles,
            original_subtitle_removal_mode,
            subtitle_style_items,
        ) = common
        baseline_video = next(
            (
                video
                for video in videos
                if (
                    video.mode,
                    video.target_language,
                    getattr(video, "speech_recognition_model", "small"),
                    getattr(video, "tts_provider", "edge"),
                    video.tts_voice,
                    getattr(video, "speaker_mode", "single"),
                    video.enable_audio_separation,
                    video.original_video_volume,
                    getattr(video, "background_music_volume", 30),
                    getattr(video, "tts_volume", 100),
                    getattr(video, "watermark_text", ""),
                    bool(getattr(video, "remove_original_subtitles", True)),
                    str(getattr(video, "original_subtitle_removal_mode", "patch") or "patch"),
                    _subtitle_style_items(video),
                )
                == common
            ),
            videos[0],
        )
        background_music_path = str((baseline_video.files or {}).get("background_music") or "")
        if background_music_path and not os.path.isfile(background_music_path):
            background_music_path = ""
        target_language = str(target_language or "vi")
        tts_provider = host._normalized_tts_provider(target_language, tts_provider)
        return {
            "workflowMode": "review" if workflow_mode == "review" else "A",
            "targetLanguage": target_language,
            "speechRecognitionModel": str(speech_recognition_model or "small"),
            "ttsProvider": tts_provider,
            "ttsVoice": host._normalized_voice_for_language(target_language, tts_voice, tts_provider),
            "speakerMode": "multiple" if speaker_mode == "multiple" else "single",
            "enableAudioSeparation": bool(audio_separation),
            "originalVolume": int(original_volume),
            "backgroundMusicVolume": int(background_music_volume),
            "ttsVolume": int(tts_volume),
            "watermarkText": str(watermark_text or ""),
            "removeOriginalSubtitles": bool(remove_original_subtitles),
            "originalSubtitleRemovalMode": str(original_subtitle_removal_mode),
            "subtitleStyle": dict(subtitle_style_items),
            "backgroundMusicPath": background_music_path,
        }

    def batch_setting_overrides(self) -> list[dict[str, object]]:
        """List videos whose saved configuration differs from the batch default.

        The common (most frequent) configuration is the batch default.  This
        makes individual overrides visible without overwriting them or adding
        another mutable project-level copy of the settings.
        """
        host = self._host
        videos = [video for video_id in host._batch_video_ids if (video := video_store.get_video(video_id))]
        if len(videos) < 2:
            return []

        def values(video) -> tuple[object, ...]:
            music_path = str((getattr(video, "files", None) or {}).get("background_music") or "")
            music_signature = (
                (os.path.splitext(music_path)[1].lower(), os.path.getsize(music_path))
                if os.path.isfile(music_path)
                else ()
            )
            return (
                "review" if video.mode == "review" else "A",
                str(video.target_language or "vi"),
                str(getattr(video, "speech_recognition_model", "small") or "small"),
                str(getattr(video, "tts_provider", "edge") or "edge"),
                str(video.tts_voice or ""),
                str(getattr(video, "speaker_mode", "single") or "single"),
                bool(video.enable_audio_separation),
                int(video.original_video_volume),
                int(getattr(video, "background_music_volume", 30)),
                int(getattr(video, "tts_volume", 100)),
                " ".join(str(getattr(video, "watermark_text", "") or "").split())[:80],
                bool(getattr(video, "remove_original_subtitles", True)),
                str(getattr(video, "original_subtitle_removal_mode", "patch") or "patch"),
                _subtitle_style_items(video),
                music_signature,
            )

        keys = (
            "workflow",
            "targetLanguage",
            "speechRecognitionModel",
            "ttsProvider",
            "voice",
            "speakers",
            "audioSource",
            "sourceVolume",
            "backgroundMusicVolume",
            "ttsVolume",
            "watermark",
            "originalSubtitles",
            "subtitleRemovalMode",
            "subtitleLayout",
            "backgroundMusic",
        )
        baseline, _count = Counter(values(video) for video in videos).most_common(1)[0]
        overrides = []
        for video in videos:
            differences = [key for key, value, expected in zip(keys, values(video), baseline) if value != expected]
            if differences:
                overrides.append(
                    {
                        "videoId": video.video_id,
                        "fileName": video.original_filename,
                        "differences": differences,
                    }
                )
        return overrides

    def apply_batch_settings(
        self,
        workflow_mode,
        target_language,
        tts_provider,
        tts_voice,
        enable_audio_separation,
        original_volume,
        background_music_volume=None,
        tts_volume=None,
        watermark_text=None,
        background_music_path=None,
        remove_original_subtitles=None,
        subtitle_style=None,
        original_subtitle_removal_mode=None,
        speech_recognition_model=None,
        speaker_mode=None,
    ) -> bool:
        host = self._host
        mode = "review" if workflow_mode == "review" else "A"
        language = str(target_language or "vi")
        normalize_provider = getattr(host, "_normalized_tts_provider", None)
        provider = (
            normalize_provider(language, tts_provider)
            if normalize_provider
            else (str(tts_provider or "omnivoice").lower())
        )
        asr_model = (
            str(speech_recognition_model or getattr(host, "_speech_recognition_model", "small") or "small")
            .strip()
            .lower()
        )
        if asr_model not in {"small", "large-v3-turbo"}:
            asr_model = "small"
        capabilities = getattr(host, "_hardware_capabilities", None)
        turbo_gpu_available = bool(
            (capabilities and capabilities.cuda_available)
            or getattr(host, "_active_processing_device", "") == "gpu"
            or getattr(host, "_settings_processing_device", "") == "gpu"
            or runtime_profile().cuda_available
        )
        turbo_model_ready = bool(getattr(host, "_whisper_turbo_model_ready", False))
        if asr_model == "large-v3-turbo" and (not turbo_gpu_available or not turbo_model_ready):
            show_alert = getattr(host, "_show_app_alert", None)
            message = (
                "Whisper large-v3-turbo has not finished downloading or integrity verification. "
                "Wait for model setup to finish, or select WhisperX small."
                if turbo_gpu_available and not turbo_model_ready
                else "Whisper large-v3-turbo requires an NVIDIA CUDA GPU. Select WhisperX small for this device."
            )
            if callable(show_alert):
                show_alert(
                    "Speech recognition",
                    message,
                    "warning",
                )
            else:
                QMessageBox.warning(
                    None,
                    "Speech recognition",
                    message,
                )
            return False
        try:
            voice = host._normalized_voice_for_language(language, tts_voice, provider)
        except TypeError:
            voice = host._normalized_voice_for_language(language, tts_voice)
        normalized_speaker_mode = (
            "multiple"
            if str(speaker_mode or getattr(host, "_speaker_mode", "single")).strip().lower() == "multiple"
            else "single"
        )
        apply_mix_volumes = background_music_volume is not None or tts_volume is not None
        background_music_volume = (
            getattr(host, "_background_music_volume", 30)
            if background_music_volume is None
            else int(background_music_volume)
        )
        tts_volume = getattr(host, "_tts_volume", 100) if tts_volume is None else int(tts_volume)
        apply_watermark = watermark_text is not None
        watermark_text = " ".join(str(watermark_text or "").split())[:80]
        apply_background_music = background_music_path is not None
        apply_original_subtitles = remove_original_subtitles is not None
        apply_removal_mode = original_subtitle_removal_mode is not None
        removal_mode = str(original_subtitle_removal_mode or "patch").strip().lower()
        if removal_mode == "inpaint":
            removal_mode = "patch"
        if removal_mode not in {"blur", "patch"}:
            removal_mode = "patch"
        apply_subtitle_style = subtitle_style is not None
        subtitle_style_payload = dict(subtitle_style or {})
        subtitle_layout_override = bool(subtitle_style_payload.pop("manual", False))
        normalized_subtitle_style = SubtitleStyle(**subtitle_style_payload) if apply_subtitle_style else None
        background_music_path = (
            os.path.abspath(str(background_music_path or "").strip()) if background_music_path else ""
        )
        if (
            apply_background_music
            and background_music_path
            and (not os.path.isfile(background_music_path) or os.path.getsize(background_music_path) <= 0)
        ):
            QMessageBox.warning(None, "Background music", "The selected background music is no longer available.")
            return False
        videos = [video for video_id in host._batch_video_ids if (video := video_store.get_video(video_id))]
        if not videos:
            QMessageBox.information(None, "Batch settings", "Add at least one video before applying settings.")
            return False
        if any(host._processing_queue.contains(video.video_id) for video in videos):
            QMessageBox.information(
                None,
                "Batch settings",
                "Pause the batch before changing settings for every video.",
            )
            return False

        updated = 0
        for video in videos:
            video_id = video.video_id
            changes = {
                "mode": mode,
                "source_language": "auto",
                "target_language": language,
                "speech_recognition_model": asr_model,
                "tts_provider": provider,
                "tts_voice": voice,
                "speaker_mode": normalized_speaker_mode,
                "enable_audio_separation": bool(enable_audio_separation),
                "original_video_volume": int(original_volume),
            }
            if apply_mix_volumes:
                changes.update(
                    background_music_volume=max(0, min(100, background_music_volume)),
                    tts_volume=max(0, min(100, tts_volume)),
                )
            if apply_watermark:
                changes["watermark_text"] = watermark_text
            if apply_original_subtitles:
                changes["remove_original_subtitles"] = bool(remove_original_subtitles)
            if apply_removal_mode:
                changes["original_subtitle_removal_mode"] = removal_mode
            if normalized_subtitle_style is not None:
                changes["subtitle_style"] = normalized_subtitle_style
                changes["subtitle_layout_override"] = subtitle_layout_override
            if apply_background_music:
                try:
                    set_desktop_background_music(video, background_music_path)
                except (OSError, RuntimeError, ValueError) as exc:
                    QMessageBox.warning(
                        None, "Background music", f"Could not apply background music to every video: {exc}"
                    )
                    return False
            video_store.update_video(video_id, **changes)
            updated += 1
        if not updated:
            QMessageBox.information(None, "Batch settings", "Add at least one video before applying settings.")
            return False
        if apply_background_music:
            try:
                project_key_value = str(getattr(host, "_selected_project_key", "") or "")
                project_root = project_store.project_root_for_key(project_key_value)
                draft_assets = os.path.abspath(os.path.join(project_root, ".batch-assets"))
                shutil.rmtree(draft_assets, ignore_errors=True)
            except (OSError, ValueError):
                pass
        host.refreshVideos()
        host.batchChanged.emit()
        return True

    def load_batch_settings(self) -> None:
        self._sync_host_with_batch_settings()

    def _sync_host_with_batch_settings(self) -> None:
        host = self._host
        values = self.batch_settings_values()
        host._workflow_mode = values["workflowMode"]
        host._target_language = values["targetLanguage"]
        host._speech_recognition_model = values["speechRecognitionModel"]
        host._tts_provider = values["ttsProvider"]
        host._tts_voice = values["ttsVoice"]
        host._speaker_mode = values["speakerMode"]
        host._enable_audio_separation = values["enableAudioSeparation"]
        host._original_volume = values["originalVolume"]
        host._background_music_volume = values["backgroundMusicVolume"]
        host._tts_volume = values["ttsVolume"]
        host._watermark_text = values["watermarkText"]
        host._remove_original_subtitles = values["removeOriginalSubtitles"]
        host._original_subtitle_removal_mode = values["originalSubtitleRemovalMode"]
        subtitle_style = dict(values["subtitleStyle"])
        host._subtitle_layout_override = bool(subtitle_style.pop("manual", False))
        host._subtitle_style = SubtitleStyle(**subtitle_style)
        host._background_music_path = str(values.get("backgroundMusicPath") or "")
        host.workflowModeChanged.emit()
        host.targetLanguageChanged.emit()
        host.speechRecognitionModelChanged.emit()
        host.ttsProviderChanged.emit()
        host.ttsProviderOptionsChanged.emit()
        host.ttsVoiceChanged.emit()
        host.ttsVoiceOptionsChanged.emit()
        host.speakerModeChanged.emit()
        host.enableAudioSeparationChanged.emit()
        host.originalVolumeChanged.emit()
        host.backgroundMusicVolumeChanged.emit()
        host.ttsVolumeChanged.emit()
        host.watermarkTextChanged.emit()
        host.subtitleSettingsChanged.emit()
        host.backgroundMusicChanged.emit()

    def save_selected_video_settings(self) -> bool:
        return self._persist_selected_video_settings(log_change=True)

    def persist_selected_video_settings(self, expected_video_id: str = "") -> bool:
        """Persist an edited selected video without adding a noisy log entry.

        The setup panel is shared by single projects and per-video batch
        editing.  Keeping this method batch-only meant a user could change the
        subtitle-removal setting or manual layout on a completed single video,
        leave the page, and still open an export made with the earlier setup.
        Store the draft for both project types as soon as the editor settles;
        rendering remains an explicit action.
        """
        return self._persist_selected_video_settings(
            log_change=False,
            expected_video_id=str(expected_video_id or ""),
        )

    def _persist_selected_video_settings(self, *, log_change: bool, expected_video_id: str = "") -> bool:
        host = self._host
        selected_video_id = str(host._selected_video_id or "")
        if expected_video_id and expected_video_id != selected_video_id:
            return False
        settings_owner = getattr(host, "_settings_owner_video_id", None)
        if settings_owner is not None and str(settings_owner or "") != selected_video_id:
            return False
        video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if not video or host._processing_queue.contains(video.video_id):
            return False
        host._apply_setup_to_video(video)
        if log_change:
            video_store.log_to_video(video.video_id, "Per-video dubbing settings saved.")
        host.refreshVideos()
        host.selectedVideoChanged.emit()
        if video.project_type == "batch":
            host.batchChanged.emit()
        return True

    def stop_batch(self) -> None:
        host = self._host
        if not host.isBatchRunning:
            return
        if (
            QMessageBox.question(
                None, "Pause batch", "Pause the active video and the remaining queue? You can resume this batch later."
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        host._batch_stop_requested = True
        active_video_id, waiting_video_ids = host._processing_queue.detach_pending(host._batch_video_ids)
        # Remove waiting items first so the worker cannot promote the next one
        # while the active subprocess tree is winding down.
        for video_id in waiting_video_ids:
            video = video_store.get_video(video_id)
            if video:
                video_store.update_video(
                    video_id,
                    status="paused",
                    error=None,
                    step="paused",
                    resume_step=video.resume_step or "",
                    step_detail="Paused while waiting in the processing queue",
                )
                video_store.log_to_video(video_id, "Paused while waiting in the batch queue.")
        if active_video_id in host._batch_video_ids:
            active_video = video_store.get_video(active_video_id)
            resume_step = active_video.step if active_video else ""
            pause_video(active_video_id)
            video_store.update_video(
                active_video_id,
                status="paused",
                error=None,
                step="paused",
                resume_step=resume_step,
                step_detail=f"Paused during {resume_step or 'startup'}",
            )
            video_store.log_to_video(active_video_id, "Batch pause requested. Active subprocesses were stopped safely.")
        host._refresh_batch_model()
        host.batchChanged.emit()

    def clear_batch(self) -> None:
        host = self._host
        if host.isBatchRunning:
            return
        host._batch_video_ids = []
        host._refresh_batch_model()
        host.batchChanged.emit()

    def delete_current_batch(self) -> None:
        host = self._host
        batch_ids = list(host._batch_video_ids)
        if not host.hasOpenProject:
            return
        if not batch_ids:
            host.deleteCurrentProject()
            return
        message = (
            "Delete this batch project and all of its videos?\n\n"
            f"{host._project_name or 'this batch'}\n{len(batch_ids)} video(s)\n\n"
            "This removes processing logs, temporary data, copied inputs, and generated videos. "
            "If processing is active, it will be stopped first."
        )
        if (
            QMessageBox.question(
                None,
                "Delete project",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        current_key = host._selected_project_key
        try:
            project_store.validate_project_deletion_by_key(current_key)
        except Exception as exc:
            QMessageBox.warning(None, "Delete project", str(exc))
            return
        if not host._channel_importer.cancel_project(current_key):
            QMessageBox.information(
                None, "Channel import", "Channel import is still stopping. Try deleting the project again in a moment."
            )
            return
        for session_id, target in tuple(host._channel_import_targets.items()):
            if target.get("project_key") == current_key:
                host._channel_import_targets.pop(session_id, None)
        host._batch_stop_requested = True
        if host._processing_queue.active_video_id in batch_ids:
            cancel_video(host._processing_queue.active_video_id)
        failures, remaining_ids = [], []
        for video_id in batch_ids:
            video = video_store.get_video(video_id)
            if not video:
                continue
            host._deleted_video_ids.add(video_id)
            host._processing_queue.discard(video_id)
            if video.status == "processing":
                cancel_video(video_id)
            try:
                video_store.delete_video(video_id)
                host._remove_empty_batch_output_parents(video)
            except Exception as exc:
                failures.append(f"{video.original_filename}: {exc}")
                remaining_ids.append(video_id)
        host._batch_video_ids = remaining_ids
        host._refresh_batch_model()
        host.batchChanged.emit()
        host._selected_video_id = None
        host._settings_owner_video_id = None
        host._clear_logs()
        host.selectedVideoChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        if failures:
            QMessageBox.warning(
                None,
                "Batch delete incomplete",
                "Some videos could not be deleted. You can retry after closing any program using them.\n\n"
                + "\n".join(failures[:5]),
            )
            return
        try:
            project_store.delete_project_by_key(current_key)
        except Exception as exc:
            QMessageBox.warning(None, "Delete project", str(exc))
            return
        host._selected_project_key = ""
        host._project_name = ""
        host.projectSetupChanged.emit()
        host.batchDeleted.emit()

    def start_video(self) -> None:
        host = self._host
        if not host._video_path.strip():
            QMessageBox.critical(None, "Missing video", "Please choose an input video.")
            return
        try:
            video = self._create_video(host._video_path, host._build_config())
        except Exception as exc:
            QMessageBox.critical(None, "Cannot start project", str(exc))
            return
        host._assign_project_thumbnail(video)
        host._selected_video_id = video.video_id
        host._settings_owner_video_id = video.video_id
        host._background_music_path = str((video.files or {}).get("background_music") or "")
        host._replace_logs(host._read_video_logs(video.video_id))
        host.selectedVideoChanged.emit()
        host.backgroundMusicChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        host._enqueue_video(video.video_id)

    def start_project_video(self) -> bool:
        host = self._host
        if not host._video_path.strip():
            QMessageBox.critical(None, "Missing video", "Please choose an input video.")
            return False
        if not host._project_name.strip():
            QMessageBox.warning(None, "Project name", "Enter a project name.")
            return False
        if not host._project_directory.strip():
            QMessageBox.warning(None, "Project storage location", "Choose a location for this project.")
            return False
        selected_video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if selected_video and host._processing_queue.contains(selected_video.video_id):
            host._status_message = "This video is already waiting or processing."
            host.statusMessageChanged.emit()
            return False
        if selected_video and selected_video.status == "pending":
            host._apply_setup_to_video(selected_video, review_approved=False)
            video_store.log_to_video(selected_video.video_id, "Processing requested for the imported video.")
            host._enqueue_video(selected_video.video_id)
            host.selectedVideoChanged.emit()
            host.refreshVideos()
            return True
        if selected_video:
            return False
        try:
            video = self._create_video(
                host._video_path,
                host._build_config(),
                project_name=host._project_name,
                project_directory=host._project_directory,
                project_key_value=host._selected_project_key,
            )
        except Exception as exc:
            QMessageBox.critical(None, "Cannot create project", str(exc))
            return False
        host._assign_project_thumbnail(video)
        host._selected_video_id = video.video_id
        host._settings_owner_video_id = video.video_id
        host._background_music_path = str((video.files or {}).get("background_music") or "")
        host._replace_logs(host._read_video_logs(video.video_id))
        host.selectedVideoChanged.emit()
        host.backgroundMusicChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        host._enqueue_video(video.video_id)
        return True

    def stop_video(self) -> None:
        host = self._host
        selected_video_id = host._selected_video_id
        if not selected_video_id or selected_video_id != host._processing_queue.active_video_id:
            return
        selected_video = video_store.get_video(selected_video_id)
        if not selected_video:
            return
        if host.isSelectedBatchVideo:
            self.stop_batch()
            return
        if (
            QMessageBox.question(None, "Pause video", "Pause this video? You can resume it later from Projects.")
            != QMessageBox.StandardButton.Yes
        ):
            return
        resume_step = selected_video.step
        pause_video(selected_video_id)
        video_store.update_video(
            selected_video_id,
            status="paused",
            error=None,
            step="paused",
            resume_step=resume_step,
            step_detail=f"Paused during {resume_step or 'startup'}",
        )
        video_store.log_to_video(selected_video_id, "Pause requested. Active subprocesses were stopped.")
        host.selectedVideoChanged.emit()
        host.refreshVideos()

    def resume_selected_video(self) -> None:
        host = self._host
        video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if not video or video.status != "paused" or host._processing_queue.contains(video.video_id):
            return
        # enqueue_video owns the paused -> queued transition because it must
        # first clear both process-registry pause and cancellation flags.
        # Pre-writing "pending" here used to skip that cleanup and strand the
        # resumed worker in a permanently cancelled state.
        if host._enqueue_video(video.video_id):
            video_store.log_to_video(video.video_id, "Resumed from the saved processing state.")
            host.selectedVideoChanged.emit()

    def restart_selected_video(self) -> None:
        host = self._host
        video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if (
            not video
            or video.status not in {"paused", "awaiting_review", "done", "failed", "cancelled"}
            or host._processing_queue.contains(video.video_id)
        ):
            return
        if host._device_switching:
            QMessageBox.information(
                None, "Processing device", "Wait for the processing device to finish switching before restarting."
            )
            return
        if (
            QMessageBox.question(None, "Restart video", "Apply the current dubbing setup and restart this project?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        settings_owner = getattr(host, "_settings_owner_video_id", None)
        if settings_owner is not None and str(settings_owner or "") != video.video_id:
            host._show_app_alert(
                "Settings are still loading",
                "Reopen this video before restarting so its own settings are used.",
                "warning",
            )
            return
        host._apply_setup_to_video(video, review_approved=False)
        restarted = video_store.prepare_video_restart(video.video_id)
        if not restarted:
            return
        video_store.log_to_video(
            restarted.video_id,
            f"Restart requested with the latest dubbing setup and runtime: {runtime_profile().summary}.",
        )
        host._enqueue_video(restarted.video_id)
        host.selectedVideoChanged.emit()

    def approve_translation_review(self, payload: str) -> bool:
        host = self._host
        video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if not video or video.status not in {"awaiting_review", "done"}:
            return False
        try:
            segments = _validated_review_segments(payload)
            transcript_path = (video.files or {}).get("transcript_json")
            if not isinstance(transcript_path, str) or not transcript_path.strip():
                raise ValueError("Video metadata is missing its translation-review path.")
            _write_json_atomic(transcript_path, segments)
            draft_path = str((video.files or {}).get("translation_review_draft") or "")
            if draft_path:
                Path(draft_path).unlink(missing_ok=True)
                files = dict(video.files or {})
                files.pop("translation_review_draft", None)
                video_store.update_video(video.video_id, files=files)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            host._show_app_alert(
                "Could not approve subtitles",
                str(exc),
                "warning",
            )
            return False
        translation_checkpoint = video.checkpoints.get("translation")
        checkpoints = {"translation": translation_checkpoint} if translation_checkpoint else {}
        elapsed_updates = {}
        if video.status == "done":
            # A post-processing subtitle correction is a new downstream pass,
            # not a continuation of the original full pipeline duration.
            elapsed_updates = {
                "processing_elapsed_seconds": 0.0,
                "started_at": None,
                "estimated_remaining_seconds": None,
            }
        video_store.update_video(
            video.video_id,
            review_approved=True,
            status="pending",
            step="queued",
            resume_step="creating_subtitle",
            runtime_recovery_step="",
            checkpoints=checkpoints,
            step_detail="Queued to create dub",
            **elapsed_updates,
        )
        video_store.log_to_video(
            video.video_id,
            f"Translation review approved with {len(segments)} edited segments. Added to the processing queue.",
        )
        host._enqueue_video(video.video_id)
        host.selectedVideoChanged.emit()
        return True

    def save_translation_review_draft(self, payload: str) -> bool:
        host = self._host
        video = video_store.get_video(host._selected_video_id) if host._selected_video_id else None
        if not video or video.status not in {"awaiting_review", "done"}:
            return False
        try:
            segments = _validated_review_segments(payload)
            draft_path = os.path.join(video_store.get_video_dir(video.video_id), "translation-review-draft.json")
            _write_json_atomic(draft_path, segments)
            files = dict(video.files or {})
            files["translation_review_draft"] = draft_path
            video_store.update_video(video.video_id, files=files)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            host._show_app_alert(
                "Could not save subtitle draft",
                str(exc),
                "warning",
            )
            return False
        host._status_message = "Translation-review draft saved."
        host.statusMessageChanged.emit()
        video_store.log_to_video(video.video_id, f"Translation review draft saved with {len(segments)} segments.")
        return True

    def delete_selected_video(self) -> None:
        host = self._host
        if not host._selected_video_id:
            QMessageBox.information(None, "No video selected", "Select a video in this batch first.")
            return
        video_id = host._selected_video_id
        video = video_store.get_video(video_id)
        label = video.original_filename if video else video_id
        if (
            QMessageBox.question(
                None,
                "Remove video",
                f"Remove this video from the batch project and delete its generated files?\n\n{label}\n\n"
                "If it is running, it will be stopped first.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if video and (video.status == "processing" or host._processing_queue.active_video_id == video_id):
            cancel_video(video_id)
            video_store.update_video(video_id, status="cancelled", error=None, step="cancelled")
        host._deleted_video_ids.add(video_id)
        host._processing_queue.discard(video_id)
        try:
            deleted = video_store.delete_video(video_id)
            if video:
                host._remove_empty_batch_output_parents(video)
                video_store.cleanup_batch_project_orphans(host._selected_project_key)
        except Exception as exc:
            QMessageBox.critical(None, "Delete failed", str(exc))
            return
        if not deleted:
            QMessageBox.information(None, "Already removed", "Video data was already removed.")
        if video_id in host._batch_video_ids:
            host._batch_video_ids.remove(video_id)
            host._refresh_batch_model()
            host.batchChanged.emit()
        host._selected_video_id = None
        host._settings_owner_video_id = None
        host._clear_logs()
        host.selectedVideoChanged.emit()
        host.logsChanged.emit()
        host.refreshVideos()
        host.videoDeleted.emit()

    def delete_current_project(self) -> None:
        host = self._host
        if not host.hasOpenProject:
            QMessageBox.information(None, "Delete project", "Select a project first.")
            return
        current_key = host._selected_project_key
        if host._project_type == "download" and host._media_downloader.has_project_work(current_key):
            QMessageBox.information(
                None,
                "Delete project",
                "Finish or cancel this project's downloads before deleting it.",
            )
            return
        if host._project_type == "publish" and host._tiktok_publisher.has_project_work(current_key):
            QMessageBox.information(
                None,
                "Delete project",
                "Wait for this project's Zernio or video import task to finish before deleting it.",
            )
            return
        project_videos = [
            video
            for video in video_store.list_videos()
            if video.project_directory and host._video_project_key(video) == current_key
        ]
        suffix = (
            ""
            if not project_videos
            else f"\n\nThis also removes {len(project_videos)} video(s) and their generated files."
        )
        if (
            QMessageBox.question(
                None,
                "Delete project",
                f"Delete project '{host._project_name}' and all files inside its project folder?{suffix}",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            project_store.validate_project_deletion_by_key(current_key)
        except Exception as exc:
            QMessageBox.critical(None, "Delete project", str(exc))
            return
        if not host._channel_importer.cancel_project(current_key):
            QMessageBox.information(
                None, "Channel import", "Channel import is still stopping. Try deleting the project again in a moment."
            )
            return
        for session_id, target in tuple(host._channel_import_targets.items()):
            if target.get("project_key") == current_key:
                host._channel_import_targets.pop(session_id, None)
        try:
            for video in project_videos:
                host._processing_queue.discard(video.video_id)
                if video.status == "processing" or host._processing_queue.active_video_id == video.video_id:
                    cancel_video(video.video_id)
                    video_store.update_video(video.video_id, status="cancelled", error=None, step="cancelled")
                host._deleted_video_ids.add(video.video_id)
                video_store.delete_video(video.video_id)
            project_store.delete_project_by_key(current_key)
        except Exception as exc:
            QMessageBox.critical(None, "Delete project", str(exc))
            return
        host._selected_video_id = None
        host._settings_owner_video_id = None
        host._selected_project_key = ""
        if host._project_type == "download":
            host._media_downloader.attach_project("", "")
        elif host._project_type == "publish":
            host._tiktok_publisher.detach_project()
        host._batch_video_ids = []
        host._clear_logs()
        host.videoPath = ""
        host._refresh_batch_model()
        host.selectedVideoChanged.emit()
        host.projectSetupChanged.emit()
        host.logsChanged.emit()
        host.batchChanged.emit()
        host.refreshVideos()
        host.videoDeleted.emit()
