"""Last-known public OpenRouter catalogue; no credentials or account-scoped data."""
from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.services.translation_model_catalog import (
    _INCOMPATIBLE_OPENROUTER_MODELS,
    _MODEL,
    _NON_TEXT,
    _NON_TRANSLATION,
    _RETIRED_OPENROUTER_MODELS,
    _UNAVAILABLE_OPENROUTER_MODELS,
    PROTOCOL_PARAMETERS,
    supports_chat,
)
from haizflow.utils.atomic_file import atomic_json

_PATH = Path(RUNTIME_DATA_DIR) / "translation-openrouter-models.json"
_BUNDLED = Path(__file__).resolve().parents[1] / "assets" / "translation" / "openrouter-models.json"
_LOCK = threading.RLock()
_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
MAX_AGE = 60 * 60
_PROTOCOL_REVISION = 1


def _clean(options):
    rows = {}
    for row in options[:1000] if isinstance(options, list) else []:
        if not isinstance(row, dict):
            continue
        model = row.get("value")
        if (not isinstance(model, str) or not _MODEL.fullmatch(model)
                or _NON_TEXT.search(model) or model.startswith("openrouter/")
                or model in _RETIRED_OPENROUTER_MODELS or model in _INCOMPATIBLE_OPENROUTER_MODELS
                or model in _UNAVAILABLE_OPENROUTER_MODELS
                or not supports_chat(model, row)
                or _NON_TRANSLATION.search(model)):
            continue
        label = row.get("label", model)
        label = " ".join(label.split())[:120] if isinstance(label, str) else model
        item = {"value": model, "label": label or model}
        if isinstance(row.get("pricing_kind"), str) and row["pricing_kind"] in {"free", "paid", "unknown"}:
            item["pricing_kind"] = row["pricing_kind"]
        if isinstance(row.get("output_format"), str) and row["output_format"] in {"json_schema", "json_object"}:
            item["output_format"] = row["output_format"]
        for field in ("context_length", "max_completion_tokens"):
            value = row.get(field)
            if type(value) is int and 0 < value <= 10**8:
                item[field] = value
        if isinstance(row.get("prompt_format"), str) and row["prompt_format"] in {"user_only", "system_user"}:
            item["prompt_format"] = row["prompt_format"]
        if type(row.get("reasoning_supported")) is bool:
            item["reasoning_supported"] = row["reasoning_supported"]
        if isinstance(row.get("parameters"), list):
            item["parameters"] = [value for value in PROTOCOL_PARAMETERS if value in row["parameters"]]
        if "endpoints" in row:
            item["endpoints"] = ["/api/v1/chat/completions"]
        info = row.get("reasoning_capabilities")
        if isinstance(info, dict) and isinstance(info.get("values"), list):
            mandatory = info.get("mandatory") is True
            values = [value for value in _EFFORTS if value in info["values"] and not (mandatory and value == "none")]
            item["reasoning_capabilities"] = {
                "values": values, "default": next(iter(values), ""), **({"mandatory": True} if mandatory else {})}
            if info.get("toggle") is True and not mandatory:
                item["reasoning_capabilities"] = {"values": ["disabled", "enabled"],
                                                  "default": "disabled", "toggle": True}
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


@lru_cache(maxsize=8)
def _metadata_version(path, modified, size):
    if size > 512 * 1024:
        return None, {}
    try:
        data = json.loads(Path(path).read_text("utf-8"))
        if not isinstance(data, dict) or data.get("version") != 2 or not isinstance(data.get("options"), list):
            return None, {}
        endpoints = {row["value"]: supports_chat(row["value"], row) for row in data["options"][:1000]
                     if isinstance(row, dict) and isinstance(row.get("value"), str) and "endpoints" in row}
        fetched = data.get("fetched_at") if data.get("protocol_revision") == _PROTOCOL_REVISION else None
        return fetched, endpoints
    except (OSError, ValueError):
        return None, {}


def _public_metadata(path):
    try:
        stat = path.stat()
        return _metadata_version(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None, {}


def needs_refresh():
    """Only a complete live refresh is fresh; shipped/offline hints never are."""
    fetched, _endpoints = _public_metadata(_PATH)
    age = time.time() - fetched if type(fetched) in {int, float} else -1
    return not (0 <= age < MAX_AGE and _cached_read(_PATH) is not None)


def chat_supported(model):
    """Keep negative endpoint hints even though incompatible rows are hidden."""
    if not supports_chat(model, {}):
        return False
    with _LOCK:
        for path in (_PATH, _BUNDLED):
            _fetched, endpoints = _public_metadata(path)
            if model in endpoints:
                return endpoints[model]
    return True


def reasoning_for(model):
    with _LOCK:
        for options in (_load(), _cached_read(_BUNDLED) or []):
            for row in options:
                if row["value"] == model and "reasoning_capabilities" in row:
                    info = deepcopy(row["reasoning_capabilities"])
                    return {"parameter": "reasoning.enabled" if info.get("toggle") else "reasoning.effort", **info}
    return None


def format_for(model):
    return protocol_for(model).get("output_format")


def protocol_for(model):
    with _LOCK:
        info = {}
        fields = ("output_format", "context_length", "max_completion_tokens", "prompt_format", "reasoning_supported",
                  "endpoints", "parameters", "reasoning_capabilities", "pricing_kind")
        # Enrich an older successful cache with newly shipped protocol hints.
        for row in _cached_read(_BUNDLED) or []:
            if row["value"] == model:
                info.update({field: row[field] for field in fields if field in row})
                break
        for row in _load():
            if row["value"] == model:
                if "parameters" in row:
                    info.clear()  # A live complete record supersedes, rather than inherits, old capabilities.
                info.update({field: row[field] for field in fields if field in row})
                break
        return deepcopy(info)


def store(options, state, *, cancelled=None):
    """Only full success replaces the catalogue; partial refreshes merge safely."""
    with _LOCK:
        if state not in {"ready", "partial"} or cancelled is not None and cancelled.is_set():
            return load()
        options = _clean(options)
        if state == "partial":
            options = _clean(list({row["value"]: row for row in [*load(), *options]}.values()))
        try:
            data = {"version": 2, "protocol_revision": _PROTOCOL_REVISION, "options": options}
            if state == "ready":
                data["fetched_at"] = time.time()
            atomic_json(_PATH, data, ensure_ascii=True)
        except OSError:
            pass  # A cache write failure cannot discard a successfully fetched list.
        return options
