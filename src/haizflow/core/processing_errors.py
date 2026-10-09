"""Describe processing failures without changing model or recovery policy."""

from __future__ import annotations

import re


def describe_failure(error: object, language: str = "vi") -> dict[str, str]:
    raw = " ".join(str(error or "").split())
    lowered = raw.casefold()
    vi = language == "vi"
    if raw.startswith(("Chưa đủ bộ nhớ để chạy ", "Không đọc được bộ nhớ RAM/")):
        # Admission errors include measured budgets and actionable guidance.
        # Do not truncate away the remedy or misreport this as a native OOM.
        return {
            "code": "memory_preflight_failed",
            "title": "Chưa đủ bộ nhớ để xử lý" if vi else "Memory preflight failed",
            "message": raw,
        }
    gpu_oom = any(marker in lowered for marker in (
        "cuda out of memory", "cuda failed with error out of memory", "cuda_error_out_of_memory",
        "cudnn_status_alloc_failed", "cublas_status_alloc_failed", "cuda error: out of memory",
    )) or ("out of memory" in lowered and any(word in lowered for word in ("cuda", "gpu", "vram")))
    if gpu_oom:
        return {
            "code": "gpu_out_of_memory",
            "title": "Hết bộ nhớ GPU (CUDA out of memory)" if vi else "GPU out of memory (CUDA)",
            "message": (
                "Hết bộ nhớ GPU (CUDA out of memory). Đóng ứng dụng đang dùng GPU rồi thử lại, "
                "hoặc chọn model nhỏ hơn / CPU."
                if vi else "GPU out of memory (CUDA). Close other GPU applications and retry, "
                "or choose a smaller model / CPU."
            ),
        }
    system_oom = isinstance(error, MemoryError) or any(marker in lowered for marker in (
        "memoryerror", "std::bad_alloc", "bad allocation", "cannot allocate memory",
        "unable to allocate", "not enough memory", "out of memory", "winerror 1455",
        "paging file is too small", "defaultcpuallocator: can't allocate memory",
    ))
    if system_oom:
        return {
            "code": "system_out_of_memory",
            "title": "Không đủ bộ nhớ hệ thống (RAM / bộ nhớ ảo)" if vi else "Insufficient system memory (RAM / paging file)",
            "message": (
                "Không đủ bộ nhớ hệ thống (RAM / bộ nhớ ảo). Đóng ứng dụng khác rồi thử lại. "
                "Nếu lỗi vẫn lặp lại, kiểm tra bộ nhớ ảo của Windows hoặc chọn model nhỏ hơn."
                if vi else "Insufficient system memory (RAM / paging file). Close other applications and retry. "
                "If it persists, check the Windows paging file or choose a smaller model."
            ),
        }
    if any(marker in lowered for marker in ("cudnn", "cublas", "cuda error", "cuda failed")):
        match = re.search(r"(?:CUDNN|CUBLAS|CUDA)_[A-Z_]+", raw, re.I)
        name = match.group(0).upper() if match else "CUDA"
        return {
            "code": "gpu_execution_error",
            "title": f"Lỗi xử lý GPU ({name})" if vi else f"GPU execution error ({name})",
            "message": (
                f"Lỗi xử lý GPU ({name}). Chưa xác định là hết bộ nhớ. "
                "Thử lại hoặc chọn CPU; xem log kỹ thuật để biết chi tiết."
                if vi else f"GPU execution error ({name}). This is not a confirmed out-of-memory error. "
                "Retry or choose CPU; check the technical log for details."
            ),
        }
    if "gemini" in lowered and re.search(r"HTTP\s+(?:500|502|503|504)\b", raw, re.I):
        status = re.search(r"HTTP\s+(\d{3})", raw, re.I).group(1)
        return {
            "code": "google_service_unavailable",
            "title": "Dịch vụ Google tạm thời không khả dụng" if vi else "Google service temporarily unavailable",
            "message": (
                f"Gemini: lỗi dịch vụ Google (HTTP {status}). Thử lại sau hoặc chọn Flash-Lite."
                if vi else f"Gemini: Google service error (HTTP {status}). Retry later or choose Flash-Lite."
            ),
        }
    compact = raw[:240] + ("…" if len(raw) > 240 else "")
    title = "Tác vụ gặp lỗi" if vi else "Task failed"
    return {
        "code": "processing_error", "title": title,
        "message": f"{title}: {compact}" if compact else (
            "Tác vụ gặp lỗi. Mở log kỹ thuật để xem chi tiết." if vi
            else "Task failed. Open the technical log for details."
        ),
    }
