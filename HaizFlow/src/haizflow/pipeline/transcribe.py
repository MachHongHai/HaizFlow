import gc
import json
import os
import re
import statistics
import tempfile
import threading
from pathlib import Path

from haizflow.config import HF_HOME, MODELS_DIR

import torch
import torchaudio
import whisperx

from haizflow.core.dependency_security import install_lightning_checkpoint_guard
from haizflow.core.hardware import runtime_profile
from haizflow.core.model_integrity import (
    ALIGNMENT_MODELS,
    ModelIntegrityError,
    WHISPERX_VAD_SHA256,
    WHISPERX_VAD_SIZE,
    verify_alignment_model,
    verify_whisper_model,
    verify_whisper_turbo_model,
    verify_whisperx_vad_model,
)
from haizflow.pipeline.process_registry import check_cancellation, is_cancelled
from haizflow.services.video_store import log_to_video


# WhisperX imports Lightning before any model is opened. Backport Lightning's
# upstream checkpoint allowlist before the first HaizFlow model load.
install_lightning_checkpoint_guard()


_MODEL_LOCK = threading.Lock()
_ALIGNMENT_PATCH_LOCK = threading.RLock()
_WARM_ASR_MODEL = None
_WARM_DEVICE = None
_WARM_MODEL_NAME = None
_AUDIO_SAMPLE_RATE = 16000
_SEGMENT_LANGUAGE_CONFIDENCE = 0.55
_ALIGNMENT_MIN_COVERAGE_RATIO = 0.55
_ALIGNMENT_MIN_MEDIAN_WORD_SCORE = 0.03
_ALIGNMENT_GROUP_PADDING_SECONDS = 2.5
_ALIGNMENT_GROUP_SPLIT_GAP_SECONDS = 3.0
_ALIGNMENT_GROUP_MAX_SECONDS = 75.0
_MIN_SENTENCE_SPAN_SECONDS = 0.45
TIMING_SOURCE = "whisperx-context-aligned-sentences-v7"
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
_CJK_LANGUAGE_CODES = frozenset({"zh", "ja", "ko"})
_SENTENCE_END_CHARS = frozenset(".!?\u2026\u3002\uff01\uff1f")
_SENTENCE_CLOSERS = frozenset("\"'\u2019\u201d)]}\u3009\u300b\u300d\u300f\u3011")
_WHISPERX_VAD_SIZE = WHISPERX_VAD_SIZE
_WHISPERX_VAD_SHA256 = WHISPERX_VAD_SHA256
# WhisperX's Hugging Face alignment table is mutable and most entries expose
# pickle checkpoints without safetensors. Production accepts only these fixed
# torchaudio assets, verified on every load before PyTorch deserializes them.
_VERIFIED_ALIGNMENT_MODELS = ALIGNMENT_MODELS


def _whisper_model_source(model_name: str = "small") -> tuple[str, bool]:
    """Resolve only the checksum-verified model installed by first-run setup."""
    normalized = str(model_name or "small").strip().lower()
    if normalized not in {"small", "large-v3-turbo"}:
        raise RuntimeError(f"Unsupported Whisper model: {model_name}")
    candidate = Path(MODELS_DIR) / "whisper" / normalized
    try:
        verifier = verify_whisper_turbo_model if normalized == "large-v3-turbo" else verify_whisper_model
        return str(verifier(candidate)), True
    except ModelIntegrityError as exc:
        raise RuntimeError(
            "Whisper is missing or corrupted. Return to the model setup screen and retry the download."
        ) from exc


def _load_whisper_model(device: str, compute_type: str, threads: int, model_name: str = "small"):
    vad_model_path = _verify_whisperx_vad_asset()
    source, local_only = _whisper_model_source(model_name)
    return whisperx.load_model(
        source,
        device,
        compute_type=compute_type,
        threads=threads,
        download_root=os.path.join(HF_HOME, "hub"),
        local_files_only=local_only,
        vad_options={"model_fp": str(vad_model_path)},
    )


def warm_whisperx_model(model_name: str = "small"):
    """Load the ASR model once in the background so the first video starts promptly."""
    global _WARM_ASR_MODEL, _WARM_DEVICE, _WARM_MODEL_NAME
    model_name = str(model_name or "small").strip().lower()
    if model_name not in {"small", "large-v3-turbo"}:
        raise RuntimeError(f"Unsupported Whisper model: {model_name}")
    with _MODEL_LOCK:
        if _WARM_ASR_MODEL is not None and _WARM_MODEL_NAME == model_name:
            return True
        if _WARM_ASR_MODEL is not None:
            del _WARM_ASR_MODEL
            _WARM_ASR_MODEL = None
        profile = runtime_profile()
        device = "cuda" if profile.cuda_available else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        try:
            model = _load_whisper_model(device, compute_type, profile.cpu_threads, model_name)
        except Exception:
            _WARM_ASR_MODEL = None
            _WARM_DEVICE = None
            _WARM_MODEL_NAME = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise
        _WARM_ASR_MODEL = model
        _WARM_DEVICE = device
        _WARM_MODEL_NAME = model_name
        return True


