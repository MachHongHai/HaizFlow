from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from haizflow.schemas.editor import (
    EDITOR_DOCUMENT_SCHEMA_VERSION,
    EditorAsset,
    EditorClip,
    EditorDocument,
    EditorSequence,
    EditorTextStyle,
    EditorTrack,
    EditorTransform,
    SourceEditDecision,
)
from haizflow.schemas.video import SubtitleStyle
from haizflow.services import manual_artifacts, video_store
from haizflow.utils.ffmpeg import get_video_duration

TRACKS = (
    ("source-video", "source_video", "Video nguồn", 0),
    ("subtitles", "subtitle", "Phụ đề", 10),
    ("overlays", "overlay", "Lớp phủ", 20),
    ("voice", "voice", "Giọng đọc", 30),
    ("source-audio", "source_audio", "Âm thanh nguồn", 40),
    ("music", "music", "Nhạc nền", 50),
)


def document_path(video_id: str) -> Path:
    return Path(video_store.get_video_dir(video_id)) / "editor" / "document.json"


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".editor-", suffix=".json.tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
        raise


def _fingerprint(path: str) -> str:
    try:
        stat = os.stat(path)
    except OSError:
        return ""
    digest = hashlib.sha256()
    digest.update(os.path.abspath(path).encode("utf-8", errors="replace"))
    digest.update(str(stat.st_size).encode("ascii"))
    digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


def _is_nonempty_file(path: str) -> bool:
    try:
        return bool(path) and Path(path).is_file() and Path(path).stat().st_size > 0
    except OSError:
        return False


def _source_duration_ms(video, segments: list[dict]) -> int:
    source = str((video.files or {}).get("video_input") or (video.files or {}).get("input_video") or "")
    try:
        if source and os.path.isfile(source):
            return max(1, round(float(get_video_duration(source)) * 1000))
    except (OSError, RuntimeError, TypeError, ValueError):
        pass
    return max(
        1,
        max((round(float(item.get("end") or 0) * 1000) for item in segments), default=1),
    )


