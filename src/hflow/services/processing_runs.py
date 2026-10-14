"""Run-owned output rollback. Pause keeps progress; discard keeps older cache."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import uuid
from pathlib import Path

from hflow.core.storage_ownership import managed_storage_guard, owned_path, safe_tree
from hflow.services import manual_artifacts, video_store

_LOCK = threading.RLock()
_RUNS = {}
_CHECKED = set()
_ARMED_EXPORTS = {}
_ARMED_EXPORT_STATES = {}
_CURRENT = threading.local()
_LOG = logging.getLogger(__name__)
_MANUAL_IDLE_FIELDS = {
    "status", "progress", "step", "step_detail", "error", "resume_step",
    "manual_target_tool", "manual_target_stage", "current_item", "total_items", "estimated_remaining_seconds",
}


def _source_identity(video):
    return (str((video.files or {}).get("video_input") or ""), video.created_at)


def _path(video_id):
    return manual_artifacts.cache_root(video_id) / "processing-run.json"


def _save(run):
    manual_artifacts._write_json_atomic(_path(run["video_id"]),
        {key: value for key, value in run.items() if key != "running"})


def _get(video_id):
    if video_id in _RUNS:
        return _RUNS[video_id]
    if video_id in _CHECKED:
        return None
    _CHECKED.add(video_id)
    try:
        run = json.loads(_path(video_id).read_text(encoding="utf-8"))
        if (run.get("video_id") == video_id and re.fullmatch(r"[a-f0-9]{32}", str(run.get("id", "")))
                and isinstance(run.get("created"), list) and isinstance(run.get("baseline_ids"), list)
                and isinstance(run.get("active_artifacts"), dict) and isinstance(run.get("files"), dict)
                and isinstance(run.get("checkpoints"), dict) and isinstance(run.get("source_generation"), list)
                and isinstance(run.get("temp_files"), list) and isinstance(run.get("tool"), str)):
            run["running"] = False
            _RUNS[video_id] = run
            return run
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def manual_export_state(video):
    """Capture idle editor state before queueing changes its status/progress."""
    if not video or getattr(video, "project_type", "") != "manual":
        return None
    fields = {name: getattr(video, name, None) for name in _MANUAL_IDLE_FIELDS}
    if fields["status"] == "processing" or (fields["status"] == "pending" and fields["manual_target_tool"]):
        fields.update(status="manual_ready", step="manual_ready", step_detail="", error=None,
                      manual_target_tool="", manual_target_stage="", resume_step="", current_item=0, total_items=0)
    if fields["status"] == "cancelled" and fields["manual_target_tool"] == "export":
        fields.update(status="manual_ready", step="manual_ready", step_detail="", error=None,
                      manual_target_tool="", manual_target_stage="", resume_step="")
    return {"source_generation": list(_source_identity(video)), "fields": fields}


def _validated_idle_fields(video, snapshot):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("fields"), dict):
        return None
    generation = snapshot.get("source_generation")
    if not isinstance(generation, (list, tuple)) or tuple(generation) != _source_identity(video):
        return None
    fields = snapshot["fields"]
    if set(fields) != _MANUAL_IDLE_FIELDS or fields.get("status") not in {
            "manual_ready", "done", "pending", "paused", "failed", "cancelled"}:
        return None
    if hasattr(video, "model_dump"):
        try:
            validated = type(video).model_validate({**video.model_dump(), **fields})
        except (TypeError, ValueError):
            return None
        return {name: getattr(validated, name) for name in _MANUAL_IDLE_FIELDS}
    return fields


def restore_cancelled_manual_export(video_id, snapshot):
    """Queued exports can be cancelled before a worker/journal ever exists."""
    if not isinstance(snapshot, dict):
        return False
    video = video_store.get_video(video_id)
    if not video or video.project_type != "manual" or video.status != "cancelled":
        return False
    fields = _validated_idle_fields(video, snapshot)
    if fields is None:
        return False
    video_store.update_video(video_id, **fields)
    return True


def arm_export(video_id):
    with _LOCK:
        identifier = uuid.uuid4().hex
        _ARMED_EXPORTS[video_id] = identifier
        _ARMED_EXPORT_STATES[video_id] = (identifier, manual_export_state(video_store.get_video(video_id)))
        return identifier


def disarm_export(video_id):
    with _LOCK:
        _ARMED_EXPORTS.pop(video_id, None)
        _ARMED_EXPORT_STATES.pop(video_id, None)


def forget_restarted(video_id):
    """Explicit whole-video restart already retired its generated workspace."""
    with _LOCK:
        run = _RUNS.get(video_id)
        if run:
            _drop(run)


def _drop(run):
    backup = run.get("backup")
    if backup:
        from hflow.services.temporary_cleanup import discard_tree

        root = Path(video_store.get_video_dir(run["video_id"]))
        discard_tree(owned_path(root / (".processing-backup-" + run["id"]), root))
    _path(run["video_id"]).unlink(missing_ok=True)
    _RUNS.pop(run["video_id"], None)
    if _ARMED_EXPORTS.get(run["video_id"]) == run["id"]:
        _ARMED_EXPORTS.pop(run["video_id"], None)
    if (_ARMED_EXPORT_STATES.get(run["video_id"]) or (None,))[0] == run["id"]:
        _ARMED_EXPORT_STATES.pop(run["video_id"], None)


def begin(video_id, *, resuming=False):
    """Called on the pipeline worker, never scan/copy old media on the GUI."""
    with _LOCK:
        video = video_store.get_video(video_id)
        if video is None or not hasattr(video, "video_id"):
            return None
        root = Path(video_store.get_video_dir(video_id))
        if not (root / "video.json").is_file():
            return None
        tool = str(video.manual_target_tool or "") if video.project_type == "manual" else "auto"
        previous = _get(video_id)
        if previous and tuple(previous.get("source_generation", ())) != _source_identity(video):
            # A source replacement owns its own reset. Never restore old refs.
            _drop(previous)
            previous = None
        if (previous and resuming and previous["tool"] == tool and not previous.get("discard")
                and _ARMED_EXPORTS.get(video_id, previous["id"]) == previous["id"]):
            previous["running"] = True
            previous["state"] = "running"
            _CURRENT.run = previous
            _save(previous)
            return previous
        if previous:
            if (previous.get("state") in {"running", "discarding"}
                    or previous.get("state") in {"paused", "failed"} and previous["tool"] == tool and not resuming):
                previous["discard"] = True
                if not rollback(previous):
                    raise RuntimeError("File của lượt trước còn bị khóa. Đóng preview/tệp đang dùng rồi chạy lại.")
            else:
                _drop(previous)
        manifest = manual_artifacts.load_manifest(video_id)
        run = {"video_id": video_id, "id": _ARMED_EXPORTS.get(video_id) or uuid.uuid4().hex, "tool": tool,
            "source_generation": _source_identity(video), "state": "running", "running": True,
            "export_owned": video_id in _ARMED_EXPORTS, "discard": False, "created": [],
            "baseline_ids": list(manifest["artifacts"]),
            "active_artifacts": dict(video.active_artifacts or {}),
            "files": dict(video.files or {}), "checkpoints": dict(video.checkpoints or {}),
            "manual_completed_stages": list(video.manual_completed_stages or []),
            "manual_completed_stage": video.manual_completed_stage,
            "backup": "", "temp_files": [], "backup_ready": False}
        armed_state = _ARMED_EXPORT_STATES.get(video_id)
        if video.project_type == "manual" and tool == "export" and armed_state and armed_state[0] == run["id"]:
            run["manual_idle_state"] = armed_state[1]
        _RUNS[video_id] = run
        _CURRENT.run = run
        temporary = owned_path(root / "temp", root)
        if temporary.exists():
            safe_tree(temporary)
            run["temp_files"] = [str(path.relative_to(temporary)) for path in temporary.rglob("*") if path.is_file()]
        # Auto uses mutable legacy temp files. Only cancellable export runs
        # need a backup; Manual outputs already live in immutable artifacts.
        if run["export_owned"] and video.project_type != "manual" and run["temp_files"]:
            backup = root / (".processing-backup-" + run["id"])
            run["backup"] = str(backup)
            backup.mkdir()
            _save(run)
            for relative in run["temp_files"]:
                if run["discard"]:
                    raise RuntimeError("Video cancelled by user.")
                target = backup / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                source = owned_path(temporary / relative, temporary)
                with source.open("rb") as incoming, target.open("wb") as outgoing:
                    while data := incoming.read(1024 * 1024):
                        if run["discard"]:
                            raise RuntimeError("Video cancelled by user.")
                        outgoing.write(data)
                shutil.copystat(source, target)
            run["backup_ready"] = True
        _save(run)
        return run


def published(video_id, key):
    run = getattr(_CURRENT, "run", None)
    if run and run["video_id"] == video_id and key not in run["baseline_ids"] and key not in run["created"]:
        with _LOCK:
            run["created"].append(key)
            if len(run["created"]) % 16 == 0:
                _save(run)


def request_discard(video_id, run_id=None):
    # This must remain responsive while the worker backs up legacy files.
    run = _RUNS.get(video_id) or _get(video_id)
    if run_id is None or _ARMED_EXPORTS.get(video_id) == run_id:
        _ARMED_EXPORTS.pop(video_id, None)
        _ARMED_EXPORT_STATES.pop(video_id, None)
    if run_id is not None and run and run["id"] != run_id:
        return
    if run:
        run["discard"] = True
        run["state"] = "discarding"
        if not run.get("running"):
            _save(run)


def rollback(run):
    """Never remove baseline artifacts, input assets, or outputs of later runs."""
    video_id = run["video_id"]
    with _LOCK, manual_artifacts._manifest_lock(video_id), managed_storage_guard:
        video = video_store.get_video(video_id)
        if video is None or _source_identity(video) != tuple(run["source_generation"]):
            _drop(run)
            return True
        root = Path(video_store.get_video_dir(video_id))
        temporary = owned_path(root / "temp", root)
        try:
            if temporary.exists():
                safe_tree(temporary)
                baseline = set(run["temp_files"])
                for path in temporary.rglob("*"):
                    if path.is_file() and str(path.relative_to(temporary)) not in baseline:
                        path.unlink()
            if run.get("backup_ready"):
                backup = owned_path(root / (".processing-backup-" + run["id"]), root)
                for relative in run["temp_files"]:
                    source = owned_path(backup / relative, backup)
                    if source.is_file():
                        target = owned_path(temporary / relative, root)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(source, target)
        except OSError:
            run["state"] = "discarding"
            _save(run)
            return False
        manifest = manual_artifacts.load_manifest(video_id)
        created = set(run["created"])
        references = dict(video.active_artifacts or {})
        for kind, signature in list(references.items()):
            if manual_artifacts.artifact_id(kind, signature) in created:
                previous = run["active_artifacts"].get(kind)
                if previous:
                    references[kind] = previous
                else:
                    references.pop(kind, None)
        files = dict(video.files or {})
        created_directories = [manual_artifacts.artifact_directory(video_id, record["kind"], record["signature"])
            for key, record in manifest["artifacts"].items() if key in created]
        generated_names = {"srt_output", "voice_output", "transcript_json", "final_video", "voice_parts_dir",
            "source_audio", "speech_audio", "background_audio", "source_segments", "ocr_region",
            "translation_review_draft"}
        for name in generated_names:
            current = files.get(name)
            if (video.project_type == "manual" and isinstance(current, str) and current
                    and not any(Path(current).is_relative_to(directory) for directory in created_directories)):
                continue
            if name in run["files"]:
                files[name] = run["files"][name]
            else:
                files.pop(name, None)
        video_store.update_video(video_id, active_artifacts=references, files=files,
            checkpoints=run["checkpoints"], manual_completed_stages=run["manual_completed_stages"],
            manual_completed_stage=run["manual_completed_stage"], resume_step="")
        protected = manual_artifacts._active_ids(video_id)
        pending = []
        for key in created:
            record = manifest["artifacts"].get(key)
            if record is None:
                continue
            if key in protected:
                pending.append(key)
                continue
            directory = manual_artifacts.artifact_directory(video_id, record["kind"], record["signature"])
            if manual_artifacts._remove_inactive_directory(directory):
                manifest["artifacts"].pop(key, None)
            else:
                pending.append(key)
        manual_artifacts._save_manifest(video_id, manifest)
        if pending:
            run["created"] = pending
            run["state"] = "discarding"
            _save(run)
            return False
        fields = _validated_idle_fields(video, run.get("manual_idle_state"))
        if (video.project_type == "manual" and run.get("export_owned") and fields is not None
                and _ARMED_EXPORTS.get(video_id) in {None, run["id"]}):
            video_store.update_video(video_id, **fields)
        _drop(run)
        return True


def finish(video_id):
    with _LOCK:
        run = getattr(_CURRENT, "run", None)
        _CURRENT.run = None
        if not run or run["video_id"] != video_id:
            return
        run["running"] = False
        video = video_store.get_video(video_id)
        if run.get("discard"):
            _retry_rollback(run)
        elif video and video.status in {"paused", "failed"}:
            run["state"] = video.status
            _save(run)
        elif run["export_owned"]:
            run["state"] = "ready"
            _save(run)
        else:
            _drop(run)


def settle_export(video_id, status, run_id=None):
    with _LOCK:
        run = _get(video_id)
        if run_id is not None and run and run["id"] != run_id:
            return True
        if not run:
            return True
        if run.get("running"):
            return False
        if status == "cancelled" or run.get("discard"):
            return _retry_rollback(run)
        if status in {"done", "failed"}:
            if status != "failed" or run["state"] != "failed":
                _drop(run)
        return True


def retained_ids(video_id, video=None):
    run = _get(video_id)
    video = video or (video_store.get_video(video_id) if run else None)
    if not run or not video or _source_identity(video) != tuple(run["source_generation"]):
        return set()
    return {manual_artifacts.artifact_id(kind, signature) for kind, signature in run["active_artifacts"].items()}


def discard_pending(video_id, run_id):
    run = _RUNS.get(video_id)
    return bool(run and run["id"] == run_id and run.get("discard"))


def current_id(video_id):
    run = _RUNS.get(video_id)
    return run["id"] if run else None


def commit_previous_ready(video_id):
    """A finished render recovered after app restart is older than this copy."""
    with _LOCK:
        run = _get(video_id)
        if run and run["state"] == "ready" and not run.get("running"):
            _drop(run)


def _retry_rollback(run):
    try:
        return rollback(run)
    except (OSError, ValueError, RuntimeError):
        run["state"] = "discarding"
        _LOG.exception("Run cleanup deferred: %s", run["video_id"])
        try:
            _save(run)
        except OSError:
            pass
        return False
