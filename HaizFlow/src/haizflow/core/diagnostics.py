"""Create privacy-preserving diagnostics archives for support."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from haizflow.config import INSTALL_ROOT, LOGS_DIR

_MAX_LOG_BYTES = 2 * 1024 * 1024
_PACKAGE_NAMES = (
    "haizflow",
    "PySide6",
    "torch",
    "transformers",
    "whisperx",
    "llama-cpp-python",
    "edge-tts",
    "yt-dlp",
)
_SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|cookie|password|passwd|secret|token|api[_-]?key)\b"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_WINDOWS_PATH_PATTERN = re.compile(r"(?i)(?:[A-Z]:\\|\\\\)[^\r\n\"'<>|]*")
_POSIX_HOME_PATTERN = re.compile(r"(?<![\w.-])/(?:home|users)/[^/\s]+(?:/[^\s\"'<>]*)?", re.IGNORECASE)


def redact_diagnostic_text(value: str) -> str:
    """Remove credentials, URLs, e-mail addresses, and user paths from logs."""
    text = str(value or "")
    text = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    text = _URL_PATTERN.sub("<url>", text)
    text = _EMAIL_PATTERN.sub("<email>", text)
    text = _WINDOWS_PATH_PATTERN.sub("<path>", text)
    return _POSIX_HOME_PATTERN.sub("<path>", text)


def _read_tail(path: Path, max_bytes: int = _MAX_LOG_BYTES) -> str:
    with path.open("rb") as file:
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(max(0, size - max_bytes))
        data = file.read()
    text = data.decode("utf-8", errors="replace")
    if size > max_bytes:
        _discarded, separator, text = text.partition("\n")
        if not separator:
            return ""
    return text


def _recent_log_files(directory: Path, pattern: str, limit: int) -> list[Path]:
    """Return regular local log files without following attacker-made links."""
    candidates: list[tuple[int, Path]] = []
    if not directory.is_dir():
        return []
    for path in directory.glob(pattern):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            candidates.append((path.stat().st_mtime_ns, path))
        except OSError:
            # Rotation may remove a file between directory enumeration and
            # stat; a support export should still include the remaining logs.
            continue
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _mtime, path in candidates[:limit]]


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _build_information(install_directory: Path) -> dict[str, object]:
    path = install_directory / "BUILD-INFO.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    allowed = (
        "application",
        "version",
        "build_id",
        "built_at_utc",
        "git_commit",
        "git_branch",
        "git_dirty",
        "python",
        "packaging",
        "model_delivery",
        "model_storage",
        "bundled_cpu_model",
        "bundled_gpu_model",
        "bundled_whisper_model",
        "bundled_demucs_model",
        "bundled_alignment_models",
    )
    return {key: payload[key] for key in allowed if key in payload}


def diagnostic_summary(*, install_directory: Path | None = None) -> dict[str, object]:
    """Return support metadata that deliberately excludes user/project data."""
    install_path = Path(install_directory or INSTALL_ROOT).resolve()
    build = _build_information(install_path)
    packages = _package_versions()
    version = str(build.get("version") or packages["haizflow"])
    build_id = str(build.get("build_id") or f"source-{version}")
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "application": "HaizFlow",
        "version": version,
        "build_id": build_id,
        "frozen": bool(getattr(sys, "frozen", False)),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "packages": packages,
        "build": build,
        "privacy": {
            "contains_project_names": False,
            "contains_project_media": False,
            "contains_project_logs": False,
            "logs_redacted": True,
        },
    }


def export_diagnostics(
    destination: str | os.PathLike[str],
    *,
    logs_directory: Path | None = None,
    install_directory: Path | None = None,
) -> Path:
    """Atomically create a redacted ZIP containing bounded application logs."""
    output_path = Path(destination).expanduser().resolve()
    if output_path.suffix.lower() != ".zip":
        output_path = output_path.with_suffix(".zip")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_root = Path(logs_directory or LOGS_DIR).resolve()

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}-",
        suffix=".zip.tmp",
        dir=output_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            summary = diagnostic_summary(install_directory=install_directory)
            archive.writestr(
                "diagnostics.json",
                json.dumps(summary, ensure_ascii=True, indent=2) + "\n",
            )

            if log_root.is_dir():
                app_logs = _recent_log_files(log_root, "app.log*", 4)
                worker_root = log_root / "hymt2-workers"
                worker_logs = _recent_log_files(worker_root, "*.log", 5)
                for index, path in enumerate(app_logs, 1):
                    archive.writestr(
                        f"logs/app-{index}.log",
                        redact_diagnostic_text(_read_tail(path)),
                    )
                for index, path in enumerate(worker_logs, 1):
                    archive.writestr(
                        f"logs/model-worker-{index}.log",
                        redact_diagnostic_text(_read_tail(path, 256 * 1024)),
                    )
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return output_path
