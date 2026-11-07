"""Bounded discovery and observation helpers; never start work or call AI APIs."""

from __future__ import annotations

import hashlib
import json

COMMAND_AREAS = {
    "translation": {"translation_models"},
    "projects": {"projects", "project", "open", "create", "rename", "prepare_delete", "delete"},
    "sources": {"import_video", "replace_source", "replace_url_inspect", "replace_url_start",
                "import_url_inspect", "import_url_start", "import_url_cancel"},
    "processing": {"run", "pause", "resume", "auto_start", "prepare_restart", "restart", "manual_cancel"},
    "subtitles": {"subtitles", "srt", "import_srt", "remove_srt", "export_srt", "edit_subtitle",
                  "subtitle_timing", "merge_subtitle", "delete_subtitle", "split_subtitle", "subtitle_replace",
                  "review", "review_save", "review_approve", "translation_context", "translation_patch",
                  "subtitle_fonts"},
    "editor": {"editor", "undo", "redo", "clip_properties", "track_properties", "source_cover", "text_style",
               "clip_trim", "clip_move", "clip_remove", "result_split", "background_music", "background_music_clear",
               "watermark_asset", "visual_context", "subtitle_layout_apply"},
    "voice": {"voice_reference", "voice_reference_clear", "voice_configuration", "voice_run"},
}


def command_area(name: str) -> str:
    for area, commands in COMMAND_AREAS.items():
        if name in commands:
            return area
    for prefix, area in (("batch_", "batch"), ("export", "exports"), ("channel_", "downloads"),
                         ("download_", "downloads"), ("social_", "social"), ("resource", "resources")):
        if name.startswith(prefix):
            return area
    if name in {"publish", "prepare_publish"}:
        return "social"
    return "system"


def encoded_size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def observed(value: dict, since: str = "") -> dict:
    """Content-addressed status: never substitute a cached state for a live read."""
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    cursor = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if since == cursor:
        return {"cursor": cursor, "changed": False}
    return {"cursor": cursor, "changed": True, **value}


def unsettled(value: dict) -> bool:
    return bool(value.get("queued_video_ids") or value.get("active_video_id")
                or any(job.get("busy") for job in value.get("auxiliary", {}).values())
                or value.get("import_busy") or value.get("url_import_busy")
                or any(row.get("status") in {"pending", "rendering", "exporting"}
                       for row in value.get("exports", []))
                or any(row.get("status") == "processing"
                       for row in value.get("videos", [])))
