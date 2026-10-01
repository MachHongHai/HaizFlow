"""Stable export names and explicit, source-bounded MP4 quality presets."""

import hashlib
import json
import os
import shutil
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from haizflow.core.storage_ownership import owned_path
from haizflow.services import manual_artifacts, project_store, video_store


EXPORT_PRESETS = {
    "source": {"label": "Theo nguồn · Chất lượng cao", "en": "Source · High quality", "crf": 18, "height": 0},
    "1080p": {"label": "Full HD 1080p · Tiêu chuẩn", "en": "Full HD 1080p · Standard", "crf": 21, "height": 1080},
    "1080p-high": {"label": "Full HD 1080p · Chất lượng cao", "en": "Full HD 1080p · High quality", "crf": 18, "height": 1080},
    "720p": {"label": "HD 720p · Dung lượng nhỏ", "en": "HD 720p · Smaller file", "crf": 24, "height": 720},
    "2160p": {"label": "4K 2160p · Chất lượng cao", "en": "4K 2160p · High quality", "crf": 18, "height": 2160},
}


def preset_settings(value: str) -> dict:
    if value not in EXPORT_PRESETS:
        raise ValueError("Unsupported export preset.")
    return dict(EXPORT_PRESETS[value])


def project_display_name(video) -> str:
    key = str(getattr(video, "project_key", "") or "")
    project = project_store.get_project(key) if key else None
    return str((project or {}).get("project_name") or getattr(video, "project_name", "")
               or Path(video.original_filename).stem)


def export_filename(name: str) -> str:
    try:
        stem = project_store.validate_new_project_name(str(name))
    except ValueError:
        stem = project_store.safe_project_name(str(name))[:120].rstrip(" .")
        if stem.split(".", 1)[0].upper() in project_store._WINDOWS_RESERVED_NAMES:
            stem = "project-" + stem
    return (stem or "project") + ".mp4"


def export_destination(video) -> Path:
    """Render workspace only. External export destinations are never stored here."""
    root = Path(video_store.get_video_dir(video.video_id))
    return owned_path(root / "temp" / "render.mp4", root)


def render_revision(video) -> str:
    if video.project_type == "manual":
        from haizflow.pipeline.manual_tools import export_signature

        return export_signature(video, validate=False)
    from haizflow.schemas.video import VideoConfig

    ignored = {"project_name", "project_directory", "project_id", "project_key", "background_music_path", "review_approved"}
    config = {key: getattr(video, key, None) for key in VideoConfig.model_fields if key not in ignored}
    media = {key: manual_artifacts.file_state((video.files or {}).get(key)) for key in (
        "video_input", "srt_output", "voice_output", "background_music", "watermark_image", "watermark_video",
    )}
    return manual_artifacts.signature("managed-render-v1", config, media, getattr(video, "export_preset", "source"), video.checkpoints.get("render"))


def current_render(video, *, verify: bool = True) -> dict | None:
    """Return only the current, intact managed render; never follow export history."""
    if not video:
        return None
    signature = str((getattr(video, "active_artifacts", {}) or {}).get("export") or "")
    if not signature:
        return None
    try:
        record = (manual_artifacts.resolve if verify else manual_artifacts.peek)(video.video_id, "export", signature)
        if not record or record.get("config_fingerprint") != render_revision(video):
            return None
        path = record["resolved_outputs"].get("video")
        owned_path(path, video_store.get_video_dir(video.video_id))
        return record
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        return None


def render_path(video, *, verify: bool = False) -> str:
    record = current_render(video, verify=verify)
    return str(record["resolved_outputs"]["video"]) if record else ""


def adopt_legacy_render(video) -> dict | None:
    """Copy, never move, a project-owned legacy result with a completion checkpoint.

    An external absolute path is deliberately not adopted. Missing files do not
    change the project status or write placeholder projects.
    """
    if not video or (getattr(video, "active_artifacts", {}) or {}).get("export"):
        return current_render(video)
    if video.project_type == "manual" or video.status != "done" or not video.checkpoints.get("render"):
        return None
    path = str((video.files or {}).get("final_video") or "")
    if not path:
        return None
    try:
        if not legacy_render_owned(video, path):
            return None
        if not manual_artifacts.file_state(path):
            return None
        from haizflow.utils.ffmpeg import validate_video_integrity

        validate_video_integrity(path)
        revision = render_revision(video)
        record = manual_artifacts.register_existing(video.video_id, "export", revision, {"video": path}, config_fingerprint=revision)
        if record:
            files = dict(video.files or {})
            files["final_video"] = record["resolved_outputs"]["video"]
            video_store.update_video(video.video_id, files=files)
        return record
    except (OSError, RuntimeError, ValueError):
        return None


def legacy_render_owned(video, path) -> bool:
    if video_store._is_inside(str(path), video_store.get_video_dir(video.video_id)):
        return True
    key = getattr(video, "project_key", "") or project_store.resolve_project_key(
        video.project_name, video.project_directory, video.project_type,
    )
    if not key:
        return False
    root = Path(project_store.project_root_for_key(key))
    try:
        candidate = owned_path(path, root)
        return (candidate.name in {"dubbed_video.mp4", "final.mp4", export_filename(video.project_name)}
                and (candidate.parent == root or video_store._is_inside(str(candidate), str(root / "exports"))))
    except (OSError, ValueError):
        return False


