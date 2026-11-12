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
        return f"{label}: dịch vụ đang giới hạn yêu cầu (HTTP 429). Thử lại sau."
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


def _openrouter_rate_limit(answer=None, headers=None):
    """Classify bounded server hints; never echo raw messages, metadata or keys."""
    fault = answer.get("error") if isinstance(answer, dict) else None
    fault = fault if isinstance(fault, dict) else {}
    metadata = fault.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    message = fault.get("message")
    message = message[:8192].lower() if isinstance(message, str) else ""
    if "free-models-per-day" in message:
        return ("OpenRouter: đã chạm hạn mức request miễn phí trong ngày (HTTP 429). "
                "Chờ hạn mức được làm mới trên OpenRouter.")
    if fault.get("code") == "insufficient_quota":
        return ("OpenRouter: dịch vụ báo đã chạm hạn mức sử dụng (HTTP 429). "
                "Kiểm tra hạn mức tài khoản trên OpenRouter.")
    retry = headers.get("Retry-After", "") if headers is not None else ""
    retry = retry.strip() if isinstance(retry, str) else ""
    action = (f"Thử lại sau khoảng {int(retry)} giây." if re.fullmatch(r"[0-9]{1,5}", retry)
              and 0 < int(retry) <= 86400 else "Thử lại sau hoặc chọn model khác.")
    if metadata.get("provider_name") or metadata.get("provider_code"):
        detail = "nhà cung cấp của model đang giới hạn yêu cầu hoặc thiếu công suất"
    elif "free-models-per-min" in message:
        detail = "đang giới hạn số request miễn phí trong phút"
    else:
        return ("OpenRouter: yêu cầu đang bị giới hạn hoặc nhà cung cấp đang thiếu công suất (HTTP 429). "
                "Không đồng nghĩa đã dùng hết quota. " + action)
    return f"OpenRouter: {detail} (HTTP 429). {action}"


def _model_error(status, profile, *, answer=None, headers=None):
    if status == 429 and profile["provider"] == "openrouter":
        return _openrouter_rate_limit(answer, headers)
    if status == 404 and profile["provider"] == "openrouter" and _request_failure_kind(answer) == "data_policy":
        return ("OpenRouter: endpoint của model yêu cầu quyền thu thập dữ liệu hoặc bị chặn bởi "
                "cài đặt quyền riêng tư (HTTP 404). Chọn lại model để xem cảnh báo và cấp quyền, "
                "hoặc chọn model khác. App không tự thay đổi quyền riêng tư của tài khoản OpenRouter.")
    if status == 404 and profile["provider"] == "openrouter" and profile["model"].endswith(":free"):
        return ("OpenRouter: không có endpoint khả dụng cho model miễn phí đã chọn "
                "hoặc endpoint không hỗ trợ yêu cầu này (HTTP 404). "
                "Hãy tải lại danh sách và chọn model miễn phí khác; "
                "app không tự chuyển sang model tính phí.")
    if status in {400, 422} and profile["provider"] == "openrouter":
        kind = _request_failure_kind(answer)
        detail = {"context_length": "nội dung hoặc hướng dẫn vượt giới hạn ngữ cảnh của model",
                  "output_limit": "giới hạn token đầu ra không được endpoint chấp nhận",
                  "system_role": "endpoint không hỗ trợ kiểu prompt đang gửi",
                  "json_format": "endpoint không chấp nhận định dạng JSON yêu cầu"}.get(
                      kind, "endpoint từ chối yêu cầu dịch; khả năng tương thích của model có thể đã thay đổi")
        return f"OpenRouter: {detail} (HTTP {status}). Hãy kiểm tra model đang chọn hoặc tải lại danh sách."
    return public_error(status, translation_connections.PROVIDERS[profile["provider"]]["label"])


