"""Checksum-pinned OmniVoice synthesis in a dependency-isolated worker."""

from __future__ import annotations

import hashlib
import gc
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from collections import deque
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS, MODELS_DIR, TMP_DIR
from haizflow.core.hardware import processing_device_preference
from haizflow.core.model_integrity import (
    OMNIVOICE_RUNTIME_FILES,
    verify_omnivoice_model,
    verify_omnivoice_sdk,
)
from haizflow.pipeline.process_registry import (
    check_cancellation,
    communicate_process,
    register_process,
    unregister_process,
)
from haizflow.services.video_store import log_to_video
from haizflow.utils.ffmpeg import _binary

_RUNTIME_MARKER_VERSION = "omnivoice-0.2.1-transformers-5.3.0-hub-1.3.0-httpx-0.28.1"
_SAMPLE_RATE = 24_000
_RUNTIME_PREPARE_LOCK = threading.Lock()
_PERSISTENT_WORKER_LOCK = threading.RLock()
_PERSISTENT_OPERATION_LOCK = threading.Lock()
_PERSISTENT_WORKER_PROCESS: subprocess.Popen[str] | None = None
_PERSISTENT_WORKER_DEVICE = ""
_PERSISTENT_MODEL_KEY: tuple[str, str] | None = None
_PERSISTENT_IDLE_TIMER: threading.Timer | None = None
_PERSISTENT_STDERR_LOCK = threading.Lock()
_PERSISTENT_STDERR_TAIL: deque[str] = deque(maxlen=192)
_PERSISTENT_STDERR_THREAD: threading.Thread | None = None
_PERSISTENT_WORKER_REGISTRY_ID = "omnivoice-warm-runtime"
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
    # Entertainment presets deliberately use only OmniVoice's documented
    # instruction vocabulary. Distinct preset IDs provide stable latent seeds
    # without claiming to reproduce a real person or protected character.
    "omnivoice:animated_bright": "child, very high pitch",
    "omnivoice:animated_soft": "child, moderate pitch",
    "omnivoice:comic_low": "child, low pitch",
    "omnivoice:tech_presenter": "male, young adult, moderate pitch",
    "omnivoice:show_host": "female, young adult, high pitch",
    "omnivoice:trailer_deep": "male, young adult, low pitch",
    "omnivoice:radio_warm": "female, young adult, low pitch",
    "omnivoice:mystery_whisper": "whisper, elderly, low pitch",
    "omnivoice:female_gentle": "female, young adult, moderate pitch",
    "omnivoice:male_soft": "male, young adult, low pitch",
    "omnivoice:female_confident": "female, young adult, high pitch",
    "omnivoice:male_broadcast": "male, elderly, moderate pitch",
    "omnivoice:child_bright": "child, high pitch",
    "omnivoice:elder_warm": "elderly, low pitch",
    "omnivoice:comic_high": "child, very high pitch",
    "omnivoice:documentary": "male, elderly, low pitch",
}

# The desktop catalog uses ISO 639-1 identifiers. OmniVoice accepts most of
# those directly, but its language table represents Modern Standard Arabic by
# the ISO 639-3 identifier ``arb``. Keep the translation at this integration
# boundary so projects and the rest of the pipeline retain their stable
# two-letter language contract.
OMNIVOICE_LANGUAGE_IDS = {
    "ar": "arb",
}

OMNIVOICE_NARRATOR_ANCHORS = {
    "vi": "Giọng kể này được giữ ổn định và tự nhiên trong suốt video.",
    "en": "This narrator keeps a clear and consistent voice throughout the video.",
    "zh": "这位旁白在整段视频中保持清晰自然的声音。",
    "hi": "यह कथावाचक पूरे वीडियो में एक स्पष्ट और समान आवाज़ बनाए रखता है।",
    "es": "Esta narración mantiene una voz clara y constante durante todo el video.",
    "fr": "Cette narration garde une voix claire et constante pendant toute la vidéo.",
    "arb": "يحافظ هذا الراوي على صوت واضح ومتناسق طوال الفيديو.",
    "pt": "Esta narração mantém uma voz clara e consistente durante todo o vídeo.",
    "ru": "Этот диктор сохраняет ясный и ровный голос на протяжении всего видео.",
    "id": "Narator ini menjaga suara yang jelas dan konsisten sepanjang video.",
    "de": "Diese Erzählstimme bleibt im gesamten Video klar und einheitlich.",
    "ja": "このナレーションは動画全体で自然で一貫した声を保ちます。",
    "ko": "이 내레이션은 영상 전체에서 자연스럽고 일관된 목소리를 유지합니다.",
    "it": "Questa narrazione mantiene una voce chiara e uniforme per tutto il video.",
    "th": "เสียงบรรยายนี้คงความชัดเจนและสม่ำเสมอตลอดทั้งวิดีโอ",
    "fil": "Pananatilihin ng tagapagsalaysay ang malinaw at pare-parehong boses sa buong video.",
}


def _omnivoice_language_id(language_id: str) -> str:
    normalized = str(language_id or "").strip().lower()
    return OMNIVOICE_LANGUAGE_IDS.get(normalized, normalized)


def _narrator_anchor_text(language_id: str) -> str:
    return OMNIVOICE_NARRATOR_ANCHORS.get(
        _omnivoice_language_id(language_id),
        OMNIVOICE_NARRATOR_ANCHORS["en"],
    )


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
    temporary = status_path.with_name(f".{status_path.name}.{os.getpid()}.{threading.get_ident()}.part")
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
        if str(item.get("text") or "").strip() and not str(item.get("reference_path") or "").strip()
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

    sentences = [value.strip() for value in re.split(r"(?<=[.!?\u3002\uff01\uff1f;:])\s*", normalized) if value.strip()]
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
        site_packages / "httpx" / "__init__.py",
        site_packages / "httpcore" / "__init__.py",
        site_packages / "anyio" / "__init__.py",
        site_packages / "h11" / "__init__.py",
        site_packages / "idna" / "__init__.py",
        site_packages / "typing_extensions.py",
        site_packages / "certifi" / "__init__.py",
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
        for filename in OMNIVOICE_RUNTIME_FILES:
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
    from haizflow.services.resource_packs import installed_engine_command

    external = installed_engine_command(
        "voice",
        "omnivoice_worker",
        {"provider": "omnivoice-gpu" if str(json.loads(request_path.read_text(encoding="utf-8")).get("device")).startswith("cuda") else "omnivoice"},
    )
    if external:
        return [*external, str(request_path)]
    if getattr(sys, "frozen", False):
        return [sys.executable, "--omnivoice-worker", str(request_path)]
    return [
        sys.executable,
        "-m",
        "haizflow.pipeline.omnivoice_tts",
        "--worker",
        str(request_path),
    ]


def _worker_server_command(device: str = "") -> list[str]:
    from haizflow.services.resource_packs import installed_engine_command

    external = installed_engine_command(
        "voice",
        "omnivoice_server",
        {"provider": "omnivoice-gpu" if (device or processing_device_preference()) in {"gpu", "cuda:0"} else "omnivoice"},
    )
    if external:
        return external
    if getattr(sys, "frozen", False):
        return [sys.executable, "--omnivoice-server"]
    return [
        sys.executable,
        "-m",
        "haizflow.pipeline.omnivoice_tts",
        "--server",
    ]


