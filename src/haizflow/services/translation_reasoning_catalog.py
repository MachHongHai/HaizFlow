"""Bounded public OpenRouter capability hints shared with processing workers."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.utils.atomic_file import atomic_json

_PATH = Path(RUNTIME_DATA_DIR) / "translation-reasoning-capabilities.json"
_LOCK = threading.RLock()
_VALUES = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
_MODEL = re.compile(r"[A-Za-z0-9@~][A-Za-z0-9._:/@+~-]{0,199}\Z")


def advertised(reasoning):
    if not isinstance(reasoning, dict):
        return None
    mandatory = reasoning.get("mandatory") is True
    if "supported_efforts" not in reasoning:
        return {"values": [], "default": "", "mandatory": True} if mandatory else None
    supported = reasoning["supported_efforts"]
    if supported is None:
        supported = list(_VALUES)  # OpenRouter explicitly advertises all gateway efforts with null.
    if not isinstance(supported, list):
        return None
    values = [value for value in _VALUES if value in supported]
    if mandatory:
        values = [value for value in values if value != "none"]
    return {"values": values, "default": values[0] if values else "", **({"mandatory": True} if mandatory else {})}


def _read():
    try:
        if _PATH.stat().st_size > 512 * 1024:
            return {}
        data = json.loads(_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    result = {}
    for model, info in list(data.items())[:1000] if isinstance(data, dict) else []:
        if not _MODEL.fullmatch(model) or not isinstance(info, dict) or not isinstance(info.get("values"), list):
            continue
        values = [value for value in _VALUES if value in info["values"]]
        result[model] = {"parameter": "reasoning.effort", "values": values, "default": values[0] if values else ""}
        if info.get("mandatory") is True:
            result[model]["mandatory"] = True
            result[model]["values"] = [value for value in values if value != "none"]
            result[model]["default"] = next(iter(result[model]["values"]), "")
    return result


def get(model):
    with _LOCK:
        result = _read().get(model)
    if result is not None:
        return result
    from haizflow.services.translation_catalog_cache import reasoning_for

    return reasoning_for(model)


def remember(options):
    updates = {row["value"]: row["reasoning_capabilities"] for row in options
               if isinstance(row, dict) and "reasoning_capabilities" in row}
    if not updates:
        return
    with _LOCK:
        data = {**_read(), **updates}
        data = dict(list(data.items())[-1000:])
        try:
            atomic_json(_PATH, data, ensure_ascii=True)
        except OSError:
            pass  # Optional public metadata must not break model discovery.
