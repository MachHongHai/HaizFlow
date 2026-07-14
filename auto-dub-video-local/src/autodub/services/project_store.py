"""Persistent metadata for desktop projects, including projects without jobs."""

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from autodub.config import RUNTIME_DATA_DIR


PROJECT_INDEX_PATH = os.path.join(RUNTIME_DATA_DIR, "projects.json")
PROJECT_MANIFEST_NAME = ".autodub-project.json"


def safe_project_name(project_name: str) -> str:
    """Return the directory name used for a user-visible project name."""
    cleaned = "".join(
        character if character.isalnum() or character in {"-", "_", " "} else "_"
        for character in project_name.strip()
    ).strip()
    return cleaned or "project"


def project_key(project_name: str, project_directory: str, project_type: str) -> str:
    directory = os.path.abspath(project_directory).lower()
    kind = "batch" if project_type == "batch" else "single"
    return f"{kind}:{directory}:{project_name.strip().lower()}"


def project_root(project_name: str, project_directory: str) -> str:
    return os.path.abspath(os.path.join(os.path.abspath(project_directory), safe_project_name(project_name)))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json_atomic(path: str, data: Any) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(prefix=".projects-", suffix=".json.tmp", dir=directory)
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


def _load_index() -> list[dict[str, Any]]:
    if not os.path.exists(PROJECT_INDEX_PATH):
        return []
    try:
        with open(PROJECT_INDEX_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def ensure_project(project_name: str, project_directory: str, project_type: str) -> dict[str, Any]:
    """Create or update a project manifest and return its normalized record."""
    name = project_name.strip()
    directory_input = project_directory.strip()
    directory = os.path.abspath(directory_input)
    kind = "batch" if project_type == "batch" else "single"
    if not name:
        raise ValueError("Enter a project name.")
    if not directory_input:
        raise ValueError("Choose a project folder.")

    root = project_root(name, directory)
    now = _now()
    key = project_key(name, directory, kind)
    records = _load_index()
    existing = next((record for record in records if record.get("key") == key), None)
    record = {
        "key": key,
        "project_name": name,
        "project_directory": directory,
        "project_root": root,
        "project_type": kind,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
    }
    os.makedirs(root, exist_ok=True)
    _write_json_atomic(os.path.join(root, PROJECT_MANIFEST_NAME), record)
    records = [item for item in records if item.get("key") != key]
    records.append(record)
    _write_json_atomic(PROJECT_INDEX_PATH, records)
    return record


def list_projects() -> list[dict[str, Any]]:
    """Return registered projects. Jobs are intentionally stored separately."""
    records = _load_index()
    valid = [record for record in records if record.get("key") and record.get("project_name")]
    return sorted(valid, key=lambda record: record.get("updated_at", ""), reverse=True)
