"""Checksum-pinned OmniVoice synthesis in a dependency-isolated worker."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS, MODELS_DIR, TMP_DIR
from haizflow.core.hardware import processing_device_preference
from haizflow.core.model_integrity import (
    OMNIVOICE_HUB_FILE,
    OMNIVOICE_RUNTIME_FILES,
    OMNIVOICE_SDK_FILE,
    OMNIVOICE_TRANSFORMERS_FILE,
    verify_omnivoice_model,
    verify_omnivoice_sdk,
)
from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.services.video_store import log_to_video
from haizflow.utils.ffmpeg import _binary

_RUNTIME_MARKER_VERSION = "omnivoice-0.2.1-transformers-5.3.0-hub-1.3.0"
_SAMPLE_RATE = 24_000
_RUNTIME_PREPARE_LOCK = threading.Lock()
_GPU_STALL_TIMEOUT_SECONDS = 15 * 60
_CPU_STALL_TIMEOUT_SECONDS = 40 * 60
_HEARTBEAT_LOG_INTERVAL_SECONDS = 30
_STATUS_WRITE_ATTEMPTS = 9
_VOICE_ANCHOR_TARGET_CHARS = 80
_VOICE_ANCHOR_MIN_CHARS = 24
_VOICE_ANCHOR_MAX_CHARS = 120

OMNIVOICE_VOICE_INSTRUCTIONS = {
    # OmniVoice validates this vocabulary strictly. Keep every preset within
    # the model's published instruction set.
    "omnivoice:female": "female, young adult, moderate pitch",
    "omnivoice:male": "male, young adult, moderate pitch",
    "omnivoice:female_low": "female, young adult, low pitch",
    "omnivoice:deep": "male, young adult, low pitch",
    "omnivoice:bright": "female, young adult, high pitch",
    "omnivoice:male_high": "male, young adult, high pitch",
    "omnivoice:female_mature": "female, elderly, moderate pitch",
    "omnivoice:male_mature": "male, elderly, moderate pitch",
    "omnivoice:female_soprano": "female, young adult, very high pitch",
    "omnivoice:male_tenor": "male, young adult, very high pitch",
    "omnivoice:female_narrator": "female, elderly, low pitch",
    "omnivoice:male_narrator": "male, elderly, low pitch",
    "omnivoice:female_elder_high": "female, elderly, high pitch",
    "omnivoice:male_elder_high": "male, elderly, high pitch",
    "omnivoice:whisper": "whisper, young adult, moderate pitch",
    "omnivoice:whisper_low": "whisper, young adult, low pitch",
    "omnivoice:whisper_high": "whisper, young adult, high pitch",
    "omnivoice:whisper_elder": "whisper, elderly, low pitch",
    "omnivoice:elder": "elderly, moderate pitch",
    "omnivoice:storyteller": "elderly, low pitch",
    "omnivoice:child": "child, high pitch",
    "omnivoice:cartoon": "child, very high pitch",
    "omnivoice:child_soft": "child, moderate pitch",
    "omnivoice:child_low": "child, low pitch",
}

# The desktop catalog uses ISO 639-1 identifiers. OmniVoice accepts most of
# those directly, but its language table represents Modern Standard Arabic by
# the ISO 639-3 identifier ``arb``. Keep the translation at this integration
# boundary so projects and the rest of the pipeline retain their stable
# two-letter language contract.
OMNIVOICE_LANGUAGE_IDS = {
    "ar": "arb",
}


def _omnivoice_language_id(language_id: str) -> str:
    normalized = str(language_id or "").strip().lower()
    return OMNIVOICE_LANGUAGE_IDS.get(normalized, normalized)


def _write_status_file(status_path: Path, payload: dict[str, Any]) -> bool:
    """Publish worker progress without letting a transient Windows lock stop TTS.

    Qt, antivirus software and the progress monitor can briefly hold the old
    status file open. ``os.replace`` then raises WinError 5/32 on Windows even
    though synthesis itself is healthy. Progress is advisory, so retry the
    atomic replacement and continue the worker if every retry is exhausted.
    """
    if not status_path.name:
        return False
    status_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = status_path.with_name(
        f".{status_path.name}.{os.getpid()}.{threading.get_ident()}.part"
    )
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    delay = 0.01
    try:
        for attempt in range(_STATUS_WRITE_ATTEMPTS):
            try:
                temporary.write_text(serialized, encoding="utf-8")
                os.replace(temporary, status_path)
                return True
            except OSError:
                temporary.unlink(missing_ok=True)
                if attempt + 1 < _STATUS_WRITE_ATTEMPTS:
                    time.sleep(delay)
                    delay = min(0.25, delay * 2)
        return False
    finally:
        temporary.unlink(missing_ok=True)


def _select_voice_anchor(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick an informative but short narrator sample for stable fast cloning."""
    candidates = [
        item
        for item in items
        if str(item.get("text") or "").strip()
        and not str(item.get("reference_path") or "").strip()
    ]
    if not candidates:
        return None

    def score(item: dict[str, Any]) -> tuple[bool, int, int]:
        length = len(str(item.get("text") or "").strip())
        return (
            length < _VOICE_ANCHOR_MIN_CHARS,
            abs(length - _VOICE_ANCHOR_TARGET_CHARS),
            length,
        )

    return min(candidates, key=score)


