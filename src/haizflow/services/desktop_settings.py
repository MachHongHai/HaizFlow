import json
import os
import tempfile
import threading
from pathlib import Path

from haizflow.config import RUNTIME_DATA_DIR


SETTINGS_PATH = Path(RUNTIME_DATA_DIR) / "desktop-settings.json"
DEFAULT_SETTINGS = {
    "theme": "graphite",
    "language": "en",
    "processing_device": "cpu",
    "processing_device_origin": "detected",
    "keep_models_warm": True,
    "manual_project_cache_gib": 4,
    "manual_global_cache_gib": 16,
}
_SETTINGS_LOCK = threading.RLock()


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    migrate_legacy_settings = False
    try:
        with _SETTINGS_LOCK:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
                saved = json.load(file)
        if isinstance(saved, dict):
            settings.update({key: saved[key] for key in DEFAULT_SETTINGS if key in saved})
            if saved.get("processing_device") == "auto":
                settings["processing_device"] = "cpu"
                settings["processing_device_origin"] = "detected"
                migrate_legacy_settings = True
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    if settings.get("theme") != "graphite":
        settings["theme"] = "graphite"
        migrate_legacy_settings = True
    if migrate_legacy_settings:
        try:
            save_settings(settings)
        except OSError:
            pass
    return settings


def save_settings(settings: dict) -> dict:
    # Callers that only own one setting (for example the runtime device
    # controller) must not reset newer preferences added by another feature.
    # Merge the persisted document first, then normalize the complete result.
    merged = dict(DEFAULT_SETTINGS)
    with _SETTINGS_LOCK:
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
                existing = json.load(file)
            if isinstance(existing, dict):
                merged.update({key: existing[key] for key in DEFAULT_SETTINGS if key in existing})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            existing = {}
    merged.update({key: value for key, value in settings.items() if key in DEFAULT_SETTINGS})

    def bounded_integer(key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(merged.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    normalized = {
        # Theme switching was removed in favour of one production palette.
        # Always normalize legacy dark/light preferences so old installations
        # cannot silently reintroduce a second appearance.
        "theme": "graphite",
        "language": merged.get("language") if merged.get("language") in {"en", "vi"} else "en",
        "processing_device": (
            merged.get("processing_device")
            if merged.get("processing_device") in {"cpu", "gpu"}
            else "cpu"
        ),
        "processing_device_origin": (
            merged.get("processing_device_origin")
            if merged.get("processing_device_origin") in {"detected", "manual"}
            else "detected"
        ),
        "keep_models_warm": bool(merged.get("keep_models_warm", True)),
        "manual_project_cache_gib": bounded_integer("manual_project_cache_gib", 4, 1, 64),
        "manual_global_cache_gib": bounded_integer("manual_global_cache_gib", 16, 4, 256),
    }
    with _SETTINGS_LOCK:
        if isinstance(existing, dict) and all(existing.get(key) == value for key, value in normalized.items()):
            return normalized
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