def _request_failure_kind(answer):
    fault = answer.get("error") if isinstance(answer, dict) else None
    fault = fault if isinstance(fault, dict) else {}
    meta = fault.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    texts = [fault.get("message"), meta.get("raw"), meta.get("error_type")]
    text = " ".join(value[:8192].lower() for value in texts if isinstance(value, str))
    if re.search(r"data polic|data[_ ]collection|privacy|enable.{0,30}(?:training|logging)", text):
        return "data_policy"
    if re.search(r"context.?length|max_model_len|上下文", text):
        return "context_length"
    if re.search(r"max[_ ](?:completion[_ ]|output[_ ])?tokens|最大.{0,8}token", text):
        return "output_limit"
    if "system" in text and re.search(r"not support|unsupported|not allow", text):
        return "system_role"
    if re.search(r"json_schema|response_format|structured.output", text):
        return "json_format"
    return "unclassified"


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
    reasoning, output, visible = (counts.get(name, 0) for name in ("reasoning", "output", "visible"))
    return ("reasoning_budget_exhausted" if reasoning > 0 and (visible == 0 or
            output > 0 and reasoning >= output * .9 and visible <= max(32, output // 100))
            else "token_limit")


def _request_chunk(profile, chunk, *, key, model, source_language, target_language, video_id="",
                   reasoning_effort="", **kwargs):
    from haizflow.services.translation_api_policy import request_limits, request_options

    if profile["provider"] == "openrouter":
        from haizflow.services import translation_privacy
        from haizflow.services.translation_model_catalog import (
            _INCOMPATIBLE_OPENROUTER_MODELS, _UNAVAILABLE_OPENROUTER_MODELS,
        )

        if profile["model"] in _UNAVAILABLE_OPENROUTER_MODELS:
            raise RuntimeError("OpenRouter: model miễn phí đang lưu hiện không ổn định hoặc bị giới hạn phía nhà cung cấp. "
                               "Hãy chọn model khác trong Model dịch; app chưa gửi yêu cầu API.")
        if translation_privacy.required(profile) and not translation_privacy.allowed(profile):
            raise RuntimeError("OpenRouter: model này yêu cầu quyền thu thập dữ liệu. "
                               "Chọn lại model trong dự án và đồng ý cảnh báo trước khi dịch; "
                               "app chưa gửi nội dung phụ đề.")
        if profile["model"] in _INCOMPATIBLE_OPENROUTER_MODELS:
            raise RuntimeError("OpenRouter: model đang lưu trong dự án hiện không tương thích với dịch phụ đề JSON. "
                               "Hãy chọn model khác trong Model dịch; app chưa gửi yêu cầu API.")
    label = translation_connections.PROVIDERS[profile["provider"]]["label"]
    source_payload = gemini_translation._payload_for_chunk(
        chunk, model=model, source_language=source_language, target_language=target_language,
        video_id=video_id, **kwargs)
    system, user = _messages(source_payload)
    schema = {"name": "subtitle_translation", "strict": True, "schema": _SCHEMA}
    limits = request_limits(profile["provider"], profile["model"],
                            source_payload["generationConfig"]["maxOutputTokens"], reasoning_effort)
    token_limit = limits["max_tokens"]
    protocol = {}
    if profile["provider"] == "openrouter":
        from haizflow.services.translation_catalog_cache import protocol_for

        protocol = protocol_for(profile["model"])
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
        if protocol.get("prompt_format") == "user_only":
            payload["messages"] = [{"role": "user", "content":
                payload["messages"][0]["content"] + "\n\nSubtitle task and context (JSON data):\n" + user}]
        if profile["provider"] == "openrouter":
            payload["provider"] = {"require_parameters": True, "allow_fallbacks": True,
                                   "data_collection": "allow" if translation_privacy.allowed(profile) else "deny"}
    payload.update(request_options(profile["provider"], profile["model"], reasoning_effort))
    if video_id:
        try:
            log_to_video(video_id, f"{label} request budget: sentences={len(chunk)}, max_tokens={token_limit}, "
                         f"model={profile['model']}, "
                         f"reasoning_active={limits['reasoning_active']}, "
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
            answer = None
            headers = exc.headers
            if status in {400, 404, 422, 429} and profile["provider"] == "openrouter":
                try:
                    raw = exc.read(64 * 1024 + 1)
                    if len(raw) <= 64 * 1024:
                        answer = json.loads(raw)
                except (OSError, ValueError, TypeError, HTTPException):
                    pass  # Missing/broken hints must not replace the original HTTP error.
            exc.close()
            if video_id and status in {400, 404, 422} and profile["provider"] == "openrouter":
                try:
                    log_to_video(video_id, f"{label}: model={profile['model']}, "
                                 f"request_rejected={_request_failure_kind(answer)}.",
                                 level="WARNING", component="TRANSLATE")
                except (OSError, RuntimeError):
                    pass
            if status in {408, 500, 502, 503, 504} and attempt < 2:
                gemini_translation._retry_delay(2 ** attempt, video_id)
                continue
            raise RuntimeError(_model_error(status, profile, answer=answer, headers=headers)) from None
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
            message = (_model_error(status, profile, answer=answer) if status
                       else f"{label}: dịch vụ trả về lỗi không xác định.")
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
                detail = ("model dùng gần hết giới hạn token cho suy luận, chưa tạo được bản dịch đầy đủ"
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