def _voice_anchor_excerpt(text: str) -> str:
    """Return one useful, bounded sentence for the narrator voice prompt.

    Whisper can produce a 20-40 second source segment for unpunctuated CJK
    speech.  Reusing the full translated paragraph as a clone reference makes
    every later OmniVoice call encode an unnecessarily long waveform.  Keep
    translation segmentation intact and derive only a short voice-identity
    prompt after translation.
    """
    normalized = " ".join(str(text or "").split()).strip()
    if len(normalized) <= _VOICE_ANCHOR_MAX_CHARS:
        return normalized

    sentences = [
        value.strip()
        for value in re.split(r"(?<=[.!?\u3002\uff01\uff1f;:])\s*", normalized)
        if value.strip()
    ]
    suitable = [value for value in sentences if len(value) >= _VOICE_ANCHOR_MIN_CHARS]
    if suitable:
        return min(
            suitable,
            key=lambda value: (
                len(value) > _VOICE_ANCHOR_MAX_CHARS,
                abs(len(value) - _VOICE_ANCHOR_TARGET_CHARS),
            ),
        )[:_VOICE_ANCHOR_MAX_CHARS].rstrip()

    words = normalized.split()
    if len(words) > 1:
        excerpt: list[str] = []
        length = 0
        for word in words:
            added = len(word) + (1 if excerpt else 0)
            if excerpt and length + added > _VOICE_ANCHOR_MAX_CHARS:
                break
            excerpt.append(word)
            length += added
        if excerpt:
            return " ".join(excerpt)
    return normalized[:_VOICE_ANCHOR_MAX_CHARS].rstrip()


def _sdk_root() -> Path:
    return Path(MODELS_DIR) / "omnivoice" / "sdk"


