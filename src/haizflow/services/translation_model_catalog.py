"""Bounded, read-only model discovery. Never invokes inference or persists keys."""
from __future__ import annotations

import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib import error, parse

from haizflow.services import translation_connections as connections

PRESETS = {
    "openai": (
        ("gpt-6-luna", "GPT-6 Luna"),
        ("gpt-6.1-sol", "GPT-6.1 Sol"),
        ("gpt-6.1-terra", "GPT-6.1 Terra"),
        ("gpt-6-astra", "GPT-6 Astra"),
    ),
    "deepseek": (("deepseek-flash", "DeepSeek Flash"), ("deepseek-v4-pro", "DeepSeek V4 Pro")),
}
_MODEL = re.compile(r"[A-Za-z0-9@~][A-Za-z0-9._:/@+~-]{0,199}\Z")
_NON_TEXT = re.compile(
    r"audio|tts|transcrib|whisper|realtime|embed|moderation|dall-e|image|sora|video|search|diariz",
    re.IGNORECASE,
)
# Public catalogue and endpoint audit, 2026-11-03: historical pages remain,
# but these free variants have no serving endpoints. Do not resurrect them
# from an older public cache or a saved connection's default model.
_RETIRED_OPENROUTER_MODELS = frozenset({
    "deepseek/deepseek-r1:free", "deepseek/deepseek-r1-0528:free",
})


def presets(provider):
    return [{"value": model, "label": label} for model, label in PRESETS.get(provider, ())]


def _pricing_kind(pricing):
    if not isinstance(pricing, dict):
        return "unknown"
    try:
        amounts = [Decimal(str(pricing[key])) for key in ("prompt", "completion")]
        amounts.append(Decimal(str(pricing.get("request", "0"))))
        if any(not value.is_finite() or value < 0 for value in amounts):
            return "unknown"
        return "paid" if any(value > 0 for value in amounts) else "free"
    except (KeyError, InvalidOperation, ValueError):
        return "unknown"


def _option(provider, row):
    if not isinstance(row, dict):
        return None
    model = row.get("id")
    if not isinstance(model, str) or not _MODEL.fullmatch(model):
        return None
    expiration = row.get("expiration_date") or row.get("shutdown_date")
    if isinstance(expiration, str) and expiration[:10] <= date.today().isoformat():
        return None
    if _NON_TEXT.search(model):
        return None
    if provider == "openai":
        # /models does not advertise endpoint/JSON capabilities. Omit legacy chat,
        # fine-tuned IDs and routing aliases rather than presenting them as compatible.
        supported = re.match(r"^(?:gpt-(?:[5-9]|[1-9][0-9])(?:[.-]|$)|gpt-4\.1(?:-|$)|o[3-9](?:-|$))", model)
        supported = supported or model in {"gpt-4o", "gpt-4o-mini", "o1"}
        supported = supported or re.match(r"^gpt-4o-mini-2024-07-18$|^gpt-4o-2024-(?:08-06|11-20)$", model)
        if not supported:
            return None
    if provider == "openrouter":
        if model in _RETIRED_OPENROUTER_MODELS:
            return None
        architecture = row.get("architecture")
        if not isinstance(architecture, dict):
            return None
        inputs, outputs = architecture.get("input_modalities"), architecture.get("output_modalities")
        if (not isinstance(inputs, list) or not isinstance(outputs, list)
                or "text" not in inputs or outputs != ["text"]):
            return None
        parameters = row.get("supported_parameters", [])
        if not isinstance(parameters, list):
            return None
        # Free text models with JSON mode still pass the same strict post-
        # validation. Never send a JSON Schema to an endpoint advertising only
        # response_format, or silently downgrade an unknown/paid model.
        if "structured_outputs" in parameters:
            output_format = "json_schema"
        elif _pricing_kind(row.get("pricing")) == "free" and "response_format" in parameters:
            output_format = "json_object"
        else:
            return None
        if model in {"openrouter/auto", "openrouter/free"} or model.startswith("openrouter/"):
            return None  # Do not turn an explicit model choice into automatic model routing.
    known = dict(PRESETS.get(provider, ()))
    name = known.get(model, row.get("name", model))
    if not isinstance(name, str):
        name = model
    name = " ".join(name.split())[:120]
    option = {"value": model, "label": name or model}
    if provider == "openrouter":
        from haizflow.services.translation_reasoning_catalog import advertised
        option["pricing_kind"] = _pricing_kind(row.get("pricing"))
        option["output_format"] = output_format
        info = advertised(row.get("reasoning"))
        if info is not None:
            option["reasoning_capabilities"] = info
    return option


def fetch_models(provider, key, base_url="", *, cancelled=None):
    """Return (safe options, state); bounded pagination, no raw service errors."""
    from haizflow.services.api_translation import _json_request

    if (provider not in connections.PROVIDERS or not key or len(key) > 4096
            or any(ord(char) < 33 or ord(char) > 126 for char in key)):
        return [], "invalid"
    try:
        base = connections.normalized_url(base_url if provider == "custom"
                                          else connections.PROVIDERS[provider]["base_url"])
    except ValueError:
        return [], "invalid"
    rows = {}
    truncated = False
    deadline = time.monotonic() + 40
    try:
        for page in range(10 if provider == "openrouter" else 1):
            if cancelled and cancelled.is_set():
                return [], "cancelled"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return list(rows.values()), "partial" if rows else "error"
            url = base + "/models"
            if provider == "openrouter":
                url += "?" + parse.urlencode({"offset": page * 100, "limit": 100,
                    "input_modalities": "text", "output_modalities": "text"})
            data = _json_request(url, key, timeout=min(12, remaining))
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                return list(rows.values()), "partial" if rows else "error"
            batch = data["data"]
            if len(batch) > 10000:
                return list(rows.values()), "partial" if rows else "error"
            before = len(rows)
            for row in batch:
                option = _option(provider, row)
                if option:
                    if len(rows) < 1000 or option["value"] in rows:
                        rows[option["value"]] = option
                    else:
                        truncated = True
            if provider == "openrouter":
                from haizflow.services.translation_reasoning_catalog import remember
                remember(list(rows.values()))
            if provider != "openrouter" or len(batch) < 100:
                options = sorted(rows.values(), key=lambda row: row["label"].casefold())
                return options, "partial" if truncated else "ready"
            if len(rows) == before and page > 0:
                break  # A server ignoring offset must not cause repeated requests forever.
    except error.HTTPError as exc:
        status = exc.code
        exc.close()
        state = "auth" if status in {401, 403} else "unsupported" if status in {404, 405} else "error"
        return list(rows.values()), "partial" if rows else state
    except (OSError, ValueError, TypeError):
        return list(rows.values()), "partial" if rows else "error"
    return sorted(rows.values(), key=lambda row: row["label"].casefold()), "partial"