def _worker_environment() -> dict[str, str]:
    from haizflow.core.paths import engine_environment

    environment = engine_environment()
    environment["PYTHONFAULTHANDLER"] = "1"
    # Transformers 5 materializes safetensors in a thread pool by default.
    # On Windows/CUDA this can crash natively during model loading and raises
    # peak memory. Use its supported sequential loader in this isolated worker.
    environment["HF_DEACTIVATE_ASYNC_LOAD"] = "1"
    environment["PYTHONUTF8"] = "1"
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    environment["OMP_NUM_THREADS"] = "1"
    environment["MKL_NUM_THREADS"] = "1"
    # Development/source launches do not necessarily inherit the editable
    # install's ``src`` entry.  The long-lived worker is started with
    # ``python -m haizflow...``; without this path both the warm worker and its
    # isolated fallback exit before they can read a synthesis request.  Frozen
    # builds use their embedded importer and must not be coupled to a source
    # checkout.
    if not getattr(sys, "frozen", False):
        source_root = str(Path(__file__).resolve().parents[2])
        inherited = [
            value
            for value in environment.get("PYTHONPATH", "").split(os.pathsep)
            if value
        ]
        normalized = {os.path.normcase(os.path.abspath(value)) for value in inherited}
        if os.path.normcase(os.path.abspath(source_root)) not in normalized:
            inherited.insert(0, source_root)
        environment["PYTHONPATH"] = os.pathsep.join(inherited)
    return environment


def _log_monitor_event(video_id: str, message: str) -> None:
    """Keep status monitoring alive if the metadata/log file is temporarily busy."""
    try:
        log_to_video(video_id, message)
    except OSError:
        # TimeoutError from the metadata lock is an OSError too. Losing one
        # diagnostic entry must not disable progress or stalled-worker checks.
        pass


def _stop_persistent_worker_unlocked() -> None:
    global _PERSISTENT_WORKER_PROCESS, _PERSISTENT_STDERR_THREAD
    global _PERSISTENT_MODEL_KEY
    _cancel_idle_shutdown()
    process = _PERSISTENT_WORKER_PROCESS
    _PERSISTENT_WORKER_PROCESS = None
    _PERSISTENT_MODEL_KEY = None
    if process is None:
        return
    try:
        if process.stdin is not None:
            process.stdin.write("__quit__\n")
            process.stdin.flush()
    except (OSError, ValueError):
        pass
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
    stderr_thread = _PERSISTENT_STDERR_THREAD
    _PERSISTENT_STDERR_THREAD = None
    if stderr_thread is not None and stderr_thread is not threading.current_thread():
        stderr_thread.join(timeout=0.5)
    unregister_process(_PERSISTENT_WORKER_REGISTRY_ID, process, force=True)


def _drain_persistent_stderr(process: subprocess.Popen[str]) -> None:
    """Drain worker diagnostics without allowing a full stderr pipe to stall inference."""
    stream = process.stderr
    if stream is None:
        return
    try:
        while True:
            chunk = stream.read(1024)
            if not chunk:
                return
            with _PERSISTENT_STDERR_LOCK:
                _PERSISTENT_STDERR_TAIL.append(chunk)
    except (OSError, ValueError):
        return


def _persistent_worker_error_tail(process: subprocess.Popen[str]) -> str:
    """Return the useful end of stderr after a crashed persistent worker."""
    stderr_thread = _PERSISTENT_STDERR_THREAD
    if process.poll() is not None and stderr_thread is not None:
        stderr_thread.join(timeout=0.5)
    with _PERSISTENT_STDERR_LOCK:
        return "".join(_PERSISTENT_STDERR_TAIL).strip()[-4000:]


def _cancel_idle_shutdown() -> None:
    global _PERSISTENT_IDLE_TIMER
    if _PERSISTENT_IDLE_TIMER is not None:
        _PERSISTENT_IDLE_TIMER.cancel()
        _PERSISTENT_IDLE_TIMER = None


def _schedule_idle_shutdown() -> None:
    global _PERSISTENT_IDLE_TIMER
    _cancel_idle_shutdown()
    def expire():
        # A cancelled timer may already be waiting for the worker lock.
        with _PERSISTENT_WORKER_LOCK:
            if _PERSISTENT_IDLE_TIMER is timer:
                _stop_persistent_worker_unlocked()

    timer = threading.Timer(300.0, expire)
    timer.daemon = True
    _PERSISTENT_IDLE_TIMER = timer
    timer.start()


