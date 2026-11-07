"""Actionable GPU failures: preserve the selected device instead of silent CPU work."""
from __future__ import annotations


def unavailable(detail: object) -> bool:
    value = str(detail).lower()
    return any(marker in value for marker in (
        "cuda is unavailable", "cuda unavailable", "no cuda gpus", "no cuda-capable",
        "no nvidia gpu", "gpu became unavailable", "cuda driver", "cuda device lost",
        "cuda-capable device", "not compiled with cuda", "does not include cuda",
        "nvidia gpu is no longer detected", "gpu cần gpu nvidia/cuda",
    ))


def memory_failure(detail: object) -> bool:
    value = str(detail).lower()
    return isinstance(detail, MemoryError) or any(marker in value for marker in (
        "out of memory", "not enough memory", "cublas_status_alloc_failed", "cudnn_status_alloc_failed",
        "defaultcpuallocator", "cannot allocate memory", "can't allocate memory",
    ))


def notice(detail: object) -> str:
    if memory_failure(detail):
        return "GPU thiếu bộ nhớ. Hãy giải phóng VRAM hoặc tự chọn CPU rồi chạy lại. App không tự đổi thiết bị."
    return "GPU không khả dụng. Hãy kiểm tra GPU/driver hoặc tự chọn CPU rồi chạy lại. App không tự đổi thiết bị."
