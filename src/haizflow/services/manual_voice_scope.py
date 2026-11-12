"""Stable sentence identities for bounded Manual voice requests."""
from __future__ import annotations


def selected_ids(files, segments):
    if "manual_voice_selection" not in (files or {}):
        return None
    request = files["manual_voice_selection"]
    known = {str(item.get("segment_id") or "") for item in segments}
    if (not isinstance(request, list) or not request or len(request) > len(segments)
            or any(not isinstance(key, str) or not key or key not in known for key in request)
            or len(set(request)) != len(request)):
        raise ValueError("Các câu đã chọn không còn hợp lệ. Hãy chọn lại phạm vi tạo giọng.")
    return set(request)


def effective_mode(video, override):
    if override.get("speaker_mode") in {"single", "multiple"}:
        return override["speaker_mode"]
    if override.get("voice"):
        return "single"
    return str(getattr(video, "speaker_mode", "single") or "single")
