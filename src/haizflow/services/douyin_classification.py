"""Semantic response classification, independent of retry and network libraries."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum


class Outcome(StrEnum):
    SUCCESS = "success"
    UNAVAILABLE = "private_removed_unavailable"
    RISK = "risk_control"
    SIGNATURE = "signature_session_rejected"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network_transient"
    UPSTREAM = "upstream_format_changed"
    METADATA = "invalid_metadata"
    MEDIA_EXPIRED = "media_expired"
    CHALLENGE = "verification_required"


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    retryable: bool = False
    payload: dict | None = None


def classify(response, *, list_endpoint=False) -> Verdict:
    body = response.body
    head = body[:4096].decode("utf-8", "replace").lower()
    try:
        payload = json.loads(body)
    except (ValueError, RecursionError):
        payload = None
    if not isinstance(payload, dict):
        payload = None
    # Never scan a successful video's title/description for CAPTCHA/private words.
    status_values = [payload.get(k) for k in ("status_code", "statusCode", "error_code")] if payload else []
    codes = [int(v) for v in status_values if not isinstance(v, bool) and str(v).lstrip("-").isdigit()]
    code = next((v for v in codes if v), 0)
    if code in {2053, 2, 10204} or response.status in {404, 410, 451}:
        return Verdict(Outcome.UNAVAILABLE)
    reason = payload.get("filter_detail") if payload else None
    if (payload and not payload.get("aweme_detail") and isinstance(reason, dict)
            and (reason.get("filter_reason") or reason.get("detail_msg"))):
        return Verdict(Outcome.UNAVAILABLE)
    if response.status == 429:
        return Verdict(Outcome.RATE_LIMIT, True)
    if response.status >= 500 or response.status in {407, 408}:
        return Verdict(Outcome.NETWORK, True)
    if response.status in {401, 403, 412} and any(m in head for m in (
            "uifid not found", "signature not found", "sign invalid", "sign expired")):
        return Verdict(Outcome.SIGNATURE, True)
    if not payload or code:
        if any(m in head for m in ("captcha", "verify_center", "slide_verify", "verify_page")):
            return Verdict(Outcome.CHALLENGE)
    if response.status in {401, 403, 405, 412, 444} or code in {2483, 10000}:
        return Verdict(Outcome.RISK, True)
    if response.status >= 400:
        return Verdict(Outcome.UNAVAILABLE)
    if not body.strip() or body.strip() in {b"{}", b"null"}:
        return Verdict(Outcome.RISK, True)
    if payload is None:
        return Verdict(Outcome.UPSTREAM)
    if code:
        # Unknown business codes are not guessed to be a deleted video.
        return Verdict(Outcome.METADATA)
    key = "aweme_list" if list_endpoint else "aweme_detail"
    if key not in payload or payload[key] is None or (not list_endpoint and not payload[key]):
        return Verdict(Outcome.RISK, True)
    if not isinstance(payload[key], list if list_endpoint else dict):
        return Verdict(Outcome.UPSTREAM)
    if list_endpoint and ("has_more" not in payload or "max_cursor" not in payload):
        return Verdict(Outcome.UPSTREAM)
    return Verdict(Outcome.SUCCESS, payload=payload)


MESSAGES = {
    Outcome.UNAVAILABLE: "Douyin: this video or profile is private, removed or unavailable.",
    Outcome.RISK: "Douyin withheld the video data. Create a Douyin session, then try again.",
    Outcome.SIGNATURE: "Douyin rejected the session signature. Create a Douyin session, then try again.",
    Outcome.RATE_LIMIT: "Douyin is limiting requests. Wait a moment before trying again.",
    Outcome.NETWORK: "Could not reach Douyin. Check the connection and try again.",
    Outcome.UPSTREAM: "Douyin returned an unexpected response format.",
    Outcome.METADATA: "Douyin returned unusable video data.",
    Outcome.MEDIA_EXPIRED: "The Douyin video link expired. Retry to refresh it.",
    Outcome.CHALLENGE: "Douyin requires verification. HaizFlow does not solve verification challenges.",
}


class DouyinError(RuntimeError):
    def __init__(self, outcome: Outcome):
        self.outcome = outcome
        super().__init__(MESSAGES[outcome])
