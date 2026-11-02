"""Text-only translation adapters. No audio, tools, uploads or automatic model fallback."""
from __future__ import annotations

import json
import re
from http.client import HTTPException
from urllib import error, request

from haizflow.pipeline.process_registry import check_cancellation
from haizflow.services import gemini_translation, translation_connections
from haizflow.services.video_store import log_to_video

_MAX_RESPONSE = 2 * 1024 * 1024
_SCHEMA = {"type": "object", "properties": {"translations": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
    "required": ["id", "text"], "additionalProperties": False}}},
    "required": ["translations"], "additionalProperties": False}


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a credential to a redirected endpoint.


class _ResponseError(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _json_request(url, key, payload=None, *, timeout=90):
    outgoing = request.Request(url, data=None if payload is None else json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="GET" if payload is None else "POST")
    with request.build_opener(_NoRedirect()).open(outgoing, timeout=timeout) as response:
        raw = response.read(_MAX_RESPONSE + 1)
    if len(raw) > _MAX_RESPONSE:
        raise ValueError("API trả dữ liệu quá lớn; hãy giảm số câu mỗi yêu cầu.")
    return json.loads(raw)


def public_error(status: int, label: str) -> str:
    if status in {401, 403}:
        return f"{label}: API key không hợp lệ hoặc thiếu quyền dùng model (HTTP {status})."
    if status == 402:
        return f"{label}: không đủ số dư hoặc cần bật thanh toán (HTTP 402)."
    if status == 429:
        return f"{label}: hết quota hoặc đang giới hạn tốc độ (HTTP 429). Thử lại sau."
    if status in {400, 404, 422}:
        return f"{label}: Model ID, endpoint hoặc định dạng JSON không được hỗ trợ (HTTP {status})."
    if status in {408, 500, 502, 503, 504}:
        return f"{label}: dịch vụ tạm thời quá tải hoặc không phản hồi (HTTP {status})."
    if 300 <= status < 400:
        return f"{label}: endpoint chuyển hướng đã bị chặn để bảo vệ API key. Kiểm tra Base URL."
    return f"{label}: không xử lý được yêu cầu (HTTP {status})."


def _messages(gemini_payload):
    system = gemini_payload["systemInstruction"]["parts"][0]["text"]
    user = "\n".join(part["text"] for part in gemini_payload["contents"][0]["parts"])
    return system, user


def _model_error(status, profile):
    if status == 404 and profile["provider"] == "openrouter" and profile["model"].endswith(":free"):
        return ("OpenRouter: không có endpoint khả dụng cho model miễn phí đã chọn "
                "hoặc endpoint không hỗ trợ yêu cầu này (HTTP 404). "
                "Hãy tải lại danh sách và chọn model miễn phí khác; "
                "app không tự chuyển sang model tính phí.")
    return public_error(status, translation_connections.PROVIDERS[profile["provider"]]["label"])


def _response_error_status(answer):
    """Read allowlisted error codes only; never surface raw provider messages."""
    if not isinstance(answer, dict) or answer.get("error") is None:
        return None
    fault = answer["error"]
    code = fault.get("code") or fault.get("type") if isinstance(fault, dict) else None
    if type(code) is int and 400 <= code <= 599:
        return code
    if isinstance(code, str):
        if re.fullmatch(r"[45][0-9]{2}", code):
            return int(code)
        return {"invalid_api_key": 401, "authentication_error": 401,
                "permission_denied": 403, "model_not_found": 404,
                "insufficient_quota": 429, "rate_limit_exceeded": 429,
                "billing_hard_limit_reached": 402, "credit_balance_exhausted": 402,
                "context_length_exceeded": 400, "invalid_request_error": 400,
                "server_error": 500, "server_overloaded": 503}.get(code, 0)
    return 0


def _usage_counts(answer):
    if not isinstance(answer, dict) or not isinstance(answer.get("usage"), dict):
        return {}
    usage = answer["usage"]
    counts = {}
    for name, alternatives in {"input": ("input_tokens", "prompt_tokens"),
                               "output": ("output_tokens", "completion_tokens")}.items():
        for field in alternatives:
            value = usage.get(field)
            if type(value) is int and 0 <= value <= 10**9:
                counts[name] = value
                break
    details = usage.get("output_tokens_details") or usage.get("completion_tokens_details")
    if isinstance(details, dict):
        value = details.get("reasoning_tokens")
        if type(value) is int and 0 <= value <= 10**9:
            counts["reasoning"] = value
    if "output" in counts and "reasoning" in counts and counts["output"] >= counts["reasoning"]:
        counts["visible"] = counts["output"] - counts["reasoning"]
    return counts


def _log_usage(answer, label, video_id):
    if not video_id:
        return
    counts = _usage_counts(answer)
    if counts:
        try:
            summary = ", ".join(f"{key}={value}" for key, value in counts.items())
            log_to_video(video_id, label + " token usage: " + summary,
                         component="TRANSLATE", level="INFO")
        except (OSError, RuntimeError):
            pass  # Optional metrics must not discard an already-paid successful reply.


def _response_diagnostic(answer, provider):
    """Allowlisted state and counters only, never content/reasoning/provider errors."""
    state = "unknown"
    if isinstance(answer, dict):
        if provider == "openai":
            state = answer.get("status")
        else:
            choices = answer.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                state = choices[0].get("finish_reason")
    if not isinstance(state, str) or state not in {
        "stop", "length", "content_filter", "tool_calls", "completed", "incomplete", "failed"
    }:
        state = "unknown"
    counters = ", ".join(f"{key}={value}" for key, value in _usage_counts(answer).items())
    return "finish=" + state + (", " + counters if counters else "")


def _token_failure(answer):
    counts = _usage_counts(answer)
    return ("reasoning_budget_exhausted" if counts.get("reasoning", 0) > 0 and counts.get("visible") == 0
            else "token_limit")


def _request_chunk(profile, chunk, *, key, model, source_language, target_language, video_id="",
                   reasoning_effort="", **kwargs):
    from haizflow.services.translation_api_policy import request_limits, request_options

    label = translation_connections.PROVIDERS[profile["provider"]]["label"]
    source_payload = gemini_translation._payload_for_chunk(
        chunk, model=model, source_language=source_language, target_language=target_language,
        video_id=video_id, **kwargs)
    system, user = _messages(source_payload)
    schema = {"name": "subtitle_translation", "strict": True, "schema": _SCHEMA}
    limits = request_limits(profile["provider"], profile["model"],
                            source_payload["generationConfig"]["maxOutputTokens"], reasoning_effort)
    token_limit = limits["max_tokens"]
    if profile["provider"] == "openai":
        suffix = "/responses"
        payload = {"model": profile["model"], "instructions": system,
                   "input": [{"role": "user", "content": user}], "store": False,
                   "text": {"format": {"type": "json_schema", **schema}},
                   "max_output_tokens": token_limit}
    else:
        suffix = "/chat/completions"
        payload = {"model": profile["model"], "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": token_limit}
        output_format = profile["format"]
        if profile["provider"] == "openrouter":
            from haizflow.services.translation_catalog_cache import format_for

            output_format = format_for(profile["model"]) or output_format
        if output_format == "json_schema":
            payload["response_format"] = {"type": "json_schema", "json_schema": schema}
        elif output_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
            payload["messages"][0]["content"] += (
                ' Output shape: {"translations":[{"id":0,"text":"translated subtitle"}]}. '
                'Use the exact requested integer IDs; no other fields.')
        if profile["provider"] == "openrouter":
            payload["provider"] = {"require_parameters": True, "allow_fallbacks": True, "data_collection": "deny"}
    payload.update(request_options(profile["provider"], profile["model"], reasoning_effort))
    if video_id:
        try:
            log_to_video(video_id, f"{label} request budget: sentences={len(chunk)}, max_tokens={token_limit}, "
                         f"reasoning_required={limits['mandatory']}, timeout={limits['timeout']}s.",
                         component="TRANSLATE", level="INFO")
        except (OSError, RuntimeError):
            pass
    for attempt in range(3):
        check_cancellation(video_id)
        try:
            answer = _json_request(profile["base_url"] + suffix, key, payload,
                                   **({"timeout": limits["timeout"]} if limits["timeout"] != 90 else {}))
        except error.HTTPError as exc:
            if video_id:
                log_to_video(video_id, f"{label}: HTTP {exc.code}, attempt {attempt + 1}/3.",
                             level="WARNING", component="TRANSLATE")
            status = exc.code
            exc.close()
            if status in {408, 500, 502, 503, 504} and attempt < 2:
                gemini_translation._retry_delay(2 ** attempt, video_id)
                continue
            raise RuntimeError(_model_error(status, profile)) from None
        except (error.URLError, TimeoutError, OSError, HTTPException):
            # A lost POST response may already have incurred a charge. Do not
            # blindly resubmit it, or silently downgrade/change the chosen model.
            raise RuntimeError(f"{label}: mất kết nối hoặc quá thời gian. "
                               "Các câu đã hoàn thành được giữ lại.") from None
        except (TypeError, ValueError):
            raise RuntimeError(f"{label}: phản hồi không phải JSON hợp lệ. Dữ liệu cũ được giữ nguyên.") from None
        _log_usage(answer, label, video_id)
        status = _response_error_status(answer)
        if status is not None:
            # A HTTP-200 error can occur after generation started and incurred
            # a charge. Report its real category, never blindly submit again.
            message = _model_error(status, profile) if status else f"{label}: dịch vụ trả về lỗi không xác định."
            raise RuntimeError(message + " Các câu đã hoàn thành được giữ lại.")
        try:
            text = _response_text(answer, profile["provider"])
            # Reuse the exact ID/count/non-empty validation used for Gemini.
            envelope = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}
            return gemini_translation._parse_translations(envelope, chunk)
        except (TypeError, ValueError, KeyError, IndexError, AttributeError) as exc:
            reason = getattr(exc, "reason", "invalid_response")
            if video_id:
                try:
                    log_to_video(video_id, f"{label}: response={reason}; "
                                 f"{_response_diagnostic(answer, profile['provider'])}; max_tokens={token_limit}; "
                                 "rejected complete batch; no automatic paid retry.",
                                 level="WARNING", component="TRANSLATE")
                except (OSError, RuntimeError):
                    pass
            if reason in {"token_limit", "reasoning_budget_exhausted"}:
                detail = ("model dùng hết giới hạn token cho suy luận, chưa tạo được bản dịch"
                          if reason == "reasoning_budget_exhausted" else "bản dịch chưa hoàn tất vì hết giới hạn token")
                raise RuntimeError(f"{label}: {detail}. Các câu đã lưu được giữ nguyên; "
                                   "app không tự gửi lại yêu cầu để tránh tính phí thêm.") from None
            raise RuntimeError(f"{label}: bản dịch bị thiếu câu, sai ID, bị chặn hoặc chưa hoàn tất. "
                               "Các câu đã lưu được giữ nguyên; hãy kiểm tra model và thử tiếp tục.") from None
    raise RuntimeError(f"{label}: không phản hồi sau các lần thử.")


