"""Local-only VieNeu v3 Turbo synthesis for HaizFlow.

The public VieNeu constructor can download missing Hugging Face artifacts. The
desktop pipeline must never do that after processing starts, so this adapter
constructs the pinned ONNX engine from model_bootstrap's verified directories.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS, MODELS_DIR
from haizflow.core.model_integrity import (
    VIENEU_SDK_SHA256,
    verify_vieneu_models,
    verify_vieneu_sdk,
)
from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.utils.ffmpeg import _binary


_RUNTIME_LOCK = threading.RLock()
_INFERENCE_LOCK = threading.RLock()
_RUNTIME = None


def _prepare_sdk() -> None:
    """Extract the checksum-pinned SDK without installing its unused web UI."""
    sdk_root = Path(MODELS_DIR) / "vieneu" / "sdk"
    wheel = verify_vieneu_sdk(Path(MODELS_DIR) / "vieneu")
    site_packages = sdk_root / "site-packages"
    marker = site_packages / ".haizflow-vieneu-sdk"
    required_modules = (
        site_packages / "vieneu" / "v3turbo.py",
        site_packages / "vieneu_utils" / "phonemize_text.py",
    )
    needs_extract = (
        not marker.is_file()
        or marker.read_text(encoding="ascii", errors="ignore") != VIENEU_SDK_SHA256
        or any(not item.is_file() for item in required_modules)
    )
    if needs_extract:
        temporary = sdk_root / f"site-packages-{os.getpid()}.part"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        try:
            with zipfile.ZipFile(wheel) as archive:
                members = [
                    info for info in archive.infolist()
                    if info.filename.startswith(("vieneu/", "vieneu_utils/"))
                    and not info.is_dir()
                ]
                for info in members:
                    relative = Path(info.filename)
                    if relative.is_absolute() or ".." in relative.parts:
                        raise RuntimeError("VieNeu SDK contains an unsafe path.")
                    destination = temporary / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)
            extracted_modules = (
                temporary / "vieneu" / "v3turbo.py",
                temporary / "vieneu_utils" / "phonemize_text.py",
            )
            if any(not item.is_file() for item in extracted_modules):
                raise RuntimeError("VieNeu SDK wheel is missing required inference modules.")
            (temporary / ".haizflow-vieneu-sdk").write_text(VIENEU_SDK_SHA256, encoding="ascii")
            if site_packages.exists():
                shutil.rmtree(site_packages)
            os.replace(temporary, site_packages)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    sdk_path = str(site_packages)
    if sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)


def _cpu_threads() -> int:
    """Leave CPU capacity for Qt, FFmpeg and pipeline coordination."""
    logical = os.cpu_count() or 4
    return max(1, min(8, logical // 2))


def _load_runtime():
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            return _RUNTIME

        model_root, codec_root = verify_vieneu_models(Path(MODELS_DIR) / "vieneu")
        _prepare_sdk()
        try:
            from vieneu.base import BaseVieneuTTS
            from vieneu.v3turbo import V3TurboVieNeuTTS
            from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
        except ImportError as exc:
            raise RuntimeError("VieNeu TTS is not installed in this HaizFlow build.") from exc

        class LocalOnlyOnnxEngine(OnnxV3LiteEngine):
            def _load_denoiser(self):
                # HaizFlow exposes preset voices only. Avoid the optional
                # voice-cloning artifacts and any SDK fallback download.
                return None

        runtime = V3TurboVieNeuTTS.__new__(V3TurboVieNeuTTS)
        BaseVieneuTTS.__init__(runtime)
        runtime.sample_rate = 48_000
        runtime.engine = LocalOnlyOnnxEngine(
            checkpoint_path=str(model_root.parent),
            onnx_dir=str(model_root),
            codec_dir=str(codec_root),
            threads=_cpu_threads(),
        )
        runtime.backend = "onnx"
        runtime.default_style = "tu_nhien"
        runtime._preset_voices = {}
        runtime._default_voice = None
        runtime._load_v3_voices()
        runtime.max_batch_size = 1
        runtime._batch_engine = None
        if not runtime.list_preset_voices():
            raise RuntimeError("VieNeu preset voices are missing from the installed package.")
        _RUNTIME = runtime
        return runtime


def _encode_mp3(wav_path: str, output_path: str, video_id: str) -> None:
    command = [
        _binary("ffmpeg"), "-y", "-v", "error", "-i", wav_path,
        "-vn", "-codec:a", "libmp3lame", "-q:a", "3", "-f", "mp3", output_path,
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _stdout, stderr = communicate_process(
        video_id,
        process,
        label="VieNeu audio encoding",
        timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
    )
    if process.returncode != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError((stderr or "FFmpeg could not encode VieNeu audio.").strip()[:500])


def synthesize_to_mp3(text: str, voice: str, output_path: str, video_id: str) -> None:
    """Synthesize one verified preset-voice segment without network access."""
    check_cancellation(video_id)
    runtime = _load_runtime()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(f"{output.name}.part")
    temporary_output.unlink(missing_ok=True)
    wav_path = ""
    try:
        with _INFERENCE_LOCK:
            check_cancellation(video_id)
            waveform = runtime.infer(
                str(text or "").strip(),
                voice=voice,
                batch_size=1,
                apply_watermark=False,
            )
        waveform = np.asarray(waveform, dtype=np.float32).reshape(-1)
        if waveform.size < 480 or not np.isfinite(waveform).all():
            raise RuntimeError("VieNeu returned empty or invalid audio.")
        handle, wav_path = tempfile.mkstemp(prefix="haizflow-vieneu-", suffix=".wav", dir=output.parent)
        os.close(handle)
        sf.write(wav_path, waveform, runtime.sample_rate, subtype="PCM_16")
        check_cancellation(video_id)
        _encode_mp3(wav_path, str(temporary_output), video_id)
        os.replace(temporary_output, output)
    finally:
        temporary_output.unlink(missing_ok=True)
        if wav_path:
            Path(wav_path).unlink(missing_ok=True)


def clear_runtime() -> None:
    """Release ONNX sessions during controlled shutdown or tests."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None
