import asyncio
import contextlib
import json
import os
import re
import shutil
import threading
import time
import unicodedata
import uuid

import edge_tts

from haizflow.config import TTS_MAX_CONCURRENCY
from haizflow.pipeline.process_registry import check_cancellation, is_cancelled
from haizflow.services.video_store import get_video, log_to_video


_INITIAL_RETRIES = 2
_RECOVERY_RETRIES = 3
_MP3_MIN_BYTES = 512
_EDGE_MIN_REQUEST_INTERVAL_SECONDS = 1.5
_EDGE_TRANSIENT_COOLDOWN_SECONDS = 6.0
_EDGE_MAX_REQUEST_CHARACTERS = 180
_EDGE_CJK_MAX_REQUEST_CHARACTERS = 64
_EDGE_REQUEST_TIMEOUT_SECONDS = 75.0
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_EDGE_REQUEST_GUARD = threading.Lock()
_EDGE_NEXT_REQUEST_AT = 0.0
_CJK_CHARACTER = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")


def resolve_tts_provider(provider: str, target_language: str) -> str:
    normalized = str(provider or "auto").strip().lower()
    if normalized in {"auto", "vieneu"}:
        # Read old projects without preserving the retired VieNeu runtime.
        return "omnivoice"
    if normalized not in {"omnivoice", "edge"}:
        raise ValueError(f"Unsupported TTS provider: {provider}")
    return normalized


def _edge_request_limit(text: str, upper_bound: int | None = None) -> int:
    """Use materially smaller requests for unspaced CJK transcripts."""
    base = _EDGE_CJK_MAX_REQUEST_CHARACTERS if _CJK_CHARACTER.search(text or "") else _EDGE_MAX_REQUEST_CHARACTERS
    return min(base, upper_bound) if upper_bound else base


