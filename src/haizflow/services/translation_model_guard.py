"""Read-only compatibility preflight before sending any subtitle to OpenRouter."""
from __future__ import annotations

from http.client import HTTPException
from urllib import error, parse


def _read_public(url, video_id):
    from haizflow.pipeline.process_registry import check_cancellation
    from haizflow.services.api_translation import _json_request, _response_error_status

    check_cancellation(video_id)
    try:
        answer = _json_request(url, "", timeout=12)
    except error.HTTPError as exc:
        status = exc.code
        exc.close()
        check_cancellation(video_id)
        if status in {404, 410}:
            raise RuntimeError("OpenRouter: model đã chọn không còn khả dụng. "
                               "Hãy tải lại danh sách; app chưa gửi nội dung dịch.") from None
        raise RuntimeError("OpenRouter: chưa kiểm tra được khả năng của model. "
                           "Hãy thử lại; app chưa gửi nội dung dịch.") from None
    except (OSError, ValueError, TypeError, HTTPException):
        check_cancellation(video_id)
        raise RuntimeError("OpenRouter: chưa kiểm tra được khả năng của model. "
                           "Hãy thử lại; app chưa gửi nội dung dịch.") from None
    check_cancellation(video_id)
    if _response_error_status(answer) is not None:
        raise RuntimeError("OpenRouter: không xác minh được model đã chọn. "
                           "Hãy tải lại danh sách; app chưa gửi nội dung dịch.")
    return answer.get("data") if isinstance(answer, dict) else None


def _check_endpoints(option, *, reasoning_effort="", video_id=""):
    from haizflow.services.translation_api_policy import request_options
    from haizflow.services.translation_model_catalog import _pricing_kind

    model = option["value"]
    try:
        knobs = request_options("openrouter", model, reasoning_effort, protocol=option)
    except ValueError:
        raise RuntimeError("OpenRouter: mức reasoning đã chọn không còn được model hỗ trợ. "
                           "Hãy tải lại danh sách và chọn lại Mức; app chưa gửi nội dung dịch.") from None
    required = {"max_tokens", "structured_outputs" if option["output_format"] == "json_schema" else "response_format"}
    if "reasoning" in knobs:
        required.add("reasoning")
    data = _read_public("https://openrouter.ai/api/v1/models/" + parse.quote(model, safe="/") + "/endpoints", video_id)
    endpoints = data.get("endpoints") if isinstance(data, dict) else None
    eligible = []
    for endpoint in endpoints[:1000] if isinstance(endpoints, list) else []:
        if not isinstance(endpoint, dict):
            continue
        declared = endpoint.get("model_id", model)
        if not isinstance(declared, str) or declared not in {model, option.get("canonical_slug", model)}:
            continue
        parameters = endpoint.get("supported_parameters")
        if (not isinstance(parameters, list) or not all(value in parameters for value in required)
                or endpoint.get("status", 0) != 0):
            continue
        if option.get("pricing_kind") == "free" and _pricing_kind(endpoint.get("pricing")) != "free":
            continue
        eligible.append(endpoint)
    if not eligible:
        raise RuntimeError("OpenRouter: chưa có endpoint khả dụng hỗ trợ cấu hình dịch đã chọn. "
                           "Hãy thử model khác; app chưa gửi nội dung dịch.")
    # Use a bound safe for any matching provider, not an aggregate limit from
    # a different provider. Gateway require_parameters remains enabled too.
    result = dict(option)
    for field in ("context_length", "max_completion_tokens"):
        limits = [endpoint[field] for endpoint in eligible if type(endpoint.get(field)) is int
                  and 0 < endpoint[field] <= 10**8]
        if limits:
            result[field] = min(result[field], *limits)
    return result


def prepare(profile, *, video_id="", reasoning_effort=""):
    """Return one verified protocol snapshot for the complete translation run.

    Custom servers remain explicitly configured OpenAI-compatible endpoints;
    they need not implement model discovery. No inference probes or fallback
    model selection are performed by this preflight.
    """
    if profile["provider"] != "openrouter":
        return None
    from haizflow.services.translation_model_catalog import _MODEL, _option, supports_chat

    model = profile["model"]
    if (not _MODEL.fullmatch(model) or "/" not in model or not supports_chat(model, {})
            or any(part in {"", ".", ".."} for part in model.split("/"))):
        raise RuntimeError("OpenRouter: Model ID không phù hợp với dịch phụ đề. Hãy chọn lại model.")
    # Pin the official host and exact opaque ID. Never send the stored key,
    # subtitles, instructions or user content to a metadata endpoint.
    url = "https://openrouter.ai/api/v1/model/" + parse.quote(model, safe="/")
    row = _read_public(url, video_id)
    if not isinstance(row, dict) or row.get("id") != model:
        raise RuntimeError("OpenRouter: không xác minh được model đã chọn. "
                           "Hãy tải lại danh sách; app chưa gửi nội dung dịch.")
    option = _option("openrouter", row)
    if (not option or "endpoints" not in option
            or "max_tokens" not in option.get("parameters", [])):
        raise RuntimeError("OpenRouter: model hiện không hỗ trợ cấu hình dịch phụ đề của app. "
                           "Hãy chọn model khác; app chưa gửi nội dung dịch.")
    if model.endswith(":free") and option["pricing_kind"] != "free":
        raise RuntimeError("OpenRouter: chưa xác nhận được mức phí miễn phí của model. "
                           "Hãy chọn lại model; app chưa gửi nội dung dịch.")
    from haizflow.services.translation_catalog_cache import protocol_for

    if protocol_for(model).get("pricing_kind") == "free" and option["pricing_kind"] == "paid":
        raise RuntimeError("OpenRouter: model không còn miễn phí như danh sách trước đó. "
                           "Hãy tải lại danh sách và chọn lại; app chưa gửi nội dung dịch.")
    canonical = row.get("canonical_slug")
    if isinstance(canonical, str) and _MODEL.fullmatch(canonical):
        option["canonical_slug"] = canonical
    return _check_endpoints(option, reasoning_effort=reasoning_effort, video_id=video_id)