def _persistent_worker_unlocked(device: str = "") -> subprocess.Popen[str]:
    global _PERSISTENT_WORKER_PROCESS, _PERSISTENT_STDERR_THREAD, _PERSISTENT_WORKER_DEVICE
    _cancel_idle_shutdown()
    process = _PERSISTENT_WORKER_PROCESS
    if process is not None and process.poll() is None and process.stdin is not None and (not device or device == _PERSISTENT_WORKER_DEVICE):
        return process
    _stop_persistent_worker_unlocked()
    with _PERSISTENT_STDERR_LOCK:
        _PERSISTENT_STDERR_TAIL.clear()
    process = subprocess.Popen(
        _worker_server_command(device),
        cwd=str(Path(__file__).resolve().parents[3]),
        env=_worker_environment(),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stderr_thread = threading.Thread(
        target=_drain_persistent_stderr,
        args=(process,),
        name="omnivoice-worker-stderr",
        daemon=True,
    )
    _PERSISTENT_STDERR_THREAD = stderr_thread
    stderr_thread.start()
    register_process(_PERSISTENT_WORKER_REGISTRY_ID, process)
    _PERSISTENT_WORKER_PROCESS = process
    _PERSISTENT_WORKER_DEVICE = device
    return process


def _timing_detail(status: dict[str, Any]) -> str:
    values = status.get("timing_seconds")
    if not isinstance(values, dict):
        return ""
    parts = []
    for key in ("runtime_imports", "model_load", "reference_encoding", "synthesis"):
        value = values.get(key)
        if isinstance(value, (int, float)) and 0 <= value <= MEDIA_PROCESS_TIMEOUT_SECONDS:
            parts.append(f"{key}={value:.2f}s")
    for key in ("batch_size", "batch_retries"):
        value = status.get(key)
        if isinstance(value, int) and 0 <= value <= 1024:
            parts.append(f"{key}={value}")
    return " " + " ".join(parts) if parts else ""


def _request_model_key(request: dict[str, Any]) -> tuple[str, str]:
    return str(request.get("model_root") or ""), str(request.get("device") or "cpu")


def _cpu_voice_threads() -> int:
    from haizflow.core.hardware import cpu_runtime_profile

    # Choose before loading the FP32 weights. Their own resident memory must
    # not make every otherwise healthy 16 GiB machine drop to two threads.
    return max(1, min(8, cpu_runtime_profile(force_cpu=True).cpu_threads))


@contextmanager
def _inference_activity(model, callback):
    """Observe real decoder forwards, never a timer heartbeat or fake completion."""
    register = getattr(model, "register_forward_hook", None)
    handle = register(lambda *_args: callback()) if callable(register) else None
    try:
        yield
    finally:
        if handle is not None:
            handle.remove()


def _preflight_cpu_request(request: dict[str, Any], *, allow_resident: bool = False) -> None:
    if str(request.get("device") or "cpu").startswith("cuda"):
        return
    from haizflow.core.memory import require_cpu_memory

    with _PERSISTENT_WORKER_LOCK:
        process = _PERSISTENT_WORKER_PROCESS
        if allow_resident and process is not None and process.poll() is None and (
            _PERSISTENT_WORKER_DEVICE != str(request.get("device") or "cpu")
            or (_PERSISTENT_MODEL_KEY is not None and _PERSISTENT_MODEL_KEY != _request_model_key(request))
        ):
            _stop_persistent_worker_unlocked()
            process = None
        resident = bool(allow_resident and process is not None and process.poll() is None
                        and _PERSISTENT_MODEL_KEY == _request_model_key(request))
    require_cpu_memory("voice", resident=resident)


def _run_worker_process(
    request_path: Path,
    request: dict[str, Any],
    video_id: str,
    progress_callback=None,
    *,
    cancellation_id: str | None = None,
) -> tuple[int, str]:
    """Run one isolated inference attempt and surface stage progress."""
    process_key = cancellation_id or video_id
    check_cancellation(process_key)
    _preflight_cpu_request(request)
    environment = _worker_environment()
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
        last_forwards = -1
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
                forwards = int(status.get("inference_forwards", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                status = None
            if status is not None and (completed != last_completed or stage != last_stage or current != last_current
                                       or forwards != last_forwards):
                last_completed = completed
                last_stage = stage
                last_current = current
                last_forwards = forwards
                monitor_state["last_activity"] = now
                monitor_state["last_heartbeat"] = now
                _log_monitor_event(
                    video_id,
                    f"[TTS][PROGRESS] provider=omnivoice stage={stage} "
                    f"completed={completed}/{total} current={current or '-'}{_timing_detail(status)}",
                )
                if progress_callback is not None:
                    try:
                        progress_callback(completed, total, stage)
                    except Exception as exc:
                        monitor_state["abort_reason"] = str(exc)
                        try:
                            process.terminate()
                        except OSError:
                            pass
                        return
                continue
            if now - float(monitor_state["last_activity"]) >= stall_timeout:
                monitor_state["abort_reason"] = (
                    "OmniVoice stopped making progress for "
                    f"{stall_timeout // 60} minutes while running on "
                    f"{request.get('device') or 'cpu'}."
                )
                _log_monitor_event(
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
                _log_monitor_event(
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
            process_key,
            process,
            label="OmniVoice synthesis",
            timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
        )
    finally:
        stop_progress.set()
        progress_thread.join()
    check_cancellation(process_key)
    detail = str(stderr or "")
    if monitor_state["abort_reason"]:
        detail = f"{detail}\n{monitor_state['abort_reason']}".strip()
    if process.returncode and not detail:
        code = int(process.returncode) & 0xFFFFFFFF
        detail = f"OmniVoice worker exited during model loading (0x{code:08X})."
    return int(process.returncode or 0), detail


@contextmanager
def _cancellable_voice_operation(cancellation_id: str):
    # Speculative warm-up or another request may own the resident worker.
    # Cancelling a waiter must neither wait for inference nor kill its owner.
    while not _PERSISTENT_OPERATION_LOCK.acquire(timeout=0.15):
        check_cancellation(cancellation_id)
    try:
        check_cancellation(cancellation_id)
        yield
    finally:
        _PERSISTENT_OPERATION_LOCK.release()


def _run_persistent_worker_process(
    request_path: Path,
    request: dict[str, Any],
    video_id: str,
    progress_callback=None,
    *,
    cancellation_id: str | None = None,
) -> tuple[int, str]:
    """Run inference in a long-lived isolated process that keeps the model warm."""
    global _PERSISTENT_MODEL_KEY
    response_path = request_path.with_name("response.json")
    response_path.unlink(missing_ok=True)
    request["response_path"] = str(response_path)
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    status_path = Path(str(request["status_path"]))
    stall_timeout = (
        _GPU_STALL_TIMEOUT_SECONDS
        if str(request.get("device") or "").startswith("cuda")
        else _CPU_STALL_TIMEOUT_SECONDS
    )

    process_key = cancellation_id or video_id
    with _cancellable_voice_operation(process_key):
        with _PERSISTENT_WORKER_LOCK:
            check_cancellation(process_key)
            _preflight_cpu_request(request, allow_resident=True)
            process = _persistent_worker_unlocked(str(request.get("device") or "cpu"))
            # Bind the active request, not the resident worker's entire lifetime,
            # to its video. Pause can then interrupt a long synthesis even if
            # the status callback is busy encoding/publishing completed clips.
            try:
                register_process(process_key, process)
            except BaseException:
                _stop_persistent_worker_unlocked()
                raise
            try:
                assert process.stdin is not None
                process.stdin.write(f"{request_path}\n")
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                unregister_process(process_key, process)
                _stop_persistent_worker_unlocked()
                check_cancellation(process_key)
                return 1, f"Could not start the warm OmniVoice request: {exc}"
            except BaseException:
                unregister_process(process_key, process)
                _stop_persistent_worker_unlocked()
                raise

        last_completed = -1
        last_stage = ""
        last_current = -1
        last_forwards = -1
        last_activity = time.monotonic()
        last_heartbeat = last_activity
        started = last_activity
        try:
            while True:
                check_cancellation(cancellation_id or video_id)
                if response_path.is_file():
                    try:
                        response = json.loads(response_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError, TypeError, json.JSONDecodeError):
                        time.sleep(0.05)
                        continue
                    with _PERSISTENT_WORKER_LOCK:
                        if _PERSISTENT_WORKER_PROCESS is process:
                            _PERSISTENT_MODEL_KEY = _request_model_key(request) if int(response.get("return_code", 1)) == 0 else None
                            _schedule_idle_shutdown()
                    return int(response.get("return_code", 1)), str(response.get("error") or "")
                if process.poll() is not None:
                    detail = f"Warm OmniVoice worker exited unexpectedly ({process.returncode})."
                    stderr_tail = _persistent_worker_error_tail(process)
                    if stderr_tail:
                        detail = f"{detail}\n{stderr_tail}"
                    with _PERSISTENT_WORKER_LOCK:
                        if _PERSISTENT_WORKER_PROCESS is process:
                            _stop_persistent_worker_unlocked()
                    return int(process.returncode or 1), detail

                now = time.monotonic()
                try:
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    completed = int(status.get("completed", 0))
                    total = int(status.get("total", len(request.get("items") or [])))
                    stage = str(status.get("stage") or "synthesizing")
                    current = int(status.get("current", 0))
                    forwards = int(status.get("inference_forwards", 0))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    status = None
                if status is not None and (
                    completed != last_completed or stage != last_stage or current != last_current
                    or forwards != last_forwards
                ):
                    last_completed = completed
                    last_stage = stage
                    last_current = current
                    last_forwards = forwards
                    last_activity = now
                    last_heartbeat = now
                    log_to_video(
                        video_id,
                        f"[TTS][PROGRESS] provider=omnivoice stage={stage} "
                        f"completed={completed}/{total} current={current or '-'} "
                        f"decoder_forwards={forwards}{_timing_detail(status)}",
                    )
                    if progress_callback is not None:
                        progress_callback(completed, total, stage)
                elif now - last_activity >= stall_timeout:
                    detail = (
                        "OmniVoice stopped making progress for "
                        f"{stall_timeout // 60} minutes while running on "
                        f"{request.get('device') or 'cpu'}."
                    )
                    log_to_video(video_id, f"[TTS][ERROR] {detail}")
                    with _PERSISTENT_WORKER_LOCK:
                        if _PERSISTENT_WORKER_PROCESS is process:
                            _stop_persistent_worker_unlocked()
                    return 1, detail
                elif now - last_heartbeat >= _HEARTBEAT_LOG_INTERVAL_SECONDS:
                    last_heartbeat = now
                    log_to_video(
                        video_id,
                        "[TTS][WAIT] OmniVoice is still working "
                        f"(stage={last_stage or 'starting'}, item={last_current or '-'}).",
                    )
                if now - started >= MEDIA_PROCESS_TIMEOUT_SECONDS:
                    detail = "OmniVoice synthesis exceeded the configured processing timeout."
                    with _PERSISTENT_WORKER_LOCK:
                        if _PERSISTENT_WORKER_PROCESS is process:
                            _stop_persistent_worker_unlocked()
                    return 1, detail
                time.sleep(0.15)
        except BaseException:
            # A cancelled editor generation must not leave an old request
            # consuming the GPU while the replacement waits behind it.
            with _PERSISTENT_WORKER_LOCK:
                if _PERSISTENT_WORKER_PROCESS is process:
                    _stop_persistent_worker_unlocked()
            raise
        finally:
            unregister_process(process_key, process)


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


def _is_persistent_transport_failure(detail: str) -> bool:
    """Identify a failed warm-worker channel, not an inference/model error response."""
    normalized = str(detail or "").lower()
    return any(
        marker in normalized
        for marker in (
            "warm omnivoice worker exited unexpectedly",
            "could not start the warm omnivoice request",
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
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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


def _preset_reference(voice: str, language: str) -> tuple[str, str]:
    """Use the same packaged speaker identity as the library preview."""
    if voice not in OMNIVOICE_VOICE_INSTRUCTIONS or language not in {"vi", "en", "zh"}:
        return "", ""
    root = Path(__file__).resolve().parents[1] / "desktop" / "assets" / "voice_samples"
    try:
        metadata = json.loads((root / "samples.json").read_text(encoding="utf-8"))
        text = str(metadata["sentences"][language]).strip()
        safe_voice = re.sub(r"[^a-zA-Z0-9._-]+", "_", voice).strip("_")
        sample = root / "omnivoice" / safe_voice / f"{language}.mp3"
        if text and sample.is_file() and sample.stat().st_size > 512:
            return str(sample), text
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return "", ""


def _usable_source_reference(start: float, end: float, text: str) -> bool:
    # Chinese captions need not contain spaces. Do not discard every Chinese
    # speaker sample merely because the whitespace-token count is one.
    enough_text = len(text.split()) >= 3 or len(re.findall(r"[\u3400-\u9fff]", text)) >= 6
    return 2.5 <= end - start <= 15.0 and enough_text


def synthesize_batch_to_mp3(
    items: list[dict[str, str]],
    video_id: str,
    *,
    language_id: str,
    speaker_mode: str = "single",
    progress_callback=None,
    keep_worker_warm: bool = False,
    process_registry_id: str | None = None,
    inference_steps: int | None = None,
    narrator_anchor_text: str = "",
    device: str | None = None,
) -> None:
    """Synthesize missing segments, normally reusing one warm isolated model."""
    if not items:
        return
    cancellation_id = process_registry_id or video_id
    check_cancellation(cancellation_id)
    log_to_video(
        video_id,
        "[TTS][PREPARE] provider=omnivoice stage=verifying_runtime "
        "detail=Checking the local model and isolated SDK runtime.",
    )
    prepared_items = [dict(item) for item in items]
    reference_texts: dict[str, str] = {}
    for item in prepared_items:
        if item.get("reference_path") and not str(item.get("reference_text") or "").strip():
            from haizflow.pipeline.voice_reference import transcribe_reference

            reference_path = str(item["reference_path"])
            if reference_path not in reference_texts:
                reference_texts[reference_path] = transcribe_reference(
                    reference_path, video_id, process_registry_id=cancellation_id,
                    device=device or processing_device_preference())
            item["reference_text"] = reference_texts[reference_path]
    items = prepared_items
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
            source_start = max(0.0, float(item.get("source_start") or 0.0))
            source_end = max(source_start, float(item.get("source_end") or source_start))
            source_text = str(item.get("source_text") or "").strip()
            usable_source_reference = _usable_source_reference(source_start, source_end, source_text)
            if speaker_mode == "multiple" and not reference_path and source_audio and not usable_source_reference:
                log_to_video(video_id, f"WARNING: Source voice sample {index} is too short or unreliable "
                             f"({source_end - source_start:.2f}s). Using the library voice instead of cloning this fragment.")
            if speaker_mode == "multiple" and not reference_path and source_audio and usable_source_reference:
                reference_wav = temp_root / f"source-speaker-{index:04d}.wav"
                start, end = source_start, source_end
                process = subprocess.Popen(
                    [
                        _binary("ffmpeg"),
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        f"{start:.3f}",
                        "-to",
                        f"{end:.3f}",
                        "-i",
                        source_audio,
                        "-vn",
                        "-ac",
                        "1",
                        "-ar",
                        str(_SAMPLE_RATE),
                        "-c:a",
                        "pcm_s16le",
                        str(reference_wav),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                _stdout, stderr = communicate_process(
                    cancellation_id,
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
                    "preset_reference_path": _preset_reference(str(item.get("voice") or "omnivoice:female"), language_id)[0],
                    "preset_reference_text": _preset_reference(str(item.get("voice") or "omnivoice:female"), language_id)[1],
                }
            )
            output_pairs.append((wav, output))
        request = {
            "model_root": str(model_root),
            "site_packages": str(_sdk_root() / "site-packages"),
            "device": "cuda:0" if (device or processing_device_preference()) == "gpu" else "cpu",
            "cpu_threads": _cpu_voice_threads() if (device or processing_device_preference()) != "gpu" else 1,
            "language": _omnivoice_language_id(language_id),
            "narrator_anchor_text": str(narrator_anchor_text or "").strip()
            or _narrator_anchor_text(language_id),
            "items": request_items,
            "speaker_mode": "multiple" if speaker_mode == "multiple" else "single",
            "inference_steps": max(8, min(32, int(inference_steps or
                (32 if (device or processing_device_preference()) == "gpu" else 16)))),
            "status_path": str(temp_root / "status.json"),
            # One stable latent seed per voice keeps a single narrator's
            # identity consistent across every subtitle segment in the video.
            "voice_seed": int.from_bytes(
                hashlib.sha256(str(request_items[0].get("voice") or "omnivoice:female").encode("utf-8")).digest()[:4],
                "big",
            ),
        }
        if any(not item.get("reference_path") for item in request_items):
            reference_path, reference_text = _preset_reference(
                str(request_items[0]["voice"]), language_id,
            )
            request["preset_reference_path"] = reference_path
            request["preset_reference_text"] = reference_text
        request_path = temp_root / "request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        log_to_video(
            video_id,
            f"[TTS][PREPARE] provider=omnivoice stage=launching_worker "
            f"device={request['device']} steps={request['inference_steps']} segments={len(request_items)}",
        )
        encoded: set[int] = set()
        encoding_errors: list[Exception] = []

        def publish_completed(completed, total, stage):
            # A worker status is emitted only after sf.write has closed a WAV.
            # Commit each MP3 before reporting it; pause can retain these clips.
            if not encoding_errors:
                try:
                    for index in range(min(max(0, int(completed)), len(output_pairs))):
                        if index not in encoded:
                            wav, output = output_pairs[index]
                            if wav.is_file() and wav.stat().st_size > 44:
                                _encode_mp3(wav, output, cancellation_id)
                                encoded.add(index)
                except Exception as exc:
                    encoding_errors.append(exc)
                    raise
            if progress_callback is not None:
                progress_callback(len(encoded), total, stage)

        worker_runner = _run_persistent_worker_process if keep_worker_warm else _run_worker_process
        worker_kwargs = ({"cancellation_id": cancellation_id}
                         if keep_worker_warm or cancellation_id != video_id else {})
        return_code, stderr = worker_runner(request_path, request, video_id, publish_completed, **worker_kwargs)
        check_cancellation(cancellation_id)
        recovered_invalid_batch = False
        if (return_code != 0 and not encoding_errors and len(request_items) > 1
                and str(request["device"]).startswith("cuda")
                and any(message in str(stderr) for message in (
                    "OmniVoice returned empty or invalid audio",
                    "OmniVoice returned an unexpected number of audio clips",
                ))):
            recovered_invalid_batch = True
            # Older released engines cannot reduce an invalid pair themselves.
            # Keep completed clips and retry each remaining sentence once. A
            # single-sentence failure stays an error; quality/seed are unchanged.
            publish_completed(len(output_pairs), len(output_pairs), "synthesizing")
            if len(encoded) == len(output_pairs):
                return_code, stderr = 0, ""
            log_to_video(video_id, "[TTS][WARN] Invalid GPU audio batch; recovering missing sentences individually.")
            for index, item in enumerate(request_items):
                if index in encoded:
                    continue
                check_cancellation(cancellation_id)
                output_pairs[index][0].unlink(missing_ok=True)
                Path(str(request["status_path"])).unlink(missing_ok=True)
                single_request = {**request, "items": [item]}
                request_path.write_text(json.dumps(single_request, ensure_ascii=False), encoding="utf-8")

                def publish_single(completed, _total, stage, *, target=index):
                    publish_completed(target + 1 if completed else 0, len(output_pairs), stage)

                return_code, stderr = worker_runner(request_path, single_request, video_id, publish_single, **worker_kwargs)
                check_cancellation(cancellation_id)
                if return_code != 0:
                    break
                publish_single(1, 1, "synthesizing")
        if return_code != 0 and not recovered_invalid_batch and keep_worker_warm and _is_persistent_transport_failure(stderr):
            # A warm server is an optimization, never a requirement for a
            # successful edit. Retry the same request once in an isolated
            # process so a stale stdin channel or a crashed resident worker
            # cannot leave one edited subtitle permanently without speech.
            log_to_video(
                video_id,
                "[TTS][WARN] Warm OmniVoice worker stopped; retrying this request in an isolated worker.",
            )
            with _PERSISTENT_WORKER_LOCK:
                _stop_persistent_worker_unlocked()
            return_code, stderr = _run_worker_process(
                request_path,
                request,
                video_id,
                publish_completed,
                **({"cancellation_id": cancellation_id} if cancellation_id != video_id else {}),
            )
            check_cancellation(cancellation_id)
        if return_code != 0 and not recovered_invalid_batch and str(request["device"]).startswith("cuda") and _is_cuda_resource_failure(stderr):
            log_to_video(
                video_id,
                "[TTS][WARN] OmniVoice ran out of GPU resources; retrying this video on CPU.",
            )
            for wav, _output in output_pairs:
                wav.unlink(missing_ok=True)
            Path(str(request["status_path"])).unlink(missing_ok=True)
            request["device"] = "cpu"
            request["cpu_threads"] = _cpu_voice_threads()
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            if keep_worker_warm:
                with _PERSISTENT_WORKER_LOCK:
                    _stop_persistent_worker_unlocked()
            return_code, stderr = worker_runner(request_path, request, video_id, publish_completed, **worker_kwargs)
        if encoding_errors:
            raise encoding_errors[0]
        if return_code != 0:
            detail = (stderr or "OmniVoice worker stopped unexpectedly.").strip()
            raise RuntimeError(detail[-1200:])
        for index, (wav, output) in enumerate(output_pairs):
            if index in encoded:
                continue
            check_cancellation(cancellation_id)
            if not wav.is_file() or wav.stat().st_size <= 44:
                raise RuntimeError("OmniVoice did not produce a valid waveform.")
            _encode_mp3(wav, output, cancellation_id)


def synthesize_to_mp3(
    text: str,
    voice: str,
    output_path: str,
    video_id: str,
    *,
    language_id: str,
    reference_path: str = "",
    reference_text: str = "",
    keep_worker_warm: bool = False,
    inference_steps: int = 32,
    device: str | None = None,
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
        keep_worker_warm=keep_worker_warm,
        inference_steps=inference_steps,
        device=device,
    )


def runtime_description() -> str:
    return "cuda:0 (isolated worker)" if processing_device_preference() == "gpu" else "cpu (isolated worker)"


def clear_runtime() -> None:
    """Release the long-lived isolated model worker and its GPU allocation."""
    with _PERSISTENT_WORKER_LOCK:
        _stop_persistent_worker_unlocked()


def release_model_memory() -> bool:
    """Free weights/voice prompts but retain imported SDK modules when RAM allows.

    Never start a process for this operation. Cancellation/shutdown still use
    clear_runtime(), which terminates the process completely.
    """
    global _PERSISTENT_MODEL_KEY
    from haizflow.core.memory import memory_snapshot

    with _PERSISTENT_OPERATION_LOCK:
        with _PERSISTENT_WORKER_LOCK:
            process = _PERSISTENT_WORKER_PROCESS
            if process is None or process.poll() is not None:
                return False
            _cancel_idle_shutdown()
        try:
            Path(TMP_DIR).mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="omnivoice-release-", dir=TMP_DIR) as directory:
                request_path = Path(directory) / "request.json"
                response_path = Path(directory) / "response.json"
                request_path.write_text(json.dumps({"operation": "release_model", "response_path": str(response_path)}), encoding="utf-8")
                if process.stdin is None:
                    raise RuntimeError("OmniVoice worker input is unavailable.")
                process.stdin.write(f"{request_path}\n")
                process.stdin.flush()
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline and process.poll() is None:
                    if response_path.is_file():
                        response = json.loads(response_path.read_text(encoding="utf-8"))
                        if response.get("return_code") != 0:
                            break
                        if (not response.get("model_released")
                                or int(response.get("resident_cuda_bytes", 0)) > 64 * 1024**2):
                            # A new SDK may retain tensors through a global
                            # cache. Never keep that worker across GPU handoff.
                            break
                        _PERSISTENT_MODEL_KEY = None
                        # Imports alone consume RAM. Retain them only with a
                        # substantial remaining budget for the next model.
                        memory = memory_snapshot()
                        if (memory.usable_bytes is None or memory.usable_bytes < 24 * 1024**3
                                or memory.available_bytes is None or memory.available_bytes < 3 * 1024**3
                                or (os.name == "nt" and memory.commit_available_bytes is None)
                                or (memory.commit_available_bytes is not None and memory.commit_available_bytes < 4 * 1024**3)):
                            break
                        with _PERSISTENT_WORKER_LOCK:
                            if _PERSISTENT_WORKER_PROCESS is process:
                                _schedule_idle_shutdown()
                                return True
                        return False
                    time.sleep(0.05)
        except (OSError, ValueError, RuntimeError):
            pass
        with _PERSISTENT_WORKER_LOCK:
            if _PERSISTENT_WORKER_PROCESS is process:
                _stop_persistent_worker_unlocked()
        return False


def _release_worker_model(runtime: dict[str, Any]) -> None:
    """Release every weight/prompt reference; leave only the imported modules."""
    modules = runtime.get("modules")
    profiles = runtime.get("batch_profiles")
    model = runtime.get("model")
    # Transformers 5.3's Higgs codec uses an lru_cache on a bound method.
    # The cache keys retain `self` and its Conv1d modules (roughly 0.8 GiB),
    # so deleting the model alone does not release the codec's CUDA weights.
    codec = getattr(model, "audio_tokenizer", None)
    layers = getattr(codec, "_get_conv1d_layers", None)
    clear_layers = getattr(layers, "cache_clear", None)
    if callable(clear_layers):
        clear_layers()
    runtime.clear()
    if modules is not None:
        runtime["modules"] = modules
    if profiles is not None:
        runtime["batch_profiles"] = profiles  # Bounded scalar measurements, never tensors/audio.
    del model, codec, layers, clear_layers
    gc.collect()
    if modules is not None:
        torch = modules[2]
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _batch_identity(item: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(item.get(key) or "").strip() for key in (
        "voice", "reference_path", "reference_text", "preset_reference_path", "preset_reference_text",
    ))


def _encode_voice_reference(model, torch, reference, transcript):
    # SDK 0.2.1 does not decorate create_voice_clone_prompt with inference_mode.
    # Its acoustic codec otherwise builds autograd activations on GPU/CPU,
    # despite returning only discrete reference tokens for inference.
    with torch.inference_mode():
        return model.create_voice_clone_prompt(ref_audio=reference, ref_text=transcript)


def _next_synthesis_batch(items: list[dict[str, Any]], offset: int, ceiling: int) -> list[dict[str, Any]]:
    """Batch adjacent similar short utterances with exactly the same voice.

    No sorting: timestamps, progress and pause checkpoints retain their order.
    Long utterances stay single because attention memory grows quadratically.
    """
    first = items[offset]
    length = len(str(first.get("text") or "").strip())
    batch = [first]
    if length > 160 or length == 0:
        return batch
    for item in items[offset + 1:offset + max(1, ceiling)]:
        other = len(str(item.get("text") or "").strip())
        if (_batch_identity(item) != _batch_identity(first) or not other or other > 160
                or max(length, other) > max(24, min(length, other) * 1.6)):
            break
        batch.append(item)
    return batch


def _gpu_batch_ceiling(torch, device: str, maximum: int = 2) -> int:
    """Use reclaimable allocator blocks as well as driver free VRAM."""
    if not device.startswith("cuda"):
        return 1  # CPU throughput is not improved by padding unlike GPU.
    free, _total = torch.cuda.mem_get_info()
    reclaimable = max(0, torch.cuda.memory_reserved() - torch.cuda.memory_allocated())
    # Reserve 1.5 GiB for codec work and other desktop/GPU consumers, plus a
    # conservative 0.5 GiB for each concurrent short sentence.
    budget = free + reclaimable - int(1.5 * 1024**3)
    return max(1, min(maximum, int(budget // (512 * 1024**2))))


def _adaptive_batch_profile(runtime, device, language, item, steps=32):
    length = len(str(item.get("text") or ""))
    bucket = 40 if length <= 40 else 80 if length <= 80 else 160 if length <= 160 else 320
    key = (device, language, bucket, steps)
    profiles = runtime.setdefault("batch_profiles", {})
    profile = profiles.setdefault(key, {"single": [], "paired": [], "trials": 0})
    while len(profiles) > 12:
        profiles.pop(next(iter(profiles)))
    return profile


def _adaptive_batch_size(profile, memory_limit):
    if memory_limit < 2:
        return 1
    if len(profile["single"]) < 2 or len(profile["paired"]) < 2:
        # Trial uses real pending sentences, not extra generated benchmarks.
        size = 1 if profile["trials"] % 2 == 0 else 2
        profile["trials"] += 1
        return size
    # Padding can make a larger batch slower even when VRAM easily permits it.
    # Require a 5% measured gain; otherwise prefer the smaller memory footprint.
    return 2 if statistics.median(profile["paired"]) < statistics.median(profile["single"]) * 0.95 else 1


def _record_batch_performance(profile, size, seconds, audio_seconds):
    if size not in {1, 2} or audio_seconds <= 0:
        return
    values = profile["single" if size == 1 else "paired"]
    values.append(seconds / audio_seconds)
    del values[:-6]


class _InvalidSynthesisAudio(RuntimeError):
    """A decoded batch failed validation before any audio was published."""


def _validated_waveforms(generated, count, np, torch):
    outputs = generated if isinstance(generated, (list, tuple)) else [generated]
    if len(outputs) != count:
        raise _InvalidSynthesisAudio("OmniVoice returned an unexpected number of audio clips.")
    waves = []
    for output in outputs:
        if isinstance(output, torch.Tensor):
            output = output.detach().float().cpu().numpy()
        wave = np.asarray(output, dtype=np.float32).reshape(-1)
        if wave.size < 240 or not np.isfinite(wave).all():
            raise _InvalidSynthesisAudio("OmniVoice returned empty or invalid audio.")
        waves.append(wave)
    return waves


def _generate_bounded_batch(generate, items, torch, device):
    """Reduce invalid paired audio or CUDA OOM to individual synthesis.

    Never retry arbitrary SDK errors, a corrupt single output, or CPU OOM.
    Completed sentences remain untouched and quality settings stay unchanged.
    """
    candidate = list(items)
    retries = 0
    while True:
        allocation_failed = False
        try:
            return generate(candidate), candidate, retries
        except RuntimeError as exc:
            allocation_error = isinstance(exc, torch.OutOfMemoryError) or any(
                marker in str(exc).lower() for marker in (
                    "out of memory", "cublas_status_alloc_failed", "cudnn_status_alloc_failed", "not enough memory",
                )
            )
            invalid_batch = isinstance(exc, _InvalidSynthesisAudio)
            if (len(candidate) == 1 or not (invalid_batch or (device.startswith("cuda") and allocation_error))):
                raise
            allocation_failed = True
        # Leave the exception frame before GC: its traceback may own tensors.
        if allocation_failed:
            gc.collect()
            if device.startswith("cuda"):
                torch.cuda.empty_cache()
            candidate = candidate[:1 if invalid_batch else max(1, len(candidate) // 2)]
            retries += 1


def warm_runtime(language_id: str = "vi", *, device: str | None = None) -> None:
    global _PERSISTENT_MODEL_KEY
    """Load OmniVoice in its isolated worker without synthesizing user audio."""
    _prepare_isolated_runtime()
    model_root = verify_omnivoice_model(Path(MODELS_DIR) / "omnivoice")
    runtime_tmp = Path(TMP_DIR)
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="omnivoice-warm-", dir=runtime_tmp) as temp_name:
        temp_root = Path(temp_name)
        response_path = temp_root / "response.json"
        request_path = temp_root / "request.json"
        request = {
            "model_root": str(model_root),
            "site_packages": str(_sdk_root() / "site-packages"),
            "device": "cuda:0" if (device or processing_device_preference()) == "gpu" else "cpu",
            "language": _omnivoice_language_id(language_id),
            "items": [],
            "speaker_mode": "single",
            "inference_steps": 8,
            "status_path": str(temp_root / "status.json"),
            "response_path": str(response_path),
            "voice_seed": 0,
        }
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        with _PERSISTENT_OPERATION_LOCK:
            with _PERSISTENT_WORKER_LOCK:
                _preflight_cpu_request(request, allow_resident=True)
                process = _persistent_worker_unlocked(str(request["device"]))
                if process.stdin is None:
                    raise RuntimeError("OmniVoice worker input channel is unavailable.")
                process.stdin.write(f"{request_path}\n")
                process.stdin.flush()
            deadline = time.monotonic() + 600.0
            while time.monotonic() < deadline:
                if response_path.is_file():
                    response = json.loads(response_path.read_text(encoding="utf-8"))
                    if int(response.get("return_code", 1)) != 0:
                        raise RuntimeError(str(response.get("error") or "OmniVoice warm-up failed."))
                    with _PERSISTENT_WORKER_LOCK:
                        if _PERSISTENT_WORKER_PROCESS is process:
                            _PERSISTENT_MODEL_KEY = _request_model_key(request)
                            _schedule_idle_shutdown()
                    return
                if process.poll() is not None:
                    detail = _persistent_worker_error_tail(process)
                    with _PERSISTENT_WORKER_LOCK:
                        if _PERSISTENT_WORKER_PROCESS is process:
                            _stop_persistent_worker_unlocked()
                    message = "OmniVoice warm-up worker stopped unexpectedly."
                    if detail:
                        message = f"{message}\n{detail}"
                    raise RuntimeError(message)
                time.sleep(0.1)
            with _PERSISTENT_WORKER_LOCK:
                if _PERSISTENT_WORKER_PROCESS is process:
                    _stop_persistent_worker_unlocked()
            raise RuntimeError("OmniVoice warm-up timed out.")


def _worker_main(request_path: str, runtime: dict[str, Any] | None = None) -> int:
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    runtime = {} if runtime is None else runtime
    if request.get("operation") == "release_model":
        _release_worker_model(runtime)
        return 0
    site_packages = str(request["site_packages"])
    modules = runtime.get("modules")
    items = request.get("items") or []
    status_path = Path(str(request.get("status_path") or ""))
    timings = {"runtime_imports": 0.0, "model_load": 0.0,
               "reference_encoding": 0.0, "synthesis": 0.0}

    batch_size = 1
    batch_retries = 0
    inference_forwards = 0

    def write_status(completed: int, stage: str, *, current: int = 0) -> None:
        _write_status_file(
            status_path,
            {
                "completed": completed,
                "total": len(items),
                "stage": stage,
                "current": current,
                "batch_size": batch_size,
                "batch_retries": batch_retries,
                "inference_forwards": inference_forwards,
                "timing_seconds": {key: round(value, 3) for key, value in timings.items()},
            },
        )

    # Publish before importing Torch/Transformers: this cold-start interval
    # used to look like a stalled model load despite no checkpoint being read.
    write_status(0, "importing_runtime" if modules is None else "reusing_runtime")
    if modules is None:
        imports_started = time.monotonic()
        sys.path.insert(0, site_packages)

        # Imports intentionally happen only after the isolated Transformers 5
        # path is first. The desktop keeps its pinned Transformers 4 runtime.
        import numpy as np  # noqa: PLC0415
        import soundfile as sf  # noqa: PLC0415
        import torch  # noqa: PLC0415
        from omnivoice import OmniVoice  # noqa: PLC0415

        modules = (np, sf, torch, OmniVoice)
        runtime["modules"] = modules
        timings["runtime_imports"] = time.monotonic() - imports_started
    np, sf, torch, OmniVoice = modules

    # On Windows the default CPU parallel pools can fault inside torch_cpu.dll
    # while mapping OmniVoice's multi-gigabyte checkpoints, even for CUDA
    # inference. Configure them before from_pretrained initializes workers.
    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass

    device = str(request.get("device") or "cpu")
    cpu_threads = max(1, min(8, int(request.get("cpu_threads") or _cpu_voice_threads()))) if device == "cpu" else 1
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("OmniVoice GPU mode was selected, but CUDA is unavailable.")
    if device.startswith("cuda"):
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    model_key = (str(request["model_root"]), device)
    model = runtime.get("model") if runtime.get("model_key") == model_key else None
    write_status(0, "reusing_model" if model is not None else "loading_model")
    if model is None:
        loading_started = time.monotonic()
        from haizflow.core.dependency_security import (
            install_transformers_generation_guard, validate_checkpoint_weight_maps,
        )

        install_transformers_generation_guard()
        previous_model = runtime.pop("model", None)
        runtime.pop("model_key", None)
        if previous_model is not None:
            runtime["model"] = previous_model
            del previous_model
            _release_worker_model(runtime)
        model_root = str(request["model_root"])
        validate_checkpoint_weight_maps(model_root)
        model = OmniVoice.from_pretrained(
            model_root,
            device_map=device,
            dtype=dtype,
            low_cpu_mem_usage=True,
        )
        runtime["model"] = model
        runtime["model_key"] = model_key
        timings["model_load"] = time.monotonic() - loading_started
    if not device.startswith("cuda"):
        # Map weights with one thread (Windows native loader safety), then
        # enable parallel inference while leaving a core for the desktop.
        torch.set_num_threads(cpu_threads)
    voice_seed = int(request.get("voice_seed") or 0) & 0x7FFFFFFF
    speaker_mode = str(request.get("speaker_mode") or "single")
    synthesis_items = list(items)
    anchor_prompt: Any = None
    # Two authorised references at most. Persist across retries/edits, but do
    # not accumulate an unbounded number of GPU-resident clone prompts.
    prompt_cache = runtime.setdefault("clone_prompt_cache", {})

    def reset_seed(seed=voice_seed) -> None:
        torch.manual_seed(seed)
        np.random.seed(seed % (2**32 - 1))
        if device.startswith("cuda"):
            torch.cuda.manual_seed_all(seed)

    # A fixed, language-specific reference keeps the same preset identity when
    # a later edit regenerates only one segment. The persistent worker retains
    # the prompt; multiple-speaker mode deliberately keeps per-segment voices.
    if speaker_mode != "multiple" and synthesis_items and any(not item.get("reference_path") for item in synthesis_items):
        anchor_text = str(request.get("narrator_anchor_text") or "").strip()
        anchor_voice = str(synthesis_items[0].get("voice") or "omnivoice:female").strip().lower()
        anchor_instruction = OMNIVOICE_VOICE_INSTRUCTIONS.get(
            anchor_voice,
            OMNIVOICE_VOICE_INSTRUCTIONS["omnivoice:female"],
        )
        narrator_prompt_cache = runtime.setdefault("narrator_prompt_cache", {})
        anchor_key = (
            model_key,
            str(request.get("language") or ""),
            anchor_voice,
            voice_seed,
            anchor_text,
        )
        anchor_prompt = narrator_prompt_cache.get(anchor_key)
        preset_reference = str(request.get("preset_reference_path") or "")
        preset_transcript = str(request.get("preset_reference_text") or "")
        if anchor_prompt is None and preset_reference and preset_transcript:
            write_status(0, "loading_voice_reference")
            reference_started = time.monotonic()
            anchor_prompt = _encode_voice_reference(model, torch, preset_reference, preset_transcript)
            narrator_prompt_cache[anchor_key] = anchor_prompt
            while len(narrator_prompt_cache) > 4:
                narrator_prompt_cache.pop(next(iter(narrator_prompt_cache)))
            timings["reference_encoding"] += time.monotonic() - reference_started
        elif anchor_prompt is None and anchor_text:
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
                        num_step=int(request.get("inference_steps") or 32),
                        normalize_text=False,
                        audio_chunk_duration=10.0,
                        audio_chunk_threshold=8.0,
                    )
                anchor_waveform = (
                    generated_anchor[0] if isinstance(generated_anchor, (list, tuple)) else generated_anchor
                )
                if isinstance(anchor_waveform, torch.Tensor):
                    anchor_waveform = anchor_waveform.detach().float().cpu().numpy()
                anchor_waveform = np.asarray(anchor_waveform, dtype=np.float32).reshape(-1)
                if anchor_waveform.size < 240 or not np.isfinite(anchor_waveform).all():
                    raise RuntimeError("OmniVoice returned an invalid narrator anchor.")
                anchor_path = status_path.parent / "narrator-anchor.wav"
                sample_rate = int(getattr(model, "sampling_rate", None) or _SAMPLE_RATE)
                sf.write(str(anchor_path), anchor_waveform, sample_rate, subtype="PCM_16")
                anchor_prompt = _encode_voice_reference(model, torch, str(anchor_path), anchor_text)
                narrator_prompt_cache[anchor_key] = anchor_prompt
                while len(narrator_prompt_cache) > 4:
                    narrator_prompt_cache.pop(next(iter(narrator_prompt_cache)))
            finally:
                del generated_anchor, anchor_waveform
        elif anchor_prompt is not None:
            write_status(0, "reusing_voice_anchor")

    write_status(0, "synthesizing")
    offset = 0
    maximum_batch = 2
    while offset < len(synthesis_items):
        item = synthesis_items[offset]
        completed = offset + 1
        profile = _adaptive_batch_profile(runtime, device, str(request.get("language") or ""), item,
                                          int(request.get("inference_steps") or 32))
        ceiling = _adaptive_batch_size(profile, _gpu_batch_ceiling(torch, device, maximum_batch))
        batch = _next_synthesis_batch(synthesis_items, offset, ceiling)
        batch_size = len(batch)
        write_status(offset, "synthesizing", current=completed)
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
            if not reference_text:
                raise RuntimeError("Mẫu giọng cần có bản chép lời trước khi nạp OmniVoice.")
            stat = Path(reference_path).stat()
            prompt_key = (model_key, reference_path, stat.st_size, stat.st_mtime_ns, reference_text)
            # Multiple-speaker mode creates a different reference for nearly
            # every subtitle. Retaining all of those GPU prompts caused DAC
            # convolution failures after several segments on 8 GB cards.
            cache_prompt = speaker_mode != "multiple"
            voice_clone_prompt = prompt_cache.get(prompt_key) if cache_prompt else None
            if voice_clone_prompt is None:
                reference_started = time.monotonic()
                voice_clone_prompt = _encode_voice_reference(model, torch, reference_path, reference_text)
                if cache_prompt:
                    prompt_cache[prompt_key] = voice_clone_prompt
                    while len(prompt_cache) > 2:
                        prompt_cache.pop(next(iter(prompt_cache)))
                timings["reference_encoding"] += time.monotonic() - reference_started
        elif speaker_mode == "multiple" and item.get("preset_reference_path") and item.get("preset_reference_text"):
            preset_key = (model_key, str(request.get("language") or ""), str(item.get("voice") or ""))
            preset_cache = runtime.setdefault("preset_prompt_cache", {})
            voice_clone_prompt = preset_cache.get(preset_key)
            if voice_clone_prompt is None:
                reference_started = time.monotonic()
                voice_clone_prompt = _encode_voice_reference(
                    model, torch, str(item["preset_reference_path"]), str(item["preset_reference_text"]))
                preset_cache[preset_key] = voice_clone_prompt
                while len(preset_cache) > 4:
                    preset_cache.pop(next(iter(preset_cache)))
                timings["reference_encoding"] += time.monotonic() - reference_started
        elif anchor_prompt is not None and speaker_mode != "multiple":
            voice_clone_prompt = anchor_prompt
        generated: Any = None
        waveform: Any = None
        outputs: Any = None
        waveforms: Any = None
        output: Any = None
        try:
            # OmniVoice is generative. Resetting the same voice-specific seed
            # before each utterance prevents random speaker-identity drift
            # while text and prosody remain segment-specific.
            item_seed = int(hashlib.sha256(str(item.get("voice") or "").encode()).hexdigest()[:8], 16) & 0x7FFFFFFF
            reset_seed(item_seed if speaker_mode == "multiple" else voice_seed)
            synthesis_started = time.monotonic()

            def generate(candidate):
                last_observation = 0.0

                def observe_forward():
                    nonlocal inference_forwards, last_observation
                    inference_forwards += 1
                    now = time.monotonic()
                    if now - last_observation >= 2:
                        last_observation = now
                        write_status(offset, "synthesizing", current=completed)

                reset_seed(item_seed if speaker_mode == "multiple" else voice_seed)
                with torch.inference_mode(), (
                    _inference_activity(model, observe_forward) if device == "cpu" else nullcontext()
                ):
                    result = model.generate(
                        text=[str(entry["text"]).strip() for entry in candidate] if len(candidate) > 1 else text,
                        language=str(request.get("language") or "") or None,
                        instruct=None if voice_clone_prompt is not None else instruction,
                        voice_clone_prompt=voice_clone_prompt,
                        num_step=int(request.get("inference_steps") or 32),
                        normalize_text=False,
                        audio_chunk_duration=10.0,
                        audio_chunk_threshold=8.0,
                    )
                # Validate inside the bounded batch operation, not afterwards:
                # otherwise one invalid pair aborts the complete video.
                return _validated_waveforms(result, len(candidate), np, torch)

            generated, batch, retries = _generate_bounded_batch(generate, batch, torch, device)
            batch_retries += retries
            if retries:
                maximum_batch = len(batch)
            batch_size = len(batch)
            waveforms = generated
            sample_rate = int(getattr(model, "sampling_rate", None) or _SAMPLE_RATE)
            synthesis_seconds = time.monotonic() - synthesis_started
            if not retries:
                _record_batch_performance(profile, len(batch), synthesis_seconds,
                                          sum(wave.size for wave in waveforms) / sample_rate)
            # Validate the whole batch before publishing any completion.
            for entry, waveform in zip(batch, waveforms):
                sf.write(str(entry["wav_path"]), waveform, sample_rate, subtype="PCM_16")
            offset += len(batch)
            timings["synthesis"] += synthesis_seconds
            write_status(offset, "synthesizing")
        finally:
            # A video can contain hundreds of calls to generate().  Keep the
            # model resident, but release per-utterance tensors immediately so
            # an 8 GB GPU does not accumulate allocator pressure until OOM.
            del generated, waveform, voice_clone_prompt, outputs, waveforms, output
            if device.startswith("cuda") and speaker_mode == "multiple" and reference_path:
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


def _worker_server_main() -> int:
    """Serve request files over stdin while retaining the loaded SDK model."""
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    runtime: dict[str, Any] = {}
    for raw_line in sys.stdin:
        request_path = raw_line.strip()
        if not request_path:
            continue
        if request_path == "__quit__":
            return 0
        response_path = Path(request_path).with_name("response.json")
        try:
            request = json.loads(Path(request_path).read_text(encoding="utf-8"))
            configured_response = str(request.get("response_path") or "").strip()
            if configured_response:
                response_path = Path(configured_response)
            return_code = _worker_main(request_path, runtime)
            payload = {"return_code": return_code, "error": ""}
            if request.get("operation") == "release_model":
                modules = runtime.get("modules")
                torch = modules[2] if modules else None
                payload["model_released"] = "model" not in runtime
                payload["resident_cuda_bytes"] = (
                    torch.cuda.memory_allocated() if torch is not None and torch.cuda.is_available() else 0
                )
        except BaseException as exc:  # The server must report model/runtime failures to its parent.
            payload = {
                "return_code": 1,
                "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            }
        _write_status_file(response_path, payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) == 2 and arguments[0] in {"--worker", "--omnivoice-worker"}:
        return _worker_main(arguments[1])
    if len(arguments) == 1 and arguments[0] in {"--server", "--omnivoice-server"}:
        return _worker_server_main()
    raise SystemExit("OmniVoice worker requires a request file.")


if __name__ == "__main__":
    raise SystemExit(main())