def _legacy_segments(video) -> list[dict]:
    try:
        from haizflow.pipeline.manual_tools import _load_segments

        segments = _load_segments(video, validate=False)
        if segments:
            return segments
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    path = str((video.files or {}).get("transcript_json") or "")
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return [dict(item) for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []


def _subtitle_style(video) -> EditorTextStyle:
    style = getattr(video, "subtitle_style", None)
    if isinstance(style, dict) or style is None:
        style = SubtitleStyle.model_validate(style or {})
    return EditorTextStyle(
        style_id="subtitle-default",
        name="Phụ đề mặc định",
        target_type="subtitle",
        font_family=style.font_family,
        font_weight=700 if style.bold else 400,
        italic=style.italic,
        uppercase=style.uppercase,
        font_size=style.font_size,
        text_color=style.text_color,
        karaoke_color=style.karaoke_color,
        outline_color=style.outline_color,
        outline_width=style.outline,
        shadow_offset_x=style.shadow,
        shadow_offset_y=style.shadow,
        position_x_percent=style.position_x_percent,
        position_y_percent=style.position_y_percent,
        max_width_percent=style.box_width_percent,
        box_height_percent=style.box_height_percent,
    )


def _watermark_style(video) -> EditorTextStyle:
    return EditorTextStyle(
        style_id="watermark-default",
        name="Watermark",
        target_type="watermark",
        font_family=getattr(video, "watermark_font_family", "Arial"),
        font_weight=700 if getattr(video, "watermark_bold", True) else 400,
        italic=getattr(video, "watermark_italic", True),
        text_color=getattr(video, "watermark_text_color", "#FFFFFF"),
        karaoke_color=getattr(video, "watermark_text_color", "#FFFFFF"),
        outline_width=max(0.0, float(getattr(video, "watermark_outline_percent", 100)) / 50.0),
    )


def build_legacy_document(video) -> EditorDocument:
    segments = _legacy_segments(video)
    duration_ms = _source_duration_ms(video, segments)
    source_path = str((video.files or {}).get("video_input") or (video.files or {}).get("input_video") or "")
    tracks = [
        EditorTrack(track_id=track_id, kind=kind, name=name, order=order)
        for track_id, kind, name, order in TRACKS
    ]
    assets = [
        EditorAsset(
            asset_id="source",
            kind="source",
            name=str(getattr(video, "original_filename", "") or "Video nguồn"),
            path=source_path,
            fingerprint=_fingerprint(source_path),
            duration_ms=duration_ms,
            width=max(0, int(getattr(video, "video_width", 0) or 0)),
            height=max(0, int(getattr(video, "video_height", 0) or 0)),
        )
    ]
    clips = [
        EditorClip(
            clip_id="source-1",
            track_id="source-video",
            kind="source_video",
            asset_id="source",
            name=str(getattr(video, "original_filename", "") or "Video nguồn"),
            duration_ms=duration_ms,
            source_out_ms=duration_ms,
        )
    ]
    clips.append(
        EditorClip(
            clip_id="source-audio-1",
            track_id="source-audio",
            kind="audio",
            asset_id="source",
            name="Âm thanh nguồn",
            duration_ms=duration_ms,
            source_out_ms=duration_ms,
            volume_percent=int(getattr(video, "original_video_volume", 100)),
        )
    )
    try:
        from haizflow.services import manual_artifacts

        has_voice = bool(manual_artifacts.active(video, "voice"))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        has_voice = False
    for index, segment in enumerate(segments):
        start_ms = max(0, round(float(segment.get("start") or 0) * 1000))
        end_ms = max(start_ms + 1, round(float(segment.get("end") or 0) * 1000))
        segment_id = str(segment.get("segment_id") or segment.get("id") or f"segment-{index + 1}")
        clips.append(
            EditorClip(
                clip_id=f"subtitle-{segment_id}",
                track_id="subtitles",
                kind="subtitle",
                segment_id=segment_id,
                name=str(segment.get("text") or ""),
                start_ms=start_ms,
                duration_ms=end_ms - start_ms,
                style_id="subtitle-default",
            )
        )
        clips.append(
            EditorClip(
                clip_id=f"voice-{segment_id}",
                track_id="voice",
                kind="voice",
                segment_id=segment_id,
                name=str(segment.get("text") or ""),
                start_ms=start_ms,
                duration_ms=end_ms - start_ms,
                enabled=has_voice,
                volume_percent=int(getattr(video, "tts_volume", 100)),
            )
        )

    background_path = str((video.files or {}).get("background_music") or "")
    if background_path:
        assets.append(
            EditorAsset(
                asset_id="background-music",
                kind="audio",
                name=Path(background_path).name,
                path=background_path,
                fingerprint=_fingerprint(background_path),
                duration_ms=duration_ms,
            )
        )
        clips.append(
            EditorClip(
                clip_id="music-1",
                track_id="music",
                kind="audio",
                asset_id="background-music",
                name="Nhạc nền",
                duration_ms=duration_ms,
                source_out_ms=duration_ms,
                loop=True,
                volume_percent=int(getattr(video, "background_music_volume", 30)),
            )
        )

    watermark_kind = str(getattr(video, "watermark_kind", "text") or "text")
    watermark_path = str((video.files or {}).get(f"watermark_{watermark_kind}") or "")
    watermark_text = str(getattr(video, "watermark_text", "") or "")
    if watermark_text or watermark_path:
        asset_id = ""
        if watermark_path:
            asset_id = "watermark-media"
            assets.append(
                EditorAsset(
                    asset_id=asset_id,
                    kind="image" if watermark_kind == "image" else "video",
                    name=Path(watermark_path).name,
                    path=watermark_path,
                    fingerprint=_fingerprint(watermark_path),
                    duration_ms=duration_ms,
                )
            )
        clips.append(
            EditorClip(
                clip_id="watermark-1",
                track_id="overlays",
                kind=watermark_kind if watermark_kind in {"text", "image", "video"} else "text",
                asset_id=asset_id,
                name=watermark_text or "Watermark",
                duration_ms=duration_ms,
                source_out_ms=duration_ms,
                style_id="watermark-default",
                transform=EditorTransform(
                    position_x_percent=50,
                    position_y_percent=50,
                    scale_x_percent=float(getattr(video, "watermark_scale_percent", 100)),
                    scale_y_percent=float(getattr(video, "watermark_scale_percent", 100)),
                    opacity_percent=float(getattr(video, "watermark_opacity_percent", 46)),
                ),
                metadata={"preset": "watermark", "legacy_motion": True},
            )
        )

    return EditorDocument(
        video_id=video.video_id,
        sequence=EditorSequence(
            duration_ms=duration_ms,
            edit_decisions=[
                SourceEditDecision(
                    decision_id="source-decision-1",
                    source_start_ms=0,
                    source_end_ms=duration_ms,
                    sequence_start_ms=0,
                )
            ],
        ),
        tracks=tracks,
        clips=clips,
        assets=assets,
        styles=[_subtitle_style(video), _watermark_style(video)],
    )


def load(video_id: str) -> EditorDocument | None:
    path = document_path(video_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EditorDocument.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _artifact_segments(record: dict | None) -> list[dict]:
    path = str(((record or {}).get("resolved_outputs") or {}).get("segments") or "")
    if not path:
        return []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _published_voice_sources(video) -> tuple[dict | None, list[dict]]:
    signature = str((getattr(video, "active_artifacts", {}) or {}).get("tts_manifest") or "")
    voice = manual_artifacts.peek(video.video_id, "tts_manifest", signature) if signature else None
    subtitle_signature = next(
        (
            str(value).split(":", 1)[1]
            for value in (voice or {}).get("inputs", [])
            if str(value).startswith("subtitle_document:")
        ),
        "",
    )
    subtitle = (
        manual_artifacts.peek(video.video_id, "subtitle_document", subtitle_signature)
        if subtitle_signature
        else None
    )
    return voice, _artifact_segments(subtitle)


def _reconcile_media_assets(video, document: EditorDocument) -> EditorDocument:
    """Reattach persisted music and voice to an existing editor document.

    ``editor/document.json`` is intentionally independent from the artifact
    manifest.  Older projects, however, can gain a valid voice/music artifact
    after the editor document was first created (for example when startup
    cache recovery finishes).  Keeping this adapter cheap and deterministic
    lets project-open repair those references without running a model or
    decoding media on Qt's GUI thread.
    """

    changed = document.model_copy(deep=True)
    dirty = False

    tracks_by_id = {track.track_id: track for track in changed.tracks}
    for track_id, kind, name, order in TRACKS:
        if track_id not in tracks_by_id:
            changed.tracks.append(
                EditorTrack(track_id=track_id, kind=kind, name=name, order=order)
            )
            dirty = True

    assets_by_id = {asset.asset_id: asset for asset in changed.assets}
    music_path = str((video.files or {}).get("background_music") or "")
    music_is_valid = _is_nonempty_file(music_path)
    music_clip = next((clip for clip in changed.clips if clip.track_id == "music"), None)
    music_asset = assets_by_id.get("background-music")
    if music_is_valid:
        fingerprint = _fingerprint(music_path)
        if music_asset is None:
            music_asset = EditorAsset(
                asset_id="background-music",
                kind="audio",
                name=Path(music_path).name,
                path=music_path,
                fingerprint=fingerprint,
                duration_ms=changed.sequence.duration_ms,
            )
            changed.assets.append(music_asset)
            assets_by_id[music_asset.asset_id] = music_asset
            dirty = True
        elif (
            music_asset.path != music_path
            or music_asset.fingerprint != fingerprint
            or music_asset.name != Path(music_path).name
        ):
            music_asset.path = music_path
            music_asset.fingerprint = fingerprint
            music_asset.name = Path(music_path).name
            dirty = True
        if music_clip is None:
            changed.clips.append(
                EditorClip(
                    clip_id="music-1",
                    track_id="music",
                    kind="audio",
                    asset_id="background-music",
                    name="Nhạc nền",
                    duration_ms=changed.sequence.duration_ms,
                    source_out_ms=changed.sequence.duration_ms,
                    loop=True,
                    volume_percent=int(getattr(video, "background_music_volume", 30)),
                )
            )
            dirty = True
        elif music_clip.asset_id != "background-music":
            music_clip.asset_id = "background-music"
            dirty = True
    elif music_clip is not None or music_asset is not None:
        changed.clips = [clip for clip in changed.clips if clip.track_id != "music"]
        changed.assets = [asset for asset in changed.assets if asset.asset_id != "background-music"]
        dirty = True

    voice, source_segments = _published_voice_sources(video)
    resolved = dict((voice or {}).get("resolved_outputs") or {})
    clip_outputs = [
        value
        for key, value in sorted(
            (
                (key, value)
                for key, value in resolved.items()
                if str(key).startswith("clip_")
            ),
            key=lambda item: int(str(item[0]).split("_", 1)[1])
            if str(item[0]).split("_", 1)[1].isdigit()
            else 10**9,
        )
    ]
    current_segments = _legacy_segments(video) if source_segments and clip_outputs else []
    current_by_id = {
        str(item.get("segment_id") or item.get("id") or ""): item
        for item in current_segments
        if str(item.get("segment_id") or item.get("id") or "")
    }
    voice_by_segment = {
        clip.segment_id: clip
        for clip in changed.clips
        if clip.track_id == "voice" and clip.segment_id
    }
    subtitle_clips = sorted(
        (clip for clip in changed.clips if clip.track_id == "subtitles" and clip.segment_id),
        key=lambda clip: (clip.start_ms, clip.clip_id),
    )
    current_by_order = sorted(
        current_segments,
        key=lambda item: (float(item.get("start") or 0), float(item.get("end") or 0)),
    )
    matched_voice_segments: set[str] = set()
    for index, source in enumerate(source_segments):
        if index >= len(clip_outputs):
            break
        source_id = str(source.get("segment_id") or source.get("id") or "")
        current = current_by_id.get(source_id)
        if current is None and index < len(current_by_order):
            current = current_by_order[index]
        if current is None or _normalized_text(current.get("text")) != _normalized_text(source.get("text")):
            continue
        current_id = str(current.get("segment_id") or current.get("id") or source_id)
        if not current_id and index < len(subtitle_clips):
            subtitle_clip = subtitle_clips[index]
            if _normalized_text(subtitle_clip.name) == _normalized_text(source.get("text")):
                current_id = subtitle_clip.segment_id
        clip = voice_by_segment.get(current_id)
        audio_path = str(clip_outputs[index] or "")
        if (
            clip is None
            or not audio_path
            or not _is_nonempty_file(audio_path)
        ):
            continue
        asset_id = f"voice-asset-{current_id}"
        asset = assets_by_id.get(asset_id)
        fingerprint = _fingerprint(audio_path)
        if asset is None:
            asset = EditorAsset(
                asset_id=asset_id,
                kind="audio",
                name=clip.name or current_id,
                path=audio_path,
                fingerprint=fingerprint,
            )
            changed.assets.append(asset)
            assets_by_id[asset_id] = asset
            dirty = True
        elif asset.path != audio_path or asset.fingerprint != fingerprint:
            asset.path = audio_path
            asset.fingerprint = fingerprint
            dirty = True
        revision = int(current.get("revision") or 0)
        if (
            clip.asset_id != asset_id
            or not clip.enabled
            or clip.metadata.get("state") != "ready"
            or int(clip.metadata.get("text_revision") or 0) != revision
        ):
            clip.asset_id = asset_id
            clip.enabled = True
            clip.metadata["state"] = "ready"
            clip.metadata["text_revision"] = revision
            dirty = True
        matched_voice_segments.add(current_id)

    for clip in voice_by_segment.values():
        if clip.segment_id in matched_voice_segments:
            continue
        if clip.enabled or clip.asset_id or clip.metadata.get("state") == "ready":
            clip.enabled = False
            clip.asset_id = ""
            clip.metadata["state"] = "stale"
            dirty = True

    return changed if dirty else document


def save(video, document: EditorDocument, *, bump_revision: bool = True) -> EditorDocument:
    if document.video_id != video.video_id:
        raise ValueError("Editor document belongs to another video.")
    stored = document.model_copy(deep=True)
    stored.schema_version = EDITOR_DOCUMENT_SCHEMA_VERSION
    if bump_revision:
        stored.revision += 1
    path = document_path(video.video_id)
    _atomic_write(path, stored.model_dump())
    video.editor_document_schema_version = EDITOR_DOCUMENT_SCHEMA_VERSION
    video.editor_document_revision = stored.revision
    video.editor_document_path = str(path)
    video_store.save_video(video)
    return stored


def ensure(video) -> EditorDocument:
    existing = load(video.video_id)
    if existing is not None:
        reconciled = _reconcile_media_assets(video, existing)
        if reconciled is not existing:
            return save(video, reconciled)
        metadata_changed = (
            int(getattr(video, "editor_document_schema_version", 0) or 0) != existing.schema_version
            or int(getattr(video, "editor_document_revision", 0) or 0) != existing.revision
            or str(getattr(video, "editor_document_path", "") or "") != str(document_path(video.video_id))
        )
        if metadata_changed:
            video.editor_document_schema_version = existing.schema_version
            video.editor_document_revision = existing.revision
            video.editor_document_path = str(document_path(video.video_id))
            video_store.save_video(video)
        return existing

    metadata_path = Path(video_store.get_video_json_path(video.video_id))
    backup_path = metadata_path.with_name("video.pre-editor-v2.json")
    if metadata_path.is_file() and not backup_path.exists():
        shutil.copy2(metadata_path, backup_path)
    document = build_legacy_document(video)
    return save(video, document, bump_revision=False)


def restore(video, payload: dict) -> EditorDocument:
    document = EditorDocument.model_validate(payload)
    return save(video, document, bump_revision=False)


def mutate(video, callback: Callable[[EditorDocument], None]) -> tuple[EditorDocument, dict, dict]:
    document = ensure(video)
    before = document.model_dump()
    changed = document.model_copy(deep=True)
    callback(changed)
    after_candidate = changed.model_dump()
    if before == after_candidate:
        return document, before, before
    stored = save(video, changed)
    return stored, before, stored.model_dump()


def sync_subtitle_clips(video, segments: list[dict]) -> EditorDocument:
    """Mirror the working subtitle document into the editor timeline.

    Subtitle publication and the editor document intentionally remain separate
    atomic files.  This adapter keeps their stable IDs/timing aligned without
    making subtitle persistence depend on QML or on an open workspace.  Text
    changes invalidate only the matching voice clip; timing-only changes keep
    the clip usable and merely move it on the sequence.
    """
    document = ensure(video)
    changed = document.model_copy(deep=True)
    subtitle_by_segment = {
        clip.segment_id: clip
        for clip in changed.clips
        if clip.track_id == "subtitles" and clip.segment_id
    }
    voice_by_segment = {
        clip.segment_id: clip
        for clip in changed.clips
        if clip.track_id == "voice" and clip.segment_id
    }
    retained = [
        clip
        for clip in changed.clips
        if clip.track_id not in {"subtitles", "voice"}
    ]
    subtitle_clips: list[EditorClip] = []
    voice_clips: list[EditorClip] = []
    for index, raw in enumerate(segments):
        segment_id = str(raw.get("segment_id") or raw.get("id") or f"segment-{index + 1}")
        text = str(raw.get("text") or "")
        start_ms = max(0, round(float(raw.get("start") or 0) * 1000))
        end_ms = max(start_ms + 1, round(float(raw.get("end") or 0) * 1000))
        duration_ms = end_ms - start_ms

        subtitle = subtitle_by_segment.get(segment_id)
        if subtitle is None:
            subtitle = EditorClip(
                clip_id=f"subtitle-{segment_id}",
                track_id="subtitles",
                kind="subtitle",
                segment_id=segment_id,
                style_id=changed.default_subtitle_style_id,
            )
        previous_text = subtitle.name
        subtitle.name = text
        subtitle.start_ms = start_ms
        subtitle.duration_ms = duration_ms
        subtitle.source_in_ms = 0
        subtitle.source_out_ms = duration_ms
        # Keep the complete subtitle payload with the clip.  Source ripple
        # edits can then rebuild the working subtitle document (including
        # word timing and provider metadata) and Undo can restore a removed
        # segment without guessing its original contents.
        subtitle.metadata["segment_payload"] = deepcopy(raw)
        subtitle_clips.append(subtitle)

        voice = voice_by_segment.get(segment_id)
        if voice is None:
            voice = EditorClip(
                clip_id=f"voice-{segment_id}",
                track_id="voice",
                kind="voice",
                segment_id=segment_id,
                enabled=False,
            )
        if previous_text != text:
            voice.enabled = False
            voice.asset_id = ""
            voice.metadata["state"] = "stale"
            voice.metadata["text_revision"] = int(raw.get("revision") or 0)
        voice.name = text
        voice.start_ms = start_ms
        voice.duration_ms = duration_ms
        voice.source_out_ms = duration_ms
        voice_clips.append(voice)

    changed.clips = retained + subtitle_clips + voice_clips
    if changed.model_dump() == document.model_dump():
        return document
    return save(video, changed)


def mark_voice_clips_ready(
    video,
    segments: list[dict],
    clip_paths: dict[str, str] | None = None,
) -> EditorDocument:
    """Publish voice readiness into the shared editor document.

    A voice manifest is complete only after every requested clip has been
    committed.  Updating the document at that boundary prevents preview and
    export from reviving stale speech for an edited sentence.
    """
    document = ensure(video)
    changed = document.model_copy(deep=True)
    subtitle_clips = sorted(
        (clip for clip in changed.clips if clip.track_id == "subtitles" and clip.segment_id),
        key=lambda clip: (clip.start_ms, clip.clip_id),
    )
    revision_by_segment: dict[str, int] = {}
    resolved_paths: dict[str, str] = {}
    clip_paths = {str(key): str(value) for key, value in (clip_paths or {}).items()}
    for index, item in enumerate(segments):
        segment_id = str(item.get("segment_id") or item.get("id") or "")
        if not segment_id and index < len(subtitle_clips):
            subtitle_clip = subtitle_clips[index]
            if _normalized_text(subtitle_clip.name) == _normalized_text(item.get("text")):
                segment_id = subtitle_clip.segment_id
        if segment_id:
            revision_by_segment[segment_id] = int(item.get("revision") or 0)
            resolved_paths[segment_id] = clip_paths.get(segment_id) or clip_paths.get(
                f"index:{index + 1}", ""
            )
    did_change = False
    for clip in changed.clips:
        if clip.track_id != "voice" or not clip.segment_id:
            continue
        if clip.segment_id not in revision_by_segment:
            continue
        revision = revision_by_segment[clip.segment_id]
        if (
            not clip.enabled
            or clip.metadata.get("state") != "ready"
            or int(clip.metadata.get("text_revision") or 0) != revision
        ):
            clip.enabled = True
            clip.metadata["state"] = "ready"
            clip.metadata["text_revision"] = revision
            did_change = True
        audio_path = resolved_paths.get(clip.segment_id, "")
        if audio_path and Path(audio_path).is_file():
            asset_id = f"voice-asset-{clip.segment_id}"
            asset = next(
                (item for item in changed.assets if item.asset_id == asset_id),
                None,
            )
            if asset is None:
                changed.assets.append(EditorAsset(
                    asset_id=asset_id,
                    kind="audio",
                    name=clip.name or clip.segment_id,
                    path=audio_path,
                    fingerprint=_fingerprint(audio_path),
                ))
            else:
                asset.name = clip.name or clip.segment_id
                asset.path = audio_path
                asset.fingerprint = _fingerprint(audio_path)
            if clip.asset_id != asset_id:
                clip.asset_id = asset_id
                did_change = True
    return save(video, changed) if did_change else document


def asset_by_id(document: EditorDocument, asset_id: str) -> EditorAsset | None:
    return next((item for item in document.assets if item.asset_id == asset_id), None)


def clip_by_id(document: EditorDocument, clip_id: str) -> EditorClip | None:
    return next((item for item in document.clips if item.clip_id == clip_id), None)


def resolved_text_style(document: EditorDocument, clip: EditorClip) -> EditorTextStyle:
    style = next((item for item in document.styles if item.style_id == clip.style_id), None)
    if style is None and clip.kind == "subtitle":
        style = next(
            (item for item in document.styles if item.style_id == document.default_subtitle_style_id),
            None,
        )
    if style is None:
        target = "subtitle" if clip.kind == "subtitle" else "text_overlay"
        style = EditorTextStyle(style_id=f"fallback-{target}", target_type=target)
    if not clip.style_override:
        return style
    payload = style.model_dump()
    payload.update(clip.style_override)
    return EditorTextStyle.model_validate(payload)


def import_asset(video_id: str, source_path: str, kind: str) -> EditorAsset:
    source = Path(str(source_path or "")).resolve()
    if kind not in {"image", "video", "audio", "font"}:
        raise ValueError("Unsupported editor asset type.")
    if not source.is_file() or source.stat().st_size <= 0:
        raise ValueError("Choose an available, non-empty asset.")
    asset_id = f"asset-{uuid.uuid4().hex}"
    destination_dir = Path(video_store.get_video_dir(video_id)) / "input" / "editor_assets"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{asset_id}{source.suffix.lower()}"
    temporary = destination.with_suffix(destination.suffix + ".part")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)
    return EditorAsset(
        asset_id=asset_id,
        kind=kind,
        name=source.stem,
        path=str(destination),
        fingerprint=_fingerprint(str(destination)),
    )


def evaluate_keyframes(clip: EditorClip, property_name: str, time_ms: int, default: float) -> float:
    frames = sorted(
        (frame for frame in clip.keyframes if frame.property_name == property_name),
        key=lambda item: item.time_ms,
    )
    if not frames:
        return float(default)
    local_time = max(0, int(time_ms) - clip.start_ms)
    if local_time <= frames[0].time_ms:
        return float(frames[0].value)
    if local_time >= frames[-1].time_ms:
        return float(frames[-1].value)
    left = frames[0]
    right = frames[-1]
    for index in range(1, len(frames)):
        if local_time <= frames[index].time_ms:
            left, right = frames[index - 1], frames[index]
            break
    span = max(1, right.time_ms - left.time_ms)
    progress = (local_time - left.time_ms) / span
    interpolation = right.interpolation
    if interpolation == "ease_in":
        progress *= progress
    elif interpolation == "ease_out":
        progress = 1 - (1 - progress) * (1 - progress)
    elif interpolation == "ease_in_out":
        progress = 2 * progress * progress if progress < 0.5 else 1 - ((-2 * progress + 2) ** 2) / 2
    return float(left.value + (right.value - left.value) * progress)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def snapshot(document: EditorDocument) -> dict:
    return deepcopy(document.model_dump())
