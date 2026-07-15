import gc
import json
import re
import threading

import torch
import whisperx

from autodub.config import WHISPER_MODEL
from autodub.core.hardware import runtime_profile
from autodub.services.job_store import log_to_job


_MODEL_LOCK = threading.Lock()
_WARM_ASR_MODEL = None
_WARM_DEVICE = None
_AUDIO_SAMPLE_RATE = 16000
_SEGMENT_LANGUAGE_CONFIDENCE = 0.55
_MAX_SENTENCE_GAP_SECONDS = 1.0
_MAX_SENTENCE_DURATION_SECONDS = 15.0
_MAX_SENTENCE_CHARACTERS = 280
TIMING_SOURCE = "faster-whisper-native-words-v1"
_SENTENCE_END_RE = re.compile(r"[.!?\u2026\u3002\uff01\uff1f]+[\"'\u201d\u2019)\]}]*$")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def warm_whisperx_model():
    """Load the ASR model once in the background so the first job starts promptly."""
    global _WARM_ASR_MODEL, _WARM_DEVICE
    with _MODEL_LOCK:
        if _WARM_ASR_MODEL is not None:
            return True
        profile = runtime_profile()
        device = "cuda" if profile.cuda_available else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        _WARM_ASR_MODEL = whisperx.load_model(
            WHISPER_MODEL,
            device,
            compute_type=compute_type,
            threads=profile.cpu_threads,
        )
        _WARM_DEVICE = device
        return True


def release_warm_whisperx_model():
    global _WARM_ASR_MODEL, _WARM_DEVICE
    with _MODEL_LOCK:
        if _WARM_ASR_MODEL is not None:
            del _WARM_ASR_MODEL
        _WARM_ASR_MODEL = None
        _WARM_DEVICE = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _release_cuda(job_id: str, stage: str) -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        log_to_job(job_id, f"Released WhisperX VRAM after {stage}.")