def validate_export_destination(destination) -> Path:
    target = Path(str(destination))
    if not target.is_absolute() or target.suffix.casefold() != ".mp4":
        raise ValueError("Choose an absolute MP4 destination.")
    project_store.validate_new_project_name(target.name)
    if not target.parent.is_dir():
        raise FileNotFoundError("Export folder or drive is unavailable.")
    # Explicitly reject app-owned destinations, including another project's
    # root, junction aliases and legacy standalone video storage.
    roots = [Path(project_store.project_root_for_key(record["key"])) for record in project_store.list_projects()]
    roots.append(Path(video_store.LEGACY_VIDEO_WORKSPACES_DIR))
    for root in roots:
        try:
            target.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        raise ValueError("Choose an export location outside managed project storage. This keeps exports safe when deleting a project.")
    if target.exists() and not target.is_file():
        raise ValueError("Export destination is not a regular file.")
    return target


class ExportCancelled(Exception):
    pass


def destination_identity(destination) -> tuple | None:
    try:
        info = Path(destination).stat()
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    except FileNotFoundError:
        return None


@contextmanager
def render_lease(video):
    owner = "export-" + uuid.uuid4().hex
    signature = str((getattr(video, "active_artifacts", {}) or {}).get("export") or "")
    if not signature:
        raise FileNotFoundError("Render artifact needs to be rebuilt.")
    manual_artifacts.pin(video.video_id, "export", signature, owner)
    try:
        record = current_render(video)
        if not record:
            raise FileNotFoundError("Render artifact is missing, outdated or corrupted. Rebuild the result before exporting.")
        yield record
    finally:
        manual_artifacts.unpin(video.video_id, owner)


def export_video(video, destination, *, overwrite: bool = False, cancel: threading.Event | None = None,
                 progress=None, expected_target=None) -> str:
    """Verified, durable copy and same-filesystem atomic publication.

    Failure never changes pipeline status, checkpoints, or the internal render.
    A no-overwrite Windows rename also protects against a file created after
    the confirmation dialog. Existing output survives every pre-publication error.
    """
    target = validate_export_destination(destination)
    if target.exists() and not overwrite:
        raise FileExistsError("Destination already exists; overwrite confirmation is required.")
    confirmed_target = expected_target if expected_target is not None else destination_identity(target)
    token = cancel or threading.Event()
    temporary = None
    with render_lease(video) as record:
        source = Path(record["resolved_outputs"]["video"])
        marker_path = manual_artifacts.artifact_directory(video.video_id, "export", record["signature"]) / "complete.json"
        expected_digest = json.loads(marker_path.read_text(encoding="utf-8"))["outputs"]["video"]["sha256"]
        size = source.stat().st_size
        if source.resolve() == target.resolve() or (target.exists() and os.path.samefile(source, target)):
            raise ValueError("Cannot export onto the internal render artifact.")
        if shutil.disk_usage(target.parent).free < size + 8 * 1024**2:
            raise OSError(28, "Not enough free space for export.")
        try:
            handle, temporary = tempfile.mkstemp(prefix=".haizflow-export-", suffix=".partial", dir=target.parent)
            digest, copied = hashlib.sha256(), 0
            with source.open("rb") as incoming, os.fdopen(handle, "wb") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    if token.is_set():
                        raise ExportCancelled("Export cancelled.")
                    outgoing.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                    if progress:
                        progress(min(95, round(copied * 95 / size)))
                outgoing.flush()
                os.fsync(outgoing.fileno())
            if (copied != size or digest.hexdigest() != expected_digest
                    or manual_artifacts._sha256(Path(temporary)) != digest.hexdigest()
                    or not current_render(video)):
                raise OSError("Export verification failed.")
            if token.is_set():
                raise ExportCancelled("Export cancelled.")
            validate_export_destination(target)  # Recheck ownership after a long copy.
            if overwrite:
                if destination_identity(target) != confirmed_target:
                    raise FileExistsError("Destination changed since replacement was confirmed. Choose it again.")
                os.replace(temporary, target)
            elif os.name == "nt":
                os.rename(temporary, target)  # Windows: fails if another file appeared.
            else:
                os.link(temporary, target)  # Atomic no-clobber publication on POSIX.
                os.unlink(temporary)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    # A disconnected drive may make cleanup impossible. Keep
                    # the original failure; a .partial is never a finished MP4.
                    pass
    if progress:
        progress(100)
    # History is informational only. A history write failure cannot undo a
    # verified export or turn a successful copy into a processing failure.
    history = {"path": str(target), "size": size, "sha256": digest.hexdigest(), "exported_at": datetime.now(UTC).isoformat()}
    try:
        video_store.update_video(video.video_id, export_history=[*(getattr(video, "export_history", []) or [])[-19:], history])
    except (OSError, RuntimeError, ValueError):
        pass
    return str(target)


def batch_filename(video) -> str:
    return export_filename(f"{project_store.safe_project_name(Path(video.original_filename).stem)[:70]}--{video.video_id[:12]}")


def output_dimensions(width: int, height: int, preset: str) -> tuple[int, int]:
    limit = int(preset_settings(preset)["height"])
    if width <= 0 or height <= 0:
        raise ValueError("Cannot determine export dimensions.")
    scale = min(1.0, limit / min(width, height), limit * 16 / 9 / max(width, height)) if limit else 1.0
    return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)
