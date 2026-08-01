import json
import os
import tempfile
import threading
from pathlib import Path

from haizflow.config import RUNTIME_DATA_DIR


SETTINGS_PATH = Path(RUNTIME_DATA_DIR) / "desktop-settings.json"
DEFAULT_SETTINGS = {
    "theme": "dark",
    "language": "en",
    "processing_device": "cpu",
    "processing_device_origin": "detected",
}
_SETTINGS_LOCK = threading.RLock()


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    migrate_legacy_device = False
    try:
        with _SETTINGS_LOCK:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
                saved = json.load(file)
        if isinstance(saved, dict):
            settings.update({key: saved[key] for key in DEFAULT_SETTINGS if key in saved})
            if saved.get("processing_device") == "auto":
                settings["processing_device"] = "cpu"
                settings["processing_device_origin"] = "detected"
                migrate_legacy_device = True
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    if migrate_legacy_device:
        try:
            save_settings(settings)
        except OSError:
            pass
    return settings


def save_settings(settings: dict) -> dict:
    normalized = {
        "theme": settings.get("theme") if settings.get("theme") in {"dark", "light"} else "dark",
        "language": settings.get("language") if settings.get("language") in {"en", "vi"} else "en",
        "processing_device": (
            settings.get("processing_device")
            if settings.get("processing_device") in {"cpu", "gpu"}
            else "cpu"
        ),
        "processing_device_origin": (
            settings.get("processing_device_origin")
            if settings.get("processing_device_origin") in {"detected", "manual"}
            else "detected"
        ),
    }
    with _SETTINGS_LOCK:
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
                existing = json.load(file)
            if isinstance(existing, dict) and all(existing.get(key) == value for key, value in normalized.items()):
                return normalized
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_path = tempfile.mkstemp(
            prefix=".desktop-settings-",
            suffix=".json.tmp",
            dir=SETTINGS_PATH.parent,
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(normalized, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, SETTINGS_PATH)
        except Exception:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
            raise
    return normalized


def reset_settings() -> dict:
    return save_settings(DEFAULT_SETTINGS)
