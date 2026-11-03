"""Explicit, local consent for OpenRouter endpoints that require data collection."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.utils.atomic_file import atomic_json

_PATH = Path(RUNTIME_DATA_DIR) / "translation-data-consent.json"
_LOCK = threading.RLock()
# Confirmed by public terms and data-policy 404 responses on 2026-11-03.
COLLECTION_MODELS = frozenset({
    "nvidia/nemotron-3.5-super-vl:free", "liquid/lfm-2.5-2.6b:free",
})


def required(profile):
    return profile.get("provider") == "openrouter" and profile.get("model") in COLLECTION_MODELS


def _scope(profile):
    identifier = profile.get("id", "")
    if not required(profile) or not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Kết nối/model không hỗ trợ quyền thu thập dữ liệu này.")
    return identifier + ":" + profile["model"]


def _read():
    try:
        if _PATH.stat().st_size > 256 * 1024:
            return set()
        data = json.loads(_PATH.read_text("utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("grants"), list):
            return set()
        return {value for value in data["grants"][:1000] if isinstance(value, str)
                and len(value) <= 240 and re.fullmatch(r"[a-f0-9]{32}:.+", value)}
    except (OSError, ValueError):
        return set()


def allowed(profile):
    try:
        scope = _scope(profile)
    except ValueError:
        return False
    with _LOCK:
        return scope in _read()


def grant(profile):
    scope = _scope(profile)
    with _LOCK:
        grants = _read()
        if scope not in grants and len(grants) >= 1000:
            raise ValueError("Đã đạt giới hạn số quyền model được lưu.")
        atomic_json(_PATH, {"version": 1, "grants": sorted(grants | {scope})})


def forget(identifier):
    with _LOCK:
        grants = _read()
        retained = {scope for scope in grants if not scope.startswith(identifier + ":")}
        if retained != grants:
            atomic_json(_PATH, {"version": 1, "grants": sorted(retained)})