def release_warm_whisperx_model():
    global _WARM_ASR_MODEL, _WARM_DEVICE, _WARM_MODEL_NAME
    with _MODEL_LOCK:
        if _WARM_ASR_MODEL is not None:
            del _WARM_ASR_MODEL
        _WARM_ASR_MODEL = None
        _WARM_DEVICE = None
        _WARM_MODEL_NAME = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _release_cuda(video_id: str, stage: str) -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        log_to_video(video_id, f"Released WhisperX VRAM after {stage}.")


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


def _detect_segment_languages(asr_model, audio, segments, fallback_language: str, video_id: str):
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
            clip = audio[int(start * _AUDIO_SAMPLE_RATE) : int(end * _AUDIO_SAMPLE_RATE)]
            try:
                detected, confidence, _all_probabilities = asr_model.model.detect_language(
                    audio=clip,
                    language_detection_threshold=0.0,
                )
                if detected and confidence >= _SEGMENT_LANGUAGE_CONFIDENCE:
                    language = detected
                else:
                    log_to_video(
                        video_id,
                        f"Sentence {index} language confidence {confidence:.2f} is low; using '{fallback_language}'.",
                    )
            except Exception as exc:
                log_to_video(
                    video_id, f"Sentence {index} language detection failed; using '{fallback_language}': {exc}"
                )

        segment_with_language = dict(segment)
        segment_with_language["language"] = language
        segment_with_language["language_confidence"] = round(float(confidence), 3)
        detected_segments.append(segment_with_language)
        counts[language] = counts.get(language, 0) + 1

    if counts:
        summary = ", ".join(f"{language}={count}" for language, count in sorted(counts.items()))
        log_to_video(video_id, f"Detected languages per sentence: {summary}.")
    return detected_segments


def _retranscription_language(segment: dict, primary_language: str) -> tuple[str, str | None]:
    """Choose a forced language without turning a detector outlier into new text.

    Whisper's full-pass transcript is produced with the primary language detected
    for the video.  A short Vietnamese sentence can occasionally receive a CJK
    language label during the later, per-sentence detector pass.  Re-running that
    Latin-script sentence with ``zh`` replaces otherwise usable Vietnamese text
    with a hallucinated Chinese phrase.  Prefer the primary language for that
    conflicting case, while retaining real CJK speech whose original transcript
    already uses a CJK script.
    """
    detected_language = str(segment.get("language") or primary_language).lower()
    normalized_primary = (primary_language or "en").lower()
    text_has_cjk = bool(_CJK_RE.search(str(segment.get("text") or "")))
    detected_is_cjk = detected_language in _CJK_LANGUAGE_CODES
    primary_is_cjk = normalized_primary in _CJK_LANGUAGE_CODES

    if detected_is_cjk and not primary_is_cjk and not text_has_cjk:
        return normalized_primary, (
            f"detector reported '{detected_language}' for a non-CJK transcript; "
            f"using primary language '{normalized_primary}'"
        )
    return detected_language, None


def _retranscribe_mixed_language_segments(asr_model, audio, segments, primary_language: str, video_id: str):
    """Correct switched-language text while preserving every original timestamp."""
    primary_language = (primary_language or "en").lower()
    corrected_segments = []

    for index, segment in enumerate(segments, start=1):
        language, correction_reason = _retranscription_language(segment, primary_language)
        confidence = float(segment.get("language_confidence", 0.0))
        start = max(0.0, float(segment.get("start", 0.0)))
        end = min(len(audio) / _AUDIO_SAMPLE_RATE, float(segment.get("end", start)))
        corrected_segment = dict(segment)
        if language == primary_language or confidence < _SEGMENT_LANGUAGE_CONFIDENCE or end <= start:
            if correction_reason:
                corrected_segment["language"] = language
                log_to_video(video_id, f"Sentence {index}: {correction_reason}.")
            corrected_segments.append(corrected_segment)
            continue

        try:
            if correction_reason:
                log_to_video(video_id, f"Sentence {index}: {correction_reason}.")
            log_to_video(video_id, f"Re-transcribing sentence {index} with language '{language}'.")
            clip = audio[int(start * _AUDIO_SAMPLE_RATE) : int(end * _AUDIO_SAMPLE_RATE)]
            local_result = asr_model.transcribe(clip, batch_size=1, language=language)
            corrected_text = ""
            for local_segment in local_result.get("segments", []):
                corrected_text = _merge_transcript_text(
                    corrected_text,
                    str(_value(local_segment, "text", "") or ""),
                )
            if corrected_text.strip():
                corrected_segment["text"] = corrected_text.strip()
            corrected_segment["language"] = language
        except Exception as exc:
            log_to_video(video_id, f"Could not re-transcribe sentence {index} in '{language}'; keeping its text: {exc}")
        corrected_segments.append(corrected_segment)

    return corrected_segments


