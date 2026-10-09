import os
import re
import hashlib
import json
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from haizflow.config import HYMT2_MODEL_REVISION
from haizflow.core.hardware import (
    configure_processing_device,
    configure_translation_model,
    detect_hardware_capabilities,
    processing_device_preference,
    runtime_profile,
    translation_model_preference,
    translation_model_signature_parts,
)
from haizflow.core.runtime_probe import probe_runtime
from haizflow.pipeline.audio_timeline import build_audio_timeline
from haizflow.pipeline.extract_audio import extract_audio
from haizflow.pipeline.process_registry import check_cancellation, clean_video, is_cancelled, is_paused, start_video
from haizflow.pipeline.render import render_video
from haizflow.pipeline.subtitle import generate_srt
from haizflow.pipeline.timing_contract import AUDIO_TIMELINE_VERSION, TIMING_SOURCE
from haizflow.pipeline.tts import generate_voice_parts, resolve_tts_provider
from haizflow.schemas.video import SubtitleStyle
from haizflow.services.video_store import get_video, log_to_video, update_video
from haizflow.services.translation import (
    is_hymt2_worker_warm,
    shutdown_hymt2_worker,
    translate_segments,
    warm_hymt2_worker,
)
from haizflow.utils.ffmpeg import validate_video_integrity




def separate_audio(*args, **kwargs):
    from haizflow.pipeline.audio_separation import separate_audio as implementation

    return implementation(*args, **kwargs)


def detect_original_subtitle_region(*args, **kwargs):
    from haizflow.pipeline.manual_tools import detect_original_subtitle_region as implementation

    return implementation(*args, **kwargs)


def transcribe(*args, **kwargs):
    from haizflow.pipeline.manual_tools import transcribe as implementation

    return implementation(*args, **kwargs)


def _release_recognition_runtime() -> None:
    """Release the active ASR model without importing AI packages in Core."""

    from haizflow.services.external_engine import shared_external_engine_pool

    shared_external_engine_pool().release({"recognition", "separation", "ocr"})
    # An isolated ASR process is already gone. Do not import WhisperX/Torch
    # into Core just to release a model that never lived in this process.
    recognition = sys.modules.get("haizflow.pipeline.transcribe")
    if recognition is not None:
        recognition.release_warm_whisperx_model()