def _value(item, name: str, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _merge_transcript_text(left: str, right: str) -> str:
    """Join adjacent model fragments without inserting spaces into CJK text."""
    left = (left or "").strip()
    raw_right = right or ""
    right = raw_right.strip()
    if not left:
        return right
    if not right:
        return left
    if raw_right[:1].isspace():
        return f"{left} {right}"
    if _CJK_RE.search(left[-1:]) and _CJK_RE.match(right[:1]):
        return left + right
    if right[:1] in ",.;:!?%)]}\u3001\u3002\uff0c\uff01\uff1f":
        return left + right
    return f"{left} {right}"


def _normalize_native_segment(segment) -> dict | None:
    text = str(_value(segment, "text", "") or "")
    words = list(_value(segment, "words", None) or [])
    timed_words = [
        word
        for word in words
        if _value(word, "start") is not None and _value(word, "end") is not None
    ]
    if timed_words:
        start = float(_value(timed_words[0], "start"))
        end = float(_value(timed_words[-1], "end"))
    else:
        start = float(_value(segment, "start", 0.0) or 0.0)
        end = float(_value(segment, "end", start) or start)
    if not text.strip() or end <= start:
        return None
    return {
        "start": round(max(0.0, start), 3),
        "end": round(max(start, end), 3),
        "text": text,
    }


def _group_native_segments(native_segments) -> list[dict]:
    """Build complete spoken sentences from native timestamp fragments.

    Boundaries come only from Whisper's own timed fragments, punctuation and
    actual pauses. No fixed-duration audio window is introduced.
    """
    grouped: list[dict] = []
    current = None
    for native_segment in native_segments:
        segment = _normalize_native_segment(native_segment)
        if segment is None:
            continue
        if current is None:
            current = segment
            continue

        gap = max(0.0, segment["start"] - current["end"])
        combined_text = _merge_transcript_text(current["text"], segment["text"])
        combined_duration = segment["end"] - current["start"]
        can_join = (
            not _SENTENCE_END_RE.search(current["text"].strip())
            and gap <= _MAX_SENTENCE_GAP_SECONDS
            and combined_duration <= _MAX_SENTENCE_DURATION_SECONDS
            and len(combined_text) <= _MAX_SENTENCE_CHARACTERS
        )
        if can_join:
            current["end"] = segment["end"]
            current["text"] = combined_text
            continue

        current["text"] = current["text"].strip()
        grouped.append(current)
        current = segment

    if current is not None:
        current["text"] = current["text"].strip()
        grouped.append(current)
    return grouped


def _transcribe_with_native_timestamps(asr_model, audio, job_id: str):
    """Transcribe once and retain Faster-Whisper's language-neutral word timing."""
    native_segments, info = asr_model.model.transcribe(
        audio,
        language=None,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=True,
        multilingual=True,
        language_detection_segments=3,
        hallucination_silence_threshold=1.0,
    )
    sentence_segments = _group_native_segments(native_segments)
    detected_language = getattr(info, "language", None)
    if not sentence_segments:
        raise RuntimeError("Whisper did not return any timed speech segments.")
    log_to_job(
        job_id,
        f"Native word timestamps prepared {len(sentence_segments)} complete sentence segment(s).",
    )
    return sentence_segments, detected_language


def _detect_segment_languages(asr_model, audio, segments, fallback_language: str, job_id: str):
    """Detect one source language for each immutable sentence timestamp."""
    fallback_language = fallback_language or "en"
    detected_segments = []
    counts = {}
    audio_duration = len(audio) / _AUDIO_SAMPLE_RATE

    for index, segment in enumerate(segments, start=1):
        start = max(0.0, float(segment.get("start", 0.0)))
        end = min(audio_duration, float(segment.get("end", start)))
        language = fallback_language
        confidence = 0.0

        if end > start:
            clip = audio[int(start * _AUDIO_SAMPLE_RATE): int(end * _AUDIO_SAMPLE_RATE)]
            try:
                detected, confidence, _all_probabilities = asr_model.model.detect_language(
                    audio=clip,
                    language_detection_threshold=0.0,
                )
                if detected and confidence >= _SEGMENT_LANGUAGE_CONFIDENCE:
                    language = detected
                else:
                    log_to_job(
                        job_id,
                        f"Sentence {index} language confidence {confidence:.2f} is low; using '{fallback_language}'.",
                    )
            except Exception as exc:
                log_to_job(job_id, f"Sentence {index} language detection failed; using '{fallback_language}': {exc}")

        segment_with_language = dict(segment)
        segment_with_language["language"] = language
        segment_with_language["language_confidence"] = round(float(confidence), 3)
        detected_segments.append(segment_with_language)
        counts[language] = counts.get(language, 0) + 1

    if counts:
        summary = ", ".join(f"{language}={count}" for language, count in sorted(counts.items()))
        log_to_job(job_id, f"Detected languages per sentence: {summary}.")
    return detected_segments


def _retranscribe_mixed_language_segments(asr_model, audio, segments, primary_language: str, job_id: str):
    """Correct switched-language text while preserving every original timestamp."""
    primary_language = primary_language or "en"
    corrected_segments = []

    for index, segment in enumerate(segments, start=1):
        language = segment.get("language") or primary_language
        confidence = float(segment.get("language_confidence", 0.0))
        start = max(0.0, float(segment.get("start", 0.0)))
        end = min(len(audio) / _AUDIO_SAMPLE_RATE, float(segment.get("end", start)))
        corrected_segment = dict(segment)
        if language == primary_language or confidence < _SEGMENT_LANGUAGE_CONFIDENCE or end <= start:
            corrected_segments.append(corrected_segment)
            continue

        try:
            log_to_job(job_id, f"Re-transcribing sentence {index} with detected language '{language}'.")
            clip = audio[int(start * _AUDIO_SAMPLE_RATE): int(end * _AUDIO_SAMPLE_RATE)]
            local_segments, _info = asr_model.model.transcribe(
                clip,
                language=language,
                beam_size=5,
                word_timestamps=False,
                vad_filter=False,
                condition_on_previous_text=False,
                multilingual=False,
            )
            corrected_text = ""
            for local_segment in local_segments:
                corrected_text = _merge_transcript_text(
                    corrected_text,
                    str(_value(local_segment, "text", "") or ""),
                )
            if corrected_text.strip():
                corrected_segment["text"] = corrected_text.strip()
        except Exception as exc:
            log_to_job(job_id, f"Could not re-transcribe sentence {index} in '{language}'; keeping its text: {exc}")
        corrected_segments.append(corrected_segment)

    return corrected_segments


def _validate_timestamp_invariants(segments: list[dict], audio_duration: float) -> None:
    """Reject timestamp corruption before translation, subtitles or TTS can use it."""
    previous_start = -1.0
    previous_end = -1.0
    for index, segment in enumerate(segments, start=1):
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        if not segment.get("text", "").strip():
            raise RuntimeError(f"Whisper sentence {index} has no text.")
        if start < previous_start or end <= start:
            raise RuntimeError(f"Whisper sentence {index} has invalid or non-monotonic timestamps.")
        if start < previous_end - 0.05:
            raise RuntimeError(f"Whisper sentence {index} overlaps the previous sentence timestamp.")
        if end > audio_duration + 0.5:
            raise RuntimeError(f"Whisper sentence {index} ends outside the source audio.")
        previous_start = start
        previous_end = end


def transcribe(audio_path: str, output_json_path: str, source_language: str, job_id: str, progress_callback=None):
    """Transcribe with immutable native timestamps for every source language."""
    log_to_job(job_id, f"Initializing WhisperX with model '{WHISPER_MODEL}'.")
    profile = runtime_profile()
    device = "cuda" if profile.cuda_available else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    log_to_job(
        job_id,
        f"WhisperX device: {device}, compute type: {compute_type}, threads: {profile.cpu_threads}.",
    )

    asr_model = None
    using_warm_model = False
    audio = None
    try:
        log_to_job(job_id, "Loading WhisperX transcription model.")
        if progress_callback:
            progress_callback("loading_model", "Loading WhisperX speech model")
        with _MODEL_LOCK:
            if _WARM_ASR_MODEL is not None and _WARM_DEVICE == device:
                asr_model = _WARM_ASR_MODEL
                using_warm_model = True
                log_to_job(job_id, "Reusing warmed WhisperX speech model.")
            else:
                asr_model = whisperx.load_model(
                    WHISPER_MODEL,
                    device,
                    compute_type=compute_type,
                    threads=profile.cpu_threads,
                )
        audio = whisperx.load_audio(audio_path)
        if source_language != "auto":
            log_to_job(job_id, f"Ignoring legacy source language '{source_language}'; using automatic detection.")

        log_to_job(job_id, "Running continuous transcription with native word timestamps.")
        if progress_callback:
            progress_callback("transcribing", "Transcribing speech with native timestamps")
        sentence_segments, detected_language = _transcribe_with_native_timestamps(asr_model, audio, job_id)
        log_to_job(job_id, f"Transcription completed. Primary detected language: '{detected_language}'.")
        if progress_callback:
            progress_callback("transcribed", f"Detected {detected_language or 'unknown'} speech")
            progress_callback("segmenting", f"Prepared {len(sentence_segments)} complete sentences")

        source_segments = _detect_segment_languages(
            asr_model,
            audio,
            sentence_segments,
            detected_language or "en",
            job_id,
        )
        source_segments = _retranscribe_mixed_language_segments(
            asr_model,
            audio,
            source_segments,
            detected_language or "en",
            job_id,
        )
        _validate_timestamp_invariants(source_segments, len(audio) / _AUDIO_SAMPLE_RATE)
        if progress_callback:
            progress_callback("detecting_languages", f"Validated {len(source_segments)} timed sentences")

        output_segments = [
            {
                "start": round(float(segment["start"]), 3),
                "end": round(float(segment["end"]), 3),
                "text": segment["text"].strip(),
                "language": segment.get("language") or detected_language or "en",
                "language_confidence": round(float(segment.get("language_confidence", 0.0)), 3),
                "timing_source": TIMING_SOURCE,
            }
            for segment in source_segments
        ]
        with open(output_json_path, "w", encoding="utf-8") as file:
            json.dump(output_segments, file, ensure_ascii=False, indent=2)

        log_to_job(job_id, f"Saved {len(output_segments)} timestamp-locked source sentences to: {output_json_path}")
        if progress_callback:
            progress_callback("saved", f"Prepared {len(output_segments)} timestamp-locked sentences")
        return output_segments, detected_language
    finally:
        if asr_model is not None and not using_warm_model:
            del asr_model
        if audio is not None:
            del audio
        _release_cuda(job_id, "WhisperX cleanup")
