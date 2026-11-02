"""Last-known public OpenRouter catalogue; no credentials or account-scoped data."""
from __future__ import annotations

import json
import threading
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.services.translation_model_catalog import _MODEL, _NON_TEXT, _RETIRED_OPENROUTER_MODELS
from haizflow.utils.atomic_file import atomic_json

_PATH = Path(RUNTIME_DATA_DIR) / "translation-openrouter-models.json"
_BUNDLED = Path(__file__).resolve().parents[1] / "assets" / "translation" / "openrouter-models.json"
_LOCK = threading.RLock()
_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def _clean(options):
    rows = {}
    for row in options[:1000] if isinstance(options, list) else []:
        if not isinstance(row, dict):
            continue
        model = row.get("value")
        if (not isinstance(model, str) or not _MODEL.fullmatch(model)
                or _NON_TEXT.search(model) or model.startswith("openrouter/")
                or model in _RETIRED_OPENROUTER_MODELS):
            continue
        label = row.get("label", model)
        label = " ".join(label.split())[:120] if isinstance(label, str) else model
        item = {"value": model, "label": label or model}
        if isinstance(row.get("pricing_kind"), str) and row["pricing_kind"] in {"free", "paid", "unknown"}:
            item["pricing_kind"] = row["pricing_kind"]
        if isinstance(row.get("output_format"), str) and row["output_format"] in {"json_schema", "json_object"}:
            item["output_format"] = row["output_format"]
        info = row.get("reasoning_capabilities")
        if isinstance(info, dict) and isinstance(info.get("values"), list):
            mandatory = info.get("mandatory") is True
            values = [value for value in _EFFORTS if value in info["values"] and not (mandatory and value == "none")]
            item["reasoning_capabilities"] = {
                "values": values, "default": next(iter(values), ""), **({"mandatory": True} if mandatory else {})}
        rows[model] = item
    return sorted(rows.values(), key=lambda item: item["label"].casefold())


def _read(path):
    try:
        if path.stat().st_size > 512 * 1024:
            return None
        data = json.loads(path.read_text("utf-8"))
        if not isinstance(data, dict) or data.get("version") != 2 or not isinstance(data.get("options"), list):
            return None
        options = _clean(data["options"])
        return options if options or not data["options"] else None
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=8)
def _read_version(path, modified, size):
    return _read(Path(path))


def _cached_read(path):
    try:
        stat = path.stat()
        return _read_version(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def _load():
    cached = _cached_read(_PATH)
    return cached if cached is not None else _cached_read(_BUNDLED) or []


def load():
    with _LOCK:
        return deepcopy(_load())


def reasoning_for(model):
    with _LOCK:
        for row in _load():
            if row["value"] == model and "reasoning_capabilities" in row:
                return {"parameter": "reasoning.effort", **deepcopy(row["reasoning_capabilities"])}
    return None


def format_for(model):
    with _LOCK:
        for row in _load():
            if row["value"] == model:
                return row.get("output_format")
        # A manually entered newly supported model may be absent from an older
        # successful refresh; the shipped snapshot can still describe it.
        for row in _cached_read(_BUNDLED) or []:
            if row["value"] == model:
                return row.get("output_format")
    return None


def store(options, state, *, cancelled=None):
    """Only full success replaces the catalogue; partial refreshes merge safely."""
    with _LOCK:
        if state not in {"ready", "partial"} or cancelled is not None and cancelled.is_set():
            return load()
        options = _clean(options)
        if state == "partial":
            options = _clean(list({row["value"]: row for row in [*load(), *options]}.values()))
        try:
            atomic_json(_PATH, {"version": 2, "options": options}, ensure_ascii=True)
        except OSError:
            pass  # A cache write failure cannot discard a successfully fetched list.
        return options