def _signature(*values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _file_state(path):
    if not os.path.exists(path):
        return None
    stat = os.stat(path)
    return (os.path.abspath(path), stat.st_size, stat.st_mtime_ns)


def _required_video_path(video, key: str, *, must_exist: bool = False) -> str:
    """Return a non-empty path from persisted video metadata.

    Legacy or interrupted migrations can leave nullable entries in ``files``.
    Failing here gives the user a useful pipeline error instead of an obscure
    ``TypeError`` from ``os.path`` or FFmpeg.
    """
    path = (video.files or {}).get(key)
    if not isinstance(path, str) or not path.strip():
        raise RuntimeError(f"Video metadata is missing the required '{key}' path.")
    path = os.path.abspath(path)
    if must_exist and (not os.path.isfile(path) or os.path.getsize(path) <= 0):
        raise FileNotFoundError(f"Required video artifact is missing or empty: {path}")
    return path


def _timing_file_is_current(path):
    try:
        with open(path, "r", encoding="utf-8") as timing_file:
            segments = json.load(timing_file)
        return bool(segments) and all(
            isinstance(segment, dict) and segment.get("timing_source") == TIMING_SOURCE for segment in segments
        )
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def _source_subtitle_intervals(path: str) -> list[tuple[float, float]]:
    """Load source caption visibility windows for temporal OCR treatment."""
    try:
        with open(path, "r", encoding="utf-8") as source_file:
            segments = json.load(source_file)
    except (OSError, TypeError, json.JSONDecodeError):
        return []
    intervals: list[tuple[float, float]] = []
    for segment in segments if isinstance(segments, list) else []:
        if not isinstance(segment, dict):
            continue
        try:
            start = max(0.0, float(segment.get("start", 0) or 0))
            end = max(start, float(segment.get("end", start) or start))
        except (TypeError, ValueError):
            continue
        if end > start + 0.01:
            intervals.append((round(start, 3), round(end, 3)))
    return intervals


def _checkpoint_valid(video, name, signature, outputs):
    # Auto projects reuse checkpoints only for pause/resume. Manual projects
    # deliberately execute downstream modules in separate runs, so their
    # completed artifacts must remain reusable without pretending to resume.
    manual_reuse = (
        getattr(video, "project_type", "single") == "manual"
        and name in set(getattr(video, "manual_completed_stages", []) or [])
    )
    return (
        (bool(video.resume_step) or manual_reuse)
        and video.checkpoints.get(name) == signature
        and all(os.path.exists(path) and os.path.getsize(path) > 0 for path in outputs)
    )


def _recognize_for_translation(video, reporter, audio_path, output_path):
    signature = _signature(
        _file_state(video.files["video_input"]), video.source_language,
        getattr(video, "speech_recognition_model", "small"), video.enable_audio_separation,
        TIMING_SOURCE, "recognition-progress-v1",
    )
    if (_checkpoint_valid(video, "recognition", signature, [output_path])
            or _recovery_checkpoint_valid(video, "recognition", signature, [output_path])):
        try:
            with open(output_path, encoding="utf-8") as source:
                segments = json.load(source)
        except (OSError, ValueError):
            segments = []
        if isinstance(segments, list) and segments and all(isinstance(row, dict) and row.get("text") for row in segments):
            reporter.update(48, "transcribing", "Reusing completed speech recognition")
            return segments, str(video.checkpoints.get("recognition_language") or segments[0].get("language") or "en")
    reporter.update(24, "transcribing", "Preparing Whisper speech recognition")
    result = transcribe(
        audio_path, output_path, video.source_language, video.video_id,
        progress_callback=lambda event, detail: reporter.update(
            {"loading_model": 25, "transcribing": 29, "transcribed": 39,
             "loading_alignment": 40, "aligning": 41, "segmenting": 42,
             "detecting_languages": 46, "saved": 48}.get(event, 24), "transcribing", detail,
        ),
        model_name=_execution_models(video)["speech_recognition_model"],
    )
    video.checkpoints["recognition_language"] = str(result[1] or "en")
    _mark_checkpoint(video, "recognition", signature)
    return result


def _execution_models(video) -> dict[str, str]:
    """Resolve only this recovery invocation; persisted choices/cache keys stay intact."""
    from haizflow.core.model_choices import models_for_device

    choices = {
        "speech_recognition_model": str(getattr(video, "speech_recognition_model", "small") or "small"),
        "translation_model": str(getattr(video, "translation_model", "auto") or "auto"),
        "tts_provider": str(getattr(video, "tts_provider", "omnivoice") or "omnivoice"),
    }
    if getattr(video, "runtime_recovery_step", "") and processing_device_preference() == "cpu":
        return models_for_device("cpu", recognition=choices["speech_recognition_model"],
                                 translation=choices["translation_model"], voice=choices["tts_provider"])
    return choices


def _recovery_checkpoint_valid(video, name, signature, outputs):
    """Reuse durable artifacts only while recovering from a lost GPU.

    This is deliberately independent from pause/resume: Restart must still
    discard every generated artifact and run from the input video.
    """
    return (
        bool(getattr(video, "runtime_recovery_step", ""))
        and video.checkpoints.get(name) == signature
        and all(os.path.exists(path) and os.path.getsize(path) > 0 for path in outputs)
    )


class GpuRuntimeUnavailable(RuntimeError):
    """Raised at a safe pipeline boundary when the active GPU disappears."""


_GPU_FAILURE_MARKERS = (
    "cuda",
    "cudnn",
    "cublas",
    "nvidia",
    "gpu",
    "device-side",
    "driver",
)

_NON_RECOVERABLE_RUNTIME_MARKERS = (
    "0xc0000005",
    "3221225477",
    "native torch crash",
    "native windows crash",
    "paging file is too small",
    "os error 1455",
)


def _ensure_gpu_available(stage: str) -> None:
    """Do not start a new GPU stage after power/device availability changed."""
    profile = runtime_profile()
    if not profile.cuda_available:
        return
    capabilities = detect_hardware_capabilities()
    if not capabilities.cuda_available or capabilities.ac_powered is False:
        reason = (
            "the NVIDIA GPU is no longer detected" if not capabilities.cuda_available else "AC power was disconnected"
        )
        raise GpuRuntimeUnavailable(f"GPU became unavailable before {stage}: {reason}.")


def _is_gpu_runtime_failure(error: Exception) -> bool:
    if isinstance(error, GpuRuntimeUnavailable):
        return True
    # A GPU-named path/DLL in an OS error is not evidence of GPU failure.
    # In particular, retrying on CPU cannot fix locks or exhausted commit.
    if isinstance(error, (OSError, MemoryError)):
        return False
    if not runtime_profile().cuda_available:
        return False
    message = str(error).lower()
    windows_code = re.search(r"(?:winerror|os error)\s*(\d+)\b", message)
    if windows_code and int(windows_code.group(1)) in {2, 3, 5, 8, 14, 32, 33, 112, 145, 206, 1450, 1455}:
        return False
    # Memory-commit failures and native access violations need investigation.
    # Treating them as a lost GPU would hide the original defect behind a CPU
    # retry and make the failing runtime impossible to diagnose.
    if any(marker in message for marker in _NON_RECOVERABLE_RUNTIME_MARKERS):
        return False
    return any(marker in message for marker in _GPU_FAILURE_MARKERS)


def _recover_gpu_to_cpu(video_id: str, stage: str, error: Exception) -> bool:
    """Move one interrupted video to CPU at a durable stage boundary.

    The interrupted stage is restarted, while completed checkpoints remain
    available only to this recovery run. A second automatic retry is refused
    so an unstable driver cannot leave a project in an endless loop.
    """
    video = get_video(video_id)
    if not video or video.gpu_recovery_attempted or not _is_gpu_runtime_failure(error):
        return False

    detail = f"GPU unavailable during {stage}. Switching this project to CPU and retrying that stage."
    update_video(
        video_id,
        status="processing",
        step="recovering_device",
        step_detail=detail,
        runtime_recovery_step=stage,
        gpu_recovery_attempted=True,
        error=None,
    )
    log_to_video(video_id, detail)
    log_to_video(video_id, f"GPU recovery reason: {error}")
    try:
        cpu_probe = probe_runtime("cpu")
        if not cpu_probe.ok:
            log_to_video(video_id, f"CPU fallback runtime is unavailable: {cpu_probe.message}")
            return False
        shutdown_hymt2_worker()
        _release_recognition_runtime()
        configure_processing_device("cpu")
        log_to_video(video_id, "Released GPU models. CPU runtime is ready to resume from the last completed stage.")
        return True
    except Exception as recovery_error:
        log_to_video(video_id, f"Could not prepare CPU fallback: {recovery_error}")
        return False


def _mark_checkpoint(video, name, signature):
    video.checkpoints[name] = signature
    update_video(video.video_id, checkpoints=video.checkpoints)


def _resolve_audio_mix(video, fallback_audio_path: str) -> tuple[str, int]:
    """Return the source/Demucs track and its user-selected mix volume."""
    if not video.enable_audio_separation:
        return fallback_audio_path, video.original_video_volume
    separated_background = video.files.get("background_audio") or ""
    if separated_background and os.path.exists(separated_background) and os.path.getsize(separated_background) > 44:
        return separated_background, video.original_video_volume
    return "", video.original_video_volume


def _manual_subtitle_layout_for_render(video) -> bool:
    """Cover removal and caption placement are independent user choices."""
    return bool(getattr(video, "subtitle_layout_override", False))


def _prepare_audio_mix(video, reporter, video_dir: str, fallback_audio_path: str) -> tuple[str, int]:
    # Upgrade the old ASR-only mono master before reusing translated/voice checkpoints.
    import wave

    # A separated stem is normally 44.1 kHz; it is not the original master.
    # Inspect the source WAV only, otherwise every export re-runs Demucs and
    # can even overwrite a no-vocals stem with the original voice track.
    source_master = os.path.join(video_dir, "temp", "audio.wav") if video.enable_audio_separation else fallback_audio_path
    try:
        with wave.open(source_master, "rb") as master:
            legacy_master = master.getnchannels() != 2 or master.getframerate() != 48000
    except (OSError, wave.Error, EOFError):
        legacy_master = False
    if legacy_master:
        extract_audio(_required_video_path(video, "video_input", must_exist=True), source_master, video.video_id)
        fallback_audio_path = source_master
        if video.enable_audio_separation:
            video.files.pop("background_audio", None)
            video.files.pop("speech_audio", None)
    background_audio_path, background_volume = _resolve_audio_mix(video, fallback_audio_path)
    if background_audio_path:
        return background_audio_path, background_volume

    check_cancellation(video.video_id)
    _ensure_gpu_available("audio separation")
    if not os.path.exists(fallback_audio_path):
        reporter.update(12, "extracting_audio", "Restoring source audio")
        extract_audio(
            _required_video_path(video, "video_input", must_exist=True),
            fallback_audio_path,
            video.video_id,
        )
    reporter.update(14, "separating_audio", "Restoring separated background audio")
    separation_dir = os.path.join(video_dir, "temp", "separation")
    vocals_path, background_audio_path = separate_audio(
        fallback_audio_path,
        separation_dir,
        video.video_id,
    )
    files = dict(video.files)
    files["speech_audio"] = vocals_path
    files["background_audio"] = background_audio_path
    video.files = files
    update_video(video.video_id, files=files)
    log_to_video(video.video_id, "Separated background audio restored for the final mix.")
    return background_audio_path, video.original_video_volume


class ProgressReporter:
    """Persist real stage details and item progress for the desktop UI."""

    def __init__(self, video_id: str):
        self.video_id = video_id
        self.started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.started_monotonic = time.monotonic()
        existing = get_video(video_id)
        self.previous_elapsed = max(0.0, float(getattr(existing, "processing_elapsed_seconds", 0.0) or 0.0))

    def update(self, progress: int, step: str, detail: str, current: int = 0, total: int = 0):
        progress = max(0, min(99, int(progress)))
        session_elapsed = time.monotonic() - self.started_monotonic
        elapsed = self.previous_elapsed + session_elapsed
        eta = None
        if progress >= 5:
            eta = max(0, round(elapsed * (100 - progress) / progress))
        update_video(
            self.video_id,
            status="processing",
            progress=progress,
            step=step,
            step_detail=detail,
            current_item=max(0, current),
            total_items=max(0, total),
            started_at=self.started_at,
            estimated_remaining_seconds=eta,
        )


def _finish_recovered_translation(
    video,
    reporter,
    video_dir,
    temp_audio_wav,
    source_segments_json,
    transcript_json,
    translation_signature,
    *,
    stop_after=None,
):
    """Continue from a durable translation or post-translation artifact."""
    recovery_step = getattr(video, "runtime_recovery_step", "")
    late_stages = {"creating_subtitle", "creating_voice", "building_audio_timeline", "rendering"}
    if recovery_step in late_stages and _recovery_checkpoint_valid(
        video,
        "translation",
        translation_signature,
        [transcript_json],
    ):
        log_to_video(video.video_id, f"CPU recovery: keeping translated subtitles and retrying from {recovery_step}.")
        _finish_after_translation(video, reporter, video_dir, temp_audio_wav, stop_after=stop_after)
        return True
    if recovery_step != "translating" or not os.path.exists(source_segments_json):
        return False
    if not _timing_file_is_current(source_segments_json):
        log_to_video(video.video_id, "CPU recovery discarded legacy source timestamps and will transcribe again.")
        return False

    log_to_video(video.video_id, "CPU recovery: keeping the transcript and retrying HY-MT2 translation.")
    reporter.update(50, "translating", "Retrying translation on CPU")

    def report_translation_progress(current, total, detail):
        progress = 50 + round(12 * current / total) if total else 50
        reporter.update(progress, "translating", detail, current, total)

    translate_segments(
        source_segments_json,
        transcript_json,
        video.video_id,
        video.target_language,
        source_language="en",
        provider="gemini" if str(getattr(video, "translation_model", "")).startswith("gemini-") else "hymt2",
        translation_model=_execution_models(video)["translation_model"],
        progress_callback=report_translation_progress,
    )
    _mark_checkpoint(video, "translation", translation_signature)
    if stop_after == "translation":
        _finish_after_translation(video, reporter, video_dir, temp_audio_wav, stop_after="subtitles")
        return True
    if video.mode == "review" and not video.review_approved:
        _original_subtitle_region_for_render(video, reporter, video_dir, pipeline_progress=61)
        update_video(
            video.video_id,
            status="awaiting_review",
            progress=62,
            step="review_translation",
            resume_step="creating_subtitle",
            step_detail="Translation ready for review",
            runtime_recovery_step="",
        )
        return True
    _finish_after_translation(video, reporter, video_dir, temp_audio_wav, stop_after=stop_after)
    return True


MANUAL_PIPELINE_STAGES = ("translation", "subtitles", "voice", "timeline", "render")


def _translation_signature(video, video_input: str) -> str:
    using_gemini = str(getattr(video, "translation_model", "")).startswith("gemini-")
    return _signature(
        _file_state(video_input), TIMING_SOURCE,
        "gemini-batched-segments-v1" if using_gemini else "hymt2-semantic-source-context-retry-v21",
        video.target_language, video.enable_audio_separation,
        getattr(video, "speech_recognition_model", "small"),
        "gemini" if using_gemini else "hymt2",
        "gemini-segment-json-v1" if using_gemini else HYMT2_MODEL_REVISION,
        *translation_model_signature_parts(getattr(video, "translation_model", "auto")),
    )


def foreground_capability(video, manual_tool: str = "") -> str:
    """Resolve the first actual stage on the worker, not in a QML getter."""
    if manual_tool:
        return {"voice": "voice", "translation": "recognition", "separation": "separation",
                "source": "separation", "image": "ocr"}.get(manual_tool, "")
    files = getattr(video, "files", {}) or {}
    source, transcript = files.get("video_input"), files.get("transcript_json")
    if source and transcript and _checkpoint_valid(video, "translation", _translation_signature(video, source), [transcript]):
        return "voice"
    return "separation" if getattr(video, "enable_audio_separation", False) else "recognition"


def _complete_manual_stage(video_id: str, stage: str, progress: int) -> None:
    """Leave a manual project idle with an independently reusable result."""
    video = get_video(video_id)
    completed = set(getattr(video, "manual_completed_stages", []) or []) if video else set()
    completed.add(stage)
    if stage == "subtitles":
        completed.add("translation")
    if stage == "render":
        completed.update(MANUAL_PIPELINE_STAGES)
    durable_stages = [item for item in MANUAL_PIPELINE_STAGES if item in completed]
    durable_progress = max(int(getattr(video, "progress", 0) or 0), progress) if video else progress
    final_ready = "render" in completed
    update_video(
        video_id,
        status="done" if final_ready else "manual_ready",
        progress=100 if final_ready else durable_progress,
        step="done" if final_ready else f"manual_{stage}",
        step_detail="Final video ready" if final_ready else f"Manual stage ready: {stage}",
        estimated_remaining_seconds=0 if final_ready else None,
        resume_step="",
        runtime_recovery_step="",
        manual_target_stage="",
        manual_completed_stage=stage,
        manual_completed_stages=durable_stages,
    )
    log_to_video(video_id, f"Manual stage completed: {stage}.")


def process_video_sync(
    video_id: str,
    _reporter: ProgressReporter | None = None,
    *,
    stop_after: str | None = None,
):
    """Run the checkpointed dubbing pipeline, optionally stopping at one manual stage."""
    if stop_after is not None and stop_after not in MANUAL_PIPELINE_STAGES:
        raise ValueError(f"Unsupported manual pipeline stage: {stop_after}")
    # Keep this bound even when start_video() itself fails; the GPU recovery
    # branch must never mask the original exception with UnboundLocalError.
    reporter = _reporter
    try:
        start_video(video_id)
        # A recovery re-enters this function with the existing reporter so
        # elapsed processing time remains the total time for the video.
        reporter = reporter or ProgressReporter(video_id)
        video = get_video(video_id)
        if not video:
            return
        if video.mode not in {"A", "review"}:
            raise ValueError(f"Unsupported workflow: {video.mode}")

        if video.translator_provider not in {"hymt2", "gemini"}:
            log_to_video(video_id, "Migrated legacy translation setting to HY-MT2.")
            video = update_video(video_id, translator_provider="hymt2") or video
        reporter.update(3, "starting", "Preparing video")
        using_gemini = str(getattr(video, "translation_model", "")).startswith("gemini-")
        engine_name = "Gemini" if using_gemini else "HY-MT2"
        if getattr(video, "runtime_recovery_step", "") and not using_gemini:
            configure_translation_model(_execution_models(video)["translation_model"])
        log_to_video(video_id, f"Processing started | Mode: Full Auto | Translator: {engine_name}")

        video_input = _required_video_path(video, "video_input", must_exist=True)
        reporter.update(4, "validating_source", "Checking source video integrity")
        validate_video_integrity(video_input)
        transcript_json = _required_video_path(video, "transcript_json")

        video_dir = os.path.dirname(os.path.dirname(video_input))
        temp_audio_wav = os.path.join(video_dir, "temp", "audio.wav")
        source_segments_json = os.path.join(video_dir, "temp", "source_segments.json")
        translation_signature = _translation_signature(video, video_input)

        # Clicking Dịch is an explicit recomputation request. Downstream
        # Manual modules reuse this checkpoint, but Dịch itself never does.
        if stop_after != "translation" and _checkpoint_valid(
            video, "translation", translation_signature, [transcript_json]
        ):
            log_to_video(
                video_id,
                "Checkpoint hit: reusing translated segments; skipping audio extraction, transcription and translation.",
            )
            if video.mode == "review" and not video.review_approved:
                _original_subtitle_region_for_render(video, reporter, video_dir, pipeline_progress=61)
                update_video(
                    video_id,
                    status="awaiting_review",
                    progress=62,
                    step="review_translation",
                    resume_step="creating_subtitle",
                    step_detail="Translation ready for review",
                )
                return
            _finish_after_translation(video, reporter, video_dir, temp_audio_wav, stop_after=stop_after)
            return

        if video.resume_step and os.path.exists(transcript_json):
            log_to_video(
                video_id,
                "Resume discarded translated segments because their checkpoint no longer matches the current input or translation settings.",
            )
        if video.mode == "review" and video.review_approved:
            # A reviewed transcript is still tied to its source/signature.  Do
            # not silently render it after target language or input changes.
            video.review_approved = False
            update_video(video_id, review_approved=False)
            log_to_video(video_id, "Translation settings changed; the previous review must be approved again.")

        if _finish_recovered_translation(
            video,
            reporter,
            video_dir,
            temp_audio_wav,
            source_segments_json,
            transcript_json,
            translation_signature,
            stop_after=stop_after,
        ):
            return

        # A previous editor session may intentionally keep OmniVoice warm.
        # A fresh transcription needs that VRAM first; reviewed/checkpointed
        # downstream passes returned above and can still reuse the warm worker.
        from haizflow.pipeline.omnivoice_tts import clear_runtime

        clear_runtime()
        profile = runtime_profile()
        if (
            using_gemini
            or not profile.cuda_available
            or getattr(profile, "key", "") == "cuda_low_memory"
            or getattr(profile, "total_ram_gib", 24) < 24
        ):
            shutdown_hymt2_worker()
            log_to_video(video_id, "Released HY-MT2 before speech recognition to preserve memory.")
        elif not using_gemini and profile.warm_hymt2_on_startup and not is_hymt2_worker_warm():
            _ensure_gpu_available("translation model warm-up")
            reporter.update(4, "loading_models", "Preparing HY-MT2 translation model")
            log_to_video(video_id, "Preparing HY-MT2 before WhisperX to avoid peak memory usage.")

            def report_model_warmup(detail):
                log_to_video(video_id, detail)
                reporter.update(4, "loading_models", detail)

            warm_hymt2_worker(report_model_warmup)

        check_cancellation(video_id)
        reporter.update(5, "extracting_audio", "Extracting source audio")
        extract_audio(video_input, temp_audio_wav, video_id)
        reporter.update(12, "extracting_audio", "Source audio ready")

        transcribe_audio_target = temp_audio_wav
        original_audio_target = temp_audio_wav
        if video.enable_audio_separation:
            check_cancellation(video_id)
            _ensure_gpu_available("audio separation")
            reporter.update(14, "separating_audio", "Separating speech from background audio")
            separation_dir = os.path.join(video_dir, "temp", "separation")
            vocals_path, no_vocals_path = separate_audio(temp_audio_wav, separation_dir, video_id)
            transcribe_audio_target = vocals_path
            original_audio_target = no_vocals_path
            files = dict(video.files)
            files["speech_audio"] = vocals_path
            files["background_audio"] = no_vocals_path
            video.files = files
            update_video(video_id, files=files)
            log_to_video(
                video_id, "Separated mode selected. The no-vocals track will be used as the final background audio."
            )
            reporter.update(22, "separating_audio", "Speech track ready")
        else:
            log_to_video(video_id, "Audio separation disabled. Transcribing from original audio.")

        check_cancellation(video_id)
        _ensure_gpu_available("speech recognition")
        _segments, detected_language = _recognize_for_translation(
            video, reporter, transcribe_audio_target, source_segments_json,
        )

        if not profile.cuda_available or profile.key == "cuda_low_memory":
            _release_recognition_runtime()
            log_to_video(
                video_id, "Released the warmed WhisperX model before translation to conserve processing memory."
            )

        check_cancellation(video_id)
        if not using_gemini:
            if (_execution_models(video)["translation_model"] == "q4"
                    or processing_device_preference() == "cpu"):
                _release_recognition_runtime()
                from haizflow.services.external_engine import shared_external_engine_pool

                shared_external_engine_pool().release({"voice", "translation"})
            _ensure_gpu_available("translation")
        reporter.update(50, "translating", f"Starting {engine_name} translation")

        def report_translation_progress(current, total, detail):
            progress = 50 + round(12 * current / total) if total else 50
            reporter.update(progress, "translating", detail, current, total)

        translate_segments(
            source_segments_json,
            transcript_json,
            video_id,
            video.target_language,
            source_language=detected_language or "en",
            provider="gemini" if using_gemini else "hymt2",
            translation_model=_execution_models(video)["translation_model"],
            progress_callback=report_translation_progress,
        )
        _mark_checkpoint(video, "translation", translation_signature)

        if stop_after == "translation":
            _finish_after_translation(video, reporter, video_dir, original_audio_target, stop_after="subtitles")
            return

        refreshed = get_video(video_id)
        draft_path = str(((refreshed.files if refreshed else {}) or {}).get("translation_review_draft") or "")
        if draft_path:
            Path(draft_path).unlink(missing_ok=True)
            files = dict((refreshed.files if refreshed else {}) or {})
            files.pop("translation_review_draft", None)
            update_video(video_id, files=files)

        if video.mode == "review" and not video.review_approved:
            _original_subtitle_region_for_render(video, reporter, video_dir, pipeline_progress=61)
            update_video(
                video_id,
                status="awaiting_review",
                progress=62,
                step="review_translation",
                resume_step="creating_subtitle",
                step_detail="Translation ready for review",
            )
            log_to_video(
                video_id, "Translation review is ready. Edit the translated segments, then continue the video."
            )
            return

        _finish_after_translation(video, reporter, video_dir, original_audio_target, stop_after=stop_after)

    except Exception as exc:
        error_msg = str(exc)
        if is_cancelled(video_id) or error_msg == "Video cancelled by user.":
            if is_paused(video_id):
                paused_video = get_video(video_id)
                update_video(
                    video_id,
                    status="paused",
                    error=None,
                    step="paused",
                    resume_step=(paused_video.resume_step if paused_video else ""),
                    step_detail=f"Paused during {(paused_video.resume_step if paused_video else '') or 'processing'}",
                )
                log_to_video(video_id, "Video paused by user. Resume from Projects to run it again.")
                return
            update_video(video_id, status="cancelled", error=None, step="cancelled")
            log_to_video(video_id, "Video cancelled by user.")
            return
        failed_video = get_video(video_id)
        failed_stage = (failed_video.step if failed_video else "processing") or "processing"
        original_device = processing_device_preference()
        original_translation = translation_model_preference()
        if _recover_gpu_to_cpu(video_id, failed_stage, exc):
            try:
                log_to_video(video_id, "Restarting the interrupted pipeline stage on CPU.")
                return process_video_sync(video_id, _reporter=reporter, stop_after=stop_after)
            finally:
                configure_processing_device(original_device)
                configure_translation_model(original_translation)
        stack_trace = traceback.format_exc()
        log_to_video(video_id, f"Execution failed: {error_msg}\n{stack_trace}", level="ERROR", component="PIPELINE")
        update_video(video_id, status="failed", error=error_msg, step="failed")
    finally:
        clean_video(video_id)


def _original_subtitle_region_for_render(video, reporter, video_dir, *, pipeline_progress: int = 87):
    """Return the OCR region, or bypass OCR when the user keeps source pixels."""
    video_id = video.video_id
    if not bool(getattr(video, "remove_original_subtitles", True)):
        reporter.update(pipeline_progress, "detecting_original_subtitles", "Keeping original video subtitles unchanged")
        log_to_video(video_id, "Original subtitle detection and removal disabled; preserving the source picture.")
        return None

    from haizflow.services.ocr_regions import effective_region

    override = effective_region(video)
    if override:
        return override

    reporter.update(pipeline_progress, "detecting_original_subtitles", "Preparing original subtitle scan")

    def report_ocr_progress(current: int, total: int) -> None:
        detail = "Scanning the full frame for original subtitles"
        if total:
            detail = f"Scanning original subtitles ({current}/{total})"
        reporter.update(pipeline_progress, "detecting_original_subtitles", detail, current, total)

    region = detect_original_subtitle_region(
        _required_video_path(video, "video_input", must_exist=True),
        os.path.join(video_dir, "temp"),
        video_id,
        progress_callback=report_ocr_progress,
    )
    if region:
        log_to_video(
            video_id,
            "Original subtitle coverage is enabled: covering source region "
            f"x={region['x_percent']}%, y={region['y_percent']}%, "
            f"w={region['width_percent']}%, h={region['height_percent']}%. "
            "Manual replacement-subtitle positioning does not change this region.",
            component="OCR",
        )
    else:
        log_to_video(
            video_id,
            "Original subtitle coverage is enabled, but OCR did not find a stable burned-in subtitle region.",
            level="WARNING",
            component="OCR",
        )
    return region


def _finish_after_translation(video, reporter, video_dir, original_audio_target, *, stop_after=None):
    video_id = video.video_id
    video_input = _required_video_path(video, "video_input", must_exist=True)
    from haizflow.services.video_export import export_destination

    final_video = str(export_destination(video))
    srt_output = _required_video_path(video, "srt_output")
    voice_output = _required_video_path(video, "voice_output")
    transcript_json = _required_video_path(video, "transcript_json", must_exist=True)
    voice_parts_dir = os.path.join(video_dir, "temp", "voice_parts")
    transcript_state = _file_state(transcript_json)
    subtitle_style = getattr(video, "subtitle_style", None) or SubtitleStyle()
    subtitle_signature = _signature(transcript_state, subtitle_style.max_chars_per_line)
    # Subtitle rendering and voice generation are sibling branches. A visual
    # adjustment must not regenerate speech, and a voice adjustment must not
    # run OCR or subtitle formatting. Export/full-auto materialise both.
    needs_subtitle_artifact = stop_after in {None, "subtitles", "render"}
    if needs_subtitle_artifact:
        check_cancellation(video_id)
        if _checkpoint_valid(video, "subtitles", subtitle_signature, [srt_output]) or _recovery_checkpoint_valid(
            video, "subtitles", subtitle_signature, [srt_output]
        ):
            reporter.update(64, "creating_subtitle", "Reusing subtitles checkpoint")
        else:
            reporter.update(63, "creating_subtitle", "Formatting timed subtitles")
            generate_srt(transcript_json, srt_output, subtitle_style.max_chars_per_line, video_id)
            _mark_checkpoint(video, "subtitles", subtitle_signature)

    if stop_after == "subtitles":
        # Manual projects treat source-subtitle cleanup as part of the
        # subtitle step.  Detect it here so the editor preview can show the
        # same region before the voice and final-render stages are run.
        _original_subtitle_region_for_render(video, reporter, video_dir, pipeline_progress=64)
        _complete_manual_stage(video_id, "subtitles", 64)
        return

    check_cancellation(video_id)
    target_language = str(getattr(video, "target_language", "vi") or "vi")
    configured_tts_provider = str(getattr(video, "tts_provider", "omnivoice") or "omnivoice")
    effective_tts_provider = resolve_tts_provider(configured_tts_provider, target_language)
    voice_reference = str((video.files or {}).get("voice_reference") or "")
    voice_reference_transcript = str((video.files or {}).get("voice_reference_transcript") or "")
    from haizflow.pipeline.speaker_identity import IDENTITY_VERSION
    voice_signature = _signature(
        transcript_state,
        configured_tts_provider,
        effective_tts_provider,
        target_language,
        video.tts_voice,
        getattr(video, "speaker_mode", "single"),
        _file_state(voice_reference),
        voice_reference_transcript,
        # Dedicated short narrator anchors are materially different from the
        # old first-segment reference. Do not combine cached voice parts made
        # by both strategies after a paused/failed run.
        ("omnivoice-stable-speaker-map-target-language-r7"
         if getattr(video, "speaker_mode", "single") == "multiple"
         else "omnivoice-dedicated-short-anchor-or-source-speaker-r5"),
        *((IDENTITY_VERSION,) if getattr(video, "speaker_mode", "single") == "multiple" else ()),
    )
    with open(transcript_json, "r", encoding="utf-8") as transcript_file:
        transcript_segments = json.load(transcript_file)
    if not isinstance(transcript_segments, list) or not transcript_segments:
        raise RuntimeError("The translated transcript contains no subtitle segments.")
    for index, segment in enumerate(transcript_segments, 1):
        if not isinstance(segment, dict) or not str(segment.get("text") or "").strip():
            raise RuntimeError(f"Translated subtitle segment {index} is missing text.")
    expected_parts = len(transcript_segments)
    voice_outputs = [os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3") for index in range(1, expected_parts + 1)]
    if _checkpoint_valid(video, "voice", voice_signature, voice_outputs) or _recovery_checkpoint_valid(
        video, "voice", voice_signature, voice_outputs
    ):
        reporter.update(82, "creating_voice", "Reusing generated voices", expected_parts, expected_parts)
    else:
        reporter.update(65, "creating_voice", "Starting voice synthesis")
        if effective_tts_provider == "omnivoice":
            # Translation and speech recognition can leave several GB of
            # model weights resident on the GPU. OmniVoice runs in an
            # isolated process, so hand the accelerator over before that
            # worker loads its own checkpoint instead of waiting for an
            # avoidable CUDA allocation failure.
            shutdown_hymt2_worker()
            _release_recognition_runtime()
            log_to_video(
                video_id,
                "Released translation and speech-recognition models before local TTS.",
            )
        partial_signature_matches = (
            (bool(video.resume_step) or bool(video.runtime_recovery_step) or getattr(video, "project_type", "single") == "manual")
            and video.checkpoints.get("voice_partial") == voice_signature
        )
        if os.path.isdir(voice_parts_dir) and not partial_signature_matches:
            shutil.rmtree(voice_parts_dir)
        os.makedirs(voice_parts_dir, exist_ok=True)
        # Persist the input signature before synthesis so an interrupted job
        # can reuse verified clips and regenerate only missing segments.
        _mark_checkpoint(video, "voice_partial", voice_signature)

        def report_voice_progress(current, total):
            detail = f"Verified voice audio {current} of {total}"
            reporter.update(65 + round(17 * current / max(1, total)), "creating_voice", detail, current, total)

        def report_voice_status(stage, current, total):
            if stage == "identifying_speakers":
                reporter.update(65, "creating_voice", f"Identifying speakers {current} of {total}")
            elif stage in {"synthesizing", "completed"}:
                report_voice_progress(current, total)
            else:
                reporter.update(65, "creating_voice", f"Preparing voice: {stage}")

        try:
            generate_voice_parts(
                transcript_json,
                voice_parts_dir,
                video.tts_voice,
                video_id,
                progress_callback=report_voice_progress,
                status_callback=report_voice_status,
                provider=_execution_models(video)["tts_provider"],
                target_language=target_language,
                keep_worker_warm=effective_tts_provider == "omnivoice",
            )
        finally:
            if effective_tts_provider == "omnivoice":
                # Subtitle-editor preview and downstream regeneration share
                # one warm model, then release it before FFmpeg/rendering needs
                # the accelerator. This avoids both a second checkpoint load
                # and a long-lived VRAM reservation.
                from haizflow.pipeline.omnivoice_tts import release_model_memory

                release_model_memory()
        _mark_checkpoint(video, "voice", voice_signature)

    if stop_after == "voice":
        _complete_manual_stage(video_id, "voice", 82)
        return

    check_cancellation(video_id)
    mix_audio_path, mix_audio_volume = _prepare_audio_mix(
        video,
        reporter,
        video_dir,
        original_audio_target,
    )
    timeline_signature = _signature(
        voice_signature,
        _file_state(video_input),
        _file_state(mix_audio_path),
        video.enable_audio_separation,
        mix_audio_volume,
        _file_state((video.files or {}).get("background_music") or ""),
        getattr(video, "background_music_volume", 30),
        video.background_music_loop,
        video.audio_ducking_enabled,
        video.audio_ducking_reduction_db,
        getattr(video, "tts_volume", 100),
        AUDIO_TIMELINE_VERSION,
        "exclusive-audio-source-v4-source-speech-window-sync",
    )
    if _checkpoint_valid(video, "timeline", timeline_signature, [voice_output]) or _recovery_checkpoint_valid(
        video, "timeline", timeline_signature, [voice_output]
    ):
        reporter.update(87, "building_audio_timeline", "Reusing mixed audio checkpoint")
    else:
        reporter.update(83, "building_audio_timeline", "Fitting voices to the video timeline")
        build_audio_timeline(
            transcript_json,
            voice_parts_dir,
            video_input,
            voice_output,
            video_id,
            background_audio_path=mix_audio_path,
            original_video_volume=mix_audio_volume,
            background_music_path=(video.files or {}).get("background_music") or None,
            background_music_volume=getattr(video, "background_music_volume", 30),
            background_music_loop=video.background_music_loop,
            ducking_enabled=video.audio_ducking_enabled,
            ducking_reduction_db=video.audio_ducking_reduction_db,
            tts_volume=getattr(video, "tts_volume", 100),
        )
        _mark_checkpoint(video, "timeline", timeline_signature)

    if stop_after == "timeline":
        _complete_manual_stage(video_id, "timeline", 87)
        return

    # Only presentation timing follows speech; editable source windows stay intact.
    generate_srt(
        transcript_json, srt_output, subtitle_style.max_chars_per_line, video_id,
        preserve_segment_boundaries=True, voice_parts_dir=voice_parts_dir,
    )

    check_cancellation(video_id)
    style_data = subtitle_style.model_dump() if hasattr(subtitle_style, "model_dump") else subtitle_style.dict()
    crop_data = video.crop.model_dump() if hasattr(video.crop, "model_dump") else video.crop.dict()
    remove_original_subtitles = bool(getattr(video, "remove_original_subtitles", True))
    original_subtitle_removal_mode = str(getattr(video, "original_subtitle_removal_mode", "patch") or "patch")
    # Hiding source captions and positioning translated captions are separate
    # choices. The alignment checkbox controls whether the OCR region wins.
    manual_subtitle_layout = _manual_subtitle_layout_for_render(video)
    original_subtitle_region = _original_subtitle_region_for_render(video, reporter, video_dir)
    original_subtitle_intervals = _source_subtitle_intervals(
        os.path.join(video_dir, "temp", "source_segments.json")
    )
    render_signature = _signature(
        timeline_signature,
        subtitle_signature,
        video.output_format,
        style_data,
        crop_data,
        # Bump when changing the visual treatment so a previously rendered
        # luma-only result is never reused as a valid final export.
        "static-largest-original-subtitle-ocr-v19-temporal-visibility",
        "captions-follow-generated-speech-v1",
        "caption-box-glyph-capacity-v2-win-metrics",
        "absolute-libass-font-directory-v1",
        remove_original_subtitles,
        original_subtitle_removal_mode,
        original_subtitle_region,
        original_subtitle_intervals,
        "watermark-media-and-text-style-v4",
        getattr(video, "watermark_text", ""),
        getattr(video, "watermark_scale_percent", 100),
        getattr(video, "watermark_kind", "text"),
        getattr(video, "watermark_opacity_percent", 46),
        getattr(video, "watermark_outline_percent", 100),
        _file_state((video.files or {}).get("watermark_image") or ""),
        _file_state((video.files or {}).get("watermark_video") or ""),
        getattr(video, "watermark_font_family", "Arial"),
        getattr(video, "watermark_text_color", "#FFFFFF"),
        getattr(video, "watermark_bold", True),
        getattr(video, "watermark_italic", True),
        manual_subtitle_layout,
        getattr(video, "export_preset", "source"),
    )
    from haizflow.services.video_export import current_render, preset_settings

    reusable_render = current_render(get_video(video_id) or video)
    if reusable_render and video.checkpoints.get("render") == render_signature:
        final_video = reusable_render["resolved_outputs"]["video"]
    if _checkpoint_valid(video, "render", render_signature, [final_video]) or _recovery_checkpoint_valid(
        video, "render", render_signature, [final_video]
    ):
        reporter.update(99, "rendering", "Reusing rendered video checkpoint")
    else:
        _ensure_gpu_available("final video render")
        reporter.update(88, "rendering", "Rendering final video")

        def report_render_progress(fraction: float) -> None:
            percent = max(0, min(100, round(fraction * 100)))
            pipeline_progress = min(98, 88 + round(fraction * 10))
            reporter.update(
                pipeline_progress,
                "rendering",
                f"Rendering final video ({percent}%)",
                percent,
                100,
            )

        render_video(
            video_input,
            voice_output,
            srt_output,
            final_video,
            video.output_format,
            subtitle_style,
            video.crop,
            video_id,
            original_subtitle_region,
            getattr(video, "watermark_text", ""),
            subtitle_layout_override=manual_subtitle_layout,
            progress_callback=report_render_progress,
            original_subtitle_removal_mode=original_subtitle_removal_mode,
            original_subtitle_intervals=original_subtitle_intervals,
            watermark_scale_percent=getattr(video, "watermark_scale_percent", 100),
            watermark_kind=getattr(video, "watermark_kind", "text"),
            watermark_image_path=str((video.files or {}).get("watermark_image") or ""),
            watermark_video_path=str((video.files or {}).get("watermark_video") or ""),
            watermark_opacity_percent=getattr(video, "watermark_opacity_percent", 46),
            watermark_outline_percent=getattr(video, "watermark_outline_percent", 100),
            watermark_font_family=getattr(video, "watermark_font_family", "Arial"),
            watermark_text_color=getattr(video, "watermark_text_color", "#FFFFFF"),
            watermark_bold=getattr(video, "watermark_bold", True),
            watermark_italic=getattr(video, "watermark_italic", True),
            encoding_quality=int(preset_settings(getattr(video, "export_preset", "source"))["crf"]),
        )
        if getattr(video, "export_preset", "source") != "source":
            from haizflow.pipeline.sequence_compiler import finish_export_resolution

            scaled = str(Path(final_video).with_name("render-quality.mp4"))
            finish_export_resolution(final_video, scaled, video.export_preset, video_id)
            os.replace(scaled, final_video)
        _mark_checkpoint(video, "render", render_signature)

    # Both Auto and Manual use the same immutable artifact infrastructure.
    # Publication precedes success; external copies are never checkpoint inputs.
    from haizflow.services import manual_artifacts
    from haizflow.services.video_export import render_revision

    completed_video = get_video(video_id) or video
    revision = render_revision(completed_video)
    managed = manual_artifacts.register_existing(
        video_id, "export", revision, {"video": final_video}, config_fingerprint=revision,
    )
    if not managed:
        raise RuntimeError("Rendered video could not be published as a managed artifact.")
    files = dict(completed_video.files or {})
    files["final_video"] = managed["resolved_outputs"]["video"]
    update_video(video_id, files=files)
    working = export_destination(completed_video)
    if str(working) != files["final_video"]:
        working.unlink(missing_ok=True)
    manual_artifacts.maintain(video_id)

    update_video(
        video_id,
        status="done",
        progress=100,
        step="done",
        step_detail="Final video ready",
        estimated_remaining_seconds=0,
        resume_step="",
        runtime_recovery_step="",
        manual_target_stage="",
        manual_completed_stage=(
            "render" if stop_after == "render" else str(getattr(video, "manual_completed_stage", "") or "")
        ),
        manual_completed_stages=(
            list(MANUAL_PIPELINE_STAGES)
            if stop_after == "render"
            else list(getattr(video, "manual_completed_stages", []) or [])
        ),
    )
    log_to_video(video_id, "Pipeline run finished successfully.")