def preprocess_text_for_tts(text: str) -> str:
    """Normalize transport-sensitive characters without changing words."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).translate(
        str.maketrans(
            {
                "\u00a0": " ",
                "\u200b": "",
                "\u200c": "",
                "\u200d": "",
                "\ufeff": "",
                "\u2018": "'",
                "\u2019": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u2013": ",",
                "\u2014": ",",
                "\u2026": "...",
            }
        )
    )
    text = " ".join(text.split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if text and text[-1] not in ".!?,;:。！？；：":
        text += "."
    return text


def _split_edge_request(text: str, limit: int = _EDGE_MAX_REQUEST_CHARACTERS) -> list[str]:
    """Split long narration into service-friendly requests at natural stops."""
    normalised = preprocess_text_for_tts(text)
    if len(normalised) <= limit:
        return [normalised] if normalised else []
    # Chinese/Japanese transcripts commonly have no spaces. Split after both
    # Western and CJK punctuation, with optional whitespace.
    pieces = re.split(r"(?<=[.!?;:。！？；：])\s*", normalised)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        remaining = piece.strip()
        while len(remaining) > limit:
            boundary = max(
                max(
                    remaining.rfind(", ", 0, limit + 1),
                    remaining.rfind("，", 0, limit + 1),
                    remaining.rfind("、", 0, limit + 1),
                ),
                remaining.rfind(" ", 0, limit + 1),
            )
            boundary = boundary + (1 if boundary >= 0 else 0)
            if boundary < max(40, limit // 2):
                boundary = limit
            prefix, remaining = remaining[:boundary].strip(), remaining[boundary:].strip()
            if current:
                chunks.append(current)
                current = ""
            if prefix:
                chunks.append(prefix)
        candidate = f"{current} {remaining}".strip() if current else remaining
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = remaining
    if current:
        chunks.append(current)
    return chunks


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _is_valid_mp3(path: str) -> bool:
    """Reject zero-byte and partial Edge TTS responses before timeline assembly."""
    try:
        if os.path.getsize(path) < _MP3_MIN_BYTES:
            return False
        with open(path, "rb") as file:
            header = file.read(3)
    except OSError:
        return False
    if header == b"ID3":
        return True
    return len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0


def _tts_error_code(error: Exception) -> str:
    """Return a stable diagnostic label for the user-facing video log."""
    error_type = type(error).__name__.lower()
    message = str(error).lower()
    if "noaudioreceived" in error_type or "no audio was received" in message:
        return "edge_no_audio"
    if isinstance(error, asyncio.TimeoutError) or "timeout" in error_type or "timed out" in message:
        return "network_timeout"
    if "websocket" in error_type or "clientconnector" in error_type or "connection" in error_type:
        return "network_connection"
    if isinstance(error, ValueError):
        return "invalid_tts_input"
    if isinstance(error, OSError):
        return "file_io"
    if isinstance(error, RuntimeError) and "invalid mp3" in message:
        return "invalid_audio"
    return "unexpected_error"


def _tts_error_detail(error: Exception, limit: int = 180) -> str:
    message = _ANSI_ESCAPE.sub("", str(error))
    message = " ".join(message.split()) or type(error).__name__
    return message if len(message) <= limit else f"{message[: limit - 3]}..."


def _tts_text_preview(text: str, limit: int = 220) -> str:
    """Keep the active sentence visible without allowing it to break the video log."""
    preview = " ".join(str(text or "").split())
    preview = _ANSI_ESCAPE.sub("", preview).replace('"', "'")
    if len(preview) > limit:
        preview = f"{preview[: limit - 3]}..."
    return f'"{preview or "<empty>"}"'


async def _sleep_with_cancellation(delay: float, video_id: str | None) -> None:
    deadline = asyncio.get_running_loop().time() + max(0.0, delay)
    while True:
        if video_id:
            check_cancellation(video_id)
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return
        await asyncio.sleep(min(0.25, remaining))


async def _pace_edge_request(video_id: str | None) -> None:
    """Space requests across previews and pipelines to avoid Edge throttling."""
    global _EDGE_NEXT_REQUEST_AT
    with _EDGE_REQUEST_GUARD:
        now = time.monotonic()
        delay = max(0.0, _EDGE_NEXT_REQUEST_AT - now)
        _EDGE_NEXT_REQUEST_AT = max(now, _EDGE_NEXT_REQUEST_AT) + _EDGE_MIN_REQUEST_INTERVAL_SECONDS
    if delay:
        await _sleep_with_cancellation(delay, video_id)


def _penalize_edge_requests(error: Exception) -> None:
    """Apply one shared cooldown after a transient service/network failure."""
    global _EDGE_NEXT_REQUEST_AT
    if _tts_error_code(error) not in {"edge_no_audio", "network_timeout", "network_connection"}:
        return
    with _EDGE_REQUEST_GUARD:
        _EDGE_NEXT_REQUEST_AT = max(
            _EDGE_NEXT_REQUEST_AT,
            time.monotonic() + _EDGE_TRANSIENT_COOLDOWN_SECONDS,
        )


async def _save_with_cancellation(communicate, path: str, video_id: str | None) -> None:
    task = asyncio.create_task(communicate.save(path))
    deadline = asyncio.get_running_loop().time() + _EDGE_REQUEST_TIMEOUT_SECONDS
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.25)
            if video_id and is_cancelled(video_id):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                check_cancellation(video_id)
            if asyncio.get_running_loop().time() >= deadline:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                raise TimeoutError(f"Edge TTS request exceeded {_EDGE_REQUEST_TIMEOUT_SECONDS:.0f} seconds.")
        await task
    except BaseException:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        raise


async def tts_segment_with_retry(
    text: str,
    voice: str,
    output_path: str,
    retries: int = _INITIAL_RETRIES,
    *,
    video_id: str | None = None,
    base_delay: float = 1.5,
    retry_callback=None,
) -> int:
    """Create one verified MP3 atomically, using a fresh connection per attempt."""
    processed_text = preprocess_text_for_tts(text)
    if not processed_text:
        raise ValueError("TTS text is empty after normalization.")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    last_error = None
    stagger = (sum(processed_text.encode("utf-8")) % 7) * 0.15
    for attempt in range(1, max(1, retries) + 1):
        if video_id:
            check_cancellation(video_id)
        temporary_path = f"{output_path}.part-{uuid.uuid4().hex}"
        try:
            await _pace_edge_request(video_id)
            communicate = edge_tts.Communicate(
                processed_text,
                voice,
                connect_timeout=15,
                receive_timeout=60,
            )
            await _save_with_cancellation(communicate, temporary_path, video_id)
            if not _is_valid_mp3(temporary_path):
                raise RuntimeError("Edge TTS returned an empty or invalid MP3 stream.")
            os.replace(temporary_path, output_path)
            return attempt
        except asyncio.CancelledError:
            _remove_file(temporary_path)
            raise
        except Exception as exc:
            _remove_file(temporary_path)
            if video_id and is_cancelled(video_id):
                check_cancellation(video_id)
            last_error = exc
            _penalize_edge_requests(exc)
            if attempt >= retries:
                break
            delay = min(12.0, base_delay * (2 ** (attempt - 1)) + stagger)
            if retry_callback:
                retry_callback(attempt, retries, exc, delay)
            await _sleep_with_cancellation(delay, video_id)
    raise RuntimeError(
        f"Edge TTS produced no valid audio after {max(1, retries)} attempts: {last_error}"
    ) from last_error


async def _tts_text_with_retry(
    text: str,
    voice: str,
    output_path: str,
    retries: int,
    *,
    video_id: str | None = None,
    base_delay: float = 1.5,
    retry_callback=None,
    chunk_limit: int | None = None,
) -> int:
    """Synthesize long text in bounded Edge requests and join it atomically."""
    chunks = _split_edge_request(text, limit=_edge_request_limit(text, chunk_limit))
    if not chunks:
        raise ValueError("TTS text is empty after normalization.")
    if len(chunks) == 1:
        return await tts_segment_with_retry(
            # Preserve the original request for the single-chunk path.  The
            # lower-level function owns normalization already; doing it here
            # as well would subtly change retry/resume identity and logs.
            text,
            voice,
            output_path,
            retries,
            video_id=video_id,
            base_delay=base_delay,
            retry_callback=retry_callback,
        )

    from pydub import AudioSegment

    chunk_root = f"{output_path}.chunks-{uuid.uuid4().hex}"
    os.makedirs(chunk_root, exist_ok=False)
    combined_path = f"{output_path}.part-{uuid.uuid4().hex}"
    attempts = 0
    try:
        parts = []
        for index, chunk in enumerate(chunks, 1):
            if video_id:
                check_cancellation(video_id)
            part_path = os.path.join(chunk_root, f"part-{index:03d}.mp3")
            attempts += await tts_segment_with_retry(
                chunk,
                voice,
                part_path,
                retries,
                video_id=video_id,
                base_delay=base_delay,
                retry_callback=retry_callback,
            )
            parts.append(AudioSegment.from_file(part_path, format="mp3"))
        joined = AudioSegment.empty()
        for part in parts:
            joined += part
        joined.export(combined_path, format="mp3", bitrate="192k")
        if not _is_valid_mp3(combined_path):
            raise RuntimeError("Edge TTS returned invalid audio after joining bounded requests.")
        os.replace(combined_path, output_path)
        return attempts
    finally:
        _remove_file(combined_path)
        shutil.rmtree(chunk_root, ignore_errors=True)


def _run_coroutine(coroutine):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coroutine)
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        asyncio.set_event_loop(None)
        loop.close()


def _generate_edge_voice_parts(
    segments_json_path: str,
    voice_parts_dir: str,
    voice: str,
    video_id: str,
    progress_callback=None,
):
    """Generate every segment, recovering transient online failures without silence."""
    request_mode = "sequential" if TTS_MAX_CONCURRENCY == 1 else "controlled_parallel"
    log_to_video(
        video_id,
        f"[TTS][SESSION_START] voice={voice} mode={request_mode} max_concurrency={TTS_MAX_CONCURRENCY}",
    )
    os.makedirs(voice_parts_dir, exist_ok=True)
    with open(segments_json_path, "r", encoding="utf-8") as file:
        segments = json.load(file)
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("Voice generation requires at least one translated subtitle segment.")
    for index, segment in enumerate(segments, 1):
        if not isinstance(segment, dict) or not str(segment.get("text") or "").strip():
            raise RuntimeError(f"Translated subtitle segment {index} is missing text.")

    async def run_all():
        total = len(segments)
        limiter = asyncio.Semaphore(TTS_MAX_CONCURRENCY)
        completed = 0
        transient_failures = []

        def report_completed(index: int, *, phase: str, attempts: int, reused: bool = False) -> None:
            nonlocal completed
            completed += 1
            status = "REUSED" if reused else "COMPLETE"
            log_to_video(
                video_id,
                f"[TTS][{status}] segment={index}/{total} overall={completed}/{total} "
                f"phase={phase} attempts={attempts}",
            )
            if progress_callback:
                progress_callback(completed, total)

        def retry_logger(index: int, phase: str, text: str):
            def report(attempt, retries, error, delay):
                error_code = _tts_error_code(error)
                error_detail = _tts_error_detail(error)
                log_to_video(
                    video_id,
                    f"[TTS][RETRY] segment={index}/{total} phase={phase} attempt={attempt}/{retries} "
                    f"error={error_code} retry_in={delay:.1f}s text={_tts_text_preview(text)} "
                    f"detail={error_detail}",
                )

            return report

        async def synthesize(index, segment):
            text = str(segment.get("text") or "")
            part_path = os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3")
            if _is_valid_mp3(part_path):
                report_completed(index, phase="checkpoint", attempts=0, reused=True)
                return
            _remove_file(part_path)
            check_cancellation(video_id)
            log_to_video(
                video_id,
                f"[TTS][QUEUED] segment={index}/{total} characters={len(text)} text={_tts_text_preview(text)}",
            )
            async with limiter:
                try:
                    log_to_video(
                        video_id,
                        f"[TTS][START] segment={index}/{total} phase=primary voice={voice} "
                        f"characters={len(text)} text={_tts_text_preview(text)} "
                        f"output={os.path.basename(part_path)}",
                    )
                    attempts = await _tts_text_with_retry(
                        text,
                        voice,
                        part_path,
                        _INITIAL_RETRIES,
                        video_id=video_id,
                        retry_callback=retry_logger(index, "primary", text),
                    )
                except Exception as exc:
                    if is_cancelled(video_id):
                        check_cancellation(video_id)
                    transient_failures.append((index, text, part_path, exc))
                    log_to_video(
                        video_id,
                        f"[TTS][RECOVERY_QUEUED] segment={index}/{total} "
                        f"error={_tts_error_code(exc)} text={_tts_text_preview(text)} "
                        f"detail={_tts_error_detail(exc)}",
                    )
                    return
            report_completed(index, phase="primary", attempts=attempts)

        if TTS_MAX_CONCURRENCY == 1:
            for index, segment in enumerate(segments, 1):
                await synthesize(index, segment)
        else:
            await asyncio.gather(*(synthesize(index, segment) for index, segment in enumerate(segments, 1)))

        permanent_failures = []
        if transient_failures:
            transient_failures.sort(key=lambda item: item[0])
            log_to_video(
                video_id,
                f"Recovering {len(transient_failures)} TTS segment(s) sequentially with fresh connections.",
            )
            await _sleep_with_cancellation(2.0, video_id)
            for index, text, part_path, initial_error in transient_failures:
                check_cancellation(video_id)
                log_to_video(
                    video_id,
                    f"[TTS][RECOVERY_START] segment={index}/{total} error={_tts_error_code(initial_error)} "
                    f"characters={len(text)} text={_tts_text_preview(text)}",
                )
                try:
                    attempts = await _tts_text_with_retry(
                        text,
                        voice,
                        part_path,
                        _RECOVERY_RETRIES,
                        video_id=video_id,
                        base_delay=2.5,
                        retry_callback=retry_logger(index, "recovery", text),
                        chunk_limit=96,
                    )
                except Exception as exc:
                    if is_cancelled(video_id):
                        check_cancellation(video_id)
                    permanent_failures.append((index, initial_error, exc))
                    _remove_file(part_path)
                    log_to_video(
                        video_id,
                        f"[TTS][FAILED] segment={index}/{total} phase=recovery "
                        f"error={_tts_error_code(exc)} text={_tts_text_preview(text)} "
                        f"detail={_tts_error_detail(exc)}",
                    )
                    continue
                report_completed(index, phase="recovery", attempts=attempts)

        invalid_indices = [
            index
            for index in range(1, total + 1)
            if not _is_valid_mp3(os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3"))
        ]
        if permanent_failures or invalid_indices:
            failed = sorted(set(invalid_indices) | {item[0] for item in permanent_failures})
            raise RuntimeError(
                "Edge TTS could not create valid audio for subtitle segment(s): "
                + ", ".join(str(index) for index in failed)
                + ". The project was stopped before rendering; resume it when the network service is available."
            )
        if completed != total:
            raise RuntimeError(f"TTS completion mismatch: verified {completed} of {total} segments.")

    _run_coroutine(run_all())
    log_to_video(video_id, "All segment voices were generated and verified successfully.")


def generate_voice_parts(
    segments_json_path: str,
    voice_parts_dir: str,
    voice: str,
    video_id: str,
    progress_callback=None,
    *,
    provider: str = "edge",
    target_language: str = "vi",
):
    effective = resolve_tts_provider(provider, target_language)
    if effective == "edge":
        return _generate_edge_voice_parts(segments_json_path, voice_parts_dir, voice, video_id, progress_callback)

    from haizflow.pipeline.omnivoice_tts import runtime_description, synthesize_batch_to_mp3

    with open(segments_json_path, "r", encoding="utf-8") as file:
        segments = json.load(file)
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("Voice generation requires at least one translated subtitle segment.")
    total = len(segments)
    log_to_video(
        video_id,
        f"[TTS][SESSION_START] provider=omnivoice backend=local device={runtime_description()} voice={voice}",
    )
    os.makedirs(voice_parts_dir, exist_ok=True)
    pending = []
    current_video = get_video(video_id)
    current_files = dict((current_video.files if current_video else {}) or {})
    speaker_mode = str(getattr(current_video, "speaker_mode", "single") or "single")
    clone_reference = str(current_files.get("voice_reference") or "")
    clone_transcript = str(current_files.get("voice_reference_transcript") or "")
    source_segments = []
    source_audio_path = ""
    if speaker_mode == "multiple" and current_video is not None:
        video_input = str(current_files.get("video_input") or "")
        video_root = os.path.dirname(os.path.dirname(video_input)) if video_input else ""
        source_segments_path = os.path.join(video_root, "temp", "source_segments.json") if video_root else ""
        source_audio_path = str(current_files.get("speech_audio") or "")
        if not source_audio_path and video_root:
            source_audio_path = os.path.join(video_root, "temp", "audio.wav")
        if source_segments_path and os.path.isfile(source_segments_path):
            with open(source_segments_path, "r", encoding="utf-8") as source_file:
                loaded_source_segments = json.load(source_file)
            if isinstance(loaded_source_segments, list):
                source_segments = loaded_source_segments
        if not source_segments or not os.path.isfile(source_audio_path):
            raise RuntimeError(
                "Multiple-speaker OmniVoice mode requires the current source speech and timestamped source transcript."
            )
    if voice == "omnivoice:clone" and (
        not clone_reference or not os.path.isfile(clone_reference) or not clone_transcript.strip()
    ):
        raise RuntimeError("OmniVoice voice cloning requires an authorised sample and its exact transcript.")

    def source_reference_for(segment: dict) -> dict:
        """Match edited subtitles to source speech by time, never by list position."""
        if speaker_mode != "multiple" or not source_segments:
            return {}
        start = float(segment.get("start") or 0.0)
        end = max(start, float(segment.get("end") or start))
        midpoint = (start + end) / 2.0

        def match_score(source: dict) -> tuple[float, float]:
            source_start = float((source or {}).get("start") or 0.0)
            source_end = max(source_start, float((source or {}).get("end") or source_start))
            overlap = max(0.0, min(end, source_end) - max(start, source_start))
            distance = abs(midpoint - ((source_start + source_end) / 2.0))
            return overlap, -distance

        return max((item for item in source_segments if isinstance(item, dict)), key=match_score, default={})

    for index, segment in enumerate(segments, 1):
        text = str((segment or {}).get("text") or "").strip() if isinstance(segment, dict) else ""
        if not text:
            raise RuntimeError(f"Translated subtitle segment {index} is missing text.")
        part_path = os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3")
        if not _is_valid_mp3(part_path):
            _remove_file(part_path)
            log_to_video(video_id, f"[TTS][QUEUED] provider=omnivoice segment={index}/{total} voice={voice}")
            source_reference = source_reference_for(segment)
            pending.append(
                {
                    "text": preprocess_text_for_tts(text),
                    "voice": voice,
                    "output_path": part_path,
                    "index": str(index),
                    "reference_path": clone_reference if voice == "omnivoice:clone" else "",
                    "reference_text": clone_transcript if voice == "omnivoice:clone" else "",
                    "source_audio_path": source_audio_path if speaker_mode == "multiple" else "",
                    "source_start": str(source_reference.get("start", "")),
                    "source_end": str(source_reference.get("end", "")),
                    "source_text": str(source_reference.get("text", "")),
                }
            )
    completed_before_worker = total - len(pending)
    if progress_callback and completed_before_worker:
        progress_callback(completed_before_worker, total)
    if pending:

        def report_omnivoice_progress(completed, _pending_total, stage):
            if progress_callback is None:
                return
            # Loading the local checkpoint is meaningful progress but no new
            # segment is complete yet. Keep the verified count stable until
            # the worker atomically finishes each waveform.
            verified = completed_before_worker + completed
            progress_callback(min(verified, total), total)

        synthesize_batch_to_mp3(
            pending,
            video_id,
            language_id=target_language,
            speaker_mode=speaker_mode,
            progress_callback=report_omnivoice_progress,
        )
    for index in range(1, total + 1):
        part_path = os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3")
        if not _is_valid_mp3(part_path):
            raise RuntimeError(f"OmniVoice produced invalid audio for subtitle segment {index}.")
    if progress_callback:
        progress_callback(total, total)
    log_to_video(video_id, "OmniVoice generated and verified every voice segment locally.")


def generate_single_voice(
    text: str,
    output_path: str,
    voice: str,
    video_id: str,
    *,
    provider: str = "edge",
    target_language: str = "vi",
):
    """Create and verify a complete narration file."""
    log_to_video(video_id, f"Generating single narration voice file with '{voice}'.")

    effective = resolve_tts_provider(provider, target_language)
    if effective == "omnivoice":
        from haizflow.pipeline.omnivoice_tts import synthesize_to_mp3

        current_video = get_video(video_id)
        current_files = dict((current_video.files if current_video else {}) or {})
        reference_path = str(current_files.get("voice_reference") or "")
        reference_text = str(current_files.get("voice_reference_transcript") or "")
        if voice == "omnivoice:clone" and (
            not reference_path or not os.path.isfile(reference_path) or not reference_text.strip()
        ):
            raise RuntimeError("OmniVoice voice cloning requires an authorised sample and its exact transcript.")
        synthesize_to_mp3(
            preprocess_text_for_tts(text),
            voice,
            output_path,
            video_id,
            language_id=target_language,
            reference_path=reference_path if voice == "omnivoice:clone" else "",
            reference_text=reference_text if voice == "omnivoice:clone" else "",
        )
    else:

        async def run_single():
            await _tts_text_with_retry(text, voice, output_path, _INITIAL_RETRIES, video_id=video_id)

        _run_coroutine(run_single())
    log_to_video(video_id, f"Successfully created narration file: {output_path}")