def _language_for_aligned_segment(segment, source_segments, fallback_language: str) -> tuple[str, float]:
    """Carry language metadata to the aligned sentence with the greatest overlap."""
    start = float(segment.get("start", 0.0))
    end = float(segment.get("end", start))
    midpoint = (start + end) / 2
    best_source = None
    best_overlap = -1.0

    for source in source_segments:
        source_start = float(source.get("start", 0.0))
        source_end = float(source.get("end", source_start))
        overlap = max(0.0, min(end, source_end) - max(start, source_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_source = source
        elif overlap == best_overlap and best_source is not None:
            source_midpoint = (source_start + source_end) / 2
            best_midpoint = (float(best_source.get("start", 0.0)) + float(best_source.get("end", 0.0))) / 2
            if abs(midpoint - source_midpoint) < abs(midpoint - best_midpoint):
                best_source = source

    if not best_source:
        return fallback_language, 0.0
    return (
        best_source.get("language") or fallback_language,
        float(best_source.get("language_confidence", 0.0)),
    )


def _split_sentence_text(text: str) -> list[str]:
    """Split complete sentences without assuming that the language uses spaces."""
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return []

    sentences = []
    sentence_start = 0
    index = 0
    while index < len(normalized):
        character = normalized[index]
        if character not in _SENTENCE_END_CHARS:
            index += 1
            continue
        if (
            character == "."
            and index > 0
            and index + 1 < len(normalized)
            and normalized[index - 1].isdigit()
            and normalized[index + 1].isdigit()
        ):
            index += 1
            continue

        sentence_end = index + 1
        while sentence_end < len(normalized) and (
            normalized[sentence_end] in _SENTENCE_END_CHARS or normalized[sentence_end] in _SENTENCE_CLOSERS
        ):
            sentence_end += 1

        has_boundary = sentence_end >= len(normalized)
        if not has_boundary:
            has_boundary = normalized[sentence_end].isspace() or character in "\u2026\u3002\uff01\uff1f"
        if has_boundary:
            sentence = normalized[sentence_start:sentence_end].strip()
            if sentence:
                sentences.append(sentence)
            while sentence_end < len(normalized) and normalized[sentence_end].isspace():
                sentence_end += 1
            sentence_start = sentence_end
            index = sentence_end
            continue
        index += 1

    remainder = normalized[sentence_start:].strip()
    if remainder:
        sentences.append(remainder)
    return sentences


def _speech_weight(text: str) -> int:
    """Estimate spoken length consistently for spaced and unspaced languages."""
    return max(1, sum(character.isalnum() for character in str(text or "")))


def _coalesce_short_sentence_segments(segments: list[dict]) -> list[dict]:
    """Join unusably short contiguous speech fragments to a neighbour."""
    coalesced = []
    for source in segments:
        current = dict(source)
        duration = float(current.get("end", 0.0)) - float(current.get("start", 0.0))
        if duration < _MIN_SENTENCE_SPAN_SECONDS and coalesced:
            previous = coalesced[-1]
            gap = float(current.get("start", 0.0)) - float(previous.get("end", 0.0))
            if gap <= 0.15:
                previous["end"] = max(float(previous.get("end", 0.0)), float(current.get("end", 0.0)))
                previous["text"] = (
                    f"{str(previous.get('text') or '').rstrip()} {str(current.get('text') or '').lstrip()}"
                ).strip()
                previous.pop("words", None)
                continue
        coalesced.append(current)

    if len(coalesced) > 1:
        first = coalesced[0]
        first_duration = float(first.get("end", 0.0)) - float(first.get("start", 0.0))
        forward_gap = float(coalesced[1].get("start", 0.0)) - float(first.get("end", 0.0))
        if first_duration < _MIN_SENTENCE_SPAN_SECONDS and forward_gap <= 0.15:
            first = coalesced.pop(0)
            coalesced[0]["start"] = min(float(first.get("start", 0.0)), float(coalesced[0].get("start", 0.0)))
            coalesced[0]["text"] = (
                f"{str(first.get('text') or '').rstrip()} {str(coalesced[0].get('text') or '').lstrip()}"
            ).strip()
            coalesced[0].pop("words", None)
    return coalesced


def _split_segment_proportionally(segment: dict) -> list[dict]:
    """Keep Whisper's trusted span while deriving sentence-level fallback timing."""
    sentences = _split_sentence_text(segment.get("text", ""))
    if len(sentences) <= 1:
        return [dict(segment)]

    start = float(segment.get("start", 0.0))
    end = float(segment.get("end", start))
    duration = max(0.0, end - start)
    weights = [_speech_weight(sentence) for sentence in sentences]
    total_weight = sum(weights)
    elapsed_weight = 0
    fallback_segments = []
    for index, (sentence, weight) in enumerate(zip(sentences, weights)):
        sentence_start = start + duration * elapsed_weight / total_weight
        elapsed_weight += weight
        sentence_end = end if index == len(sentences) - 1 else start + duration * elapsed_weight / total_weight
        fallback_segment = dict(segment)
        fallback_segment.update(
            {
                "start": round(sentence_start, 3),
                "end": round(max(sentence_start + 0.001, sentence_end), 3),
                "text": sentence,
            }
        )
        fallback_segment.pop("words", None)
        fallback_segments.append(fallback_segment)
    # Punctuation-only sentence splitting can otherwise create impossible
    # 100ms voice slots from a perfectly valid multi-second Whisper span.
    return _coalesce_short_sentence_segments(fallback_segments)


def _alignment_groups(segments: list[dict]) -> list[list[dict]]:
    """Group consecutive same-language sentences for context-aware alignment."""
    groups = []
    current = []
    for segment in segments:
        if current:
            previous = current[-1]
            gap = float(segment.get("start", 0.0)) - float(previous.get("end", 0.0))
            group_span = float(segment.get("end", 0.0)) - float(current[0].get("start", 0.0))
            language_changed = str(segment.get("language") or "en") != str(current[0].get("language") or "en")
            if (
                language_changed
                or gap >= _ALIGNMENT_GROUP_SPLIT_GAP_SECONDS
                or group_span > _ALIGNMENT_GROUP_MAX_SECONDS
            ):
                groups.append(current)
                current = []
        current.append(segment)
    if current:
        groups.append(current)
    return groups


def _split_context_alignment(
    source_segments: list[dict],
    candidate_segments: list[dict],
    search_start: float,
    search_end: float,
) -> tuple[list[dict] | None, str]:
    """Split one context alignment back into its original ordered sentences."""
    expected_word_counts = [len(str(segment.get("text") or "").split()) for segment in source_segments]
    if not expected_word_counts or any(count <= 0 for count in expected_word_counts):
        return None, "source sentence has no alignable words"

    words = [
        word
        for candidate in candidate_segments
        for word in candidate.get("words", [])
        if word.get("start") is not None and word.get("end") is not None
    ]
    expected_total = sum(expected_word_counts)
    if len(words) != expected_total:
        return None, f"aligned word count {len(words)} does not match source count {expected_total}"

    previous_end = search_start
    scores = []
    for word in words:
        start = float(word["start"])
        end = float(word["end"])
        if start < search_start - 0.25 or end > search_end + 0.25:
            return None, "aligned words escaped the context search window"
        if end <= start or start < previous_end - 0.05:
            return None, "aligned words have invalid or overlapping timestamps"
        previous_end = end
        if word.get("score") is not None:
            scores.append(float(word["score"]))

    if scores:
        median_score = statistics.median(scores)
        if median_score < _ALIGNMENT_MIN_MEDIAN_WORD_SCORE:
            return None, (f"median word score {median_score:.3f} is below {_ALIGNMENT_MIN_MEDIAN_WORD_SCORE:.3f}")

    aligned = []
    offset = 0
    for source, count in zip(source_segments, expected_word_counts):
        sentence_words = words[offset : offset + count]
        offset += count
        sentence = dict(source)
        sentence.update(
            {
                "start": float(sentence_words[0]["start"]),
                "end": float(sentence_words[-1]["end"]),
                "words": sentence_words,
            }
        )
        aligned.append(sentence)
    return aligned, f"aligned {len(aligned)} sentences with {len(words)} timed words"


def _alignment_intrusion_detail(
    source_group: list[dict],
    aligned_group: list[dict],
    all_source_segments: list[dict],
) -> str | None:
    """Describe alignment that newly intrudes into another spoken sentence.

    Language-specific alignment runs against padded audio context.  A short
    phrase can therefore lock onto similar sounds inside a neighbouring
    sentence.  Only reject overlap introduced by alignment; overlap already
    present in Whisper's source spans is left for the final boundary validator.
    """
    if len(source_group) != len(aligned_group):
        return "aligned sentence count changed"

    group_ids = {id(segment) for segment in source_group}
    for source, aligned in zip(source_group, aligned_group):
        source_start = float(source.get("start", 0.0))
        source_end = float(source.get("end", source_start))
        aligned_start = float(aligned.get("start", source_start))
        aligned_end = float(aligned.get("end", aligned_start))
        for other in all_source_segments:
            if id(other) in group_ids:
                continue
            other_start = float(other.get("start", 0.0))
            other_end = float(other.get("end", other_start))
            source_overlap = max(0.0, min(source_end, other_end) - max(source_start, other_start))
            aligned_overlap = max(0.0, min(aligned_end, other_end) - max(aligned_start, other_start))
            if aligned_overlap > source_overlap + 0.05:
                return (
                    f"new {aligned_overlap:.3f}s overlap with another source sentence "
                    f"(previously {source_overlap:.3f}s)"
                )
    return None


def _alignment_quality(source_segment: dict, aligned_segments: list[dict]) -> tuple[bool, str]:
    """Reject aligners that return legal-looking but physically impossible timing."""
    if not aligned_segments:
        return False, "no aligned sentences"

    source_start = float(source_segment.get("start", 0.0))
    source_end = float(source_segment.get("end", source_start))
    source_duration = source_end - source_start
    aligned_start = min(float(segment.get("start", source_start)) for segment in aligned_segments)
    aligned_end = max(float(segment.get("end", aligned_start)) for segment in aligned_segments)
    aligned_duration = aligned_end - aligned_start
    if source_duration <= 0 or aligned_duration <= 0:
        return False, "non-positive duration"
    if aligned_start < source_start - 0.25 or aligned_end > source_end + 0.25:
        return False, "timestamps escaped the Whisper source span"

    coverage_ratio = aligned_duration / source_duration
    if coverage_ratio < _ALIGNMENT_MIN_COVERAGE_RATIO:
        return False, f"coverage {coverage_ratio:.2f} is below {_ALIGNMENT_MIN_COVERAGE_RATIO:.2f}"

    word_scores = [
        float(word["score"])
        for segment in aligned_segments
        for word in segment.get("words", [])
        if word.get("score") is not None
    ]
    if word_scores:
        median_score = statistics.median(word_scores)
        if median_score < _ALIGNMENT_MIN_MEDIAN_WORD_SCORE:
            return False, (f"median word score {median_score:.3f} is below {_ALIGNMENT_MIN_MEDIAN_WORD_SCORE:.3f}")
    return True, f"coverage={coverage_ratio:.2f}"


def _verify_whisperx_vad_asset() -> Path:
    """Reject a missing or modified bootstrap-installed VAD checkpoint."""
    try:
        return verify_whisperx_vad_model(Path(MODELS_DIR) / "whisperx-vad")
    except ModelIntegrityError as exc:
        raise RuntimeError(
            "WhisperX VAD is missing or corrupted. Return to the model setup screen and retry the download."
        ) from exc


class _SingleSentenceSplitter:
    """NLTK-compatible splitter for a source span already split by HaizFlow."""

    @staticmethod
    def span_tokenize(text: str):
        return [(0, len(text))] if text else []


def _align_without_nltk_download(*args, **kwargs):
    """Run WhisperX alignment without its mutable punkt_tab download path."""
    import whisperx.alignment as alignment_module

    with _ALIGNMENT_PATCH_LOCK:
        original_loader = alignment_module.nltk_load
        alignment_module.nltk_load = lambda _resource: _SingleSentenceSplitter()
        try:
            return whisperx.align(*args, **kwargs)
        finally:
            alignment_module.nltk_load = original_loader


def _verified_alignment_asset(language: str, video_id: str) -> tuple[object, dict]:
    """Load one fixed torchaudio asset after size/SHA-256 verification."""
    bundle_name, _filename, _expected_size, _expected_sha256 = _VERIFIED_ALIGNMENT_MODELS[language]
    cache_directory = Path(MODELS_DIR) / "alignment"
    try:
        verify_alignment_model(cache_directory, language)
    except ModelIntegrityError as exc:
        raise RuntimeError(
            f"The '{language}' alignment model is missing or corrupted. "
            "Return to the model setup screen and retry the download."
        ) from exc
    check_cancellation(video_id)
    # Verify immediately before the pickle-compatible official state
    # dictionary is loaded. weights_only further narrows the deserializer.
    bundle = getattr(torchaudio.pipelines, bundle_name)
    align_model = bundle.get_model(
        dl_kwargs={
            "model_dir": str(cache_directory),
            "weights_only": True,
        }
    )
    labels = bundle.get_labels()
    return align_model, {
        "language": language,
        "dictionary": {character.lower(): index for index, character in enumerate(labels)},
        "type": "torchaudio",
    }


def _align_segments_by_language(audio, segments, device: str, video_id: str, progress_callback=None):
    """Align ordered sentence groups with enough context to correct ASR drift."""
    sentence_segments = _coalesce_short_sentence_segments(
        [sentence for source_segment in segments for sentence in _split_segment_proportionally(source_segment)]
    )
    context_groups = _alignment_groups(sentence_segments)
    grouped_segments = {}
    ordered_languages = []
    for group in context_groups:
        language = group[0].get("language") or "en"
        if language not in grouped_segments:
            grouped_segments[language] = []
            ordered_languages.append(language)
        grouped_segments[language].append(group)

    aligned_segments = []
    for language in ordered_languages:
        check_cancellation(video_id)
        language_groups = grouped_segments[language]
        if language not in _VERIFIED_ALIGNMENT_MODELS:
            log_to_video(
                video_id,
                f"WARNING: No checksum-pinned alignment model is supported for '{language}'. "
                "Preserving Whisper spans with proportional sentence boundaries.",
            )
            for group in language_groups:
                aligned_segments.extend(group)
            continue
        align_model = None
        try:
            log_to_video(video_id, f"Loading alignment model for language '{language}'.")
            if progress_callback:
                progress_callback("loading_alignment", f"Loading subtitle alignment for {language}")
            align_model, metadata = _verified_alignment_asset(language, video_id)
            align_model = align_model.to(device)
            if progress_callback:
                progress_callback("aligning", f"Aligning {language} subtitles")
            source_index = 0
            audio_duration = len(audio) / _AUDIO_SAMPLE_RATE
            for group in language_groups:
                check_cancellation(video_id)
                group_start_index = source_index + 1
                source_index += len(group)
                group_end_index = source_index
                search_start = max(
                    0.0,
                    float(group[0].get("start", 0.0)) - _ALIGNMENT_GROUP_PADDING_SECONDS,
                )
                search_end = min(
                    audio_duration,
                    float(group[-1].get("end", 0.0)) + _ALIGNMENT_GROUP_PADDING_SECONDS,
                )
                context_segment = {
                    **group[0],
                    "start": search_start,
                    "end": search_end,
                    "text": " ".join(str(segment.get("text") or "").strip() for segment in group),
                }
                try:
                    aligned_result = _align_without_nltk_download(
                        [context_segment],
                        align_model,
                        metadata,
                        audio,
                        device,
                        return_char_alignments=False,
                    )
                    candidate_segments = aligned_result.get("segments", [])
                    context_aligned, quality_detail = _split_context_alignment(
                        group,
                        candidate_segments,
                        search_start,
                        search_end,
                    )
                    intrusion_detail = (
                        _alignment_intrusion_detail(
                            group,
                            context_aligned,
                            sentence_segments,
                        )
                        if context_aligned
                        else None
                    )
                    if context_aligned and not intrusion_detail:
                        aligned_segments.extend(context_aligned)
                        log_to_video(
                            video_id,
                            f"Aligned '{language}' source sentences {group_start_index}-{group_end_index} "
                            f"with surrounding speech context ({quality_detail}).",
                        )
                        continue
                    if intrusion_detail:
                        quality_detail = intrusion_detail
                    log_to_video(
                        video_id,
                        f"WARNING: Rejected '{language}' context alignment for source sentences "
                        f"{group_start_index}-{group_end_index} "
                        f"({quality_detail}). Preserving Whisper timing with proportional sentence boundaries.",
                    )
                except Exception as exc:
                    if is_cancelled(video_id):
                        raise
                    log_to_video(
                        video_id,
                        f"WARNING: Context alignment failed for '{language}' source sentences "
                        f"{group_start_index}-{group_end_index}. "
                        f"Preserving Whisper timing: {exc}",
                    )
                aligned_segments.extend(group)
        except Exception as exc:
            if is_cancelled(video_id):
                raise
            log_to_video(
                video_id,
                f"WARNING: Alignment model failed or is unsupported for '{language}'. "
                f"Preserving Whisper spans with proportional sentence boundaries: {exc}",
            )
            for group in language_groups:
                aligned_segments.extend(group)
        finally:
            if align_model is not None:
                del align_model
            _release_cuda(video_id, f"{language} alignment")

    aligned_segments.sort(key=lambda segment: float(segment.get("start", 0.0)))
    return aligned_segments


def _normalize_sentence_timestamps(segments: list[dict], audio_duration: float) -> int:
    """Make independently aligned sentence spans safe for one sequential timeline.

    WhisperX can align a short foreign-language sentence against surrounding
    context.  That improves the word timing, but its independently aligned span
    may overlap the preceding primary-language span.  Two spoken sentences
    cannot be rendered concurrently by the downstream TTS/subtitle pipeline, so
    split just the ambiguous overlap at its midpoint rather than aborting an
    otherwise valid transcription.

    The function mutates ``segments`` in place and returns the number of joined
    boundaries.  Invalid spans remain the responsibility of the validator below.
    """
    if len(segments) < 2:
        return 0

    minimum_duration = 0.25
    repaired_boundaries = 0
    for previous, current in zip(segments, segments[1:]):
        previous_start = float(previous.get("start", 0.0))
        previous_end = float(previous.get("end", previous_start))
        current_start = float(current.get("start", 0.0))
        current_end = float(current.get("end", current_start))
        overlap = previous_end - current_start
        if overlap <= 0.05:
            continue

        # Keep a short, usable duration for both sentences whenever their
        # source timings make that possible.  The midpoint only affects the
        # region where two independently derived timings disagree.
        previous_minimum = min(minimum_duration, max(0.001, (previous_end - previous_start) / 2.0))
        current_minimum = min(minimum_duration, max(0.001, (current_end - current_start) / 2.0))
        lower_bound = previous_start + previous_minimum
        upper_bound = min(current_end - current_minimum, audio_duration)
        if lower_bound > upper_bound:
            # Leave genuinely malformed spans for _validate_timestamp_invariants
            # so the error remains explicit instead of silently discarding text.
            continue
        boundary = min(max((previous_end + current_start) / 2.0, lower_bound), upper_bound)
        previous["end"] = round(boundary, 3)
        current["start"] = round(boundary, 3)
        repaired_boundaries += 1
    return repaired_boundaries


def _validate_timestamp_invariants(segments: list[dict], audio_duration: float) -> None:
    """Reject timestamp corruption before translation, subtitles or TTS can use it."""
    if not segments:
        raise RuntimeError("WhisperX found no speech segments. The video cannot be dubbed without spoken content.")
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


def transcribe(
    audio_path: str,
    output_json_path: str,
    source_language: str,
    video_id: str,
    progress_callback=None,
    *,
    model_name: str = "small",
):
    """Transcribe through WhisperX and align sentence timestamps per language."""
    global _WARM_ASR_MODEL, _WARM_DEVICE, _WARM_MODEL_NAME
    model_name = str(model_name or "small").strip().lower()
    log_to_video(video_id, f"Initializing WhisperX with model '{model_name}'.")
    profile = runtime_profile()
    device = "cuda" if profile.cuda_available else "cpu"
    if model_name == "large-v3-turbo" and device != "cuda":
        raise RuntimeError(
            "Whisper large-v3-turbo requires an available NVIDIA GPU. "
            "Choose WhisperX small for CPU or low-VRAM processing."
        )
    compute_type = "float16" if device == "cuda" else "int8"
    log_to_video(
        video_id,
        f"WhisperX device: {device}, compute type: {compute_type}, "
        f"batch size: {profile.whisper_batch_size}, threads: {profile.cpu_threads}.",
    )

    asr_model = None
    using_warm_model = False
    audio = None
    try:
        log_to_video(video_id, "Loading WhisperX transcription model.")
        if progress_callback:
            progress_callback("loading_model", "Loading WhisperX speech model")
        with _MODEL_LOCK:
            if _WARM_ASR_MODEL is not None and _WARM_DEVICE == device and _WARM_MODEL_NAME == model_name:
                asr_model = _WARM_ASR_MODEL
                using_warm_model = True
                log_to_video(video_id, "Reusing warmed WhisperX speech model.")
            else:
                # Startup warms the lightweight model so the common path is
                # responsive.  A project can subsequently select turbo.  Do
                # not keep both models resident: on an 8 GB GPU that can make
                # the turbo load fail even though turbo fits on its own.
                if _WARM_ASR_MODEL is not None:
                    del _WARM_ASR_MODEL
                    _WARM_ASR_MODEL = None
                    _WARM_DEVICE = None
                    _WARM_MODEL_NAME = None
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    log_to_video(
                        video_id,
                        "Released the warmed WhisperX model before switching ASR models.",
                    )
                asr_model = _load_whisper_model(device, compute_type, profile.cpu_threads, model_name)
        audio = whisperx.load_audio(audio_path)
        if source_language != "auto":
            log_to_video(video_id, f"Ignoring legacy source language '{source_language}'; using automatic detection.")

        log_to_video(video_id, "Running WhisperX batched transcription with automatic language detection.")
        if progress_callback:
            progress_callback("transcribing", "Transcribing speech")
        result = asr_model.transcribe(
            audio,
            batch_size=profile.whisper_batch_size,
            language=None,
        )
        detected_language = result.get("language")
        initial_segments = [
            {
                **segment,
                "language": detected_language or "en",
                "language_confidence": 1.0,
            }
            for segment in result.get("segments", [])
            if segment.get("text", "").strip()
        ]
        if not initial_segments:
            raise RuntimeError("WhisperX did not return any speech segments.")
        log_to_video(video_id, f"Transcription completed. Primary detected language: '{detected_language}'.")
        if progress_callback:
            progress_callback("transcribed", f"Detected {detected_language or 'unknown'} speech")

        sentence_segments = _align_segments_by_language(
            audio,
            initial_segments,
            device,
            video_id,
            progress_callback=progress_callback,
        )
        if progress_callback:
            progress_callback("segmenting", f"Prepared {len(sentence_segments)} complete sentences")

        source_segments = _detect_segment_languages(
            asr_model,
            audio,
            sentence_segments,
            detected_language or "en",
            video_id,
        )
        source_segments = _retranscribe_mixed_language_segments(
            asr_model,
            audio,
            source_segments,
            detected_language or "en",
            video_id,
        )
        has_language_switch = any(
            (segment.get("language") or detected_language or "en") != (detected_language or "en")
            for segment in source_segments
        )
        if has_language_switch:
            aligned_segments = _align_segments_by_language(
                audio,
                source_segments,
                device,
                video_id,
                progress_callback=None,
            )
        else:
            aligned_segments = source_segments
            log_to_video(video_id, "Keeping validated sentence timestamps; no language-switch realignment is needed.")

        output_segments = []
        for segment in aligned_segments:
            # Both proportional fallback and context alignment preserve the
            # originating sentence dictionary.  Keep its language metadata;
            # inferring it again from a corrected timestamp can assign a
            # neighbouring sentence's language after a legitimate time shift.
            language = segment.get("language") or detected_language or "en"
            confidence = float(segment.get("language_confidence", 0.0))
            output_segments.append(
                {
                    "start": round(float(segment["start"]), 3),
                    "end": round(float(segment["end"]), 3),
                    "text": segment["text"].strip(),
                    "language": language,
                    "language_confidence": round(confidence, 3),
                    "timing_source": TIMING_SOURCE,
                }
            )

        audio_duration = len(audio) / _AUDIO_SAMPLE_RATE
        repaired_boundaries = _normalize_sentence_timestamps(output_segments, audio_duration)
        if repaired_boundaries:
            log_to_video(
                video_id,
                "Normalized "
                f"{repaired_boundaries} overlapping WhisperX sentence boundary/boundaries "
                "after mixed-language alignment.",
            )
        _validate_timestamp_invariants(output_segments, audio_duration)
        if progress_callback:
            progress_callback("detecting_languages", f"Validated {len(output_segments)} timed sentences")
        output_directory = os.path.dirname(os.path.abspath(output_json_path))
        os.makedirs(output_directory, exist_ok=True)
        handle, temporary_path = tempfile.mkstemp(
            prefix=".transcript-",
            suffix=".json.tmp",
            dir=output_directory,
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(output_segments, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, output_json_path)
        except Exception:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
            raise

        log_to_video(video_id, f"Saved {len(output_segments)} timestamp-locked source sentences to: {output_json_path}")
        if progress_callback:
            progress_callback("saved", f"Prepared {len(output_segments)} timestamp-locked sentences")
        return output_segments, detected_language
    finally:
        if asr_model is not None and not using_warm_model:
            del asr_model
        if audio is not None:
            del audio
        _release_cuda(video_id, "WhisperX cleanup")