def _prepare_isolated_runtime_unlocked() -> Path:
    """Extract pinned runtime wheels; caller serializes replacement of the tree."""
    model_root = Path(MODELS_DIR) / "omnivoice"
    verify_omnivoice_sdk(model_root)
    sdk_root = _sdk_root()
    site_packages = sdk_root / "site-packages"
    marker = site_packages / ".haizflow-omnivoice-runtime"
    required = (
        site_packages / "omnivoice" / "__init__.py",
        site_packages / "transformers" / "__init__.py",
        site_packages / "huggingface_hub" / "__init__.py",
    )
    if (
        marker.is_file()
        and marker.read_text(encoding="ascii", errors="ignore") == _RUNTIME_MARKER_VERSION
        and all(path.is_file() for path in required)
    ):
        return site_packages

    temporary = sdk_root / f"site-packages-{os.getpid()}.part"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True, exist_ok=True)
    try:
        for filename in (
            OMNIVOICE_SDK_FILE,
            OMNIVOICE_TRANSFORMERS_FILE,
            OMNIVOICE_HUB_FILE,
        ):
            wheel = sdk_root / filename
            expected_size, _digest = OMNIVOICE_RUNTIME_FILES[filename]
            if not wheel.is_file() or wheel.stat().st_size != expected_size:
                raise RuntimeError(f"OmniVoice runtime asset is missing: {filename}")
            with zipfile.ZipFile(wheel) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    relative = Path(info.filename)
                    if relative.is_absolute() or ".." in relative.parts:
                        raise RuntimeError("OmniVoice runtime wheel contains an unsafe path.")
                    destination = temporary / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)
        if not all((temporary / path.relative_to(site_packages)).is_file() for path in required):
            raise RuntimeError("The isolated OmniVoice runtime is incomplete.")
        (temporary / ".haizflow-omnivoice-runtime").write_text(_RUNTIME_MARKER_VERSION, encoding="ascii")
        shutil.rmtree(site_packages, ignore_errors=True)
        os.replace(temporary, site_packages)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return site_packages


def _prepare_isolated_runtime() -> Path:
    """Prepare the runtime once, even if preview and processing start together."""
    with _RUNTIME_PREPARE_LOCK:
        return _prepare_isolated_runtime_unlocked()


