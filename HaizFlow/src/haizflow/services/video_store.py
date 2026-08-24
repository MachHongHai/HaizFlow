import json
import hashlib
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import List, Optional

from haizflow.config import LEGACY_VIDEO_WORKSPACES_DIR
from haizflow.core.events import emit_log
from haizflow.schemas.video import (
    VIDEO_METADATA_SCHEMA_VERSION,
    VIDEO_METADATA_TYPE,
    VideoConfig,
    VideoInfo,
    MediaSource,
    CropSettings,
    SubtitleStyle,
)
from haizflow.services import project_store


_VIDEO_LOCKS: dict[str, threading.RLock] = {}
_VIDEO_LOCKS_GUARD = threading.Lock()
_VIDEO_DIR_CACHE: dict[str, str] = {}
_VIDEO_METADATA_CACHE: dict[str, tuple[VideoInfo, tuple[str, int, int]]] = {}
_METADATA_REVISION = 0
_METADATA_REVISION_LOCK = threading.Lock()
_METADATA_CHANGES: deque[tuple[int, str]] = deque(maxlen=4_096)
_LEGACY_METADATA_NAME = "job.json"

_LOG_COMPONENTS = {
    "audio_separation": "DEMUCS",
    "audio_timeline": "AUDIO",
    "extract_audio": "FFMPEG",
    "process_video": "PIPELINE",
    "render": "RENDER",
    "subtitle": "SUBTITLES",
    "subtitle_ocr": "OCR",
    "transcribe": "WHISPERX",
    "translation": "TRANSLATE",
}


def _video_lock(video_id: str) -> threading.RLock:
    with _VIDEO_LOCKS_GUARD:
        lock = _VIDEO_LOCKS.get(video_id)
        if lock is None:
            lock = threading.RLock()
            _VIDEO_LOCKS[video_id] = lock
        return lock


def _mark_metadata_changed(video_id: str) -> None:
    global _METADATA_REVISION
    with _METADATA_REVISION_LOCK:
        _METADATA_REVISION += 1
        _METADATA_CHANGES.append((_METADATA_REVISION, video_id))


def _copy_video(video: VideoInfo) -> VideoInfo:
    """Return a detached metadata snapshot without re-reading video.json."""
    if hasattr(video, "model_copy"):
        return video.model_copy(deep=True)
    return video.copy(deep=True)


