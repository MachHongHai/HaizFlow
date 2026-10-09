"""Lazy, backend-aware Whisper precision selection (no GPU-name heuristics)."""

import logging
from collections.abc import Collection

_LOG = logging.getLogger(__name__)


def whisper_compute_type(device: str, *, supported_types: Collection[str] | None = None) -> str:
    preferred = "float16" if device == "cuda" else "int8"
    if supported_types is None:
        try:
            from ctranslate2 import get_supported_compute_types

            supported_types = get_supported_compute_types(device, device_index=0)
        except (ImportError, RuntimeError, ValueError, OSError) as exc:
            # Unknown telemetry is not evidence that a modern GPU needs downgrading.
            # Keep the established mode; model loading still validates the backend.
            _LOG.warning("Whisper compute capabilities unavailable: device=%s error=%s", device, type(exc).__name__)
            return preferred
    supported = supported_types
    if preferred in supported:
        return preferred
    # Pascal (e.g. GTX 1070) has efficient INT8/FP32, not efficient FP16.
    # Preserve GPU execution and the installed checkpoint, rather than forcing CPU.
    for candidate in ("int8_float32", "float32"):
        if candidate in supported:
            _LOG.info("Whisper compatibility mode: device=%s compute_type=%s", device, candidate)
            return candidate
    raise RuntimeError("Bộ xử lý Whisper không hỗ trợ kiểu tính toán phù hợp. Kiểm tra driver và gói tài nguyên.")
