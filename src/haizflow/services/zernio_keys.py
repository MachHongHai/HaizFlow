"""Named Zernio credentials; metadata stays portable, secrets stay in Windows."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.services import secure_credentials

CREDENTIAL_TARGET = "HaizFlow/Zernio/APIKey"
INDEX_PATH = Path(RUNTIME_DATA_DIR) / "zernio-api-keys.json"
_LOCK = threading.RLock()


def _index():
    try:
        value = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    entries, seen = [], set()
    for item in value.get("keys", []) if isinstance(value.get("keys"), list) else []:
        if (isinstance(item, dict) and re.fullmatch(r"[0-9a-f]{32}", str(item.get("id", "")))
            and isinstance(item.get("label"), str) and 0 < len(item["label"]) <= 64 and item["id"] not in seen):
            entries.append({"id": item["id"], "label": item["label"]})
            seen.add(item["id"])
    active = str(value.get("active", "legacy"))
    return {"active": active if active == "legacy" or active in seen else "", "keys": entries}


def _save(index):
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".zernio-keys-", suffix=".tmp", dir=INDEX_PATH.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(index, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, INDEX_PATH)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _target(key_id):
    if key_id == "legacy":
        return CREDENTIAL_TARGET
    if not re.fullmatch(r"[0-9a-f]{32}", str(key_id)):
        raise ValueError("Không tìm thấy API key đã chọn.")
    return f"{CREDENTIAL_TARGET}/{key_id}"


def list_keys():
    with _LOCK:
        index = _index()
        legacy = [{"id": "legacy", "label": "Zernio"}] if secure_credentials.read_secret(CREDENTIAL_TARGET).strip() else []
        return [{**item, "active": item["id"] == index["active"]} for item in legacy + index["keys"]]


def key_value(key_id):
    with _LOCK:
        index = _index()
        if key_id != "legacy" and not any(item["id"] == key_id for item in index["keys"]):
            raise ValueError("Không tìm thấy API key đã chọn.")
        value = secure_credentials.read_secret(_target(key_id)).strip()
        if not value:
            raise ValueError("API key này không còn trong Windows Credential Manager.")
        return value


def active_key():
    with _LOCK:
        active = _index()["active"]
        return secure_credentials.read_secret(_target(active)).strip() if active else ""


def active_id():
    with _LOCK:
        return _index()["active"]


def add_named_key(label, value):
    name = str(label or "").strip()
    if not name or len(name) > 64:
        raise ValueError("Đặt tên key từ 1 đến 64 ký tự.")
    with _LOCK:
        index = _index()
        key_id = uuid.uuid4().hex
        target = _target(key_id)
        secure_credentials.write_secret(target, value, username="Zernio API")
        index["keys"].append({"id": key_id, "label": name})
        index["active"] = key_id
        try:
            _save(index)
        except OSError:
            secure_credentials.delete_secret(target)
            raise
        return key_id


def select_key(key_id):
    with _LOCK:
        key_value(key_id)
        index = _index()
        index["active"] = key_id
        _save(index)


def save_legacy_key(value):
    with _LOCK:
        previous = secure_credentials.read_secret(CREDENTIAL_TARGET)
        secure_credentials.write_secret(CREDENTIAL_TARGET, value, username="Zernio API")
        index = _index()
        index["active"] = "legacy"
        try:
            _save(index)
        except OSError:
            if previous:
                secure_credentials.write_secret(CREDENTIAL_TARGET, previous, username="Zernio API")
            else:
                secure_credentials.delete_secret(CREDENTIAL_TARGET)
            raise


def remove_key(key_id):
    with _LOCK:
        index = _index()
        if key_id != "legacy" and not any(item["id"] == key_id for item in index["keys"]):
            return False
        target = _target(key_id)
        previous = secure_credentials.read_secret(target)
        deleted = secure_credentials.delete_secret(target)
        index["keys"] = [item for item in index["keys"] if item["id"] != key_id]
        if index["active"] == key_id:
            index["active"] = ""
        try:
            _save(index)
        except OSError:
            if deleted and previous:
                secure_credentials.write_secret(target, previous, username="Zernio API")
            raise
        return bool(deleted)