def _metadata_signature(path: str) -> tuple[str, int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return os.path.abspath(path), stat.st_mtime_ns, stat.st_size


def _cache_video(video: VideoInfo) -> None:
    path = _existing_video_json_path(video.video_id)
    signature = _metadata_signature(path)
    if signature is not None:
        _VIDEO_METADATA_CACHE[video.video_id] = (_copy_video(video), signature)


def metadata_revision() -> int:
    """Return the in-process revision for project/video metadata writes."""
    with _METADATA_REVISION_LOCK:
        return _METADATA_REVISION


def metadata_changes_since(revision: int) -> tuple[int, set[str]] | None:
    """Return changed video IDs, or None when a full catalog refresh is needed."""
    with _METADATA_REVISION_LOCK:
        current = _METADATA_REVISION
        if revision >= current:
            return current, set()
        if not _METADATA_CHANGES or revision < _METADATA_CHANGES[0][0] - 1:
            return None
        return current, {video_id for change, video_id in _METADATA_CHANGES if change > revision}


def _legacy_video_dir(video_id: str) -> str:
    return os.path.join(LEGACY_VIDEO_WORKSPACES_DIR, video_id)


def _workspace_label(original_filename: str) -> str:
    stem = os.path.splitext(os.path.basename(original_filename))[0]
    cleaned = "".join(
        character if character.isalnum() or character in {"-", "_", " "} else "_"
        for character in stem
    ).strip(" .")
    return (cleaned or "video")[:48].rstrip(" .") or "video"


def _compact_video_workspace_name(video_id: str, original_filename: str) -> str:
    """Keep workspaces recognizable without exposing a full UUID in the path."""
    compact_id = hashlib.sha256(video_id.encode("utf-8")).hexdigest()[:10]
    return f"{_workspace_label(original_filename)}--{compact_id}"


def _project_video_dir(video_id: str, config: VideoConfig, original_filename: str = "") -> str:
    if config.project_name.strip() and config.project_directory.strip():
        videos_dir = (
            project_store.project_videos_dir_for_key(config.project_key)
            if config.project_key
            else project_store.project_videos_dir(config.project_name, config.project_directory, config.project_type)
        )
        return os.path.join(
            videos_dir,
            _compact_video_workspace_name(video_id, original_filename),
        )
    return _legacy_video_dir(video_id)


def _workspace_video_id(workspace: str) -> str:
    """Read the stable ID from a workspace, regardless of its folder name."""
    for metadata_name in ("video.json", _LEGACY_METADATA_NAME):
        metadata_path = os.path.join(workspace, metadata_name)
        if not os.path.isfile(metadata_path):
            continue
        try:
            with open(metadata_path, "r", encoding="utf-8") as file:
                value = str(json.load(file).get("video_id") or "").strip()
            if value:
                return value
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            return ""
    return ""


def _find_video_dir(video_id: str) -> str:
    cached = _VIDEO_DIR_CACHE.get(video_id)
    if cached and os.path.isdir(cached):
        return cached
    _VIDEO_DIR_CACHE.pop(video_id, None)

    legacy = _legacy_video_dir(video_id)
    if os.path.isdir(legacy):
        _VIDEO_DIR_CACHE[video_id] = legacy
        return legacy

    for project in project_store.list_projects():
        videos_dir = project_store.project_videos_dir_for_key(project["key"])
        candidate = os.path.join(videos_dir, video_id)
        if os.path.isdir(candidate):
            _VIDEO_DIR_CACHE[video_id] = candidate
            return candidate
        if not os.path.isdir(videos_dir):
            continue
        for name in os.listdir(videos_dir):
            candidate = os.path.join(videos_dir, name)
            if not os.path.isdir(candidate) or name.startswith("."):
                continue
            discovered_id = _workspace_video_id(candidate)
            if discovered_id:
                _VIDEO_DIR_CACHE.setdefault(discovered_id, candidate)
            if discovered_id == video_id:
                return candidate
    return legacy


def get_video_dir(video_id: str) -> str:
    return _find_video_dir(video_id)


def get_video_json_path(video_id: str) -> str:
    return os.path.join(get_video_dir(video_id), "video.json")


def _legacy_video_json_path(video_id: str) -> str:
    return os.path.join(get_video_dir(video_id), _LEGACY_METADATA_NAME)


def _existing_video_json_path(video_id: str) -> str:
    canonical = get_video_json_path(video_id)
    if os.path.isfile(canonical):
        return canonical
    legacy = _legacy_video_json_path(video_id)
    return legacy if os.path.isfile(legacy) else canonical


def _get_video_backup_path(video_id: str) -> str:
    return get_video_json_path(video_id) + ".bak"


def get_video_logs_path(video_id: str) -> str:
    return os.path.join(get_video_dir(video_id), "logs.txt")


def create_video(video_id: str, original_filename: str, config: VideoConfig, video_ext: str = ".mp4") -> VideoInfo:
    video_dir = _project_video_dir(video_id, config, original_filename)
    _VIDEO_DIR_CACHE[video_id] = video_dir
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(os.path.join(video_dir, "input"), exist_ok=True)
    os.makedirs(os.path.join(video_dir, "temp"), exist_ok=True)
    os.makedirs(os.path.join(video_dir, "temp", "voice_parts"), exist_ok=True)
    project_owned = bool(config.project_name and config.project_directory)
    # Modern desktop projects export through <project>/exports. Preserve the
    # per-video output folder only for legacy videos without a project owner.
    if not project_owned:
        os.makedirs(os.path.join(video_dir, "output"), exist_ok=True)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if project_owned:
        export_dir = (
            project_store.project_exports_dir_for_key(config.project_key)
            if config.project_key
            else project_store.project_exports_dir(config.project_name, config.project_directory, config.project_type)
        )
        if config.project_type == "batch":
            safe_stem = "".join(
                character if character.isalnum() or character in {"-", "_", " "} else "_"
                for character in os.path.splitext(original_filename)[0]
            ).strip()
            export_dir = os.path.join(export_dir, f"{safe_stem or 'video'}--{video_id[:8]}")
        os.makedirs(export_dir, exist_ok=True)
        final_video = os.path.join(export_dir, "dubbed_video.mp4")
    else:
        final_video = os.path.join(video_dir, "output", "final.mp4")
    files = {
        "video_input": os.path.join(video_dir, "input", f"video{video_ext}"),
        "final_video": final_video,
        "srt_output": os.path.join(video_dir, "temp", "vi.srt"),
        "voice_output": os.path.join(video_dir, "temp", "voice_final.wav"),
        "transcript_json": os.path.join(video_dir, "temp", "vi_segments.json"),
    }
    video_info = VideoInfo(
        video_id=video_id,
        original_filename=original_filename,
        mode=config.mode,
        source_language=config.source_language,
        target_language=config.target_language,
        translator_provider=config.translator_provider,
        tts_provider=config.tts_provider,
        tts_voice=config.tts_voice,
        speaker_mode=config.speaker_mode,
        subtitle_style=config.subtitle_style,
        subtitle_layout_override=config.subtitle_layout_override,
        remove_original_subtitles=config.remove_original_subtitles,
        original_subtitle_removal_mode=config.original_subtitle_removal_mode,
        output_format=config.output_format,
        crop=config.crop,
        enable_audio_separation=config.enable_audio_separation,
        original_video_volume=config.original_video_volume,
        background_music_volume=config.background_music_volume,
        tts_volume=config.tts_volume,
        watermark_text=config.watermark_text,
        project_name=config.project_name,
        project_directory=config.project_directory,
        project_type=config.project_type,
        project_id=config.project_id,
        project_key=config.project_key,
        review_approved=config.review_approved,
        status="pending",
        progress=0,
        step="pending",
        created_at=now,
        updated_at=now,
        error=None,
        files=files,
    )
    save_video(video_info)
    with open(get_video_logs_path(video_id), "w", encoding="utf-8") as file:
        file.write(f"[{now}] Video created.\n")
    return video_info


def _video_data(video_info: VideoInfo) -> dict:
    data = video_info.model_dump() if hasattr(video_info, "model_dump") else video_info.dict()
    data["schema_version"] = VIDEO_METADATA_SCHEMA_VERSION
    data["metadata_type"] = VIDEO_METADATA_TYPE
    return data


def _write_json_atomic(path: str, data: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(prefix=".video-", suffix=".json.tmp", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.remove(temporary_path)
        except FileNotFoundError:
            pass
        raise


class VideoMetadataError(RuntimeError):
    pass


class UnsupportedVideoSchemaError(VideoMetadataError):
    pass


def _video_schema_version(data: dict) -> int:
    raw_version = data.get("schema_version", 1)
    try:
        version = int(raw_version)
    except (TypeError, ValueError) as exc:
        raise VideoMetadataError(f"Video metadata has an invalid schema version: {raw_version!r}") from exc
    if version < 1:
        raise VideoMetadataError(f"Video metadata has an invalid schema version: {version}")
    if version > VIDEO_METADATA_SCHEMA_VERSION:
        raise UnsupportedVideoSchemaError(
            f"Video metadata uses schema v{version}, newer than supported v{VIDEO_METADATA_SCHEMA_VERSION}."
        )
    return version


def _migrate_video_metadata(raw_data: dict) -> tuple[dict, bool]:
    if not isinstance(raw_data, dict):
        raise VideoMetadataError("Video metadata must contain a JSON object.")
    original = dict(raw_data)
    data = dict(raw_data)
    version = _video_schema_version(data)
    while version < VIDEO_METADATA_SCHEMA_VERSION:
        if version == 1:
            data["schema_version"] = 2
            data["metadata_type"] = VIDEO_METADATA_TYPE
            data["mode"] = data.get("mode") if data.get("mode") in {"A", "review"} else "A"
            data["source_language"] = "auto"
            data["translator_provider"] = "hymt2"
            data["output_format"] = "keep_ratio"
            data["project_type"] = "batch" if data.get("project_type") == "batch" else "single"
            version = 2
            continue
        if version == 2:
            data["schema_version"] = 3
            data["media_source"] = {"type": "local_file"}
            version = 3
            continue
        if version == 3:
            project_name = str(data.get("project_name") or "").strip()
            project_directory = str(data.get("project_directory") or "").strip()
            project_type = "batch" if data.get("project_type") == "batch" else "single"
            key = project_store.resolve_project_key(project_name, project_directory, project_type)
            record = project_store.get_project(key) if key else None
            data["schema_version"] = 4
            data["project_key"] = key
            data["project_id"] = str((record or {}).get("project_id") or "")
            version = 4
            continue
        if version == 4:
            legacy_id = str(data.pop("job_id", "") or "").strip()
            if not str(data.get("video_id") or "").strip():
                data["video_id"] = legacy_id
            data["schema_version"] = 5
            version = 5
            continue
        if version == 5:
            data["schema_version"] = 6
            data.setdefault("background_music_volume", 30)
            data.setdefault("tts_volume", 100)
            version = 6
            continue
        if version == 6:
            data["schema_version"] = 7
            data.setdefault("watermark_text", "")
            version = 7
            continue
        if version == 7:
            data["schema_version"] = 8
            # Legacy batch videos are assigned a durable order when the user
            # next adds to that batch.  Until then, their creation time is the
            # stable compatibility fallback used by the presenter.
            data.setdefault("batch_import_order", 0)
            version = 8
            continue
        if version == 8:
            data["schema_version"] = 9
            data.setdefault("remove_original_subtitles", True)
            data.setdefault("subtitle_layout_override", False)
            version = 9
            continue
        if version == 9:
            data["schema_version"] = 10
            elapsed = 0.0
            started_at = data.get("started_at")
            # Older metadata only stored the beginning of the latest session.
            # Preserve that visible duration when upgrading a stopped video.
            if started_at and data.get("status") != "processing":
                try:
                    started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
                    finished = datetime.fromisoformat(str(data.get("updated_at") or started_at).replace("Z", "+00:00"))
                    elapsed = max(0.0, (finished - started).total_seconds())
                    data["started_at"] = None
                except (TypeError, ValueError):
                    pass
            data.setdefault("processing_elapsed_seconds", elapsed)
            version = 10
            continue
        if version == 10:
            data["schema_version"] = 11
            # Existing projects keep the established blur treatment.  The
            # edge-filled mode is opt-in so an upgrade cannot change exports.
            data.setdefault("original_subtitle_removal_mode", "blur")
            version = 11
            continue
        if version == 11:
            data["schema_version"] = 12
            # Preserve the output of existing projects. New projects use the
            # recommended automatic provider, while previously saved voices
            # remain explicitly tied to Edge TTS.
            data.setdefault("tts_provider", "edge")
            version = 12
            continue
        if version == 12:
            data["schema_version"] = 13
            data.setdefault("speech_recognition_model", "small")
            # VieNeu and the old automatic alias were removed in favour of
            # OmniVoice. Explicit Edge projects retain their online voice.
            if data.get("tts_provider") in {"auto", "vieneu", None, ""}:
                data["tts_provider"] = "omnivoice"
            version = 13
            continue
        if version == 13:
            data["schema_version"] = 14
            # Existing videos historically behaved as single-narrator jobs.
            # Preserve that intent instead of unexpectedly cloning every
            # source segment after an upgrade.
            data.setdefault("speaker_mode", "single")
            version = 14
            continue
        raise VideoMetadataError(f"No video metadata migration is available from schema v{version}.")
    data["schema_version"] = VIDEO_METADATA_SCHEMA_VERSION
    data["metadata_type"] = VIDEO_METADATA_TYPE
    # Canonicalize fields even for an already-current schema. Older builds
    # could write legacy provider/layout values without bumping the schema;
    # strict production models must remain able to open and repair them.
    data["mode"] = data.get("mode") if data.get("mode") in {"A", "review"} else "A"
    data["translator_provider"] = "hymt2"
    if data.get("tts_provider") in {"auto", "vieneu"}:
        data["tts_provider"] = "omnivoice"
    if data.get("tts_provider") not in {"omnivoice", "edge"}:
        data["tts_provider"] = "omnivoice"
    if data.get("speech_recognition_model") not in {"small", "large-v3-turbo"}:
        data["speech_recognition_model"] = "small"
    if data.get("speaker_mode") not in {"single", "multiple"}:
        data["speaker_mode"] = "single"
    data["output_format"] = (
        data.get("output_format")
        if data.get("output_format")
        in {
            "keep_ratio",
            "tiktok_9_16_crop",
            "blur_background_9_16",
        }
        else "keep_ratio"
    )
    data["project_type"] = "batch" if data.get("project_type") == "batch" else "single"
    try:
        batch_import_order = int(data.get("batch_import_order", 0))
    except (TypeError, ValueError):
        batch_import_order = 0
    data["batch_import_order"] = max(0, batch_import_order)
    style_defaults = SubtitleStyle().model_dump()
    style_value = data.get("subtitle_style")
    style_source = style_value if isinstance(style_value, dict) else {}
    style_limits = {
        "font_size": (10, 160),
        "margin_bottom": (0, 1000),
        "outline": (0, 20),
        "max_chars_per_line": (12, 200),
        "position_x_percent": (0, 100),
        "position_y_percent": (0, 100),
        "box_width_percent": (20, 100),
        "box_height_percent": (1, 100),
    }
    for key, (minimum, maximum) in style_limits.items():
        try:
            value = int(style_source.get(key, style_defaults[key]))
        except (TypeError, ValueError):
            value = style_defaults[key]
        style_defaults[key] = max(minimum, min(maximum, value))
    data["subtitle_style"] = style_defaults
    data["subtitle_layout_override"] = bool(data.get("subtitle_layout_override", False))
    data["remove_original_subtitles"] = bool(data.get("remove_original_subtitles", True))
    removal_mode = data.get("original_subtitle_removal_mode")
    # Early development builds called the neighbouring-picture patch
    # "inpaint". Preserve those projects while using the accurate production
    # name from schema v11 onward.
    if removal_mode == "inpaint":
        removal_mode = "patch"
    data["original_subtitle_removal_mode"] = removal_mode if removal_mode in {"blur", "patch"} else "patch"
    try:
        processing_elapsed = float(data.get("processing_elapsed_seconds", 0.0))
    except (TypeError, ValueError):
        processing_elapsed = 0.0
    data["processing_elapsed_seconds"] = max(0.0, processing_elapsed)

    crop_defaults = CropSettings().model_dump()
    crop_value = data.get("crop")
    crop_source = crop_value if isinstance(crop_value, dict) else {}
    crop_limits = {
        "zoom_percent": (1, 400),
        "pan_x_percent": (-100, 100),
        "pan_y_percent": (-100, 100),
        "left_percent": (0, 84),
        "right_percent": (0, 84),
        "top_percent": (0, 84),
        "bottom_percent": (0, 84),
    }
    for key, (minimum, maximum) in crop_limits.items():
        try:
            value = int(crop_source.get(key, crop_defaults[key]))
        except (TypeError, ValueError):
            value = crop_defaults[key]
        crop_defaults[key] = max(minimum, min(maximum, value))
    data["crop"] = crop_defaults
    try:
        volume = int(data.get("original_video_volume", 60))
    except (TypeError, ValueError):
        volume = 60
    data["original_video_volume"] = max(0, min(100, volume))
    for key, default in (("background_music_volume", 30), ("tts_volume", 100)):
        try:
            volume = int(data.get(key, default))
        except (TypeError, ValueError):
            volume = default
        data[key] = max(0, min(100, volume))
    watermark_value = data.get("watermark_text", "")
    if not isinstance(watermark_value, str):
        watermark_value = ""
    # Watermarks are always a single, bounded line. This also prevents control
    # characters from entering the FFmpeg filter expression.
    data["watermark_text"] = " ".join(watermark_value.split())[:80]
    return data, data != original


def _write_video_migration_backup(path: str, raw_data: dict) -> None:
    backup_path = f"{path}.schema-migration.bak"
    if not os.path.exists(backup_path):
        _write_json_atomic(backup_path, raw_data)


def _load_video_metadata(path: str, *, persist_migration: bool = True) -> VideoInfo:
    with open(path, "r", encoding="utf-8") as file:
        raw_data = json.load(file)
    migrated_data, migrated = _migrate_video_metadata(raw_data)
    video = VideoInfo(**migrated_data)
    if migrated and persist_migration:
        _write_video_migration_backup(path, raw_data)
        _write_json_atomic(path, _video_data(video))
    return video


def _save_video_unlocked(video_info: VideoInfo) -> None:
    path = get_video_json_path(video_info.video_id)
    backup_path = _get_video_backup_path(video_info.video_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as file:
                previous_data = json.load(file)
            _write_json_atomic(backup_path, previous_data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
    _write_json_atomic(path, _video_data(video_info))
    _cache_video(video_info)
    _mark_metadata_changed(video_info.video_id)


def save_video(video_info: VideoInfo):
    with _video_lock(video_info.video_id):
        _save_video_unlocked(video_info)


def _get_video_unlocked(video_id: str) -> Optional[VideoInfo]:
    cached = _VIDEO_METADATA_CACHE.get(video_id)
    path = _existing_video_json_path(video_id)
    if cached is not None and cached[1] == _metadata_signature(path):
        return _copy_video(cached[0])
    if not os.path.exists(path):
        _VIDEO_METADATA_CACHE.pop(video_id, None)
        return None
    try:
        legacy_path = os.path.basename(path).lower() == _LEGACY_METADATA_NAME
        video = _load_video_metadata(path, persist_migration=not legacy_path)
        if legacy_path:
            canonical = get_video_json_path(video_id)
            _write_json_atomic(canonical, _video_data(video))
            legacy_backup = f"{path}.legacy.bak"
            if not os.path.exists(legacy_backup):
                shutil.copy2(path, legacy_backup)
        _cache_video(video)
        return _copy_video(video)
    except UnsupportedVideoSchemaError as exc:
        raise RuntimeError(f"Video metadata was created by a newer application version: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError) as original_error:
        backup_path = _get_video_backup_path(video_id)
        if not os.path.exists(backup_path) and path != get_video_json_path(video_id):
            backup_path = f"{path}.bak"
        if not os.path.exists(backup_path):
            raise RuntimeError(f"Video metadata is unreadable: {path}") from original_error
        try:
            recovered = _load_video_metadata(backup_path, persist_migration=False)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError) as backup_error:
            raise RuntimeError(f"Video metadata and backup are unreadable: {path}") from backup_error
        _write_json_atomic(path, _video_data(recovered))
        log_to_video(video_id, "Recovered video metadata from the last atomic backup.")
        _cache_video(recovered)
        return _copy_video(recovered)


def get_video(video_id: str) -> Optional[VideoInfo]:
    with _video_lock(video_id):
        return _get_video_unlocked(video_id)


def update_video(video_id: str, **kwargs) -> Optional[VideoInfo]:
    with _video_lock(video_id):
        video_info = _get_video_unlocked(video_id)
        if not video_info:
            return None
        now = datetime.now(timezone.utc)
        requested_status = kwargs.get("status", video_info.status)
        if video_info.status == "processing" and requested_status != "processing":
            # Close exactly one active run session. Repeated pause/failure
            # updates see a non-processing status and cannot double-count it.
            if "processing_elapsed_seconds" not in kwargs and video_info.started_at:
                try:
                    started = datetime.fromisoformat(video_info.started_at.replace("Z", "+00:00"))
                    previous = max(0.0, float(video_info.processing_elapsed_seconds or 0.0))
                    kwargs["processing_elapsed_seconds"] = previous + max(0.0, (now - started).total_seconds())
                except (TypeError, ValueError):
                    pass
            kwargs.setdefault("started_at", None)
        for key, value in kwargs.items():
            if hasattr(video_info, key):
                setattr(video_info, key, value)
        video_info.updated_at = now.isoformat().replace("+00:00", "Z")
        _save_video_unlocked(video_info)
        return video_info


def _is_inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:
        return False


def replace_video_input(
    video_id: str,
    source_path: str,
    media_source: MediaSource | dict | None = None,
) -> Optional[VideoInfo]:
    """Replace a completed/pending video's source and discard its old artifacts."""
    source_path = os.path.abspath(source_path)
    with _video_lock(video_id):
        video = _get_video_unlocked(video_id)
        if not video:
            return None
        if video.status == "processing":
            raise RuntimeError("Cannot replace a video while it is processing.")

        video_dir = get_video_dir(video_id)
        extension = os.path.splitext(source_path)[1].lower() or ".mp4"
        input_path = os.path.join(video_dir, "input", f"video{extension}")
        if os.path.normcase(source_path) == os.path.normcase(os.path.abspath(input_path)):
            return video

        final_video = (video.files or {}).get("final_video") or ""
        previous_thumbnail = (video.files or {}).get("thumbnail") or ""
        project_root = (
            project_store.project_root_for_key(video.project_key)
            if video.project_key
            else project_store.project_root(video.project_name, video.project_directory, video.project_type)
            if video.project_name and video.project_directory
            else video_dir
        )

        transaction_directory = tempfile.mkdtemp(prefix=".replace-input-", dir=video_dir)
        staged_input_directory = os.path.join(transaction_directory, "new-input")
        staged_input_path = os.path.join(staged_input_directory, f"video{extension}")
        backup_input_directory = os.path.join(transaction_directory, "old-input")
        metadata_snapshot_path = os.path.join(transaction_directory, "video.json")
        input_directory = os.path.join(video_dir, "input")
        os.makedirs(staged_input_directory, exist_ok=True)
        input_backed_up = False
        new_input_published = False
        try:
            shutil.copy2(get_video_json_path(video_id), metadata_snapshot_path)
            shutil.copy2(source_path, staged_input_path)
            if os.path.getsize(staged_input_path) <= 0:
                raise RuntimeError(f"Replacement video is empty: {source_path}")

            if os.path.isdir(input_directory):
                os.replace(input_directory, backup_input_directory)
                input_backed_up = True
            os.replace(staged_input_directory, input_directory)
            new_input_published = True

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            video.files["video_input"] = input_path
            video.files["srt_output"] = os.path.join(video_dir, "temp", "vi.srt")
            video.files["voice_output"] = os.path.join(video_dir, "temp", "voice_final.wav")
            video.files["transcript_json"] = os.path.join(video_dir, "temp", "vi_segments.json")
            video.files["thumbnail"] = os.path.join(video_dir, "thumbnail.jpg")
            video.original_filename = os.path.basename(source_path)
            video.media_source = MediaSource.model_validate(media_source or {"type": "local_file"})
            video.video_width = 0
            video.video_height = 0
            video.review_approved = False
            video.status = "pending"
            video.progress = 0
            video.step = "pending"
            video.resume_step = ""
            video.runtime_recovery_step = ""
            video.gpu_recovery_attempted = False
            video.checkpoints = {}
            video.started_at = None
            video.processing_elapsed_seconds = 0.0
            video.estimated_remaining_seconds = None
            video.step_detail = "New source video imported"
            video.current_item = 0
            video.total_items = 0
            video.error = None
            video.created_at = now
            video.updated_at = now
            _save_video_unlocked(video)
        except Exception:
            if new_input_published and os.path.isdir(input_directory):
                shutil.rmtree(input_directory, onerror=_force_remove_readonly)
            if input_backed_up and os.path.isdir(backup_input_directory):
                os.replace(backup_input_directory, input_directory)
            if os.path.isfile(metadata_snapshot_path):
                os.replace(metadata_snapshot_path, get_video_json_path(video_id))
            _VIDEO_METADATA_CACHE.pop(video_id, None)
            raise
        finally:
            shutil.rmtree(transaction_directory, ignore_errors=True)

        cleanup_errors: list[str] = []
        temp_directory = os.path.join(video_dir, "temp")
        try:
            if os.path.isdir(temp_directory):
                shutil.rmtree(temp_directory, onerror=_force_remove_readonly)
            os.makedirs(os.path.join(temp_directory, "voice_parts"), exist_ok=True)
        except OSError as exc:
            cleanup_errors.append(f"temporary workspace: {exc}")

        legacy_output_dir = os.path.join(video_dir, "output")
        try:
            if os.path.isdir(legacy_output_dir):
                shutil.rmtree(legacy_output_dir, onerror=_force_remove_readonly)
        except OSError as exc:
            cleanup_errors.append(f"legacy output: {exc}")

        try:
            if final_video and _is_inside(final_video, project_root) and os.path.isfile(final_video):
                os.remove(final_video)
        except OSError as exc:
            cleanup_errors.append(f"previous export: {exc}")
        thumbnail_candidates = {
            previous_thumbnail,
            os.path.join(video_dir, "thumbnail.jpg"),
        }
        for thumbnail_path in thumbnail_candidates:
            try:
                if thumbnail_path and _is_inside(thumbnail_path, video_dir) and os.path.isfile(thumbnail_path):
                    os.remove(thumbnail_path)
            except OSError as exc:
                cleanup_errors.append(f"thumbnail: {exc}")

        try:
            os.remove(_get_video_backup_path(video_id))
        except FileNotFoundError:
            pass
        with open(get_video_logs_path(video_id), "w", encoding="utf-8") as file:
            file.write(f"[{now}] Input video replaced. Previous processing data was removed.\n")
            for cleanup_error in cleanup_errors:
                file.write(
                    f"[{now}] Old artifact cleanup was deferred ({cleanup_error}). "
                    "It will not be reused because all processing checkpoints were cleared.\n"
                )
        return video


def remove_empty_legacy_output_dir(video_id: str) -> bool:
    """Remove an obsolete per-video output folder only when it is empty."""
    output_dir = os.path.join(get_video_dir(video_id), "output")
    try:
        if not os.path.isdir(output_dir) or any(os.scandir(output_dir)):
            return False
        os.rmdir(output_dir)
        return True
    except OSError:
        return False


def prepare_video_restart(video_id: str) -> Optional[VideoInfo]:
    """Discard generated artifacts so a restart always runs from the source video."""
    with _video_lock(video_id):
        video = _get_video_unlocked(video_id)
        if not video:
            return None
        if video.status == "processing":
            raise RuntimeError("Cannot restart a video while it is processing.")

        video_dir = get_video_dir(video_id)
        temp_dir = os.path.join(video_dir, "temp")
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, onerror=_force_remove_readonly)
        os.makedirs(os.path.join(temp_dir, "voice_parts"), exist_ok=True)

        final_video = (video.files or {}).get("final_video") or ""
        project_root = (
            project_store.project_root_for_key(video.project_key)
            if video.project_key
            else project_store.project_root(video.project_name, video.project_directory, video.project_type)
            if video.project_name and video.project_directory
            else video_dir
        )
        if final_video and (_is_inside(final_video, project_root) or _is_inside(final_video, video_dir)):
            try:
                os.remove(final_video)
            except FileNotFoundError:
                pass

        legacy_output_dir = os.path.join(video_dir, "output")
        if _is_inside(final_video, legacy_output_dir):
            os.makedirs(legacy_output_dir, exist_ok=True)

        video.files["srt_output"] = os.path.join(temp_dir, "vi.srt")
        video.files["voice_output"] = os.path.join(temp_dir, "voice_final.wav")
        video.files["transcript_json"] = os.path.join(temp_dir, "vi_segments.json")
        video.review_approved = False
        video.status = "pending"
        video.progress = 0
        video.step = "queued"
        video.resume_step = ""
        video.runtime_recovery_step = ""
        video.gpu_recovery_attempted = False
        video.checkpoints = {}
        video.started_at = None
        video.processing_elapsed_seconds = 0.0
        video.estimated_remaining_seconds = None
        video.step_detail = "Queued to restart"
        video.current_item = 0
        video.total_items = 0
        video.error = None
        video.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _save_video_unlocked(video)
        log_to_video(video_id, "Restart prepared. Generated files and checkpoints were cleared.")
        return video


def _project_video_ids() -> list[str]:
    video_ids: list[str] = []
    for project in project_store.list_projects():
        videos_dir = project_store.project_videos_dir_for_key(project["key"])
        if not os.path.isdir(videos_dir):
            continue
        for name in os.listdir(videos_dir):
            workspace = os.path.join(videos_dir, name)
            if not os.path.isdir(workspace) or name.startswith("."):
                continue
            video_id = _workspace_video_id(workspace)
            if not video_id:
                continue
            _VIDEO_DIR_CACHE[video_id] = workspace
            video_ids.append(video_id)
    return video_ids


def list_videos() -> List[VideoInfo]:
    videos = []
    seen = set()
    for video_id in _project_video_ids():
        video_info = get_video(video_id)
        if video_info:
            videos.append(video_info)
            seen.add(video_id)
    if os.path.isdir(LEGACY_VIDEO_WORKSPACES_DIR):
        for video_id in os.listdir(LEGACY_VIDEO_WORKSPACES_DIR):
            if video_id in seen or not os.path.isdir(_legacy_video_dir(video_id)):
                continue
            video_info = get_video(video_id)
            if video_info:
                videos.append(video_info)
    videos.sort(key=lambda item: item.created_at, reverse=True)
    return videos


def recover_interrupted_videos() -> list[str]:
    """Turn stale in-progress metadata into resumable paused videos at startup."""
    recovered: list[str] = []
    for video in list_videos():
        if video.status != "processing":
            continue
        interrupted_step = video.resume_step or video.step or "processing"
        if interrupted_step == "paused":
            interrupted_step = "processing"
        elapsed = max(0.0, float(video.processing_elapsed_seconds or 0.0))
        if video.started_at:
            try:
                started = datetime.fromisoformat(video.started_at.replace("Z", "+00:00"))
                last_activity = datetime.fromisoformat(video.updated_at.replace("Z", "+00:00"))
                elapsed += max(0.0, (last_activity - started).total_seconds())
            except (TypeError, ValueError):
                pass
        updated = update_video(
            video.video_id,
            status="paused",
            error=None,
            step="paused",
            resume_step=interrupted_step,
            step_detail=f"Recovered after an interrupted exit during {interrupted_step}",
            processing_elapsed_seconds=elapsed,
            started_at=None,
            estimated_remaining_seconds=None,
        )
        if not updated:
            continue
        recovered.append(video.video_id)
        log_to_video(
            video.video_id,
            f"Recovered an interrupted application exit. Resume will continue from {interrupted_step}.",
        )
    return recovered


def _log_component_from_caller() -> str:
    """Return a concise component tag without requiring every call site to repeat it."""
    try:
        module = sys._getframe(2).f_globals.get("__name__", "")
    except (AttributeError, ValueError):  # pragma: no cover - defensive only
        return "APP"
    return _LOG_COMPONENTS.get(module.rsplit(".", 1)[-1], "APP")


def _infer_log_level(message: str, level: str | None) -> str:
    if level:
        normalized = str(level).upper()
        return normalized if normalized in {"DEBUG", "INFO", "WARN", "ERROR"} else "INFO"
    normalized = message.casefold()
    if any(
        marker in normalized
        for marker in (
            "traceback",
            " failed",
            "failure",
            " error",
            "exception",
            "cannot ",
            "unable to ",
        )
    ):
        return "ERROR"
    if any(
        marker in normalized
        for marker in (
            "retry",
            "fallback",
            "deferred",
            "could not",
            "skipping",
            "paused",
            "cancelled",
        )
    ):
        return "WARN"
    return "INFO"


def log_to_video(video_id: str, message: str, *, level: str | None = None, component: str | None = None):
    """Append a compact, structured activity entry to one video's debug log.

    Existing callers can keep passing a plain message.  Severity and component
    are inferred centrally so the log remains consistent across the pipeline.
    Multiline failures are written as individually timestamped entries: this
    keeps stack traces readable in both the compact UI tail and exported logs.
    """
    log_path = get_video_logs_path(video_id)
    if not os.path.exists(_existing_video_json_path(video_id)) and not os.path.exists(log_path):
        return
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    text = str(message or "").strip() or "(empty log message)"
    severity = _infer_log_level(text, level)
    source = (component or _log_component_from_caller()).upper().replace(" ", "_")
    source = source if source.replace("_", "").isalnum() else "APP"
    lines = [f"[{now}] [{severity}] [{source}] {entry}" for entry in text.splitlines() or [text]]
    with _video_lock(video_id):
        with open(log_path, "a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
    for line in lines:
        emit_log(video_id, line)


def _force_remove_readonly(func, path, _exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _remove_tree_verified(path: str) -> None:
    """Remove a tree and fail if Windows left any locked content behind."""
    if not os.path.exists(path):
        return
    shutil.rmtree(path, onerror=_force_remove_readonly)
    if os.path.exists(path):
        raise OSError(f"Directory is still in use: {path}")


_BATCH_EXPORT_DIRECTORY_PATTERN = re.compile(r".+-[0-9a-f]{8}$", re.IGNORECASE)
_VIDEO_WORKSPACE_PATTERN = re.compile(
    r"(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|.+--[0-9a-f]{10})",
    re.IGNORECASE,
)


def delete_video(video_id: str, attempts: int = 8, delay_seconds: float = 0.35) -> bool:
    with _video_lock(video_id):
        video_dir = get_video_dir(video_id)
        if not os.path.exists(video_dir):
            _VIDEO_DIR_CACHE.pop(video_id, None)
            _VIDEO_METADATA_CACHE.pop(video_id, None)
            return False
        video = _get_video_unlocked(video_id)
        # Batch exports live beside, rather than inside, the video workspace.
        # Delete that app-owned directory here so every deletion entry point
        # (card menu, project deletion, failed import rollback) has identical
        # cleanup semantics.
        batch_export_directory = ""
        if video and video.project_type == "batch" and video.project_key:
            final_video = str((video.files or {}).get("final_video") or "")
            if final_video:
                export_directory = os.path.abspath(os.path.dirname(final_video))
                exports_root = os.path.abspath(project_store.project_exports_dir_for_key(video.project_key))
                if (
                    export_directory != exports_root
                    and _is_inside(export_directory, exports_root)
                    and _BATCH_EXPORT_DIRECTORY_PATTERN.fullmatch(os.path.basename(export_directory))
                    and os.path.isdir(export_directory)
                ):
                    batch_export_directory = export_directory
        last_error = None
        for attempt in range(attempts):
            try:
                if batch_export_directory:
                    _remove_tree_verified(batch_export_directory)
                _remove_tree_verified(video_dir)
                _VIDEO_DIR_CACHE.pop(video_id, None)
                _VIDEO_METADATA_CACHE.pop(video_id, None)
                _mark_metadata_changed(video_id)
                return True
            except Exception as exc:
                last_error = exc
                time.sleep(delay_seconds * (attempt + 1))
        if os.path.exists(video_dir):
            raise RuntimeError(f"Could not delete video data after {attempts} attempts: {last_error}")
        _VIDEO_DIR_CACHE.pop(video_id, None)
        _VIDEO_METADATA_CACHE.pop(video_id, None)
        _mark_metadata_changed(video_id)
        return True


def cleanup_batch_project_orphans(project_key_value: str) -> list[str]:
    """Remove app-owned batch workspaces/exports that no video references.

    Batch exports live outside each video workspace so deleting only
    ``videos/<id>`` used to leave a second output folder behind.  Restrict the
    sweep to UUID workspaces and HaizFlow-owned export folders (legacy
    ``<label>-<short-id>`` or compact ``<label>--<short-id>``); arbitrary user
    folders in the project root are never touched.
    """
    project = project_store.get_project(project_key_value)
    if not project or project_store.normalize_project_type(project.get("project_type")) != "batch":
        return []

    videos_root = os.path.abspath(project_store.project_videos_dir_for_key(project_key_value))
    exports_root = os.path.abspath(project_store.project_exports_dir_for_key(project_key_value))
    referenced_export_directories: set[str] = set()
    removed: list[str] = []

    if os.path.isdir(videos_root):
        for name in tuple(os.listdir(videos_root)):
            workspace = os.path.abspath(os.path.join(videos_root, name))
            if not os.path.isdir(workspace) or name.startswith("."):
                continue
            workspace_video_id = _workspace_video_id(workspace)
            video = get_video(workspace_video_id) if workspace_video_id else None
            belongs_to_project = bool(
                video
                and video.project_type == "batch"
                and (
                    video.project_key == project_key_value
                    or (
                        not video.project_key
                        and video.project_name == project.get("project_name")
                        and os.path.abspath(video.project_directory or "")
                        == os.path.abspath(str(project.get("project_directory") or ""))
                    )
                )
            )
            if belongs_to_project:
                final_video = str((video.files or {}).get("final_video") or "")
                if final_video:
                    output_directory = os.path.abspath(os.path.dirname(final_video))
                    if output_directory != exports_root and _is_inside(output_directory, exports_root):
                        referenced_export_directories.add(os.path.normcase(output_directory))
                continue
            if not _VIDEO_WORKSPACE_PATTERN.fullmatch(name):
                continue
            _remove_tree_verified(workspace)
            if workspace_video_id:
                _VIDEO_DIR_CACHE.pop(workspace_video_id, None)
                _VIDEO_METADATA_CACHE.pop(workspace_video_id, None)
                _mark_metadata_changed(workspace_video_id)
            removed.append(workspace)

    if os.path.isdir(exports_root):
        for name in tuple(os.listdir(exports_root)):
            export_directory = os.path.abspath(os.path.join(exports_root, name))
            if not os.path.isdir(export_directory):
                continue
            if os.path.normcase(export_directory) in referenced_export_directories:
                continue
            if not _BATCH_EXPORT_DIRECTORY_PATTERN.fullmatch(name):
                continue
            _remove_tree_verified(export_directory)
            removed.append(export_directory)

    return removed


def migrate_legacy_project_data() -> list[str]:
    """Move old global video workspaces into their registered project folders."""
    if not os.path.isdir(LEGACY_VIDEO_WORKSPACES_DIR):
        return []
    registered = {record["key"]: record for record in project_store.list_projects()}
    migrated = []
    for video_id in os.listdir(LEGACY_VIDEO_WORKSPACES_DIR):
        source = _legacy_video_dir(video_id)
        metadata_path = os.path.join(source, "video.json")
        if not os.path.isfile(metadata_path):
            metadata_path = os.path.join(source, _LEGACY_METADATA_NAME)
        if not os.path.isdir(source) or not os.path.isfile(metadata_path):
            continue
        try:
            video = _load_video_metadata(metadata_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError):
            continue
        if not video.project_name or not video.project_directory:
            continue
        key = video.project_key or project_store.resolve_project_key(
            video.project_name,
            video.project_directory,
            video.project_type,
        )
        record = registered.get(key)
        if not record:
            continue
        destination = os.path.join(
            project_store.project_videos_dir_for_key(key),
            video_id,
        )
        if os.path.exists(destination):
            # A previous cross-volume migration may have published the complete
            # destination before the old copy could be removed.
            destination_metadata = os.path.join(destination, "video.json")
            try:
                migrated_video = _load_video_metadata(
                    destination_metadata,
                    persist_migration=False,
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, VideoMetadataError):
                continue
            if migrated_video.video_id == video_id:
                shutil.rmtree(source, onerror=_force_remove_readonly)
                _VIDEO_DIR_CACHE[video_id] = destination
                _cache_video(migrated_video)
                migrated.append(video_id)
            continue

        destination_parent = os.path.dirname(destination)
        os.makedirs(destination_parent, exist_ok=True)
        staging = os.path.join(destination_parent, f".{video_id}.migrating")
        if os.path.isdir(staging):
            shutil.rmtree(staging, onerror=_force_remove_readonly)

        video.project_key = key
        video.project_id = str(record.get("project_id") or "")
        for file_key, file_path in (video.files or {}).items():
            if not file_path:
                continue
            try:
                if os.path.commonpath([os.path.abspath(source), os.path.abspath(file_path)]) == os.path.abspath(source):
                    video.files[file_key] = os.path.join(destination, os.path.relpath(file_path, source))
            except ValueError:
                continue
        for checkpoint_key, checkpoint_path in (video.checkpoints or {}).items():
            try:
                if os.path.commonpath([os.path.abspath(source), os.path.abspath(checkpoint_path)]) == os.path.abspath(
                    source
                ):
                    video.checkpoints[checkpoint_key] = os.path.join(
                        destination, os.path.relpath(checkpoint_path, source)
                    )
            except (TypeError, ValueError):
                continue

        try:
            # Copy first and publish with one directory rename. The legacy
            # workspace remains intact if copying or metadata rewriting fails.
            shutil.copytree(source, staging)
            _write_json_atomic(
                os.path.join(staging, "video.json"),
                _video_data(video),
            )
            os.replace(staging, destination)
        finally:
            if os.path.isdir(staging):
                shutil.rmtree(staging, onerror=_force_remove_readonly)

        _VIDEO_DIR_CACHE[video_id] = destination
        _cache_video(video)
        _mark_metadata_changed(video_id)
        shutil.rmtree(source, onerror=_force_remove_readonly)
        migrated.append(video_id)
    try:
        os.rmdir(LEGACY_VIDEO_WORKSPACES_DIR)
    except OSError:
        pass
    return migrated


def migrate_legacy_thumbnails(legacy_directory: str) -> list[str]:
    """Move referenced legacy thumbnail-cache files into their video workspaces."""
    if not os.path.isdir(legacy_directory):
        return []
    legacy_root = os.path.abspath(legacy_directory)
    migrated = []
    for video in list_videos():
        current_path = (video.files or {}).get("thumbnail") or ""
        if not current_path or not os.path.isfile(current_path):
            continue
        try:
            if os.path.commonpath([legacy_root, os.path.abspath(current_path)]) != legacy_root:
                continue
        except ValueError:
            continue
        destination = os.path.join(get_video_dir(video.video_id), "thumbnail.jpg")
        temporary_path = ""
        try:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.normcase(os.path.abspath(current_path)) != os.path.normcase(os.path.abspath(destination)):
                handle, temporary_path = tempfile.mkstemp(
                    prefix=".thumbnail-migration-",
                    suffix=".jpg",
                    dir=os.path.dirname(destination),
                )
                os.close(handle)
                shutil.copy2(current_path, temporary_path)
                if os.path.getsize(temporary_path) <= 0:
                    raise RuntimeError(f"Legacy thumbnail is empty: {current_path}")
                os.replace(temporary_path, destination)
                temporary_path = ""
            video.files["thumbnail"] = destination
            save_video(video)
            if os.path.normcase(os.path.abspath(current_path)) != os.path.normcase(os.path.abspath(destination)):
                try:
                    os.remove(current_path)
                except OSError:
                    pass
            migrated.append(video.video_id)
        except (OSError, RuntimeError):
            continue
        finally:
            if temporary_path:
                try:
                    os.remove(temporary_path)
                except FileNotFoundError:
                    pass
    return migrated
