"""Translation choices shared by schemas, UI, resource guards and workers."""
from __future__ import annotations

import re

LOCAL_MODELS = frozenset({"auto", "q4", "full"})
GEMINI_MODELS = frozenset({"gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash"})
_API_MODEL = re.compile(
    r"api:[a-f0-9]{32}(?::[A-Za-z0-9@~][A-Za-z0-9._:/@+~-]{0,199}(?:#(?:json_object|json_schema|prompt))?)?\Z")


def is_api_model(value: str) -> bool:
    return bool(_API_MODEL.fullmatch(str(value)))


def is_cloud_model(value: str) -> bool:
    return value in GEMINI_MODELS or is_api_model(value)


def normalize_translation_model(value: str | None) -> str:
    """Normalize built-in enums, never case-fold opaque provider model IDs."""
    value = str(value or "auto").strip()
    return value if value.startswith("api:") else value.lower()


def valid_translation_model(value: str) -> str:
    if value not in LOCAL_MODELS | GEMINI_MODELS and not is_api_model(value):
        raise ValueError("Unsupported translation model.")
    return value


def translation_provider(value: str) -> str:
    return "api" if is_api_model(value) else "gemini" if value in GEMINI_MODELS else "hymt2"