def _worker_command(request_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--omnivoice-worker", str(request_path)]
    return [
        sys.executable,
        "-m",
        "haizflow.pipeline.omnivoice_tts",
        "--worker",
        str(request_path),
    ]


def _run_worker_process(
    request_path: Path,
    request: dict[str, Any],
    video_id: str,
    progress_callback=None,
) -> tuple[int, str]:
    """Run one isolated inference attempt and surface stage progress."""
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    process = subprocess.Popen(
        _worker_command(request_path),
        cwd=str(Path(__file__).resolve().parents[3]),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stop_progress = threading.Event()
    monitor_state = {
        "abort_reason": "",
        "last_activity": time.monotonic(),
        "last_heartbeat": time.monotonic(),
    }

    def monitor_progress() -> None:
        status_path = Path(str(request["status_path"]))
        last_completed = -1
        last_stage = ""
        last_current = -1
        stall_timeout = (
            _GPU_STALL_TIMEOUT_SECONDS
            if str(request.get("device") or "").startswith("cuda")
            else _CPU_STALL_TIMEOUT_SECONDS
        )
        # Status changes only at model/segment boundaries. A sub-second poll is
        # responsive enough without repeatedly opening the same file while the
        # worker is publishing it on Windows.
        while not stop_progress.wait(0.75):
            now = time.monotonic()
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
                completed = int(status.get("completed", 0))
                total = int(status.get("total", len(request.get("items") or [])))
                stage = str(status.get("stage") or "synthesizing")
                current = int(status.get("current", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                status = None
            if status is not None and (completed != last_completed or stage != last_stage or current != last_current):
                last_completed = completed
                last_stage = stage
                last_current = current
                monitor_state["last_activity"] = now
                monitor_state["last_heartbeat"] = now
                log_to_video(
                    video_id,
                    f"[TTS][PROGRESS] provider=omnivoice stage={stage} "
                    f"completed={completed}/{total} current={current or '-'}",
                )
                if progress_callback is not None:
                    progress_callback(completed, total, stage)
                continue
            if now - float(monitor_state["last_activity"]) >= stall_timeout:
                monitor_state["abort_reason"] = (
                    "OmniVoice stopped making progress for "
                    f"{stall_timeout // 60} minutes while running on "
                    f"{request.get('device') or 'cpu'}."
                )
                log_to_video(
                    video_id,
                    f"[TTS][ERROR] {monitor_state['abort_reason']}",
                )
                try:
                    process.kill()
                except OSError:
                    pass
                return
            if now - float(monitor_state["last_heartbeat"]) >= _HEARTBEAT_LOG_INTERVAL_SECONDS:
                monitor_state["last_heartbeat"] = now
                log_to_video(
                    video_id,
                    "[TTS][WAIT] OmniVoice is still working "
                    f"(stage={last_stage or 'starting'}, item={last_current or '-'}).",
                )

    progress_thread = threading.Thread(
        target=monitor_progress,
        name="omnivoice-progress",
        daemon=True,
    )
    progress_thread.start()
    try:
        _stdout, stderr = communicate_process(
            video_id,
            process,
            label="OmniVoice synthesis",
            timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
        )
    finally:
        stop_progress.set()
        progress_thread.join(timeout=1.0)
    detail = str(stderr or "")
    if monitor_state["abort_reason"]:
        detail = f"{detail}\n{monitor_state['abort_reason']}".strip()
    return int(process.returncode or 0), detail


def _is_cuda_resource_failure(detail: str) -> bool:
    normalized = str(detail or "").lower()
    return any(
        marker in normalized
        for marker in (
            "cuda out of memory",
            "cuda error",
            "cublas",
            "cudnn",
            "not enough memory",
            "cuda is unavailable",
            "unable to find an engine to execute this computation",
        )
    )


def _encode_mp3(wav_path: Path, output_path: Path, video_id: str) -> None:
    temporary_output = output_path.with_name(f"{output_path.name}.part")
    temporary_output.unlink(missing_ok=True)
    process = subprocess.Popen(
        [
            _binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-i",
            str(wav_path),
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "3",
            "-f",
            "mp3",
            str(temporary_output),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _stdout, stderr = communicate_process(
        video_id,
        process,
        label="OmniVoice audio encoding",
        timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
    )
    if process.returncode != 0 or not temporary_output.is_file() or temporary_output.stat().st_size <= 0:
        temporary_output.unlink(missing_ok=True)
        raise RuntimeError((stderr or "FFmpeg could not encode OmniVoice audio.").strip()[:500])
    os.replace(temporary_output, output_path)


def synthesize_batch_to_mp3(
    items: list[dict[str, str]],
    video_id: str,
    *,
    language_id: str,
    speaker_mode: str = "single",
    progress_callback=None,
) -> None:
    """Load OmniVoice once and synthesize all missing segments in one worker."""
    if not items:
        return
    check_cancellation(video_id)
    log_to_video(
        video_id,
        "[TTS][PREPARE] provider=omnivoice stage=verifying_runtime "
        "detail=Checking the local model and isolated SDK runtime.",
    )
    _prepare_isolated_runtime()
    model_root = verify_omnivoice_model(Path(MODELS_DIR) / "omnivoice")
    runtime_tmp = Path(TMP_DIR)
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="omnivoice-", dir=runtime_tmp) as temp_name:
        temp_root = Path(temp_name)
        request_items: list[dict[str, str]] = []
        output_pairs: list[tuple[Path, Path]] = []
        for index, item in enumerate(items, 1):
            output = Path(str(item["output_path"])).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            wav = temp_root / f"voice-{index:04d}.wav"
            reference_path = str(item.get("reference_path") or "")
            reference_text = str(item.get("reference_text") or "")
            source_audio = str(item.get("source_audio_path") or "")
            if speaker_mode == "multiple" and not reference_path and source_audio:
                reference_wav = temp_root / f"source-speaker-{index:04d}.wav"
                start = max(0.0, float(item.get("source_start") or 0.0))
                end = max(start + 0.1, float(item.get("source_end") or start + 0.1))
                process = subprocess.Popen(
                    [
                        _binary("ffmpeg"), "-y", "-v", "error", "-ss", f"{start:.3f}",
                        "-to", f"{end:.3f}", "-i", source_audio, "-vn", "-ac", "1",
                        "-ar", str(_SAMPLE_RATE), "-c:a", "pcm_s16le", str(reference_wav),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                _stdout, stderr = communicate_process(
                    video_id,
                    process,
                    label=f"OmniVoice speaker reference {index}",
                    timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
                )
                if process.returncode != 0 or not reference_wav.is_file() or reference_wav.stat().st_size <= 44:
                    raise RuntimeError((stderr or "Could not prepare a source-speaker reference.").strip()[:500])
                reference_path = str(reference_wav)
                reference_text = str(item.get("source_text") or "").strip()
            request_items.append(
                {
                    "text": str(item.get("text") or "").strip(),
                    "voice": str(item.get("voice") or "omnivoice:female"),
                    "wav_path": str(wav),
                    "reference_path": reference_path,
                    "reference_text": reference_text,
                }
            )
            output_pairs.append((wav, output))
        request = {
            "model_root": str(model_root),
            "site_packages": str(_sdk_root() / "site-packages"),
            "device": "cuda:0" if processing_device_preference() == "gpu" else "cpu",
            "language": _omnivoice_language_id(language_id),
            "items": request_items,
            "speaker_mode": "multiple" if speaker_mode == "multiple" else "single",
            "status_path": str(temp_root / "status.json"),
            # One stable latent seed per voice keeps a single narrator's
            # identity consistent across every subtitle segment in the video.
            "voice_seed": int.from_bytes(
                hashlib.sha256(str(request_items[0].get("voice") or "omnivoice:female").encode("utf-8")).digest()[:4],
                "big",
            ),
        }
        request_path = temp_root / "request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        log_to_video(
            video_id,
            f"[TTS][PREPARE] provider=omnivoice stage=launching_worker "
            f"device={request['device']} segments={len(request_items)}",
        )
        return_code, stderr = _run_worker_process(
            request_path,
            request,
            video_id,
            progress_callback,
        )
        if return_code != 0 and str(request["device"]).startswith("cuda") and _is_cuda_resource_failure(stderr):
            log_to_video(
                video_id,
                "[TTS][WARN] OmniVoice ran out of GPU resources; retrying this video on CPU.",
            )
            for wav, _output in output_pairs:
                wav.unlink(missing_ok=True)
            Path(str(request["status_path"])).unlink(missing_ok=True)
            request["device"] = "cpu"
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            return_code, stderr = _run_worker_process(
                request_path,
                request,
                video_id,
                progress_callback,
            )
        if return_code != 0:
            detail = (stderr or "OmniVoice worker stopped unexpectedly.").strip()
            raise RuntimeError(detail[-1200:])
        for wav, output in output_pairs:
            check_cancellation(video_id)
            if not wav.is_file() or wav.stat().st_size <= 44:
                raise RuntimeError("OmniVoice did not produce a valid waveform.")
            _encode_mp3(wav, output, video_id)


def synthesize_to_mp3(
    text: str,
    voice: str,
    output_path: str,
    video_id: str,
    *,
    language_id: str,
    reference_path: str = "",
    reference_text: str = "",
) -> None:
    synthesize_batch_to_mp3(
        [
            {
                "text": text,
                "voice": voice,
                "output_path": output_path,
                "reference_path": reference_path,
                "reference_text": reference_text,
            }
        ],
        video_id,
        language_id=language_id,
    )


def runtime_description() -> str:
    return "cuda:0 (isolated worker)" if processing_device_preference() == "gpu" else "cpu (isolated worker)"


def clear_runtime() -> None:
    """Workers are process-scoped, so no parent-process model can remain loaded."""


def _worker_main(request_path: str) -> int:
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    site_packages = str(request["site_packages"])
    sys.path.insert(0, site_packages)

    # Imports intentionally happen only after the isolated Transformers 5 path
    # is first.  The desktop process keeps its pinned Transformers 4 runtime.
    import numpy as np  # noqa: PLC0415
    import soundfile as sf  # noqa: PLC0415
    import torch  # noqa: PLC0415
    from omnivoice import OmniVoice  # noqa: PLC0415

    items = request.get("items") or []
    status_path = Path(str(request.get("status_path") or ""))

    def write_status(completed: int, stage: str, *, current: int = 0) -> None:
        _write_status_file(
            status_path,
            {
                "completed": completed,
                "total": len(items),
                "stage": stage,
                "current": current,
            },
        )

    device = str(request.get("device") or "cpu")
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("OmniVoice GPU mode was selected, but CUDA is unavailable.")
    if device.startswith("cuda"):
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    else:
        # Leave one logical core for Qt, FFmpeg and the operating system while
        # keeping local synthesis responsive on high-core-count machines.
        torch.set_num_threads(max(1, min(8, (os.cpu_count() or 4) - 1)))
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
    write_status(0, "loading_model")
    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    model = OmniVoice.from_pretrained(
        str(request["model_root"]),
        device_map=device,
        dtype=dtype,
        low_cpu_mem_usage=True,
    )
    voice_seed = int(request.get("voice_seed") or 0) & 0x7FFFFFFF
    speaker_mode = str(request.get("speaker_mode") or "single")
    synthesis_items = list(items)
    anchor_prompt: Any = None
    prompt_cache: dict[tuple[str, str], Any] = {}

    def reset_seed() -> None:
        torch.manual_seed(voice_seed)
        np.random.seed(voice_seed % (2**32 - 1))
        if device.startswith("cuda"):
            torch.cuda.manual_seed_all(voice_seed)

    # A dedicated short prompt avoids turning one 20-40 second translated
    # paragraph into the reference for the whole video. It is useful only for
    # multi-segment preset narration; previews and explicit clone references
    # do not need this extra generation.
    if speaker_mode == "single" and len(synthesis_items) > 1:
        anchor_candidate = _select_voice_anchor(synthesis_items)
        if anchor_candidate is not None:
            anchor_text = _voice_anchor_excerpt(str(anchor_candidate.get("text") or ""))
            if anchor_text:
                anchor_instruction = OMNIVOICE_VOICE_INSTRUCTIONS.get(
                    str(anchor_candidate.get("voice") or "").strip().lower(),
                    OMNIVOICE_VOICE_INSTRUCTIONS["omnivoice:female"],
                )
                write_status(0, "creating_voice_anchor")
                reset_seed()
                generated_anchor: Any = None
                anchor_waveform: Any = None
                try:
                    with torch.inference_mode():
                        generated_anchor = model.generate(
                            text=anchor_text,
                            language=str(request.get("language") or "") or None,
                            instruct=anchor_instruction,
                            num_step=32,
                            normalize_text=True,
                            audio_chunk_duration=10.0,
                            audio_chunk_threshold=8.0,
                        )
                    anchor_waveform = (
                        generated_anchor[0]
                        if isinstance(generated_anchor, (list, tuple))
                        else generated_anchor
                    )
                    if isinstance(anchor_waveform, torch.Tensor):
                        anchor_waveform = anchor_waveform.detach().float().cpu().numpy()
                    anchor_waveform = np.asarray(anchor_waveform, dtype=np.float32).reshape(-1)
                    if anchor_waveform.size < 240 or not np.isfinite(anchor_waveform).all():
                        raise RuntimeError("OmniVoice returned an invalid narrator anchor.")
                    anchor_path = status_path.parent / "narrator-anchor.wav"
                    sample_rate = int(getattr(model, "sampling_rate", None) or _SAMPLE_RATE)
                    sf.write(str(anchor_path), anchor_waveform, sample_rate, subtype="PCM_16")
                    anchor_prompt = model.create_voice_clone_prompt(
                        ref_audio=str(anchor_path),
                        ref_text=anchor_text,
                    )
                finally:
                    del generated_anchor, anchor_waveform

    write_status(0, "synthesizing")
    for completed, item in enumerate(synthesis_items, 1):
        write_status(completed - 1, "synthesizing", current=completed)
        text = str(item.get("text") or "").strip()
        if not text:
            raise RuntimeError("OmniVoice received an empty subtitle segment.")
        instruction = OMNIVOICE_VOICE_INSTRUCTIONS.get(
            str(item.get("voice") or "").strip().lower(),
            OMNIVOICE_VOICE_INSTRUCTIONS["omnivoice:female"],
        )
        reference_path = str(item.get("reference_path") or "").strip()
        reference_text = str(item.get("reference_text") or "").strip()
        voice_clone_prompt: Any = None
        if reference_path:
            prompt_key = (reference_path, reference_text)
            # Multiple-speaker mode creates a different reference for nearly
            # every subtitle. Retaining all of those GPU prompts caused DAC
            # convolution failures after several segments on 8 GB cards.
            cache_prompt = speaker_mode != "multiple"
            voice_clone_prompt = prompt_cache.get(prompt_key) if cache_prompt else None
            if voice_clone_prompt is None:
                voice_clone_prompt = model.create_voice_clone_prompt(
                    ref_audio=reference_path,
                    ref_text=reference_text or None,
                )
                if cache_prompt:
                    prompt_cache[prompt_key] = voice_clone_prompt
        elif speaker_mode == "single" and anchor_prompt is not None:
            voice_clone_prompt = anchor_prompt
        generated: Any = None
        waveform: Any = None
        try:
            # OmniVoice is generative. Resetting the same voice-specific seed
            # before each utterance prevents random speaker-identity drift
            # while text and prosody remain segment-specific.
            reset_seed()
            with torch.inference_mode():
                generated = model.generate(
                    text=text,
                    language=str(request.get("language") or "") or None,
                    instruct=None if voice_clone_prompt is not None else instruction,
                    voice_clone_prompt=voice_clone_prompt,
                    num_step=32,
                    normalize_text=True,
                    audio_chunk_duration=10.0,
                    audio_chunk_threshold=8.0,
                )
            waveform = generated[0] if isinstance(generated, (list, tuple)) else generated
            if isinstance(waveform, torch.Tensor):
                waveform = waveform.detach().float().cpu().numpy()
            waveform = np.asarray(waveform, dtype=np.float32).reshape(-1)
            if waveform.size < 240 or not np.isfinite(waveform).all():
                raise RuntimeError("OmniVoice returned empty or invalid audio.")
            sample_rate = int(getattr(model, "sampling_rate", None) or _SAMPLE_RATE)
            sf.write(str(item["wav_path"]), waveform, sample_rate, subtype="PCM_16")
            write_status(completed, "synthesizing")
        finally:
            # A video can contain hundreds of calls to generate().  Keep the
            # model resident, but release per-utterance tensors immediately so
            # an 8 GB GPU does not accumulate allocator pressure until OOM.
            del generated, waveform, voice_clone_prompt
            if device.startswith("cuda") and speaker_mode == "multiple":
                # Per-segment clone prompts are intentionally short-lived.
                # Return their blocks to the allocator before the next DAC
                # decode instead of accumulating unique speaker references.
                torch.cuda.empty_cache()
    if device.startswith("cuda"):
        # Emptying the CUDA allocator after every sentence forces a device
        # synchronization and defeats buffer reuse. Release cached blocks once
        # after the complete batch instead.
        torch.cuda.empty_cache()
    write_status(len(items), "completed")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) == 2 and arguments[0] in {"--worker", "--omnivoice-worker"}:
        return _worker_main(arguments[1])
    raise SystemExit("OmniVoice worker requires a request file.")


if __name__ == "__main__":
    raise SystemExit(main())
