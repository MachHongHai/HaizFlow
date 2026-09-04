"""Signature-addressed artifact storage for non-linear Manual projects."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from haizflow.services import video_store

MANIFEST_SCHEMA_VERSION = 1
PROJECT_SOFT_LIMIT_BYTES = 8 * 1024**3
GLOBAL_SOFT_LIMIT_BYTES = 32 * 1024**3
MINIMUM_FREE_BYTES = 10 * 1024**3
STALE_PARTIAL_AGE_SECONDS = 24 * 60 * 60

ARTIFACT_KINDS = {
    "source_audio",
    "separation",
    "recognition",
    "translation",
    "subtitle_document",
    "ocr_region",
    "visual_proxy",
    "tts_clip",
    "tts_manifest",
    "audio_mix",
    "export",
}

_CACHE_DIRECTORIES = {
    "source_audio": "source-audio",
    "separation": "separation",
    "recognition": "recognition",
    "translation": "translation",
    "subtitle_document": "subtitles",
    "ocr_region": "ocr",
    "visual_proxy": "visual",
    "tts_clip": "voice/clips",
    "tts_manifest": "voice/manifests",
    "audio_mix": "audio",
    "export": "export",
}

# Immutable artifact files are validated repeatedly while QML asks for tool
# state.  Cache a successful digest by file identity so a large preview/export
# is not re-read on every binding evaluation.  A size or mtime change creates a
# different key and therefore forces a fresh checksum.
_VALIDATED_DIGESTS: dict[tuple[str, int, int, str], bool] = {}
_MANIFEST_LOCKS: dict[str, threading.RLock] = {}
_MANIFEST_LOCKS_GUARD = threading.Lock()
_STAGING_LEASES: set[str] = set()
_STAGING_LEASES_GUARD = threading.Lock()
_RUNTIME_PINS: dict[tuple[str, str], str] = {}
_RUNTIME_PINS_GUARD = threading.Lock()


def _manifest_lock(video_id: str) -> threading.RLock:
    with _MANIFEST_LOCKS_GUARD:
        return _MANIFEST_LOCKS.setdefault(str(video_id), threading.RLock())


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def signature(*values: Any) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_state(path: str | os.PathLike[str] | None) -> dict[str, Any] | None:
    if not path:
        return None
    candidate = Path(path).resolve()
    try:
        stat = candidate.stat()
    except OSError:
        return None
    if not candidate.is_file() or stat.st_size <= 0:
        return None
    return {"path": str(candidate), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def cache_root(video_id: str) -> Path:
    return Path(video_store.get_video_dir(video_id)) / "cache" / "manual"


def manifest_path(video_id: str) -> Path:
    return cache_root(video_id) / "manifest.json"


def _empty_manifest() -> dict[str, Any]:
    return {"schema_version": MANIFEST_SCHEMA_VERSION, "artifacts": {}}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        # Antivirus/indexing on Windows can hold the destination for a few
        # milliseconds. Retrying the atomic replace avoids failing an entire
        # TTS job for a transient sharing violation while preserving the old
        # valid manifest until replacement succeeds.
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt >= 5:
                    raise
                time.sleep(0.025 * (attempt + 1))
    except Exception:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
        raise


def load_manifest(video_id: str) -> dict[str, Any]:
    path = manifest_path(video_id)
    if not path.is_file():
        return _empty_manifest()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _empty_manifest()
    if not isinstance(payload, dict) or not isinstance(payload.get("artifacts"), dict):
        return _empty_manifest()
    payload["schema_version"] = MANIFEST_SCHEMA_VERSION
    return payload


def _save_manifest(video_id: str, payload: dict[str, Any]) -> None:
    payload["schema_version"] = MANIFEST_SCHEMA_VERSION
    _write_json_atomic(manifest_path(video_id), payload)


def artifact_id(kind: str, artifact_signature: str) -> str:
    if kind not in ARTIFACT_KINDS:
        raise ValueError(f"Unsupported Manual artifact kind: {kind}")
    return f"{kind}:{artifact_signature}"


def artifact_directory(video_id: str, kind: str, artifact_signature: str) -> Path:
    if kind not in _CACHE_DIRECTORIES:
        raise ValueError(f"Unsupported Manual artifact kind: {kind}")
    return cache_root(video_id) / _CACHE_DIRECTORIES[kind] / artifact_signature


def create_staging_directory(video_id: str, kind: str) -> Path:
    parent = cache_root(video_id) / _CACHE_DIRECTORIES[kind]
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".partial-", dir=parent)).resolve()
    with _STAGING_LEASES_GUARD:
        _STAGING_LEASES.add(str(staging))
    _write_json_atomic(
        staging / ".lease.json",
        {"pid": os.getpid(), "created_at": _now(), "video_id": str(video_id), "kind": str(kind)},
    )
    return staging


def release_staging_directory(path: str | os.PathLike[str]) -> None:
    """Release one in-process staging lease after publish or cleanup."""
    try:
        normalized = str(Path(path).resolve())
    except (OSError, RuntimeError, ValueError):
        normalized = str(path)
    with _STAGING_LEASES_GUARD:
        _STAGING_LEASES.discard(normalized)
    try:
        (Path(normalized) / ".lease.json").unlink(missing_ok=True)
    except OSError:
        pass


def _is_live_staging(path: Path) -> bool:
    normalized = str(path.resolve())
    with _STAGING_LEASES_GUARD:
        missing = {candidate for candidate in _STAGING_LEASES if not Path(candidate).exists()}
        _STAGING_LEASES.difference_update(missing)
        if normalized in _STAGING_LEASES:
            return True
    lease_path = path / ".lease.json"
    try:
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        age = max(0.0, time.time() - lease_path.stat().st_mtime)
        pid = int(lease.get("pid") or 0)
        if pid <= 0 or age >= STALE_PARTIAL_AGE_SECONDS:
            return False
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _remove_abandoned_staging(root: Path, *, include_recent: bool = False) -> int:
    """Remove only staging directories that are not leased by a live operation."""
    removed = 0
    now = time.time()
    for partial in root.rglob(".partial-*"):
        if not partial.is_dir() or _is_live_staging(partial):
            continue
        try:
            age = max(0.0, now - partial.stat().st_mtime)
        except OSError:
            continue
        if not include_recent and age < STALE_PARTIAL_AGE_SECONDS:
            continue
        try:
            size = sum(item.stat().st_size for item in partial.rglob("*") if item.is_file())
        except OSError:
            size = 0
        shutil.rmtree(partial, ignore_errors=True)
        if not partial.exists():
            removed += size
    return removed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _has_expected_digest(path: Path, expected_size: int, expected_digest: str) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    if stat.st_size != expected_size:
        return False
    key = (str(path), stat.st_size, stat.st_mtime_ns, expected_digest)
    if key in _VALIDATED_DIGESTS:
        return True
    if _sha256(path) != expected_digest:
        return False
    if len(_VALIDATED_DIGESTS) >= 4096:
        _VALIDATED_DIGESTS.clear()
    _VALIDATED_DIGESTS[key] = True
    return True


def _output_records(directory: Path, relative_outputs: dict[str, str]) -> tuple[dict[str, str], dict[str, Any], int]:
    outputs: dict[str, str] = {}
    checksums: dict[str, Any] = {}
    total_size = 0
    for name, relative in relative_outputs.items():
        candidate = (directory / relative).resolve()
        if not candidate.is_relative_to(directory.resolve()):
            raise ValueError(f"Artifact output escapes its cache directory: {relative}")
        if not candidate.is_file() or candidate.stat().st_size <= 0:
            raise FileNotFoundError(f"Manual artifact output is missing or empty: {candidate}")
        size = candidate.stat().st_size
        outputs[name] = relative.replace("\\", "/")
        checksums[name] = {"size": size, "sha256": _sha256(candidate)}
        total_size += size
    return outputs, checksums, total_size


def publish(
    video_id: str,
    kind: str,
    artifact_signature: str,
    staging_directory: str | os.PathLike[str],
    relative_outputs: dict[str, str],
    *,
    inputs: Iterable[str] = (),
    config_fingerprint: str = "",
    activate_artifact: bool = True,
) -> dict[str, Any]:
    """Atomically publish a complete cache directory and optionally activate it."""
    staging = Path(staging_directory).resolve()
    final = artifact_directory(video_id, kind, artifact_signature).resolve()
    expected_parent = final.parent.resolve()
    if staging.parent != expected_parent or not staging.name.startswith(".partial-"):
        raise ValueError("Manual artifact staging directory is not owned by the target cache.")
    outputs, checksums, total_size = _output_records(staging, relative_outputs)
    marker = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": kind,
        "signature": artifact_signature,
        "outputs": checksums,
    }
    _write_json_atomic(staging / "complete.json", marker)
    try:
        (staging / ".lease.json").unlink(missing_ok=True)
    except OSError:
        pass
    try:
        if final.exists():
            existing_valid = (final / "complete.json").is_file() and all(
                _has_expected_digest(
                    final / outputs[name],
                    int(checksums[name]["size"]),
                    str(checksums[name]["sha256"]),
                )
                for name in outputs
            )
            if existing_valid:
                shutil.rmtree(staging, ignore_errors=True)
            else:
                # The target is a cache directory for this exact immutable
                # signature, never user output.  Replace a corrupt/incomplete
                # directory instead of discarding the newly completed artifact.
                shutil.rmtree(final)
                os.replace(staging, final)
        else:
            os.replace(staging, final)
    finally:
        release_staging_directory(staging)

    timestamp = _now()
    record = {
        "artifact_id": artifact_id(kind, artifact_signature),
        "kind": kind,
        "signature": artifact_signature,
        "status": "complete",
        "inputs": list(inputs),
        "config_fingerprint": config_fingerprint,
        "outputs": outputs,
        "created_at": timestamp,
        "last_accessed_at": timestamp,
        "size_bytes": total_size,
        "error": "",
    }
    with _manifest_lock(video_id):
        manifest = load_manifest(video_id)
        manifest["artifacts"][record["artifact_id"]] = record
        _save_manifest(video_id, manifest)
        video = video_store.get_video(video_id)
        if video and activate_artifact:
            references = dict(getattr(video, "active_artifacts", {}) or {})
            references[kind] = artifact_signature
            video_store.update_video(video_id, active_artifacts=references)
    return resolve(video_id, kind, artifact_signature) or record


def _validated_outputs(video_id: str, record: dict[str, Any]) -> dict[str, str] | None:
    directory = artifact_directory(video_id, str(record.get("kind") or ""), str(record.get("signature") or ""))
    marker_path = directory / "complete.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    marker_outputs = marker.get("outputs")
    if not isinstance(marker_outputs, dict):
        return None
    resolved: dict[str, str] = {}
    for name, relative in (record.get("outputs") or {}).items():
        metadata = marker_outputs.get(name)
        candidate = (directory / str(relative)).resolve()
        if not isinstance(metadata, dict) or not candidate.is_relative_to(directory.resolve()):
            return None
        try:
            if not _has_expected_digest(
                candidate,
                int(metadata.get("size") or -1),
                str(metadata.get("sha256") or ""),
            ):
                return None
        except OSError:
            return None
        resolved[str(name)] = str(candidate)
    return resolved or None


def resolve(video_id: str, kind: str, artifact_signature: str) -> dict[str, Any] | None:
    key = artifact_id(kind, artifact_signature)
    with _manifest_lock(video_id):
        manifest = load_manifest(video_id)
        record = manifest["artifacts"].get(key)
        if not isinstance(record, dict) or record.get("status") != "complete":
            return None
        outputs = _validated_outputs(video_id, record)
        if outputs is None:
            record["status"] = "invalid"
            record["error"] = "Cached files are missing or corrupted."
            manifest["artifacts"][key] = record
            _save_manifest(video_id, manifest)
            return None
        return {**record, "resolved_outputs": outputs}


def peek(video_id: str, kind: str, artifact_signature: str) -> dict[str, Any] | None:
    """Inspect a completed artifact without hashing media on the caller thread.

    QML asks for Manual tool state while a workspace is being constructed.
    Calling :func:`resolve` there can checksum a full export, Demucs stems and
    every TTS clip before Qt has painted its first frame.  ``peek`` performs
    the structural checks needed for presentation (manifest, completion
    marker, path containment, existence and byte size) but deliberately leaves
    cryptographic verification to the worker that consumes the artifact.

    This is never used to publish or execute cached data, so a same-size file
    corruption still gets rejected by the normal ``resolve`` path before use.
    """
    if not artifact_signature:
        return None
    key = artifact_id(kind, artifact_signature)
    with _manifest_lock(video_id):
        manifest = load_manifest(video_id)
        record = manifest["artifacts"].get(key)
        if not isinstance(record, dict) or record.get("status") != "complete":
            return None
        directory = artifact_directory(video_id, kind, artifact_signature).resolve()
        try:
            marker = json.loads((directory / "complete.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if (
            marker.get("kind") != kind
            or marker.get("signature") != artifact_signature
            or not isinstance(marker.get("outputs"), dict)
        ):
            return None
        resolved: dict[str, str] = {}
        for name, relative in (record.get("outputs") or {}).items():
            metadata = marker["outputs"].get(name)
            candidate = (directory / str(relative)).resolve()
            if not isinstance(metadata, dict) or not candidate.is_relative_to(directory):
                return None
            try:
                if not candidate.is_file() or candidate.stat().st_size != int(metadata.get("size") or -1):
                    return None
            except (OSError, TypeError, ValueError):
                return None
            resolved[str(name)] = str(candidate)
        return {**record, "resolved_outputs": resolved} if resolved else None


def active(video_or_id: Any, kind: str) -> dict[str, Any] | None:
    video = video_store.get_video(video_or_id) if isinstance(video_or_id, str) else video_or_id
    if not video:
        return None
    signature_value = str((getattr(video, "active_artifacts", {}) or {}).get(kind) or "")
    return resolve(video.video_id, kind, signature_value) if signature_value else None


def peek_active(video_or_id: Any, kind: str) -> dict[str, Any] | None:
    """Return the active artifact using the non-blocking presentation check."""
    video = video_store.get_video(video_or_id) if isinstance(video_or_id, str) else video_or_id
    if not video:
        return None
    signature_value = str((getattr(video, "active_artifacts", {}) or {}).get(kind) or "")
    return peek(video.video_id, kind, signature_value) if signature_value else None


def activate(video_id: str, kind: str, artifact_signature: str) -> None:
    with _manifest_lock(video_id):
        video = video_store.get_video(video_id)
        if not video:
            return
        manifest = load_manifest(video_id)
        key = artifact_id(kind, artifact_signature)
        record = manifest["artifacts"].get(key)
        if isinstance(record, dict):
            record["last_accessed_at"] = _now()
            manifest["artifacts"][key] = record
            _save_manifest(video_id, manifest)
        references = dict(getattr(video, "active_artifacts", {}) or {})
        references[kind] = artifact_signature
        video_store.update_video(video_id, active_artifacts=references)


def deactivate(video_id: str, kinds: Iterable[str]) -> None:
    """Detach current variants without deleting reusable cache files."""
    normalized = {str(kind) for kind in kinds if str(kind) in ARTIFACT_KINDS}
    if not normalized:
        return
    with _manifest_lock(video_id):
        video = video_store.get_video(video_id)
        if not video:
            return
        references = dict(getattr(video, "active_artifacts", {}) or {})
        changed = False
        for kind in normalized:
            changed = references.pop(kind, None) is not None or changed
        if changed:
            video_store.update_video(video_id, active_artifacts=references)


def pin(video_id: str, kind: str, artifact_signature: str, owner: str) -> None:
    """Pin one immutable artifact while a runtime consumer has it open."""
    key = artifact_id(kind, artifact_signature)
    with _RUNTIME_PINS_GUARD:
        _RUNTIME_PINS[(str(video_id), str(owner))] = key


def unpin(video_id: str, owner: str) -> None:
    with _RUNTIME_PINS_GUARD:
        _RUNTIME_PINS.pop((str(video_id), str(owner)), None)


def register_existing(
    video_id: str,
    kind: str,
    artifact_signature: str,
    paths: dict[str, str],
    *,
    inputs: Iterable[str] = (),
    config_fingerprint: str = "legacy",
    activate_artifact: bool = True,
) -> dict[str, Any] | None:
    """Copy a verified legacy output into the new immutable cache."""
    if not paths or any(file_state(path) is None for path in paths.values()):
        return None
    existing = resolve(video_id, kind, artifact_signature)
    if existing:
        if activate_artifact:
            activate(video_id, kind, artifact_signature)
        return existing
    staging = create_staging_directory(video_id, kind)
    relatives: dict[str, str] = {}
    try:
        for name, source in paths.items():
            suffix = Path(source).suffix or ".bin"
            relative = f"{name}{suffix}"
            destination = staging / relative
            try:
                os.link(source, destination)
            except OSError:
                shutil.copy2(source, destination)
            relatives[name] = relative
        return publish(
            video_id,
            kind,
            artifact_signature,
            staging,
            relatives,
            inputs=inputs,
            config_fingerprint=config_fingerprint,
            activate_artifact=activate_artifact,
        )
    finally:
        release_staging_directory(staging)
        shutil.rmtree(staging, ignore_errors=True)


def record_error(
    video_id: str,
    kind: str,
    artifact_signature: str,
    error: str,
    *,
    inputs: Iterable[str] = (),
    config_fingerprint: str = "",
) -> None:
    """Persist a failed request without publishing partial output files."""
    if not artifact_signature:
        return
    key = artifact_id(kind, artifact_signature)
    with _manifest_lock(video_id):
        manifest = load_manifest(video_id)
        previous = manifest["artifacts"].get(key) or {}
        timestamp = _now()
        manifest["artifacts"][key] = {
            "artifact_id": key,
            "kind": kind,
            "signature": artifact_signature,
            "status": "error",
            "inputs": list(inputs),
            "config_fingerprint": config_fingerprint,
            "outputs": {},
            "created_at": str(previous.get("created_at") or timestamp),
            "last_accessed_at": timestamp,
            "size_bytes": 0,
            "error": str(error or "Manual tool failed."),
        }
        _save_manifest(video_id, manifest)


def _active_ids(video_id: str) -> set[str]:
    video = video_store.get_video(video_id)
    if not video:
        return set()
    active_ids = {
        artifact_id(kind, value)
        for kind, value in (getattr(video, "active_artifacts", {}) or {}).items()
        if kind in ARTIFACT_KINDS and value
    }
    with _RUNTIME_PINS_GUARD:
        active_ids.update(
            artifact_key
            for (pinned_video_id, _owner), artifact_key in _RUNTIME_PINS.items()
            if pinned_video_id == str(video_id)
        )
    # Active manifests depend on immutable child artifacts (for example a TTS
    # manifest references each cached sentence).  Cache maintenance must pin
    # that complete dependency closure, not only the top-level references kept
    # in video.json, otherwise "Dọn cache" silently breaks a valid active tool.
    manifest = load_manifest(video_id)
    pending = list(active_ids)
    while pending:
        current = pending.pop()
        record = manifest["artifacts"].get(current)
        if not isinstance(record, dict):
            continue
        for dependency in record.get("inputs") or []:
            dependency_id = str(dependency or "")
            if dependency_id and dependency_id in manifest["artifacts"] and dependency_id not in active_ids:
                active_ids.add(dependency_id)
                pending.append(dependency_id)
    return active_ids


def _prune_unlocked(video_id: str, *, limit_bytes: int = PROJECT_SOFT_LIMIT_BYTES) -> int:
    """Remove least-recently-used inactive artifacts inside one project."""
    root = cache_root(video_id)
    root.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(video_id)
    active_ids = _active_ids(video_id)
    removed = 0
    changed = False

    removed += _remove_abandoned_staging(root)

    records = list(manifest["artifacts"].values())
    total = sum(max(0, int(record.get("size_bytes") or 0)) for record in records)
    try:
        free_bytes = shutil.disk_usage(root).free
    except OSError:
        free_bytes = MINIMUM_FREE_BYTES
    required = max(0, total - max(0, limit_bytes))
    if free_bytes < MINIMUM_FREE_BYTES:
        required = max(required, MINIMUM_FREE_BYTES - free_bytes)
    priority = {
        "visual_proxy": 0,
        "audio_mix": 1,
        "export": 1,
        "translation": 2,
        "recognition": 2,
        "tts_manifest": 2,
        "tts_clip": 3,
    }
    candidates = sorted(
        (record for record in records if record.get("artifact_id") not in active_ids),
        key=lambda record: (
            0 if record.get("status") != "complete" else 1,
            priority.get(str(record.get("kind") or ""), 2),
            str(record.get("last_accessed_at") or record.get("created_at") or ""),
        ),
    )
    for record in candidates:
        if required <= 0 and record.get("status") == "complete":
            continue
        size = max(0, int(record.get("size_bytes") or 0))
        directory = artifact_directory(video_id, str(record.get("kind") or ""), str(record.get("signature") or ""))
        shutil.rmtree(directory, ignore_errors=True)
        manifest["artifacts"].pop(str(record.get("artifact_id") or ""), None)
        required -= size
        total -= size
        removed += size
        changed = True
    if changed:
        _save_manifest(video_id, manifest)
    return removed


def prune(video_id: str, *, limit_bytes: int = PROJECT_SOFT_LIMIT_BYTES) -> int:
    with _manifest_lock(video_id):
        return _prune_unlocked(video_id, limit_bytes=limit_bytes)


def _clear_unlocked(video_id: str, *, include_active: bool = False) -> int:
    manifest = load_manifest(video_id)
    active_ids = set() if include_active else _active_ids(video_id)
    removed = 0
    for key, record in list(manifest["artifacts"].items()):
        if key in active_ids:
            continue
        removed += max(0, int(record.get("size_bytes") or 0))
        directory = artifact_directory(video_id, str(record.get("kind") or ""), str(record.get("signature") or ""))
        shutil.rmtree(directory, ignore_errors=True)
        manifest["artifacts"].pop(key, None)
    removed += _remove_abandoned_staging(cache_root(video_id), include_recent=True)
    _save_manifest(video_id, manifest)
    return removed


def clear(video_id: str, *, include_active: bool = False) -> int:
    with _manifest_lock(video_id):
        return _clear_unlocked(video_id, include_active=include_active)


def prune_global(*, limit_bytes: int = GLOBAL_SOFT_LIMIT_BYTES) -> int:
    """Apply one LRU budget across every Manual project cache."""
    try:
        videos = [video for video in video_store.list_videos() if video.project_type == "manual"]
    except (AttributeError, OSError, RuntimeError, ValueError):
        # Cache publication must remain successful if an unrelated legacy
        # record cannot be enumerated. The next maintenance pass can retry.
        return 0
    entries: list[tuple[str, dict[str, Any]]] = []
    total = 0
    for video in videos:
        manifest = load_manifest(video.video_id)
        active_ids = _active_ids(video.video_id)
        for record in manifest["artifacts"].values():
            size = max(0, int(record.get("size_bytes") or 0))
            total += size
            if record.get("artifact_id") not in active_ids:
                entries.append((video.video_id, record))
    if total <= limit_bytes:
        return 0
    required = total - limit_bytes
    removed = 0
    priority = {
        "visual_proxy": 0,
        "audio_mix": 1,
        "export": 1,
        "translation": 2,
        "recognition": 2,
        "tts_manifest": 2,
        "tts_clip": 3,
    }
    for video_id, record in sorted(
        entries,
        key=lambda item: (
            0 if item[1].get("status") != "complete" else 1,
            priority.get(str(item[1].get("kind") or ""), 2),
            str(item[1].get("last_accessed_at") or item[1].get("created_at") or ""),
        ),
    ):
        if required <= 0:
            break
        with _manifest_lock(video_id):
            current = load_manifest(video_id)
            removed_id = str(record.get("artifact_id") or "")
            latest = current["artifacts"].get(removed_id)
            if not isinstance(latest, dict) or removed_id in _active_ids(video_id):
                continue
            size = max(0, int(latest.get("size_bytes") or 0))
            directory = artifact_directory(
                video_id,
                str(latest.get("kind") or ""),
                str(latest.get("signature") or ""),
            )
            shutil.rmtree(directory, ignore_errors=True)
            current["artifacts"].pop(removed_id, None)
            _save_manifest(video_id, current)
            required -= size
            removed += size
    return removed


def maintain(video_id: str) -> int:
    """Run coalesced cache maintenance after a Manual operation is idle."""
    removed = prune(video_id)
    removed += prune_global()
    return removed


def cache_size(video_id: str) -> int:
    return sum(max(0, int(record.get("size_bytes") or 0)) for record in load_manifest(video_id)["artifacts"].values())
