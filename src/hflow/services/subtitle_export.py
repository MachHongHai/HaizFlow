"""Export editor captions without rendering or modifying project artifacts."""

import os
import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

import srt

from hflow.schemas.editor import EditorDocument
from hflow.services import project_store, video_store
from hflow.utils.atomic_file import replace_with_retry


def compose_source_srt(video, document: EditorDocument | None = None) -> str:
    """Original text follows source cuts, never translated caption edits."""
    from hflow.services import manual_artifacts, subtitle_import
    from hflow.pipeline.sequence_compiler import map_source_intervals

    if subtitle_import.has_import(video):
        segments = subtitle_import.load_segments(video)
    else:
        record = manual_artifacts.active(video, "recognition") if getattr(video, "active_artifacts", None) else None
        path = ((record or {}).get("resolved_outputs") or {}).get("segments")
        # A pending recognition-model choice may detach the active branch;
        # keep the last published original transcript available for export.
        if not path:
            path = (getattr(video, "files", {}) or {}).get("source_segments")
        if not path:
            return ""
        root = Path(video_store.get_video_dir(video.video_id))
        if not Path(path).resolve().is_relative_to(root.resolve()):
            raise ValueError("Source subtitles are outside the project workspace.")
        segments = json.loads(Path(path).read_text(encoding="utf-8"))
    cues = []
    for item in segments:
        content = str(item.get("text", "")).strip()
        if not content:
            continue
        for start, end in map_source_intervals(document, [(float(item["start"]), float(item["end"]))]):
            if start < 0 or end <= start:
                continue
            cues.append(srt.Subtitle(index=0, start=timedelta(seconds=start), end=timedelta(seconds=end), content=content))
    return srt.compose(sorted(cues, key=lambda cue: (cue.start, cue.end)), eol="\r\n")


def save_srt_pair(source: str, result: str, destination: str | Path) -> list[Path]:
    """Stage both files before publication; restore previous files on failure."""
    target = validate_srt_destination(destination)
    outputs = {target.with_name(target.stem + ".source.srt"): source,
               target.with_name(target.stem + ".result.srt"): result}
    if not all(content.strip() for content in outputs.values()):
        raise ValueError("No subtitles to export.")
    temporary = []
    prepared = []
    published = []
    try:
        for path, content in outputs.items():
            validate_srt_destination(path)
            descriptor, name = tempfile.mkstemp(prefix=".hflow-srt-", suffix=".tmp", dir=path.parent)
            temporary.append(Path(name))
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            backup = None
            if path.exists():
                descriptor, backup_name = tempfile.mkstemp(prefix=".hflow-srt-", suffix=".bak", dir=path.parent)
                os.close(descriptor)
                backup = Path(backup_name)
                temporary.append(backup)
                shutil.copy2(path, backup)
            prepared.append((path, Path(name), backup))
        for path, name, backup in prepared:
            replace_with_retry(name, path)
            published.append((path, backup))
    except Exception:
        for path, backup in reversed(published):
            if backup:
                try:
                    replace_with_retry(backup, path)
                except OSError:
                    # Preserve the recovery copy if Windows keeps the target locked.
                    temporary.remove(backup)
                    raise
            else:
                path.unlink(missing_ok=True)
        raise
    finally:
        for name in temporary:
            try:
                name.unlink(missing_ok=True)
            except OSError:
                pass
    return list(outputs)


def compose_document_srt(document: EditorDocument | None, text_overrides: dict | None = None) -> str:
    if document is None:
        return ""
    visible_tracks = {track.track_id for track in document.tracks
                      if track.kind == "subtitle" and track.visible}
    overrides = text_overrides or {}
    subtitles = []
    for clip in sorted(document.clips, key=lambda item: (item.start_ms, item.clip_id)):
        if clip.kind != "subtitle" or clip.track_id not in visible_tracks or not clip.enabled:
            continue
        text = str(overrides.get(clip.segment_id, clip.name)).replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text or clip.duration_ms <= 0:
            continue
        subtitles.append(srt.Subtitle(
            index=len(subtitles) + 1,
            start=timedelta(milliseconds=clip.start_ms),
            end=timedelta(milliseconds=clip.start_ms + clip.duration_ms),
            content=text,
        ))
    return srt.compose(subtitles, eol="\r\n")


def validate_srt_destination(destination: str | Path) -> Path:
    target = Path(destination)
    if not target.suffix:
        target = target.with_suffix(".srt")
    if not target.is_absolute() or target.suffix.casefold() != ".srt":
        raise ValueError("Choose an absolute SRT destination.")
    project_store.validate_new_project_name(target.name)
    if not target.parent.is_dir():
        raise FileNotFoundError("Export folder or drive is unavailable.")
    roots = [Path(project_store.project_root_for_key(record["key"])) for record in project_store.list_projects()]
    roots.append(Path(video_store.LEGACY_VIDEO_WORKSPACES_DIR))
    for root in roots:
        if target.resolve().is_relative_to(root.resolve()):
            raise ValueError("Choose a location outside managed project storage.")
    if target.exists() and not target.is_file():
        raise ValueError("Export destination is not a regular file.")
    return target


def save_srt(content: str, destination: str | Path) -> Path:
    if not content.strip():
        raise ValueError("No subtitles to export.")
    target = validate_srt_destination(destination)
    descriptor, temporary = tempfile.mkstemp(prefix=".hflow-srt-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(temporary, target)
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass
    return target
