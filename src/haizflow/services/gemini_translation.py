"""Bounded, per-project subtitle translation through the Gemini REST API."""

from __future__ import annotations

import json
import os
import random
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib import error, request

from haizflow.pipeline.process_registry import check_cancellation
from haizflow.config import RUNTIME_DATA_DIR
from haizflow.services import secure_credentials
from haizflow.services.video_store import log_to_video

CREDENTIAL_TARGET = "HaizFlow/Gemini/APIKey"
API_KEYS_URL = "https://aistudio.google.com/api-keys"
MODELS = {
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
    "gemini-3.8-flash": "Gemini 3.8 Flash",
}
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_KEYS_PATH = Path(RUNTIME_DATA_DIR) / "gemini-api-keys.json"
_KEYS_LOCK = threading.RLock()


def _key_index() -> dict:
    try:
        data = json.loads(_KEYS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    entries = data.get("keys") if isinstance(data, dict) else []
    keys = [
        {"id": entry["id"], "label": entry["label"]}
        for entry in entries if isinstance(entry, dict)
        and isinstance(entry.get("id"), str) and isinstance(entry.get("label"), str)
        and entry["id"] and entry["label"]
    ] if isinstance(entries, list) else []
    return {"active": str(data.get("active") or "legacy") if isinstance(data, dict) else "legacy", "keys": keys}


def _save_key_index(index: dict) -> None:
    _KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".gemini-keys-", suffix=".tmp", dir=_KEYS_PATH.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(index, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, _KEYS_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _credential_target(key_id: str) -> str:
    return CREDENTIAL_TARGET if key_id == "legacy" else f"{CREDENTIAL_TARGET}/{key_id}"


def list_keys() -> list[dict[str, str | bool]]:
    """Return labels and active state only; secrets never cross into QML."""
    with _KEYS_LOCK:
        index = _key_index()
        entries = [{"id": "legacy", "label": "Key mặc định"}] if secure_credentials.read_secret(CREDENTIAL_TARGET).strip() else []
        entries += index["keys"]
        return [{**entry, "active": entry["id"] == index["active"]} for entry in entries]


def active_key() -> str:
    with _KEYS_LOCK:
        index = _key_index()
        return secure_credentials.read_secret(_credential_target(index["active"])).strip()


def add_named_key(label: str, value: str) -> str:
    name = str(label or "").strip()
    if not name or len(name) > 64:
        raise ValueError("Đặt tên key từ 1 đến 64 ký tự.")
    key = str(value or "").strip()
    if not key or any(character.isspace() for character in key):
        raise ValueError("API key không hợp lệ. Hãy sao chép lại từ Google AI Studio.")
    with _KEYS_LOCK:
        index = _key_index()
        key_id = uuid.uuid4().hex
        target = _credential_target(key_id)
        secure_credentials.write_secret(target, key, username="Gemini API")
        index["keys"].append({"id": key_id, "label": name})
        index["active"] = key_id
        try:
            _save_key_index(index)
        except OSError:
            secure_credentials.delete_secret(target)
            raise
        return key_id


def select_key(key_id: str) -> None:
    with _KEYS_LOCK:
        index = _key_index()
        known = {entry["id"] for entry in index["keys"]}
        if key_id not in known and key_id != "legacy":
            raise ValueError("Không tìm thấy API key đã chọn.")
        if not secure_credentials.read_secret(_credential_target(key_id)).strip():
            raise ValueError("API key này không còn trong Windows Credential Manager.")
        index["active"] = key_id
        _save_key_index(index)


def remove_key(key_id: str) -> bool:
    with _KEYS_LOCK:
        index = _key_index()
        if key_id != "legacy" and not any(entry["id"] == key_id for entry in index["keys"]):
            return False
        index["keys"] = [entry for entry in index["keys"] if entry["id"] != key_id]
        if index["active"] == key_id:
            index["active"] = index["keys"][0]["id"] if index["keys"] else "legacy"
        target = _credential_target(key_id)
        previous_secret = secure_credentials.read_secret(target)
        deleted = secure_credentials.delete_secret(target)
        try:
            _save_key_index(index)
        except OSError:
            if deleted and previous_secret:
                secure_credentials.write_secret(target, previous_secret, username="Gemini API")
            raise
        return deleted


def key_configured() -> bool:
    return bool(active_key())


def save_key(value: str) -> None:
    key = str(value or "").strip()
    if not key or any(character.isspace() for character in key):
        raise ValueError("API key không hợp lệ. Hãy sao chép lại từ Google AI Studio.")
    with _KEYS_LOCK:
        secure_credentials.write_secret(CREDENTIAL_TARGET, key, username="Gemini API")
        index = _key_index()
        index["active"] = "legacy"
        _save_key_index(index)


def clear_key() -> bool:
    return remove_key("legacy")


def _chunks(texts: list[str]):
    chunk: list[tuple[int, str]] = []
    chars = 0
    for index, text in enumerate(texts):
        if chunk and (len(chunk) >= 24 or chars + len(text) > 4000):
            yield chunk
            chunk, chars = [], 0
        chunk.append((index, text))
        chars += len(text)
    if chunk:
        yield chunk


def _request_chunk(
    chunk: list[tuple[int, str]], *, key: str, model: str,
    source_language: str, target_language: str,
) -> list[str]:
    entries = [{"id": index, "text": text} for index, text in chunk]
    payload = {
        "systemInstruction": {"parts": [{"text": (
            "Translate each subtitle into " + target_language + ". Source language: "
            + source_language + ". Keep the same id and order. Preserve meaning, "
            "speaker tone, names and punctuation. Return only concise translations; "
            "never merge, omit or invent a subtitle."
        )}]},
        "contents": [{"role": "user", "parts": [{
            "text": json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
        }]}],
        "generationConfig": {
            "temperature": 0.1,
            "candidateCount": 1,
            # A cap does not prepay tokens. Leave room for language expansion,
            # JSON framing and low-level reasoning so the last cue is not cut.
            "maxOutputTokens": min(8192, max(1024, sum(len(text) for _, text in chunk) * 4)),
            "thinkingConfig": {"thinkingLevel": "minimal" if model == "gemini-3.5-flash-lite" else "low"},
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {"translations": {"type": "ARRAY", "items": {
                    "type": "OBJECT", "properties": {
                        "id": {"type": "INTEGER"}, "text": {"type": "STRING"}},
                    "required": ["id", "text"]}}},
                "required": ["translations"],
            },
        },
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    url = _ENDPOINT.format(model=model)
    for attempt in range(3):
        try:
            outgoing = request.Request(
                url, data=body,
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
                method="POST",
            )
            with request.urlopen(outgoing, timeout=90) as response:
                answer = json.load(response)
            parts = answer["candidates"][0]["content"]["parts"]
            parsed = json.loads("".join(str(part.get("text", "")) for part in parts))
            translations = parsed["translations"]
            if not isinstance(translations, list) or len(translations) != len(chunk):
                raise RuntimeError("Gemini trả về thiếu câu dịch. Dữ liệu cũ được giữ nguyên.")
            expected = [index for index, _ in chunk]
            ids = [item.get("id") for item in translations]
            output = [str(item.get("text") or "").strip() for item in translations]
            if ids != expected or not all(output):
                raise RuntimeError("Gemini trả về sai thứ tự hoặc câu dịch rỗng. Dữ liệu cũ được giữ nguyên.")
            return output
        except error.HTTPError as exc:
            if exc.code in {408, 429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(min(8, 2 ** attempt + random.random()))
                continue
            if exc.code in {401, 403}:
                raise RuntimeError(
                    "Gemini từ chối quyền truy cập (HTTP " + str(exc.code) + "). "
                    "Kiểm tra API key, quyền dùng model và thanh toán trong Google AI Studio."
                ) from None
            if exc.code == 402:
                raise RuntimeError(
                    "Gemini yêu cầu thanh toán (HTTP 402). Kiểm tra số dư và Billing trong Google AI Studio."
                ) from None
            if exc.code == 429:
                raise RuntimeError(
                    "Gemini đã hết quota hoặc đang giới hạn tốc độ. Thử lại sau trong Google AI Studio."
                ) from None
            if exc.code == 503:
                raise RuntimeError(
                    "Gemini tạm thời không khả dụng (HTTP 503 UNAVAILABLE) sau khi thử lại. "
                    "Thử lại sau hoặc chọn Gemini 3.1 Flash-Lite. Mã 503 không xác nhận lỗi thanh toán; "
                    "kiểm tra quyền truy cập, quota và Billing trong Google AI Studio."
                ) from None
            raise RuntimeError(f"Gemini không xử lý được yêu cầu (HTTP {exc.code}).") from None
        except (error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(min(8, 2 ** attempt + random.random()))
                continue
            raise RuntimeError("Không kết nối được Gemini. Kiểm tra mạng rồi thử lại.") from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise RuntimeError("Gemini không trả về dữ liệu dịch hợp lệ. Dữ liệu cũ được giữ nguyên.") from None
    raise RuntimeError("Gemini không phản hồi sau các lần thử.")


def translate_texts(
    texts: list[str], *, model: str, source_language: str,
    target_language: str, video_id: str, progress_callback=None,
) -> list[str]:
    if model not in MODELS:
        raise ValueError("Model Gemini không được hỗ trợ.")
    key = active_key()
    if not key:
        raise RuntimeError("Chưa có Gemini API key. Vào Cài đặt → Quản lý API Key để thêm key.")
    output = [""] * len(texts)
    for chunk in _chunks(texts):
        check_cancellation(video_id)
        detail = f"Sending Gemini translation batch: sentences {chunk[0][0] + 1}-{chunk[-1][0] + 1} of {len(texts)}."
        log_to_video(video_id, detail, component="TRANSLATE", level="INFO")
        if progress_callback:
            progress_callback(chunk[0][0], len(texts), detail)
        values = _request_chunk(
            chunk, key=key, model=model,
            source_language=source_language, target_language=target_language,
        )
        for (index, _), value in zip(chunk, values):
            output[index] = value
        log_to_video(
            video_id, f"Gemini translated {chunk[-1][0] + 1} of {len(texts)} sentences.",
            component="TRANSLATE", level="INFO",
        )
        if progress_callback:
            progress_callback(chunk[-1][0] + 1, len(texts), "Đang dịch bằng Gemini")
    return output
