"""Decode authorised clone samples without optional SDK audio backends."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.utils.ffmpeg import _binary


def prepare_reference(source: str, target: Path, cancellation_id: str, *,
                      sample_rate: int, max_seconds: int | None = None) -> str:
    """Produce owned mono PCM WAV; never overwrite or silently replace a sample.

    OmniVoice keeps the full clip to match its transcript. VieNeu retains its
    existing eight-second reference policy. Callers cache one decode per source
    within a synthesis request and own the temporary destination's lifetime.
    """
    check_cancellation(cancellation_id)
    origin = Path(source).resolve()
    target = Path(target).resolve()
    if not origin.is_file() or origin.stat().st_size <= 0:
        raise ValueError("Không tìm thấy mẫu giọng. Hãy chọn lại tệp mẫu.")
    if target == origin:
        raise ValueError("Không thể ghi đè tệp mẫu giọng gốc.")
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [_binary("ffmpeg"), "-nostdin", "-y", "-v", "error", "-i", str(origin)]
    if max_seconds is not None:
        command += ["-t", str(max_seconds)]
    command += ["-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(sample_rate),
                "-c:a", "pcm_s16le", "-f", "wav", str(target)]
    decoder = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    communicate_process(cancellation_id, decoder, label="Clone reference decoding", timeout_seconds=60)
    check_cancellation(cancellation_id)
    try:
        with wave.open(str(target), "rb") as audio:
            valid = (audio.getnchannels() == 1 and audio.getsampwidth() == 2
                     and audio.getframerate() == sample_rate and audio.getnframes() > 0)
    except (OSError, EOFError, wave.Error):
        valid = False
    if decoder.returncode or not valid:
        raise ValueError("Không đọc được âm thanh trong mẫu giọng. Hãy chọn tệp âm thanh hợp lệ hoặc thu lại mẫu.")
    return str(target)
