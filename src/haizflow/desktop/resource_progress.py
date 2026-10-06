"""Monotonic, dependency-aware resource installation presentation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from haizflow.services.model_bootstrap import ModelProgress


@dataclass
class InstallProgress:
    units: tuple[tuple[str, int], ...]
    maximum: float = 0.0
    fractions: dict[str, float] = field(default_factory=dict)

    def update(self, unit: str, event: ModelProgress) -> float:
        ratio = max(0.0, min(1.0, event.completed_bytes / event.total_bytes)) if event.total_bytes > 0 else 0.0
        engine = unit.startswith("engine-")
        if event.state == "ready" and event.phase != "transfer":
            fraction = 1.0
        elif event.phase == "assembly":
            fraction = 0.70 + ratio * 0.05
        elif event.phase == "installing":
            fraction = 0.75 + ratio * 0.20
        elif event.phase == "finalizing":
            fraction = 0.95 if engine else 0.97
        elif event.phase == "transfer" or event.state in {"downloading", "verifying"}:
            fraction = (0.02 + ratio * (0.68 if engine else 0.93))
        else:
            fraction = ratio * 0.02
        self.fractions[unit] = max(self.fractions.get(unit, 0.0), fraction)
        weight = sum(size for _, size in self.units) or 1
        measured = sum(size * self.fractions.get(pack, 0.0) for pack, size in self.units) * 100.0 / weight
        self.maximum = max(self.maximum, min(99.0, measured))
        return self.maximum


def progress_copy(unit: str, event: ModelProgress) -> dict:
    match = re.search(r"(?:Tệp|Kiểm tra) (\d+)/(\d+)", event.detail)
    return {"unit": unit, "state": "verifying" if event.state == "ready" else event.state,
            "file": int(match[1]) if match else 0, "count": int(match[2]) if match else 0,
            "phase": event.phase, "completed": event.completed_bytes, "total": event.total_bytes,
            "indeterminate": event.state == "checking" or event.phase == "finalizing"
                or (event.state == "verifying" and event.phase == "transfer")
                or event.total_bytes <= 0}


def pack_label(unit: str, language: str) -> str:
    vi = language == "vi"
    labels = {
        "engine-cpu-py313": ("Bộ xử lý CPU", "CPU runtime"),
        "engine-cuda128-py313": ("Bộ xử lý NVIDIA CUDA 12.8", "NVIDIA CUDA 12.8 runtime"),
        "engine-vision-onnx": ("Bộ xử lý hình ảnh", "Image runtime"),
        "model-whisper-small": ("Whisper Small", "Whisper Small"),
        "model-whisper-turbo": ("Whisper Turbo", "Whisper Turbo"),
        "model-hymt2-cpu": ("HY-MT2 CPU", "HY-MT2 CPU"),
        "model-hymt2-gpu": ("HY-MT2 GPU", "HY-MT2 GPU"),
        "model-omnivoice": ("OmniVoice", "OmniVoice"),
        "model-whisperx-vad": ("Nhận diện lời nói", "Voice activity detection"),
        "model-demucs": ("Tách giọng", "Vocal separation"),
        "model-demucs-cpu": ("Demucs CPU", "Demucs CPU"),
        "model-demucs-gpu": ("Demucs GPU NVIDIA", "Demucs GPU NVIDIA"),
        "model-subtitle-ocr": ("Nhận dạng phụ đề", "Subtitle recognition"),
    }
    return labels.get(unit, ("Tài nguyên hỗ trợ", "Supporting resources"))[0 if vi else 1]


def missing_resource_notice(pack_ids, summary: dict, language: str, feature: str = "") -> tuple[str, str]:
    from haizflow.desktop.presenters import format_memory_size

    vi = language == "vi"
    labels = ", ".join(pack_label(pack, language) for pack in pack_ids)
    size = format_memory_size(summary["downloadBytes"])
    space = format_memory_size(summary["requiredBytes"])
    if vi:
        transfer = f"Cần tải {size}." if summary["downloadBytes"] else "Gói cài đã có sẵn trên máy."
        requirement = f"{feature}: cần {labels}." if feature else f"Cần {labels}."
        return "Chưa cài đủ gói", f"{requirement} {transfer} Cần {space} trống để cài. Vào Cài đặt → Gói tài nguyên để cài gói này."
    transfer = f"Download: {size}." if summary["downloadBytes"] else "The installation archive is already on this computer."
    return "Required resources are missing", f"Required: {labels}. {transfer} Installation needs {space} of free space. Install these packs in Settings → Resource packs."


def gemini_key_notice(language: str) -> tuple[str, str]:
    if language == "vi":
        return "Chưa có Gemini API key", "Để dịch bằng Gemini, thêm key tại Cài đặt → API Key → Gemini. Bạn vẫn có thể chọn HY-MT2 để dịch cục bộ."
    return "Gemini API key is missing", "To translate with Gemini, add a key in Settings → API Key → Gemini. You can use HY-MT2 for local translation instead."


def zernio_key_notice(language: str) -> tuple[str, str]:
    if language == "vi":
        return "Chưa có Zernio API key", "Để kết nối tài khoản và đăng video, thêm key tại Cài đặt → API Key → Zernio."
    return "Zernio API key is missing", "To connect accounts and publish videos, add a key in Settings → API Key → Zernio."


def localized_progress(copy: dict, language: str) -> str:
    vi = language == "vi"
    states = {"checking": ("Đang kiểm tra", "Checking"), "downloading": ("Đang tải", "Downloading"),
              "verifying": ("Đang xác minh", "Verifying"), "installing": ("Đang cài đặt", "Installing"),
              "paused": ("Đã tạm dừng", "Paused"), "pausing": ("Đang tạm dừng…", "Pausing…"),
              "removing": ("Đang gỡ", "Removing")}
    parts = [states.get(copy.get("state"), states["checking"])[0 if vi else 1]]
    unit = copy.get("unit", "")
    label = pack_label(unit, language)
    if copy.get("count"):
        parts.append(("Tệp" if vi else "File") + f" {copy['file']}/{copy['count']}")
    parts.append(label)
    if copy.get("state") in {"checking", "downloading", "installing"} and copy.get("total", 0) >= 1024:
        def size(value):
            scale, unit = (10**9, "GB") if value >= 10**9 else (10**6, "MB")
            return f"{value / scale:.1f} {unit}"

        parts.append(f"{size(copy['completed'])} / {size(copy['total'])}")
    return " · ".join(parts)
