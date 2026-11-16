"""Immutable translation-only connections; keys never enter QML/project metadata."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.services import secure_credentials

PROVIDERS = {
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1",
               "guide": "https://platform.openai.com/api-keys"},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com",
                 "guide": "https://platform.deepseek.com/api_keys"},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1",
                   "guide": "https://openrouter.ai/settings/keys"},
    "custom": {"label": "API tùy chỉnh", "base_url": "", "guide": ""},
}
_PATH = Path(RUNTIME_DATA_DIR) / "translation-connections.json"
_LOCK = threading.RLock()
_ID = re.compile(r"[a-f0-9]{32}\Z")
_MODEL = re.compile(r"[A-Za-z0-9@~][A-Za-z0-9._:/@+~-]{0,199}\Z")


def normalized_url(value: str) -> str:
    value = str(value or "").strip()
    try:
        parts = urlsplit(value)
        port = parts.port
        host = parts.hostname or ""
        local = host == "localhost"
        try:
            local = local or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if (not host or parts.username or parts.password or parts.query or parts.fragment
                or parts.scheme not in {"http", "https"} or parts.scheme == "http" and not local
                or len(value) > 500 or any(c.isspace() for c in value)
                or any(c in value for c in "\\\r\n\t") or port == 0):
            raise ValueError
        path = parts.path.rstrip("/")
        if any(piece in {".", ".."} for piece in path.split("/")) or "%" in path:
            raise ValueError
    except ValueError:
        raise ValueError("Base URL cần HTTPS, không chứa key, tài khoản, query hoặc đường dẫn tương đối.") from None
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _target(identifier):
    if not _ID.fullmatch(identifier):
        raise ValueError("Kết nối dịch không hợp lệ.")
    return "HaizFlow/Translation/APIKey/" + identifier


def _document():
    try:
        if _PATH.stat().st_size > 1024 * 1024:
            return {}
        data = json.loads(_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read():
    rows = _document().get("connections", [])
    result = []
    for row in rows[:100] if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            _target(row["id"])
            provider = row["provider"]
            if (provider not in PROVIDERS or not isinstance(row.get("model", ""), str)
                    or row.get("model", "") and not _MODEL.fullmatch(row["model"])
                    or row.get("format", "json_object") not in {"json_object", "json_schema", "prompt"}):
                continue
            base_url = normalized_url(row["base_url"])
            if provider != "custom" and base_url != PROVIDERS[provider]["base_url"]:
                continue
            result.append({"id": row["id"], "provider": provider, "model": row.get("model", ""), "base_url": base_url,
                           "label": str(row["label"])[:64], "format": row.get("format", "json_object")})
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _selection_state(rows):
    data = _document()
    raw_active = data.get("active")
    active = {p: str(raw_active[p]) for p in PROVIDERS if p in raw_active} if isinstance(raw_active, dict) else {}
    # One-time compatibility default; explicit deselection must never choose another key.
    if not isinstance(raw_active, dict):
        for row in rows:
            active.setdefault(row["provider"], row["id"])
    aliases = data.get("providers", {})
    aliases = {i: p for i, p in aliases.items() if _ID.fullmatch(i)
               and isinstance(p, str) and p in PROVIDERS} if isinstance(aliases, dict) else {}
    aliases.update({row["id"]: row["provider"] for row in rows})
    return active, aliases


def _save(rows, *, active=None, aliases=None):
    previous_rows = _read()
    previous_active, previous_aliases = _selection_state(previous_rows)
    active = previous_active if active is None else active
    aliases = previous_aliases if aliases is None else aliases
    aliases.update({row["id"]: row["provider"] for row in rows})
    legacy = _document().get("legacy_models", {})
    legacy = legacy if isinstance(legacy, dict) else {}
    legacy.update({row["id"]: {"model": row["model"], "format": row["format"]}
                   for row in [*previous_rows, *rows]})
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".translation-connections-", suffix=".tmp", dir=_PATH.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"version": 2, "connections": rows, "active": active, "providers": aliases,
                       "legacy_models": legacy},
                      stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, _PATH)
    finally:
        Path(temporary).unlink(missing_ok=True)


def list_connections():
    with _LOCK:
        rows = _read()
        active, _ = _selection_state(rows)
        return [{**row, "active": active.get(row["provider"]) == row["id"]} for row in rows]


def choice_provider(model_choice: str):
    identifier = model_choice.removeprefix("api:").partition(":")[0]
    if identifier in PROVIDERS:
        return identifier
    with _LOCK:
        _, aliases = _selection_state(_read())
        return aliases.get(identifier, "")


def active_connection(provider: str, *, with_key=False):
    with _LOCK:
        rows = _read()
        active, _ = _selection_state(rows)
        identifier = active.get(provider, "")
        if not any(row["id"] == identifier and row["provider"] == provider for row in rows):
            raise ValueError("Chưa chọn API sử dụng. Vào Cài đặt → API Key để chọn Sử dụng.")
        return get_connection(identifier, with_key=with_key)


def select(identifier: str):
    with _LOCK:
        row, _ = get_connection(identifier, with_key=True)
        rows = _read()
        active, aliases = _selection_state(rows)
        active[row["provider"]] = identifier
        _save(rows, active=active, aliases=aliases)
    return True


def add(provider: str, label: str, key: str, model: str = "", base_url: str = "", output_format: str = "json_object"):
    if provider not in PROVIDERS:
        raise ValueError("Nhà cung cấp dịch không hợp lệ.")
    label, key, model = label.strip(), key.strip(), model.strip()
    if not 1 <= len(label) <= 64 or model and not _MODEL.fullmatch(model):
        raise ValueError("Nhập tên kết nối (1–64 ký tự) và Model ID hợp lệ.")
    if not 1 <= len(key) <= 4096 or any(not 33 <= ord(c) <= 126 for c in key):
        raise ValueError("API key không hợp lệ.")
    if output_format not in {"json_object", "json_schema", "prompt"}:
        raise ValueError("Định dạng kết quả không hợp lệ.")
    endpoint = normalized_url(base_url) if provider == "custom" else PROVIDERS[provider]["base_url"]
    if provider == "custom" and endpoint.endswith(("/chat/completions", "/responses")):
        raise ValueError("Base URL chỉ là đường dẫn gốc API (ví dụ https://example.com/v1), "
                         "không kèm /chat/completions hoặc /responses.")
    identifier = uuid.uuid4().hex
    row = {"id": identifier, "provider": provider, "label": label, "model": model, "base_url": endpoint,
           "format": output_format if provider == "custom" else
           "json_schema" if provider in {"openai", "openrouter"} else "json_object"}
    with _LOCK:
        rows = _read()
        if len(rows) >= 100:
            raise ValueError("Đã đạt giới hạn 100 kết nối dịch.")
        secure_credentials.write_secret(_target(identifier), key, username=PROVIDERS[provider]["label"])
        try:
            active, aliases = _selection_state(rows)
            if not any(item["provider"] == provider for item in rows) and provider not in active:
                active[provider] = identifier
            _save([*rows, row], active=active, aliases=aliases)
        except OSError:
            secure_credentials.delete_secret(_target(identifier))
            raise
    return identifier


def get_connection(identifier: str, *, with_key: bool = False):
    _target(identifier)
    with _LOCK:
        row = next((row for row in _read() if row["id"] == identifier), None)
        if row is None:
            raise ValueError("Kết nối dịch đã bị xóa hoặc chưa có trên máy này. Thêm API rồi chọn lại model dịch.")
        if not with_key:
            return row
        key = secure_credentials.read_secret(_target(identifier)).strip()
        if not key:
            raise ValueError("Không tìm thấy API key của kết nối dịch. Vào Cài đặt → API Key để thêm lại.")
        return row, key


def resolve(model_choice: str, *, with_key: bool = False):
    from haizflow.core.translation_models import is_api_model

    if not is_api_model(model_choice):
        raise ValueError("Model API dịch không hợp lệ.")
    identifier, _, selected_model = model_choice[4:].partition(":")
    selected_model, _, output_format = selected_model.partition("#")
    provider = choice_provider(model_choice)
    # Read legacy model before routing to the globally selected credential.
    legacy = None
    if _ID.fullmatch(identifier) and not selected_model:
        with _LOCK:
            try:
                legacy = get_connection(identifier)
            except ValueError:
                saved = _document().get("legacy_models", {})
                legacy = saved.get(identifier) if isinstance(saved, dict) else None
                if (not isinstance(legacy, dict) or not isinstance(legacy.get("model"), str)
                        or not _MODEL.fullmatch(legacy["model"])
                        or not isinstance(legacy.get("format"), str)
                        or legacy["format"] not in {"json_object", "json_schema", "prompt"}):
                    raise ValueError("Chưa chọn model dịch. Hãy chọn lại model trong dự án.") from None
    result = active_connection(provider, with_key=with_key)
    profile = result[0] if with_key else result
    if output_format and profile["provider"] != "custom":
        raise ValueError("Chỉ API tùy chỉnh mới hỗ trợ đổi định dạng JSON.")
    profile = {**profile, "model": selected_model or (legacy or profile)["model"],
               "format": output_format or (legacy or profile)["format"]}
    if not profile["model"]:
        raise ValueError("Chưa chọn model dịch. Hãy chọn model trong cài đặt của dự án.")
    return (profile, result[1]) if with_key else profile


def signature_parts(model_choice: str):
    try:
        row = resolve(model_choice)
        row = {key: row[key] for key in ("provider", "model", "base_url", "format")}
    except ValueError:
        return ("translation-api-v1", model_choice, "missing-connection")
    fingerprint = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
    return ("translation-api-v1", model_choice, fingerprint)


def remove(identifier: str):
    with _LOCK:
        rows = _read()
        if not any(row["id"] == identifier for row in rows):
            return False
        target = _target(identifier)
        active, aliases = _selection_state(rows)
        for provider, selected in active.items():
            if selected == identifier:
                active[provider] = ""
        previous = secure_credentials.read_secret(target)
        secure_credentials.delete_secret(target)
        try:
            _save([row for row in rows if row["id"] != identifier], active=active, aliases=aliases)
        except OSError:
            if previous:
                secure_credentials.write_secret(target, previous, username="Translation API")
            raise
        from haizflow.services import translation_privacy

        try:
            translation_privacy.forget(identifier)
        except OSError:
            pass  # Removed connection IDs cannot reuse a stale consent.
        return True