def _response_text(answer, provider):
    if not isinstance(answer, dict) or answer.get("error"):
        raise _ResponseError("invalid_response")
    if provider == "openai":
        if answer.get("status") != "completed":
            details = answer.get("incomplete_details")
            if isinstance(details, dict) and details.get("reason") == "max_output_tokens":
                raise _ResponseError(_token_failure(answer))
            raise _ResponseError("incomplete_response")
        parts = [part for item in answer.get("output", []) if item.get("type") == "message"
                 for part in item.get("content", [])]
        if any(part.get("type") == "refusal" for part in parts):
            raise _ResponseError("refused_response")
        return "".join(part["text"] for part in parts if part.get("type") == "output_text")
    choices = answer.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise _ResponseError("incomplete_response")
    if choices[0].get("finish_reason") == "length":
        raise _ResponseError(_token_failure(answer))
    if choices[0].get("finish_reason") != "stop":
        raise _ResponseError("incomplete_response")
    message = choices[0]["message"]
    if (isinstance(message, dict) and not message.get("content")
            and _token_failure(answer) == "reasoning_budget_exhausted"):
        raise _ResponseError("reasoning_budget_exhausted")
    if message.get("refusal") or not isinstance(message.get("content"), str):
        raise _ResponseError("refused_response")
    return message["content"]


