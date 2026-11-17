"""Opt-in live free-model translation audit with synthetic text and zero-price routing."""
from __future__ import annotations

import argparse
import json
import re
import time
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib import error, request

from haizflow.services import (
    api_translation,
    gemini_translation,
    translation_catalog_cache,
    translation_connections,
    translation_privacy,
    translation_reasoning_catalog,
)
from haizflow.services.translation_model_catalog import _option, _pricing_kind
from haizflow.utils.atomic_file import atomic_json

BASE = "https://openrouter.ai/api/v1"


def translation_warnings(translated):
    """Synthetic English-to-Vietnamese probes contain no foreign-script names."""
    return (["unexpected_script"] if any(re.search(
        r"[\u0400-\u052f\u0600-\u06ff\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text,
    ) for text in translated) else [])


def public_json(path):
    with request.urlopen(BASE + path, timeout=25) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("Public catalogue is larger than expected")
    return json.loads(raw)


def check(profile, key, option, *, allow_collection=False, extended=False, probe_unavailable=False, preflight=False,
          batch_size=None, timeout=75, start_id=0):
    profile = {**profile, "model": option["value"], "format": option["output_format"]}
    actual_json = api_translation._json_request
    result = {"model": option["value"], "format": option["output_format"],
              "data_collection": "allow" if allow_collection else "deny", "requests": 0}
    public_info = option.get("reasoning_capabilities") or {}
    capability = ({"parameter": "reasoning.enabled" if public_info.get("toggle") else "reasoning.effort",
                   **public_info} if public_info else None)

    def send(url, credential, payload=None, **kwargs):
        if preflight and payload is None and not credential and url.startswith(BASE + "/model"):
            return actual_json(url, "", timeout=min(12, kwargs.get("timeout", 12)))
        if url != BASE + "/chat/completions" or payload is None or payload.get("model") != option["value"]:
            raise RuntimeError("Audit refused a non-translation request")
        if result["requests"]:
            raise RuntimeError("Audit suppressed automatic retry")
        result["requests"] += 1
        payload["provider"]["max_price"] = {"prompt": 0, "completion": 0, "request": 0}
        result["max_tokens"] = payload.get("max_tokens")
        result["output_budget"] = "provider_default" if "max_tokens" not in payload else "explicit"
        try:
            answer = actual_json(url, credential, payload, timeout=min(timeout, kwargs.get("timeout", timeout)))
            result["http_status"] = 200
            fault = api_translation._response_error_status(answer)
            if fault:
                result["http_status"] = fault
                result["failure_kind"] = api_translation._request_failure_kind(answer)
            result["diagnostic"] = api_translation._response_diagnostic(answer, "openrouter")
            return answer
        except api_translation._TransportResponseError as exc:
            result["transport"] = {"reason": exc.reason, "body_bytes": exc.byte_count,
                                   "content_type": exc.content_type}
            raise
        except error.HTTPError as exc:
            raw = exc.read(65537)
            result["http_status"] = exc.code
            try:
                answer = json.loads(raw) if len(raw) <= 65536 else {}
            except ValueError:
                answer = {}
            result["failure_kind"] = api_translation._request_failure_kind(answer)
            # Restore the bounded body for the production error classifier.
            import io
            replacement = error.HTTPError(exc.url, exc.code, exc.reason, exc.headers, io.BytesIO(raw))
            exc.close()
            raise replacement from None

    started = time.monotonic()
    probe = (patch("haizflow.services.translation_model_catalog._UNAVAILABLE_OPENROUTER_MODELS", frozenset())
             if probe_unavailable else nullcontext())
    with probe, patch.object(api_translation, "_json_request", send), \
            patch.object(translation_catalog_cache, "protocol_for", lambda _model: option), \
            patch.object(translation_reasoning_catalog, "get", lambda _model: capability), \
            patch.object(translation_privacy, "allowed", lambda _profile: allow_collection), \
            patch.object(gemini_translation, "_retry_delay", lambda *_: None):
        try:
            protocol = None
            if preflight:
                from haizflow.services.translation_model_guard import prepare

                protocol = prepare(profile)
                result["preflight"] = "passed"
            samples = ["Thank you, Mom.", "I don't know."]
            if extended or batch_size and batch_size >= 6:
                samples += ["Please don't open the door.", "The red car costs 90,000 dollars.",
                            "We will meet tomorrow at three.", "My sister gave me this book."]
            if batch_size and batch_size >= 12:
                samples += ["You are my brother.", "I will call you tonight.", "Please wait for me outside.",
                            "This is not your fault.", "We have only twelve pounds.", "Could I sit here?"]
            result["sentences"] = len(samples)
            translated = api_translation._request_chunk(profile,
                list(enumerate(samples, start=start_id)), key=key,
                model="api:" + profile["id"] + ":" + option["value"],
                # Match services.translation: it passes language names, not
                # two-letter metadata codes, to the cloud prompt.
                source_language="English", target_language="Vietnamese", translation_style="natural",
                _protocol=protocol)
            result["translations"] = translated
            result["protocol_valid"] = True
            result["quality_warnings"] = translation_warnings(translated)
            joined = json.dumps(translated, ensure_ascii=False).casefold()
            result["usable"] = ("thank you" not in joined and "don't know" not in joined
                                and any(word in joined for word in ("cảm", "cám", "mẹ", "má"))
                                and any(word in joined for word in ("không", "chẳng"))
                                and not result["quality_warnings"])
            if not result["usable"]:
                result["failure_kind"] = "translation_quality"
        except (RuntimeError, ValueError) as exc:
            result["usable"] = False
            if "quyền thu thập dữ liệu" in str(exc):
                result["failure_kind"] = "data_policy"
            # Application messages are sanitized; never persist raw service bodies.
            result["message"] = str(exc)[:500]
    result["seconds"] = round(time.monotonic() - started, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", action="store_true")
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--batch-size", type=int, choices=[2, 6, 12])
    parser.add_argument("--request-timeout", type=int, choices=[75, 90, 240], default=75)
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--preflight", action="store_true",
                        help="Use the production live model and serving-endpoint compatibility guard")
    parser.add_argument("--probe-unavailable", action="store_true",
                        help="Recheck temporarily hidden routes without changing the app catalogue")
    parser.add_argument("--allow-synthetic-data-collection", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("build/openrouter-free-audit-20261115.json"))
    args = parser.parse_args()
    rows = public_json("/models").get("data", [])
    scope = (patch("haizflow.services.translation_model_catalog._UNAVAILABLE_OPENROUTER_MODELS", frozenset())
             if args.probe_unavailable else nullcontext())
    with scope:
        free = [option for row in rows if _pricing_kind(row.get("pricing")) == "free"
                and (option := _option("openrouter", row)) is not None]
    if args.model:
        free = [option for option in free if option["value"] in args.model]
        if set(args.model) != {row["value"] for row in free}:
            parser.error("Every requested model must be currently free and text/JSON compatible")
    report = {"checked_at": datetime.now(UTC).isoformat(), "models": []}
    if not args.inference:
        print(json.dumps(free, ensure_ascii=True, indent=2))
        return
    if args.start_id < 0:
        parser.error("Start ID must be non-negative")
    try:
        profile, key = translation_connections.active_connection("openrouter", with_key=True)
    except ValueError:
        parser.error("No active configured OpenRouter connection")
    limits = api_translation._json_request(BASE + "/key", key).get("data", {}).get("free_model_daily_requests")
    if isinstance(limits, dict):
        report["free_requests_before"] = {field: limits.get(field) for field in ("used", "limit", "remaining")}
        if isinstance(limits.get("remaining"), int) and limits["remaining"] < len(free):
            parser.error("Insufficient remaining free requests for this audit; no inference was sent")
    for option in free:
        result = check(profile, key, option, extended=args.extended, probe_unavailable=args.probe_unavailable,
                       allow_collection=translation_privacy.allowed({**profile, "model": option["value"]}),
                       preflight=args.preflight, batch_size=args.batch_size, timeout=args.request_timeout,
                       start_id=args.start_id)
        report["models"].append(result)
        atomic_json(args.output, report, indent=2)
        print(json.dumps(result, ensure_ascii=True), flush=True)
        if (not result["usable"] and result.get("failure_kind") == "data_policy"
                and args.allow_synthetic_data_collection):
            result["collection_check"] = check(profile, key, option, allow_collection=True, extended=args.extended,
                                               probe_unavailable=args.probe_unavailable, preflight=args.preflight,
                                               batch_size=args.batch_size, timeout=args.request_timeout,
                                               start_id=args.start_id)
            atomic_json(args.output, report, indent=2)
            print(json.dumps(result["collection_check"], ensure_ascii=True), flush=True)
        if result.get("http_status") == 429 and "trong ngày" in result.get("message", ""):
            break


if __name__ == "__main__":
    main()
