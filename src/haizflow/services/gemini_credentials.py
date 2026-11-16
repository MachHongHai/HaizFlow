"""Read-only Gemini key verification. Never send subtitles or generate content."""
import json
from http.client import HTTPException
from urllib import error, request

from haizflow.services.api_translation import _connection_failure, _NoRedirect, _response_error_status

_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
_MAX_BYTES = 256 * 1024


def _failure(status, payload):
    fault = payload.get("error") if isinstance(payload, dict) else None
    details = fault.get("details", []) if isinstance(fault, dict) else []
    reasons = {item["reason"] for item in details if isinstance(item, dict)
               and isinstance(item.get("reason"), str)} if isinstance(details, list) else set()
    if status == 400 and reasons.intersection({"API_KEY_INVALID", "API_KEY_EXPIRED"}):
        return "invalid"
    if status == 403:
        return "permissions"
    return _connection_failure(status)


def check_key(key):
    key = str(key or "").strip()
    if not key or any(not 33 <= ord(char) <= 126 for char in key):
        return "invalid"
    outgoing = request.Request(_URL, headers={"x-goog-api-key": key, "Cache-Control": "no-cache"}, method="GET")
    try:
        with request.build_opener(_NoRedirect()).open(outgoing, timeout=15) as response:
            raw = response.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            return "unavailable"
        answer = json.loads(raw)
        fault = _response_error_status(answer)
        if fault is not None:
            return _failure(fault, answer)
        if not isinstance(answer, dict) or not isinstance(answer.get("models"), list):
            return "unsupported-check"
        if any(not isinstance(row, dict) or not isinstance(row.get("name"), str) for row in answer["models"]):
            return "unsupported-check"
        return "verified"
    except error.HTTPError as exc:
        status = exc.code
        try:
            raw = exc.read(_MAX_BYTES + 1)
            payload = json.loads(raw) if len(raw) <= _MAX_BYTES else {}
        except (OSError, ValueError, HTTPException):
            payload = {}
        finally:
            exc.close()
        return _failure(status, payload)
    except (ValueError, TypeError, error.URLError, TimeoutError, OSError, HTTPException):
        return "unavailable"