def translate_texts(texts, *, model, **kwargs):
    from haizflow.services.translation_api_policy import request_limits

    profile, key = translation_connections.resolve(model, with_key=True)
    label = translation_connections.PROVIDERS[profile["provider"]]["label"]
    limits = request_limits(profile["provider"], profile["model"], 2048, kwargs.get("reasoning_effort", ""))
    return gemini_translation.translate_texts(
        texts, model=model, _key=key, _engine_name=label,
        _chunk_limits=(limits["sentences"], limits["characters"]),
        _request_handler=lambda chunk, **args: _request_chunk(profile, chunk, **args), **kwargs)


def check_connection(model_choice, *, model_required=True):
    """Read-only model-list check, never a billable sample translation."""
    if model_required:
        profile, key = translation_connections.resolve(model_choice, with_key=True)
    else:
        profile, key = translation_connections.get_connection(model_choice[4:], with_key=True)
    try:
        answer = _json_request(profile["base_url"] + "/models", key, timeout=15)
        rows = answer.get("data") if isinstance(answer, dict) else None
        if not isinstance(rows, list):
            return "unsupported-check"
        if not model_required:
            return "verified"
        return "verified" if any(isinstance(row, dict) and row.get("id") == profile["model"] for row in rows) \
            else "model-not-found"
    except error.HTTPError as exc:
        status = exc.code
        exc.close()
        return "invalid" if status in {401, 403} else "unsupported-check" if status == 404 else "unavailable"
    except (ValueError, TypeError, error.URLError, TimeoutError, OSError):
        return "unavailable"
