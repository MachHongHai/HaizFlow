"""Timed source-caption treatments in the saved editor document."""

import json
from pathlib import Path

from haizflow.schemas.editor import EditorClip, EditorTrack
from haizflow.services.ocr_regions import effective_region, normalize_region

PRIMARY_TRACK = "ocr-source"
PRIMARY_CLIP = "ocr-source-region"
EXTRA_LAYERS_ENABLED = True


def detected_region(video):
    from haizflow.services import video_store

    path = str((getattr(video, "files", {}) or {}).get("ocr_region") or
               Path(video_store.get_video_dir(video.video_id)) / "temp" / "original_subtitle_region.json")
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload.get("region", payload) if isinstance(payload, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def ensure_primary(document) -> bool:
    changed = False
    if not any(track.track_id == PRIMARY_TRACK for track in document.tracks):
        document.tracks.append(EditorTrack(
            track_id=PRIMARY_TRACK, kind="ocr", name="Vùng nhận diện", order=-1,
        ))
        changed = True
    if not any(clip.clip_id == PRIMARY_CLIP for clip in document.clips):
        document.clips.append(EditorClip(
            clip_id=PRIMARY_CLIP, track_id=PRIMARY_TRACK, kind="ocr",
            name="Vùng nhận diện", duration_ms=max(1, document.sequence.duration_ms),
            metadata={"primary_ocr": True},
        ))
        changed = True
    return changed


def layers(video, document, detected=None) -> list[dict]:
    """Topmost first, matching the panel and timeline track order."""
    tracks = {track.track_id: track for track in document.tracks if track.kind == "ocr"}
    primary_region = effective_region(video, detected)
    result = []
    for clip in sorted(document.clips, key=lambda clip: (
        tracks[clip.track_id].order if clip.track_id in tracks else 0, clip.start_ms, clip.clip_id,
    )):
        if clip.kind != "ocr" or clip.track_id not in tracks:
            continue
        primary = bool(clip.metadata.get("primary_ocr"))
        if not primary and not EXTRA_LAYERS_ENABLED:
            continue
        region = primary_region if primary else clip.metadata.get("region", {})
        try:
            region = normalize_region(region) if region else {}
        except ValueError:
            region = {}
        result.append({
            "clip_id": clip.clip_id, "track_id": clip.track_id,
            "name": clip.name, "primary": primary, "region": region,
            "visible": tracks[clip.track_id].visible,
            "pending": bool(clip.metadata.get("pending", False)),
            "mode": str(getattr(video, "original_subtitle_removal_mode", "patch"))
                if primary else str(clip.metadata.get("removal_mode", "blur")),
            "start_ms": clip.start_ms if EXTRA_LAYERS_ENABLED else 0,
            "duration_ms": clip.duration_ms if EXTRA_LAYERS_ENABLED else document.sequence.duration_ms,
            "enabled": (clip.enabled and tracks[clip.track_id].visible
                and (bool(getattr(video, "remove_original_subtitles", True)) if primary else True))
                if EXTRA_LAYERS_ENABLED else bool(getattr(video, "remove_original_subtitles", True)),
        })
    return result


def render_region(video, detected=None) -> dict | None:
    """Keep OCR layout geometry separate from the ordered render treatments."""
    from haizflow.services import editor_documents

    primary = effective_region(video, detected)
    if not EXTRA_LAYERS_ENABLED:
        return primary if getattr(video, "remove_original_subtitles", True) else None
    if getattr(video, "project_type", "single") != "manual":
        return primary if getattr(video, "remove_original_subtitles", True) else None
    document = editor_documents.load(video.video_id)
    if document is None:
        return primary if getattr(video, "remove_original_subtitles", True) else None
    ensure_primary(document)
    treatments = [item for item in reversed(layers(video, document, detected))
                  if item["enabled"] and item["region"] and item["duration_ms"] > 0]
    return {**(primary or {}), "treatment_layers": treatments} if treatments else None


def render_time_offset(sequence: dict, source_start: float) -> float:
    """A direct trim proxy reads source time but treatments live in sequence time."""
    decisions = sequence.get("edit_decisions", []) if sequence else []
    if len(decisions) == 1:
        return (float(decisions[0].get("sequence_start_ms", 0))
                - float(decisions[0].get("source_start_ms", 0))) / 1000 + source_start
    return source_start
