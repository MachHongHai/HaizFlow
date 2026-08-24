import array
import math
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from haizflow.schemas.video import VideoConfig, MediaSource
from haizflow.services import video_store, project_store
from haizflow.utils.ffmpeg import _binary, get_video_dimensions


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def analyze_voice_reference(source_path: str, bucket_count: int = 48) -> dict[str, object]:
    """Return a compact waveform and duration decoded from the real sample.

    Qt Multimedia does not expose recorder amplitude levels. Decoding the
    stored sample once also works for imported video/audio containers and
    makes the waveform stable after the dialog is reopened.
    """
    path = os.path.abspath(str(source_path or "").strip()) if source_path else ""
    buckets = max(24, min(96, int(bucket_count or 48)))
    empty = {"durationMs": 0, "peaks": [0.08] * buckets}
    if not path or not os.path.isfile(path) or os.path.getsize(path) <= 0:
        return empty

    sample_rate = 8_000
    try:
        completed = subprocess.run(
            [
                _binary("ffmpeg"),
                "-v",
                "error",
                "-i",
                path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-t",
                "120",
                "-f",
                "s16le",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return empty
    if completed.returncode != 0 or len(completed.stdout) < 2:
        return empty

    usable_bytes = len(completed.stdout) - (len(completed.stdout) % 2)
    samples = array.array("h")
    samples.frombytes(completed.stdout[:usable_bytes])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return empty

    bucket_size = max(1, math.ceil(len(samples) / buckets))
    raw_peaks: list[float] = []
    for index in range(buckets):
        start = index * bucket_size
        chunk = samples[start:min(len(samples), start + bucket_size)]
        if not chunk:
            raw_peaks.append(0.0)
            continue
        # RMS follows perceived loudness better than one isolated sample and
        # still preserves the shape of speech pauses and stressed syllables.
        rms = math.sqrt(sum(float(value) * float(value) for value in chunk) / len(chunk))
        raw_peaks.append(rms / 32768.0)
    ceiling = max(raw_peaks) or 1.0
    peaks = [round(max(0.08, min(1.0, value / ceiling)), 4) for value in raw_peaks]
    return {
        "durationMs": max(1, round(len(samples) * 1000 / sample_rate)),
        "peaks": peaks,
    }


def _same_path(first: str, second: str) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def _copy_file_atomically(source_path: str, destination_path: str) -> None:
    """Publish a complete input file without ever exposing a partial destination."""
    destination_directory = os.path.dirname(destination_path)
    os.makedirs(destination_directory, exist_ok=True)
    temporary_path = os.path.join(
        destination_directory,
        f".{os.path.basename(destination_path)}.import-{uuid.uuid4().hex}.part",
    )
    try:
        shutil.copyfile(source_path, temporary_path)
        if os.path.getsize(temporary_path) <= 0:
            raise RuntimeError(f"Imported video is empty: {source_path}")
        os.replace(temporary_path, destination_path)
    finally:
        try:
            os.remove(temporary_path)
        except FileNotFoundError:
            pass


def _remove_stale_background_music_files(workspace: str, keep_path: str = "") -> list[str]:
    """Delete only superseded HaizFlow-managed background music inputs."""
    input_directory = os.path.join(workspace, "input")
    retained = os.path.abspath(keep_path) if keep_path else ""
    errors: list[str] = []
    try:
        entries = list(os.scandir(input_directory))
    except FileNotFoundError:
        return errors
    for entry in entries:
        if not entry.is_file() or not entry.name.startswith("background_music."):
            continue
        candidate = os.path.abspath(entry.path)
        if retained and _same_path(candidate, retained):
            continue
        try:
            os.remove(candidate)
        except OSError as exc:
            errors.append(f"{entry.name}: {exc}")
    return errors


def set_desktop_background_music(video_info, source_path: str) -> str:
    """Copy optional music into its video's workspace for final mixing only."""
    source_path = os.path.abspath(str(source_path or "").strip()) if source_path else ""
    files = dict(video_info.files or {})
    previous_path = str(files.get("background_music") or "")
    workspace = os.path.abspath(video_store.get_video_dir(video_info.video_id))

    if not source_path:
        files.pop("background_music", None)
        video_info.files = files
        video_store.save_video(video_info)
        cleanup_errors = _remove_stale_background_music_files(workspace)
        if previous_path:
            try:
                if os.path.commonpath([os.path.abspath(previous_path), workspace]) == workspace:
                    os.remove(previous_path)
            except (FileNotFoundError, OSError, ValueError):
                pass
        video_store.log_to_video(video_info.video_id, "Removed the optional background music source.")
        for error in cleanup_errors:
            video_store.log_to_video(video_info.video_id, f"Deferred stale background-music cleanup: {error}")
        return ""

    if not os.path.isfile(source_path) or os.path.getsize(source_path) <= 0:
        raise ValueError("Choose an available, non-empty audio or video file for background music.")
    extension = os.path.splitext(source_path)[1].lower() or ".media"
    destination = os.path.join(workspace, "input", f"background_music{extension}")
    _copy_file_atomically(source_path, destination)
    files["background_music"] = destination
    video_info.files = files
    video_store.save_video(video_info)
    cleanup_errors = _remove_stale_background_music_files(workspace, destination)
    if previous_path and not _same_path(previous_path, destination):
        try:
            if os.path.commonpath([os.path.abspath(previous_path), workspace]) == workspace:
                os.remove(previous_path)
        except (FileNotFoundError, OSError, ValueError):
            pass
    video_store.log_to_video(video_info.video_id, f"Imported background music source: {os.path.basename(source_path)}")
    for error in cleanup_errors:
        video_store.log_to_video(video_info.video_id, f"Deferred stale background-music cleanup: {error}")
    return destination


def prepare_desktop_voice_recording(video_info) -> str:
    """Reserve a project-owned location for an in-app voice-clone recording."""
    workspace = os.path.abspath(video_store.get_video_dir(video_info.video_id))
    recording_directory = os.path.join(workspace, "temp", "voice_cloning")
    os.makedirs(recording_directory, exist_ok=True)
    return os.path.join(recording_directory, f"recording-{uuid.uuid4().hex}.m4a")


def _remove_stale_voice_reference_files(input_directory: str, keep_path: str = "") -> list[str]:
    """Best-effort cleanup for HaizFlow-owned voice samples.

    QtMultimedia can retain a Windows read handle for a short time after
    playback stops. A locked superseded sample must not make importing the
    replacement fail.
    """
    retained = os.path.abspath(keep_path) if keep_path else ""
    errors: list[str] = []
    for entry in Path(input_directory).glob("voice_reference*"):
        if not entry.is_file():
            continue
        if retained and _same_path(str(entry), retained):
            continue
        try:
            entry.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"{entry.name}: {exc}")
    return errors


def set_desktop_voice_reference(video_info, source_path: str, transcript: str = "") -> str:
    """Store an authorised voice-cloning sample inside the video workspace.

    OmniVoice can derive a cloning prompt directly from the reference audio.
    A transcript is accepted only to preserve older projects; new samples do
    not need one.
    """
    source_path = os.path.abspath(str(source_path or "").strip()) if source_path else ""
    files = dict(video_info.files or {})
    workspace = os.path.abspath(video_store.get_video_dir(video_info.video_id))
    input_directory = os.path.join(workspace, "input")
    previous_path = str(files.get("voice_reference") or "")

    if not source_path:
        files.pop("voice_reference", None)
        files.pop("voice_reference_transcript", None)
        video_info.files = files
        video_store.save_video(video_info)
        cleanup_errors = _remove_stale_voice_reference_files(input_directory)
        for error in cleanup_errors:
            video_store.log_to_video(video_info.video_id, f"Deferred stale voice-sample cleanup: {error}")
        return ""

    if not os.path.isfile(source_path) or os.path.getsize(source_path) <= 0:
        raise ValueError("Choose an available, non-empty voice sample.")
    normalized_transcript = " ".join(str(transcript or "").split())

    extension = os.path.splitext(source_path)[1].lower() or ".media"
    destination = os.path.join(input_directory, f"voice_reference{extension}")
    if not _same_path(source_path, destination):
        try:
            _copy_file_atomically(source_path, destination)
        except PermissionError:
            # A preview player may still own the stable filename on Windows.
            # Publish the new sample under a managed unique name instead of
            # failing or exposing a partial file.
            destination = os.path.join(
                input_directory,
                f"voice_reference-{uuid.uuid4().hex}{extension}",
            )
            _copy_file_atomically(source_path, destination)
    files["voice_reference"] = destination
    if normalized_transcript:
        files["voice_reference_transcript"] = normalized_transcript
    else:
        files.pop("voice_reference_transcript", None)
    video_info.files = files
    video_store.save_video(video_info)
    cleanup_errors = _remove_stale_voice_reference_files(input_directory, destination)
    if previous_path and not _same_path(previous_path, destination):
        try:
            if os.path.commonpath([os.path.abspath(previous_path), workspace]) == workspace:
                os.remove(previous_path)
        except (FileNotFoundError, OSError, ValueError):
            pass
    video_store.log_to_video(video_info.video_id, "Imported an authorised OmniVoice cloning sample.")
    for error in cleanup_errors:
        video_store.log_to_video(video_info.video_id, f"Deferred stale voice-sample cleanup: {error}")
    return destination


def migrate_legacy_single_export(video_info) -> bool:
    """Move a legacy single-project export out of the project root once."""
    if (
        not video_info
        or video_info.project_type == "batch"
        or not video_info.project_name
        or not video_info.project_directory
    ):
        return False

    project_root = (
        project_store.project_root_for_key(video_info.project_key)
        if video_info.project_key
        else project_store.project_root(video_info.project_name, video_info.project_directory, video_info.project_type)
    )
    legacy_export = os.path.join(project_root, "dubbed_video.mp4")
    current_export = (video_info.files or {}).get("final_video") or ""
    if not current_export or not _same_path(current_export, legacy_export):
        return False

    export_directory = (
        project_store.project_exports_dir_for_key(video_info.project_key)
        if video_info.project_key
        else project_store.project_exports_dir(
            video_info.project_name, video_info.project_directory, video_info.project_type
        )
    )
    migrated_export = os.path.join(export_directory, "dubbed_video.mp4")
    os.makedirs(export_directory, exist_ok=True)
    if os.path.isfile(legacy_export) and not os.path.exists(migrated_export):
        os.replace(legacy_export, migrated_export)

    if os.path.exists(migrated_export):
        video_info.files["final_video"] = migrated_export
        video_store.save_video(video_info)
        return True
    return False


def create_desktop_video(
    video_path: str,
    config: VideoConfig,
    project_name: str = "",
    project_directory: str = "",
    media_source: MediaSource | dict | None = None,
    *,
    move_input: bool = False,
    project_key_value: str = "",
):
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in SUPPORTED_VIDEO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        raise ValueError(f"Unsupported video extension '{ext}'. Supported: {supported}.")
    if config.mode not in {"A", "review"}:
        raise ValueError(f"Unsupported workflow: {config.mode}")

    project_name = project_name.strip()
    project_directory = project_directory.strip()
    if project_directory and not project_name:
        raise ValueError("Enter a project name before choosing an output folder.")

    video_id = str(uuid.uuid4())
    if project_directory:
        config.project_name = project_name
        config.project_directory = os.path.abspath(project_directory)
        project = project_store.ensure_project(
            project_name,
            config.project_directory,
            config.project_type,
            project_key_value=project_key_value or config.project_key,
        )
        config.project_id = str(project["project_id"])
        config.project_key = str(project["key"])
    video_info = video_store.create_video(video_id, os.path.basename(video_path), config, video_ext=ext)
    try:
        video_info.media_source = MediaSource.model_validate(media_source or {"type": "local_file"})
        input_path = (video_info.files or {}).get("video_input")
        if not isinstance(input_path, str) or not input_path.strip():
            raise RuntimeError("New video metadata did not provide an input-video path.")
        _copy_file_atomically(video_path, input_path)

        if config.background_music_path.strip():
            set_desktop_background_music(video_info, config.background_music_path)

        try:
            video_info.video_width, video_info.video_height = get_video_dimensions(input_path)
        except RuntimeError:
            # The UI can retry probing legacy or unusual files when the batch is opened.
            video_info.video_width = 0
            video_info.video_height = 0

        video_store.save_video(video_info)
        video_store.log_to_video(video_id, f"Imported input video: {video_path}")
        if move_input and not _same_path(video_path, input_path):
            try:
                os.remove(video_path)
            except OSError as exc:
                video_store.log_to_video(
                    video_id,
                    f"Imported successfully, but the temporary source could not be removed: {exc}",
                )
        return video_info
    except Exception:
        try:
            video_store.delete_video(video_id, attempts=2, delay_seconds=0.05)
        except Exception:
            pass
        export_directory = os.path.dirname(str(video_info.files.get("final_video") or ""))
        if export_directory:
            try:
                os.rmdir(export_directory)
            except OSError:
                pass
        raise
