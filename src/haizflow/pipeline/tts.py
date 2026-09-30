"""Local OmniVoice synthesis shared by automatic and manual workflows."""

import json
import os
import re
import unicodedata

from haizflow.services.video_store import get_video, log_to_video


def resolve_tts_provider(provider: str, target_language: str) -> str:
    """Read retired provider values without calling an online TTS service."""
    normalized = str(provider or "omnivoice").strip().lower()
    if normalized in {"omnivoice", "omnivoice-gpu", "auto", "vieneu", "edge"}:
        return "omnivoice"
    raise ValueError(f"Unsupported TTS provider: {provider}")


def normalize_voice(voice: str) -> str:
    """Map an old Edge voice to a local preset when opening an older project."""
    selected = str(voice or "").strip()
    if selected.startswith("omnivoice:"):
        return selected
    if selected in {"vi-VN-NamMinhNeural", "en-US-GuyNeural", "zh-CN-YunxiNeural"}:
        return "omnivoice:male"
    return "omnivoice:female"


def preprocess_text_for_tts(text: str) -> str:
    """Normalize invisible and punctuation characters without changing words."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).translate(
        str.maketrans({
            "\u00a0": " ", "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "",
            "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
            "\u2013": ",", "\u2014": ",", "\u2026": "...",
        })
    )
    text = " ".join(text.split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if text and text[-1] not in ".!?,;:。！？；：":
        text += "."
    return text


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _is_valid_mp3(path: str) -> bool:
    """Reject zero-byte and partial synthesis results before timeline assembly."""
    try:
        if os.path.getsize(path) < 512:
            return False
        with open(path, "rb") as file:
            header = file.read(3)
    except OSError:
        return False
    if header == b"ID3":
        return True
    return len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0


def generate_voice_parts(
    segments_json_path: str,
    voice_parts_dir: str,
    voice: str,
    video_id: str,
    progress_callback=None,
    *,
    provider: str = "omnivoice",
    target_language: str = "vi",
    process_registry_id: str | None = None,
    keep_worker_warm: bool = False,
    segment_indices: list[int] | None = None,
    narrator_anchor_text: str = "",
    status_callback=None,
):
    backend = resolve_tts_provider(provider, target_language)
    voice = normalize_voice(voice)
    from haizflow.pipeline.omnivoice_tts import synthesize_batch_to_mp3
    device = "gpu" if provider.endswith("-gpu") else "cpu"

    with open(segments_json_path, "r", encoding="utf-8") as file:
        segments = json.load(file)
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("Voice generation requires at least one translated subtitle segment.")
    requested_indices = (
        list(range(1, len(segments) + 1))
        if segment_indices is None
        else list(dict.fromkeys(segment_indices))
    )
    if any(index < 1 or index > len(segments) for index in requested_indices):
        raise ValueError("TTS segment index is outside the subtitle document.")
    requested_segments = [(index, segments[index - 1]) for index in requested_indices]
    if not requested_segments:
        return
    total = len(requested_segments)
    document_total = len(segments)
    log_to_video(
        video_id,
        f"[TTS][SESSION_START] provider={backend} backend=local device={device} voice={voice}",
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
        source_segments_path = str(current_files.get("source_segments") or "")
        if not source_segments_path and video_root:
            source_segments_path = os.path.join(video_root, "temp", "source_segments.json")
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
        not clone_reference or not os.path.isfile(clone_reference)
    ):
        raise RuntimeError("OmniVoice voice cloning requires an authorised reference sample.")

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

    for index, segment in requested_segments:
        text = str((segment or {}).get("text") or "").strip() if isinstance(segment, dict) else ""
        if not text:
            raise RuntimeError(f"Translated subtitle segment {index} is missing text.")
        part_path = os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3")
        if not _is_valid_mp3(part_path):
            _remove_file(part_path)
            log_to_video(
                video_id,
                f"[TTS][QUEUED] provider={backend} segment={index}/{document_total} voice={voice}",
            )
            source_reference = source_reference_for(segment)
            pending.append({
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
            })
    completed_before_worker = total - len(pending)
    if progress_callback and completed_before_worker:
        progress_callback(completed_before_worker, total)
    if pending:
        def report_omnivoice_progress(completed, _pending_total, stage):
            verified = min(completed_before_worker + completed, total)
            if status_callback is not None:
                status_callback(stage, verified, total)
            elif progress_callback is not None:
                progress_callback(verified, total)

        worker_options = {"device": device}
        if process_registry_id:
            worker_options["process_registry_id"] = process_registry_id
        if keep_worker_warm:
            worker_options["keep_worker_warm"] = True
        if narrator_anchor_text:
            worker_options["narrator_anchor_text"] = narrator_anchor_text
        synthesize_batch_to_mp3(
            pending,
            video_id,
            language_id=target_language,
            speaker_mode=speaker_mode,
            progress_callback=report_omnivoice_progress,
            **worker_options,
        )
    for index, _segment in requested_segments:
        part_path = os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3")
        if not _is_valid_mp3(part_path):
            raise RuntimeError(f"{backend} produced invalid audio for subtitle segment {index}.")
    if progress_callback:
        progress_callback(total, total)
    log_to_video(video_id, f"{backend} generated and verified every voice segment locally.")


def generate_single_voice(
    text: str,
    output_path: str,
    voice: str,
    video_id: str,
    *,
    provider: str = "omnivoice",
    target_language: str = "vi",
):
    """Create and verify a complete local narration file."""
    resolve_tts_provider(provider, target_language)
    device = "gpu" if provider.endswith("-gpu") else "cpu"
    voice = normalize_voice(voice)
    from haizflow.pipeline.omnivoice_tts import synthesize_to_mp3

    current_video = get_video(video_id)
    current_files = dict((current_video.files if current_video else {}) or {})
    reference_path = str(current_files.get("voice_reference") or "")
    reference_text = str(current_files.get("voice_reference_transcript") or "")
    if voice == "omnivoice:clone" and (not reference_path or not os.path.isfile(reference_path)):
        raise RuntimeError("OmniVoice voice cloning requires an authorised reference sample.")
    synthesize_to_mp3(
        preprocess_text_for_tts(text),
        voice,
        output_path,
        video_id,
        language_id=target_language,
        device=device,
        reference_path=reference_path if voice == "omnivoice:clone" else "",
        reference_text=reference_text if voice == "omnivoice:clone" else "",
    )
    if not _is_valid_mp3(output_path):
        raise RuntimeError("OmniVoice produced invalid narration audio.")
    log_to_video(video_id, f"Successfully created narration file: {output_path}")
