"""Bind a resumable task to its original processing settings and inputs."""

from __future__ import annotations

import json
from pathlib import Path

from haizflow.schemas.video import VideoConfig


_IDENTITY = {"project_name", "project_directory", "project_key", "project_id", "project_type", "review_approved"}
_MANUAL_FIELDS = {
    "source": set(), "separation": set(),
    "translation": {"source_language", "target_language", "speech_recognition_model",
                    "translation_model", "translator_provider", "enable_audio_separation"},
    "recognition": {"source_language", "speech_recognition_model", "enable_audio_separation"},
    "image": {"remove_original_subtitles", "original_subtitle_removal_mode", "crop", "subtitle_style"},
    "voice": {"target_language", "tts_provider", "tts_voice", "speaker_mode"},
    "subtitle": {"subtitle_style"},
}


def configuration_snapshot(video, device: str, config=None) -> dict:
    tool = str(getattr(video, "manual_target_tool", "") or "")
    defaults = VideoConfig().model_dump(mode="json")
    fields = set(defaults) - _IDENTITY
    if getattr(video, "project_type", "single") == "manual":
        fields = _MANUAL_FIELDS.get(tool, fields)
    settings = {}
    for field in sorted(fields):
        value = getattr(config, field, getattr(video, field, defaults[field])) if config is not None else getattr(video, field, defaults[field])
        settings[field] = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    # Normalize lightweight test fixtures and persisted models identically.
    settings = json.loads(json.dumps(settings, sort_keys=True))
    files = dict(getattr(video, "files", {}) or {})
    assets = {"video_input"}
    if not tool or tool in {"voice", "audio", "export"}:
        assets.update({"voice_reference", "background_music", "watermark_image", "watermark_video"})
    inputs = {}
    for key in sorted(assets):
        path = str(files.get(key) or "")
        try:
            state = Path(path).stat() if path else None
            inputs[key] = [path, state.st_size, state.st_mtime_ns] if state else [path]
        except OSError:
            inputs[key] = [path, "missing"]
    if tool in {"voice", "audio", "export"}:
        inputs["subtitle_document"] = str((getattr(video, "active_artifacts", {}) or {}).get("subtitle_document") or "")
        inputs["voice_overrides"] = files.get("manual_voice_overrides", {})
        inputs["voice_reference_transcript"] = files.get("voice_reference_transcript", "")
    return {"schema": 1, "device": str(device or "cpu"), "tool": tool,
            "settings": settings, "inputs": inputs}


def can_resume(host, video) -> bool:
    if getattr(video, "status", "") != "paused":
        return True
    original = getattr(video, "processing_configuration", {}) or {}
    device = str(getattr(host, "_settings_processing_device", "cpu") or "cpu")
    current = configuration_snapshot(video, device)
    build = getattr(host, "_build_config", None)
    selected = str(getattr(host, "_selected_video_id", "") or "") == video.video_id
    owner = str(getattr(host, "_settings_owner_video_id", video.video_id) or "") == video.video_id
    draft_matches = not (selected and owner and callable(build)) or configuration_snapshot(video, device, build()) == original
    if original and current == original and draft_matches:
        return True
    vi = getattr(host, "_settings_language", "vi") == "vi"
    title = "Không thể tiếp tục" if vi else "Cannot resume"
    detail = ("Cài đặt hoặc dữ liệu đầu vào đã thay đổi từ lúc chạy tác vụ. Chọn Chạy lại để dùng cài đặt mới, hoặc khôi phục cài đặt cũ rồi Tiếp tục."
              if original else "Tác vụ cũ chưa lưu cấu hình để kiểm tra. Chọn Chạy lại để xử lý an toàn.") if vi else (
        "Settings or inputs have changed since this task started. Choose Run again to use the new settings, or restore the original settings before resuming."
        if original else "This older task has no saved configuration to verify. Choose Run again to start safely.")
    host.appAlertRequested.emit(title, detail, "warning")
    return False
