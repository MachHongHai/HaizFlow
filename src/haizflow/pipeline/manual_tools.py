"""Independent Manual-project tools backed by immutable artifact caches."""

from __future__ import annotations

import json
import os
import shutil
import traceback
from pathlib import Path
from typing import Any

from haizflow.config import HYMT2_MODEL_REVISION
from haizflow.core.model_integrity import DEMUCS_MODEL_SIGNATURE
from haizflow.pipeline.timing_contract import TIMING_SOURCE
from haizflow.services import editor_documents, manual_artifacts, video_store

# Cache-contract versions are intentionally available without importing the
# model runtimes that implement them. Importing WhisperX/torch from a QML
# property getter used to stall the first Manual workspace paint for 20+ s.
DETECTOR_CACHE_VERSION = 21
# v1 clips may have been generated before OmniVoice used a stable narrator
# anchor. Mixing those clips with newly synthesized sentences changes timbre
# even when every segment declares the same voice ID.
VOICE_CLIP_CACHE_VERSION = "manual-tts-clip-v2-stable-narrator"
VOICE_MANIFEST_CACHE_VERSION = "manual-tts-manifest-v2-stable-narrator"


# Keep these names patchable for unit tests while loading every heavyweight
# backend only inside the worker that explicitly runs the corresponding tool.
def separate_audio(*args, **kwargs):
    from haizflow.pipeline.audio_separation import separate_audio as implementation

    return implementation(*args, **kwargs)


def build_audio_timeline(*args, **kwargs):
    from haizflow.pipeline.audio_timeline import build_audio_timeline as implementation

    return implementation(*args, **kwargs)


def extract_audio(*args, **kwargs):
    from haizflow.pipeline.extract_audio import extract_audio as implementation

    return implementation(*args, **kwargs)


def render_video(*args, **kwargs):
    from haizflow.pipeline.render import render_video as implementation

    return implementation(*args, **kwargs)


def generate_srt(*args, **kwargs):
    from haizflow.pipeline.subtitle import generate_srt as implementation

    return implementation(*args, **kwargs)


def detect_original_subtitle_region(*args, **kwargs):
    from haizflow.services.external_tasks import run_external_task

    video_path, temp_dir, video_id = args[:3]
    callback = kwargs.get("progress_callback")
    result = run_external_task(
        "ocr",
        "subtitle_ocr",
        {"video_path": video_path, "temp_dir": temp_dir, "video_id": video_id},
        str(video_id),
        progress_callback=(
            (lambda status: callback(int(status.get("current", 0)), int(status.get("total", 0))))
            if callback is not None
            else None
        ),
    )
    if result is not None:
        return result.get("region")
    from haizflow.pipeline.subtitle_ocr import detect_original_subtitle_region as implementation

    return implementation(*args, **kwargs)


def transcribe(*args, **kwargs):
    from haizflow.core.hardware import processing_device_preference
    from haizflow.services.external_tasks import run_external_task

    audio_path, output_json_path, source_language, video_id = args[:4]
    callback = kwargs.get("progress_callback")
    model_name = str(kwargs.get("model_name") or "small")
    result = run_external_task(
        "recognition",
        "transcribe",
        {
            "audio_path": audio_path,
            "output_json_path": output_json_path,
            "source_language": source_language,
            "video_id": video_id,
            "model_name": model_name,
        },
        str(video_id),
        context={"device": processing_device_preference(), "model": model_name},
        progress_callback=(
            (lambda status: callback(str(status.get("stage") or "processing"), str(status.get("detail") or "")))
            if callback is not None
            else None
        ),
    )
    if result is not None:
        return list(result.get("segments") or []), str(result.get("detected_language") or "")
    from haizflow.pipeline.transcribe import transcribe as implementation

    return implementation(*args, **kwargs)


def _release_recognition_runtime() -> None:
    """Release ASR through its engine; source AI imports remain a fallback."""

    from haizflow.services.external_engine import shared_external_engine_pool

    if "recognition" in shared_external_engine_pool().release({"recognition"}):
        return
    try:
        from haizflow.pipeline.transcribe import release_warm_whisperx_model
    except (ImportError, ModuleNotFoundError):
        return
    release_warm_whisperx_model()


def preprocess_text_for_tts(*args, **kwargs):
    from haizflow.pipeline.tts import preprocess_text_for_tts as implementation

    return implementation(*args, **kwargs)


def resolve_tts_provider(*args, **kwargs):
    from haizflow.pipeline.tts import resolve_tts_provider as implementation

    return implementation(*args, **kwargs)


def generate_voice_parts(*args, **kwargs):
    from haizflow.pipeline.tts import generate_voice_parts as implementation

    return implementation(*args, **kwargs)


def _is_valid_mp3(*args, **kwargs):
    from haizflow.pipeline.tts import _is_valid_mp3 as implementation

    return implementation(*args, **kwargs)


def shutdown_hymt2_worker(*args, **kwargs):
    from haizflow.services.translation import shutdown_hymt2_worker as implementation

    return implementation(*args, **kwargs)


def translate_segments(*args, **kwargs):
    from haizflow.services.translation import translate_segments as implementation

    return implementation(*args, **kwargs)


def start_video(*args, **kwargs):
    from haizflow.pipeline.process_registry import start_video as implementation

    return implementation(*args, **kwargs)


def clean_video(*args, **kwargs):
    from haizflow.pipeline.process_registry import clean_video as implementation

    return implementation(*args, **kwargs)


def is_cancelled(*args, **kwargs):
    from haizflow.pipeline.process_registry import is_cancelled as implementation

    return implementation(*args, **kwargs)


def is_paused(*args, **kwargs):
    from haizflow.pipeline.process_registry import is_paused as implementation

    return implementation(*args, **kwargs)

MANUAL_TOOL_IDS = ("source", "translation", "subtitle", "image", "voice", "audio", "export")
_TOOL_PROGRESS = {
    "source": 100,
    "separation": 100,
    "recognition": 100,
    "translation": 100,
    "subtitle": 100,
    "image": 100,
    "voice": 100,
    "audio": 100,
    "export": 100,
}


def _style_dict(video) -> dict[str, Any]:
    style = getattr(video, "subtitle_style", None)
    if hasattr(style, "model_dump"):
        return style.model_dump()
    if hasattr(style, "dict"):
        return style.dict()
    return dict(style or {})


def _crop_dict(video) -> dict[str, Any]:
    crop = getattr(video, "crop", None)
    if hasattr(crop, "model_dump"):
        return crop.model_dump()
    if hasattr(crop, "dict"):
        return crop.dict()
    return dict(crop or {})


def _video_input(video) -> str:
    path = str((video.files or {}).get("video_input") or "")
    if not path or manual_artifacts.file_state(path) is None:
        raise FileNotFoundError("Không tìm thấy video nguồn của project.")
    return str(Path(path).resolve())


def _active_signature(video, kind: str) -> str:
    return str((getattr(video, "active_artifacts", {}) or {}).get(kind) or "")


def _tool_generation(video, kind: str) -> int:
    return int((getattr(video, "manual_tool_generations", {}) or {}).get(kind, 0) or 0)


def _generation_token(video, kind: str) -> tuple:
    generation = _tool_generation(video, kind)
    return ("manual-rerun", generation) if generation > 0 else ()


def _record_exists(video, kind: str, artifact_signature: str, *, validate: bool = True) -> bool:
    if not artifact_signature:
        return False
    # Tool state must never advertise a corrupt or partial directory as a
    # cache hit.  Validation is memoized by file identity in the artifact
    # service, so repeated QML state reads do not re-hash large media.
    resolver = manual_artifacts.resolve if validate else manual_artifacts.peek
    return resolver(video.video_id, kind, artifact_signature) is not None


def source_signature(video) -> str:
    return manual_artifacts.signature(
        manual_artifacts.file_state(_video_input(video)),
        *_generation_token(video, "source"),
        "source-audio-pcm-v1",
    )


def separation_signature(video) -> str:
    return manual_artifacts.signature(
        source_signature(video), DEMUCS_MODEL_SIGNATURE,
        *_generation_token(video, "separation"), "two-stems-vocals-v1",
    )


def recognition_signature(video) -> str:
    input_signature = separation_signature(video) if video.enable_audio_separation else source_signature(video)
    return manual_artifacts.signature(
        input_signature,
        getattr(video, "speech_recognition_model", "small"),
        getattr(video, "source_language", "auto"),
        TIMING_SOURCE,
        *_generation_token(video, "recognition"),
        "manual-recognition-v1",
    )


def translation_signature(video) -> str:
    return manual_artifacts.signature(
        recognition_signature(video),
        getattr(video, "target_language", "vi"),
        "hymt2",
        HYMT2_MODEL_REVISION,
        "hymt2-semantic-source-context-retry-v21",
        *_generation_token(video, "translation"),
        "manual-translation-v1",
    )


def ocr_signature(video) -> str:
    return manual_artifacts.signature(
        manual_artifacts.file_state(_video_input(video)),
        DETECTOR_CACHE_VERSION,
        *_generation_token(video, "image"),
        "manual-ocr-region-v1",
    )


def _current_subtitle_record(video, *, validate: bool = True) -> dict[str, Any] | None:
    # The subtitle document is an independently editable Manual artifact.  It
    # remains the source of truth for preview/TTS even when the recognition or
    # translation settings later change.  Requiring it to keep matching the
    # current translation branch made visible, autosaved subtitles appear
    # "missing" to the Voice tool.
    active_resolver = manual_artifacts.active if validate else manual_artifacts.peek_active
    record_resolver = manual_artifacts.resolve if validate else manual_artifacts.peek
    active = active_resolver(video, "subtitle_document")
    if active and str((active.get("resolved_outputs") or {}).get("segments") or ""):
        return active
    expected_translation = translation_signature(video)
    translation = record_resolver(video.video_id, "translation", expected_translation)
    if not translation or _active_signature(video, "translation") != expected_translation:
        return None
    return translation


def _current_subtitle_path(video, *, validate: bool = True) -> str:
    record = _current_subtitle_record(video, validate=validate)
    if not record:
        return ""
    outputs = record.get("resolved_outputs") or {}
    return str(outputs.get("segments") or outputs.get("transcript") or "")


def _load_segments(video, *, validate: bool = True) -> list[dict[str, Any]]:
    path = _current_subtitle_path(video, validate=validate)
    if not path:
        return []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _subtitle_content_signature(path: str) -> str:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Tài liệu phụ đề không hợp lệ.") from exc
    return manual_artifacts.signature(payload, "manual-subtitle-document-v1")


def _subtitle_document_signature(video, path: str) -> str:
    return manual_artifacts.signature(
        _subtitle_content_signature(path),
        _active_signature(video, "translation"),
        "manual-subtitle-document-v2",
    )


def _voice_clip_signatures(video, segments: list[dict[str, Any]]) -> list[str]:
    language = str(getattr(video, "target_language", "vi") or "vi")
    speaker_mode = str(getattr(video, "speaker_mode", "single") or "single")
    files = dict(getattr(video, "files", {}) or {})
    overrides = dict(files.get("manual_voice_overrides") or {})
    reference = manual_artifacts.file_state(files.get("voice_reference"))
    reference_text = str(files.get("voice_reference_transcript") or "")
    recognition = recognition_signature(video) if speaker_mode == "multiple" else ""
    signatures = []
    for index, segment in enumerate(segments):
        segment_id = str(segment.get("segment_id") or "")
        override = overrides.get(segment_id) if segment_id else None
        override = override if isinstance(override, dict) else {}
        provider = str(
            override.get("provider")
            or getattr(video, "tts_provider", "omnivoice")
            or "omnivoice"
        )
        voice = str(override.get("voice") or getattr(video, "tts_voice", "") or "")
        signatures.append(
            manual_artifacts.signature(
                preprocess_text_for_tts(str(segment.get("text") or "")),
                provider,
                resolve_tts_provider(provider, language),
                language,
                voice,
                speaker_mode,
                reference,
                reference_text,
                recognition,
                index if speaker_mode == "multiple" else 0,
                *_generation_token(video, "voice"),
                VOICE_CLIP_CACHE_VERSION,
            )
        )
    return signatures


def _voice_generation_groups(video, segments: list[dict[str, Any]]) -> dict[tuple[str, str], list[int]]:
    """Group one-based segment indices by their requested TTS configuration."""
    files = dict(getattr(video, "files", {}) or {})
    overrides = dict(files.get("manual_voice_overrides") or {})
    groups: dict[tuple[str, str], list[int]] = {}
    for index, segment in enumerate(segments, 1):
        segment_id = str(segment.get("segment_id") or "")
        override = overrides.get(segment_id) if segment_id else None
        override = override if isinstance(override, dict) else {}
        provider = str(
            override.get("provider")
            or getattr(video, "tts_provider", "omnivoice")
            or "omnivoice"
        )
        voice = str(override.get("voice") or getattr(video, "tts_voice", "") or "")
        groups.setdefault((provider, voice), []).append(index)
    return groups


def ensure_narrator_anchor(video_id: str) -> str:
    """Persist the single-speaker identity used by existing and future clips."""
    video = video_store.get_video(video_id)
    if not video:
        return ""
    provider = resolve_tts_provider(video.tts_provider, video.target_language)
    if (
        provider != "omnivoice"
        or str(getattr(video, "speaker_mode", "single") or "single") != "single"
        or str(getattr(video, "tts_voice", "") or "") == "omnivoice:clone"
    ):
        return ""
    config = manual_artifacts.signature(
        provider,
        video.tts_voice,
        video.target_language,
        "manual-narrator-anchor-v1",
    )
    files = dict(video.files or {})
    anchors = dict(files.get("tts_narrator_anchors") or {})
    existing = str(anchors.get(config) or "")
    if not existing and str(files.get("tts_narrator_anchor_config") or "") == config:
        # Adopt the single legacy slot into the per-voice map. A project may
        # switch A -> B -> A and each preset must recover its original voice
        # identity together with its cached clips.
        existing = str(files.get("tts_narrator_anchor_text") or "")
    if existing:
        if anchors.get(config) != existing:
            anchors[config] = existing
            _update_files(video_id, tts_narrator_anchors=anchors)
        return existing
    segments = _load_segments(video, validate=False)
    if not segments:
        return ""
    from haizflow.pipeline.omnivoice_tts import _select_voice_anchor, _voice_anchor_excerpt

    candidate = _select_voice_anchor(segments)
    anchor = _voice_anchor_excerpt(str((candidate or {}).get("text") or ""))
    if not anchor:
        return ""
    anchors[config] = anchor
    _update_files(
        video_id,
        tts_narrator_anchor_text=anchor,
        tts_narrator_anchor_config=config,
        tts_narrator_anchors=anchors,
    )
    return anchor


def voice_signature(video, *, validate: bool = True) -> str:
    clips = _voice_clip_signatures(video, _load_segments(video, validate=validate))
    return manual_artifacts.signature(clips, VOICE_MANIFEST_CACHE_VERSION) if clips else ""


def _record_segments(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    path = str(((record or {}).get("resolved_outputs") or {}).get("segments") or "")
    if not path:
        return []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def published_voice_record(video, *, validate: bool = False) -> dict[str, Any] | None:
    """Return the last atomically published voice variant, even if partly stale.

    Preview uses this record to keep unchanged sentences audible while an
    edited sentence is being regenerated.  Render/mix readiness must continue
    to use :func:`active_voice_record`, which applies the stricter document
    compatibility check below.
    """
    signature = _active_signature(video, "tts_manifest")
    if not signature:
        return None
    resolver = manual_artifacts.resolve if validate else manual_artifacts.peek
    return resolver(video.video_id, "tts_manifest", signature)


def published_voice_source_segments(
    video,
    record: dict[str, Any] | None = None,
    *,
    validate: bool = False,
) -> list[dict[str, Any]]:
    """Load the subtitle revision used to create a published voice manifest."""
    voice = record or published_voice_record(video, validate=validate)
    source_signature_value = next(
        (
            str(value).split(":", 1)[1]
            for value in (voice or {}).get("inputs", [])
            if str(value).startswith("subtitle_document:")
        ),
        "",
    )
    if not source_signature_value:
        return []
    resolver = manual_artifacts.resolve if validate else manual_artifacts.peek
    return _record_segments(resolver(video.video_id, "subtitle_document", source_signature_value))


def active_voice_record(video, *, validate: bool = False) -> dict[str, Any] | None:
    """Return the published voice manifest that is still safe to play.

    The provider and preset currently selected in the inspector are a pending
    request until the Voice tool publishes a replacement manifest.  They must
    therefore never detach or silence the last complete manifest.  Subtitle
    text is different: playing speech for older words would be misleading, so
    the active document is still compared with the manifest's source document.
    """
    resolver = manual_artifacts.resolve if validate else manual_artifacts.peek
    voice = published_voice_record(video, validate=validate)
    if not voice:
        return None
    current_signature = _active_signature(video, "subtitle_document")
    source_signature_value = next(
        (
            str(value).split(":", 1)[1]
            for value in (voice.get("inputs") or [])
            if str(value).startswith("subtitle_document:")
        ),
        "",
    )
    if not current_signature or not source_signature_value:
        return None
    if current_signature == source_signature_value:
        return voice

    current = resolver(video.video_id, "subtitle_document", current_signature)
    source = resolver(video.video_id, "subtitle_document", source_signature_value)
    if not current or not source:
        return None
    # Compare timing according to the manifest that is actually playing, not
    # the pending setting in the voice dialog. Otherwise confirming a switch
    # from single to multiple speakers can detach the old, still-valid voice
    # before the replacement has been published.
    published_payload = _voice_manifest_payload(voice)
    published_speaker_mode = str(
        published_payload.get("speaker_mode")
        or getattr(video, "speaker_mode", "single")
        or "single"
    )
    multiple = published_speaker_mode == "multiple"

    def spoken_rows(record: dict[str, Any]) -> list[tuple[Any, ...]]:
        return [
            (
                " ".join(str(item.get("text") or "").split()),
                *(
                    (
                        round(float(item.get("start", 0) or 0), 3),
                        round(float(item.get("end", 0) or 0), 3),
                    )
                    if multiple
                    else ()
                ),
            )
            for item in _record_segments(record)
        ]

    return voice if spoken_rows(current) == spoken_rows(source) else None


def active_voice_clip_signatures(video, *, validate: bool = False) -> list[str]:
    """Return the exact clips referenced by the currently published manifest."""
    record = active_voice_record(video, validate=validate)
    manifest_path = str(((record or {}).get("resolved_outputs") or {}).get("manifest") or "")
    if not manifest_path:
        return []
    try:
        payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    clips = payload.get("clips") if isinstance(payload, dict) else None
    return [str(value) for value in clips] if isinstance(clips, list) else []


def _voice_manifest_payload(record: dict[str, Any] | None) -> dict[str, Any]:
    path = str(((record or {}).get("resolved_outputs") or {}).get("manifest") or "")
    if not path:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _current_voice_record(video, *, validate: bool = True) -> dict[str, Any] | None:
    # Rendering and mixing consume the last published state. The Voice tool's
    # readiness check separately compares that state with ``voice_signature``
    # for the pending configuration.
    return active_voice_record(video, validate=validate)


def _audio_background(video, *, validate: bool = True) -> tuple[str, str, list[str]]:
    """Return the best already-available base track; never create one here."""
    if getattr(video, "enable_audio_separation", False):
        resolver = manual_artifacts.resolve if validate else manual_artifacts.peek
        separated = resolver(video.video_id, "separation", separation_signature(video))
        if separated:
            return (
                str(separated["resolved_outputs"]["no_vocals"]),
                str(separated.get("artifact_id") or ""),
                [str(separated.get("artifact_id") or "")],
            )
    resolver = manual_artifacts.resolve if validate else manual_artifacts.peek
    source = resolver(video.video_id, "source_audio", source_signature(video))
    if source:
        return (
            str(source["resolved_outputs"]["audio"]),
            str(source.get("artifact_id") or ""),
            [str(source.get("artifact_id") or "")],
        )
    input_path = _video_input(video)
    return input_path, manual_artifacts.signature(manual_artifacts.file_state(input_path)), []


def audio_signature(video, *, validate: bool = True) -> str:
    subtitle = _current_subtitle_record(video, validate=validate)
    voice = published_voice_record(video, validate=validate)
    segments = _load_segments(video, validate=validate) if subtitle else []
    timing = [(float(item.get("start") or 0), float(item.get("end") or 0)) for item in segments]
    _background_path, background_token, _inputs = _audio_background(video, validate=validate)
    editor_document = editor_documents.load(video.video_id)
    audio_document = {}
    if editor_document:
        audio_tracks = {
            track.track_id: track.model_dump()
            for track in editor_document.tracks
            if track.kind in {"source_audio", "voice", "music"}
        }
        audio_document = {
            "sequence": editor_document.sequence.model_dump(),
            "tracks": audio_tracks,
            "clips": [
                clip.model_dump()
                for clip in editor_document.clips
                if clip.track_id in audio_tracks or clip.track_id == "subtitles"
            ],
            "ducking": {
                "enabled": editor_document.audio_ducking_enabled,
                "reduction_db": editor_document.audio_ducking_reduction_db,
                "attack_ms": editor_document.audio_ducking_attack_ms,
                "release_ms": editor_document.audio_ducking_release_ms,
            },
        }
    return manual_artifacts.signature(
        str((voice or {}).get("signature") or "no-voice"),
        background_token,
        timing,
        manual_artifacts.file_state((video.files or {}).get("background_music")),
        getattr(video, "original_video_volume", 60),
        getattr(video, "background_music_volume", 30),
        getattr(video, "tts_volume", 100),
        (subtitle or {}).get("signature", "") if voice else "no-subtitle-audio",
        audio_document,
        *_generation_token(video, "audio"),
        "manual-audio-mix-v5-preserve-speech-pauses",
    )


def export_signature(video, *, validate: bool = True) -> str:
    subtitle = _current_subtitle_record(video, validate=validate)
    ocr = (
        ocr_signature(video)
        if getattr(video, "remove_original_subtitles", True)
        and _artifact_ready(video, "ocr_region", ocr_signature(video), validate=validate)
        else "no-cleanup-layer"
    )
    editor_document = editor_documents.load(video.video_id)
    return manual_artifacts.signature(
        manual_artifacts.file_state(_video_input(video)),
        audio_signature(video, validate=validate),
        (subtitle or {}).get("signature", ""),
        ocr,
        getattr(video, "output_format", "keep_ratio"),
        _style_dict(video),
        _crop_dict(video),
        getattr(video, "remove_original_subtitles", True),
        getattr(video, "original_subtitle_removal_mode", "patch"),
        getattr(video, "watermark_text", ""),
        getattr(video, "watermark_scale_percent", 100),
        getattr(video, "watermark_kind", "text"),
        getattr(video, "watermark_opacity_percent", 46),
        getattr(video, "watermark_outline_percent", 100),
        manual_artifacts.file_state((video.files or {}).get("watermark_image")),
        manual_artifacts.file_state((video.files or {}).get("watermark_video")),
        getattr(video, "watermark_font_family", "Arial"),
        getattr(video, "watermark_text_color", "#FFFFFF"),
        getattr(video, "watermark_bold", True),
        getattr(video, "watermark_italic", True),
        getattr(video, "subtitle_layout_override", False),
        editor_document.model_dump() if editor_document else {},
        *_generation_token(video, "export"),
        "manual-export-v6-editor-document",
    )


def _artifact_ready(video, kind: str, expected: str, *, validate: bool = True) -> bool:
    return bool(
        expected
        and _active_signature(video, kind) == expected
        and _record_exists(video, kind, expected, validate=validate)
    )


def _source_ready(video, *, validate: bool = True) -> bool:
    return _artifact_ready(video, "source_audio", source_signature(video), validate=validate)


def _separation_ready(video, *, validate: bool = True) -> bool:
    return _artifact_ready(video, "separation", separation_signature(video), validate=validate)


def _recognition_ready(video, *, validate: bool = True) -> bool:
    return _artifact_ready(video, "recognition", recognition_signature(video), validate=validate)


def _translation_ready(video, *, validate: bool = True) -> bool:
    return _artifact_ready(video, "translation", translation_signature(video), validate=validate)


def _subtitle_ready(video, *, validate: bool = True) -> bool:
    return _current_subtitle_record(video, validate=validate) is not None


def _voice_ready(video, *, validate: bool = True) -> bool:
    if not validate:
        active = active_voice_record(video, validate=False)
        if not active:
            return False
        # A published clip can remain audible while a new voice is pending,
        # but it is not a cache hit for the current TTS algorithm or settings.
        if _active_signature(video, "tts_manifest") != voice_signature(video, validate=False):
            return False
        segments = _load_segments(video, validate=False)
        desired_groups = [
            {"provider": provider, "voice": voice, "segments": indices}
            for (provider, voice), indices in _voice_generation_groups(video, segments).items()
        ]
        payload = _voice_manifest_payload(active)
        if isinstance(payload.get("voice_configs"), list):
            return (
                payload["voice_configs"] == desired_groups
                and str(payload.get("speaker_mode") or "single")
                == str(getattr(video, "speaker_mode", "single") or "single")
            )
        # Compatibility for manifests created before per-segment voice
        # selection was introduced.
        if dict(getattr(video, "files", {}) or {}).get("manual_voice_overrides"):
            return False
        return str(active.get("config_fingerprint") or "") == manual_artifacts.signature(
            str(getattr(video, "tts_provider", "omnivoice") or "omnivoice"),
            str(getattr(video, "tts_voice", "") or ""),
            str(getattr(video, "speaker_mode", "single") or "single"),
        )
    expected = voice_signature(video, validate=validate)
    return _artifact_ready(video, "tts_manifest", expected, validate=validate)


def _audio_ready(video, *, validate: bool = True) -> bool:
    expected = audio_signature(video, validate=validate)
    return _artifact_ready(video, "audio_mix", expected, validate=validate)


def _image_ready(video, *, validate: bool = True) -> bool:
    return not getattr(video, "remove_original_subtitles", True) or _artifact_ready(
        video,
        "ocr_region",
        ocr_signature(video),
        validate=validate,
    )


def image_region_cached(video_or_id) -> bool:
    """Return whether OCR geometry exists, independent of the selected effect."""
    video = video_store.get_video(video_or_id) if isinstance(video_or_id, str) else video_or_id
    if not video:
        return False
    try:
        return _artifact_ready(video, "ocr_region", ocr_signature(video))
    except (FileNotFoundError, OSError, ValueError):
        return False


def activate_cached_voice_variant(video_id: str, *, validate: bool = False) -> bool:
    """Publish the cached voice matching current settings without running TTS.

    This is used by undo/redo and other metadata-only setting restores.  The
    previous manifest remains active when no matching variant exists, which
    preserves the editor's last complete audible state until the user confirms
    another Voice run.
    """
    video = video_store.get_video(video_id)
    if not video or video.project_type != "manual" or not _subtitle_ready(video, validate=False):
        return False
    expected = voice_signature(video, validate=False)
    resolver = manual_artifacts.resolve if validate else manual_artifacts.peek
    cached = resolver(video_id, "tts_manifest", expected) if expected else None
    if not cached:
        return False
    manual_artifacts.activate(video_id, "tts_manifest", expected)
    manual_artifacts.deactivate(video_id, {"audio_mix", "export"})
    refreshed = video_store.get_video(video_id) or video
    files = dict(refreshed.files or {})
    files["voice_parts_dir"] = str(Path(cached["resolved_outputs"]["manifest"]).parent / "parts")
    files.pop("voice_output", None)
    video_store.update_video(video_id, files=files)
    return True


def restore_cached_variants(video_id: str, *, validate: bool = True) -> list[str]:
    """Activate every cached artifact matching the current Manual settings.

    This is a metadata/cache operation used after settings are saved.  It
    never invokes a model or renderer, and walks dependencies in graph order
    so switching A → B → A immediately restores the complete A branch.
    """
    video = video_store.get_video(video_id)
    if not video or video.project_type != "manual":
        return []
    # Recover the visible/autosaved document before walking model-dependent
    # branches.  This also repairs projects whose older cache-cleanup pass
    # removed manifest metadata while leaving the user's subtitle JSON intact.
    ensure_current_subtitle_document(video_id, validate=validate)
    video = video_store.get_video(video_id) or video
    restored: list[str] = []
    try:
        expected_source = source_signature(video)
    except (FileNotFoundError, OSError, ValueError):
        return restored

    resolver = manual_artifacts.resolve if validate else manual_artifacts.peek

    def use(kind: str, expected: str) -> dict[str, Any] | None:
        if not expected:
            return None
        record = resolver(video_id, kind, expected)
        if not record:
            return None
        # Avoid rewriting both manifest.json and video.json when the desired
        # variant is already active.  This matters during startup, where a
        # workspace may contain hundreds of voice clips and several large
        # media artifacts.
        current_video = video_store.get_video(video_id)
        current_signature = str(
            ((getattr(current_video, "active_artifacts", {}) or {}).get(kind) if current_video else "")
            or ""
        )
        if current_signature != expected:
            manual_artifacts.activate(video_id, kind, expected)
        restored.append(kind)
        return record

    source = use("source_audio", expected_source)
    if source:
        _update_files(video_id, source_audio=source["resolved_outputs"]["audio"])
    if video.enable_audio_separation and source:
        separated = use("separation", separation_signature(video))
        if separated:
            _update_files(
                video_id,
                speech_audio=separated["resolved_outputs"]["vocals"],
                background_audio=separated["resolved_outputs"]["no_vocals"],
            )

    video = video_store.get_video(video_id) or video
    if not video.enable_audio_separation or _separation_ready(video, validate=validate):
        recognition = use("recognition", recognition_signature(video))
        if recognition:
            _update_files(video_id, source_segments=recognition["resolved_outputs"]["segments"])

    video = video_store.get_video(video_id) or video
    translation = (
        use("translation", translation_signature(video))
        if _recognition_ready(video, validate=validate)
        else None
    )
    current_subtitle = (
        manual_artifacts.active(video, "subtitle_document")
        if validate
        else manual_artifacts.peek_active(video, "subtitle_document")
    )
    if current_subtitle:
        _update_files(
            video_id,
            transcript_json=current_subtitle["resolved_outputs"]["segments"],
            srt_output=current_subtitle["resolved_outputs"]["srt"],
        )
    elif translation:
        matching_documents = sorted(
            (
                record
                for record in manual_artifacts.load_manifest(video_id)["artifacts"].values()
                if record.get("kind") == "subtitle_document"
                and translation["artifact_id"] in set(record.get("inputs") or [])
            ),
            key=lambda record: str(record.get("last_accessed_at") or record.get("created_at") or ""),
            reverse=True,
        )
        subtitle = None
        for record in matching_documents:
            subtitle = use("subtitle_document", str(record.get("signature") or ""))
            if subtitle:
                break
        if subtitle is None:
            subtitle = _publish_subtitles(
                video_store.get_video(video_id) or video,
                translation["resolved_outputs"]["segments"],
            )
        _update_files(
            video_id,
            transcript_json=subtitle["resolved_outputs"]["segments"],
            srt_output=subtitle["resolved_outputs"]["srt"],
        )

    video = video_store.get_video(video_id) or video
    if video.remove_original_subtitles:
        region = use("ocr_region", ocr_signature(video))
        if region:
            _update_files(video_id, ocr_region=region["resolved_outputs"]["region"])

    video = video_store.get_video(video_id) or video
    expected_voice = voice_signature(video, validate=validate)
    voice = (
        use("tts_manifest", expected_voice)
        if _subtitle_ready(video, validate=validate)
        else None
    )
    if voice:
        _update_files(video_id, voice_parts_dir=str(Path(voice["resolved_outputs"]["manifest"]).parent / "parts"))

    video = video_store.get_video(video_id) or video
    expected_audio = audio_signature(video, validate=validate)
    audio = use("audio_mix", expected_audio)
    if audio:
        _update_files(video_id, voice_output=audio["resolved_outputs"]["audio"])

    video = video_store.get_video(video_id) or video
    expected_export = export_signature(video, validate=validate)
    use("export", expected_export)
    return list(dict.fromkeys(restored))


def tool_states(video, *, language: str = "vi") -> list[dict[str, Any]]:
    labels_vi = {
        "source": "Nguồn", "translation": "Nhận dạng & dịch", "subtitle": "Phụ đề",
        "image": "Hình ảnh", "voice": "Giọng đọc", "audio": "Âm thanh", "export": "Xuất",
    }
    labels_en = {
        "source": "Source", "translation": "Recognize & translate", "subtitle": "Subtitles",
        "image": "Visuals", "voice": "Voice", "audio": "Audio", "export": "Export",
    }
    vi = language == "vi"
    # Presentation checks must not checksum large stems/exports on Qt's GUI
    # thread. Every runner performs full validation before consuming a hit.
    separation_ok = not video.enable_audio_separation or _separation_ready(video, validate=False)
    translation_ok = _translation_ready(video, validate=False)
    subtitle_ok = _subtitle_ready(video, validate=False)
    image_ok = _image_ready(video, validate=False)
    voice_ok = _voice_ready(video, validate=False)
    audio_ok = _audio_ready(video, validate=False)
    export_ok = _artifact_ready(
        video,
        "export",
        export_signature(video, validate=False),
        validate=False,
    )
    requirements = {
        "source": (True, separation_ok, ""),
        "translation": (
            separation_ok,
            translation_ok,
            "Hãy tách giọng trước" if vi else "Separate the voice first",
        ),
        "subtitle": (translation_ok, subtitle_ok, "Hãy dịch nội dung" if vi else "Translate the content first"),
        "image": (True, image_ok, ""),
        "voice": (subtitle_ok, voice_ok, "Hãy chuẩn bị phụ đề" if vi else "Prepare subtitles first"),
        "audio": (True, audio_ok, ""),
        "export": (True, export_ok, ""),
    }
    current = str(getattr(video, "manual_target_tool", "") or "")
    busy = bool(current) and video.status in {"pending", "processing", "paused"}
    published_voice = published_voice_record(video, validate=False)
    voice_notice = ""
    if published_voice and not voice_ok:
        if active_voice_record(video, validate=False) is None:
            voice_notice = (
                "Phụ đề đã đổi sau lần tạo giọng gần nhất. Giọng cũ vẫn được lưu; "
                "tạo lại để khớp nội dung mới."
                if vi else
                "Subtitles changed since the last voice generation. The previous voice is saved; "
                "regenerate to match the new text."
            )
        else:
            published_payload = _voice_manifest_payload(published_voice)
            published_groups = published_payload.get("voice_configs")
            same_global_voice = (
                isinstance(published_groups, list)
                and len(published_groups) == 1
                and str(published_groups[0].get("provider") or "")
                == str(getattr(video, "tts_provider", "omnivoice") or "omnivoice")
                and str(published_groups[0].get("voice") or "")
                == str(getattr(video, "tts_voice", "") or "")
                and str(published_payload.get("speaker_mode") or "single")
                == str(getattr(video, "speaker_mode", "single") or "single")
                and not dict(getattr(video, "files", {}) or {}).get("manual_voice_overrides")
            )
            if same_global_voice:
                voice_notice = (
                    "Giọng cũ vẫn được dùng. Tạo lại để các đoạn có cùng chất giọng."
                    if vi else
                    "The previous voice remains in use. Regenerate to give all segments the same voice."
                )
            else:
                voice_notice = (
                    "Lựa chọn giọng mới chưa được áp dụng. Giọng đã tạo vẫn được dùng."
                    if vi else
                    "The new voice selection has not been applied. The existing voice remains in use."
                )
    rows = []
    for tool_id in MANUAL_TOOL_IDS:
        can_run, cached, blocked = requirements[tool_id]
        belongs = busy and current in ({"source", "separation"} if tool_id == "source" else {tool_id})
        another_tool_busy = busy and not belongs
        if belongs and video.status == "processing":
            state = "running"
        elif belongs and video.status == "pending":
            state = "queued"
        elif belongs and video.status == "paused":
            state = "paused"
        elif video.status == "failed" and current in ({"source", "separation"} if tool_id == "source" else {tool_id}):
            state = "error"
        elif cached:
            state = "cached"
        elif can_run:
            state = "ready"
        else:
            state = "blocked"
        rows.append({
            "toolId": tool_id,
            "label": (labels_vi if vi else labels_en)[tool_id],
            "state": state,
            "progress": int(video.progress if belongs else 0),
            "canRun": bool(can_run and not another_tool_busy),
            # The active tool already owns the visible progress indicator.
            # Other controls are simply disabled while it runs; repeating a
            # generic warning under every inspector adds noise and previously
            # surfaced stale persisted state as a false error.
            "blockedReason": "" if another_tool_busy or can_run else blocked,
            "cacheHit": bool(cached),
            "voiceNotice": voice_notice if tool_id == "voice" else "",
            "hasPublishedArtifact": bool(
                published_voice
                if tool_id == "voice"
                else _active_signature(video, {
                    "source": "separation" if video.enable_audio_separation else "source_audio",
                    "translation": "translation",
                    "subtitle": "subtitle_document",
                    "image": "ocr_region",
                    "audio": "audio_mix",
                    "export": "export",
                }.get(tool_id, ""))
            ),
            "activeSignature": _active_signature(video, {
                "source": "separation" if video.enable_audio_separation else "source_audio",
                "recognition": "recognition", "translation": "translation", "subtitle": "subtitle_document",
                "image": "ocr_region", "voice": "tts_manifest", "audio": "audio_mix", "export": "export",
            }[tool_id]),
            "detail": str(video.step_detail if belongs else ""),
        })
    return rows


def _update_files(video_id: str, **paths: str) -> None:
    video = video_store.get_video(video_id)
    if not video:
        return
    files = dict(video.files or {})
    updates = {name: value for name, value in paths.items() if value and files.get(name) != value}
    if not updates:
        return
    files.update(updates)
    video_store.update_video(video_id, files=files)


def _publish_subtitles(video, source_path: str) -> dict[str, Any]:
    style = _style_dict(video)
    artifact_signature = _subtitle_document_signature(video, source_path)
    cached = manual_artifacts.resolve(video.video_id, "subtitle_document", artifact_signature)
    if cached:
        manual_artifacts.activate(video.video_id, "subtitle_document", artifact_signature)
        outputs = cached["resolved_outputs"]
        _update_files(video.video_id, transcript_json=outputs["segments"], srt_output=outputs["srt"])
        return cached
    staging = manual_artifacts.create_staging_directory(video.video_id, "subtitle_document")
    try:
        shutil.copy2(source_path, staging / "segments.json")
        generate_srt(
            str(staging / "segments.json"),
            str(staging / "subtitles.srt"),
            int(style.get("max_chars_per_line", 32)),
            video.video_id,
            preserve_segment_boundaries=True,
        )
        record = manual_artifacts.publish(
            video.video_id,
            "subtitle_document",
            artifact_signature,
            staging,
            {"segments": "segments.json", "srt": "subtitles.srt"},
            inputs=[_active_signature(video, "translation")],
            config_fingerprint="manual-subtitle-document-v1",
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    outputs = record["resolved_outputs"]
    _update_files(video.video_id, transcript_json=outputs["segments"], srt_output=outputs["srt"])
    return record


def publish_edited_subtitles(video_id: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Publish one autosaved subtitle document without mutating cached translation."""
    video = video_store.get_video(video_id)
    if not video:
        raise RuntimeError("Manual project is no longer available.")

    # A legacy Manual project can have a visible transcript file before its
    # first ``subtitle_document`` artifact is registered.  Do not walk the
    # recognition/translation signature graph merely to compare that file:
    # doing so both assumes newer metadata fields and can hash source media on
    # the caller's thread.  Read the small visible JSON directly in that case.
    if _active_signature(video, "subtitle_document"):
        previous_segments = _load_segments(video)
    else:
        files = dict(getattr(video, "files", {}) or {})
        previous_path = str(
            files.get("translation_review_draft")
            or files.get("transcript_json")
            or ""
        )
        try:
            previous_payload = json.loads(Path(previous_path).read_text(encoding="utf-8"))
        except (OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            previous_payload = []
        previous_segments = (
            [dict(item) for item in previous_payload if isinstance(item, dict)]
            if isinstance(previous_payload, list)
            else []
        )

    def spoken_text(items: list[dict[str, Any]]) -> list[str]:
        return [" ".join(str(item.get("text") or "").split()) for item in items]

    def timing(items: list[dict[str, Any]]) -> list[tuple[float, float]]:
        return [
            (
                round(float(item.get("start", 0) or 0), 3),
                round(float(item.get("end", 0) or 0), 3),
            )
            for item in items
        ]

    text_changed = spoken_text(previous_segments) != spoken_text(segments)
    timing_changed = timing(previous_segments) != timing(segments)
    staging = manual_artifacts.create_staging_directory(video_id, "subtitle_document")
    try:
        segments_path = staging / "segments.json"
        segments_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / "document.json").write_text(json.dumps({
            "schema_version": 2,
            "revision": max((int(item.get("revision", 0)) for item in segments), default=0),
            "segments": segments,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        style = _style_dict(video)
        generate_srt(
            str(segments_path),
            str(staging / "subtitles.srt"),
            int(style.get("max_chars_per_line", 32)),
            video_id,
            preserve_segment_boundaries=True,
        )
        artifact_signature = _subtitle_document_signature(video, str(segments_path))
        record = manual_artifacts.publish(
            video_id,
            "subtitle_document",
            artifact_signature,
            staging,
            {"segments": "segments.json", "srt": "subtitles.srt", "document": "document.json"},
            inputs=[value for value in [_active_signature(video, "translation")] if value],
            config_fingerprint="manual-subtitle-document-v1",
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    outputs = record["resolved_outputs"]
    _update_files(video_id, transcript_json=outputs["segments"], srt_output=outputs["srt"])
    if text_changed:
        manual_artifacts.deactivate(
            video_id,
            {"audio_mix", "export"},
        )
    elif timing_changed:
        # Single-speaker TTS clips are text keyed and remain reusable. Only
        # their placement and final rendered consumer become stale. The
        # Manual visual proxy is subtitle-free, so its cache remains valid.
        manual_artifacts.deactivate(video_id, {"audio_mix", "export"})
    if text_changed or timing_changed:
        refreshed = video_store.get_video(video_id)
        if refreshed:
            files = dict(refreshed.files or {})
            files.pop("voice_output", None)
            changes: dict[str, Any] = {"files": files}
            # A failed voice request belongs to the subtitle revision it was
            # generated for. Once the text changes, retaining that failure on
            # the new document makes the Voice tool look broken before its
            # replacement request has even started.
            if (
                text_changed
                and str(getattr(refreshed, "status", "") or "") == "failed"
                and str(getattr(refreshed, "manual_target_tool", "") or "") == "voice"
            ):
                changes.update(
                    status="manual_ready",
                    error=None,
                    step="manual_subtitle",
                    step_detail="Phụ đề đã cập nhật",
                    manual_target_tool="",
                )
            video_store.update_video(video_id, **changes)
    return record


def ensure_current_subtitle_document(
    video_id: str,
    *,
    validate: bool = True,
) -> dict[str, Any] | None:
    """Restore a durable subtitle artifact from the document visible in Manual.

    Old projects and an early cache-cleanup implementation could retain
    ``transcript_json`` while losing the active manifest reference.  The file
    is user-authored editor state, so copy it back into the immutable cache
    instead of forcing recognition/translation to run again.
    """
    video = video_store.get_video(video_id)
    if not video or video.project_type != "manual":
        return None
    active = (
        manual_artifacts.active(video, "subtitle_document")
        if validate
        else manual_artifacts.peek_active(video, "subtitle_document")
    )
    if active:
        return active
    files = dict(video.files or {})
    for candidate in (files.get("translation_review_draft"), files.get("transcript_json")):
        path = str(candidate or "")
        if manual_artifacts.file_state(path) is None:
            continue
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list) or not any(
            isinstance(item, dict) and str(item.get("text") or "").strip() for item in payload
        ):
            continue
        return publish_edited_subtitles(video_id, payload)
    return None


def _replace_subtitles_from_translation(video_id: str, translated_segments: str) -> dict[str, Any]:
    """Publish translated text and detach only artifacts that contain old text.

    Visual/audio settings and independent source analysis remain untouched.
    Old voice variants stay in the immutable cache, but are no longer active
    because their text no longer represents the current subtitle document.
    """
    video = video_store.get_video(video_id)
    if not video:
        raise RuntimeError("Manual project is no longer available.")
    subtitle = _publish_subtitles(video, translated_segments)
    manual_artifacts.deactivate(
        video_id,
        {"tts_manifest", "audio_mix", "visual_proxy", "export"},
    )
    refreshed = video_store.get_video(video_id) or video
    files = dict(refreshed.files or {})
    draft_path = str(files.pop("translation_review_draft", "") or "")
    # These references contain the old spoken text. Source/separation tracks,
    # OCR geometry, music and the last exported user file remain untouched.
    files.pop("voice_output", None)
    files.pop("voice_parts_dir", None)
    video_store.update_video(video_id, files=files)
    if draft_path:
        try:
            Path(draft_path).unlink(missing_ok=True)
        except OSError:
            pass
    return subtitle


def _run_source(video, reporter) -> None:
    expected = source_signature(video)
    cached = manual_artifacts.resolve(video.video_id, "source_audio", expected)
    if not cached:
        staging = manual_artifacts.create_staging_directory(video.video_id, "source_audio")
        try:
            reporter.update(5, "manual_source", "Đang trích âm thanh nguồn")
            extract_audio(_video_input(video), str(staging / "audio.wav"), video.video_id)
            cached = manual_artifacts.publish(
                video.video_id, "source_audio", expected, staging, {"audio": "audio.wav"},
                config_fingerprint="source-audio-pcm-v1",
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    else:
        manual_artifacts.activate(video.video_id, "source_audio", expected)
    _update_files(video.video_id, source_audio=cached["resolved_outputs"]["audio"])


def _run_separation(video, reporter) -> None:
    source = manual_artifacts.resolve(video.video_id, "source_audio", source_signature(video))
    if not source:
        # Source extraction is an implementation detail of Demucs. The user
        # starts one action—voice separation—and the reusable PCM cache is
        # prepared inside that action when necessary.
        _run_source(video, reporter)
        source = manual_artifacts.resolve(video.video_id, "source_audio", source_signature(video))
    if not source:
        raise RuntimeError("Không trích được âm thanh từ video nguồn.")
    expected = separation_signature(video)
    cached = manual_artifacts.resolve(video.video_id, "separation", expected)
    if not cached:
        staging = manual_artifacts.create_staging_directory(video.video_id, "separation")
        try:
            reporter.update(8, "manual_separation", "Đang tách giọng và nhạc nền")
            vocals, no_vocals = separate_audio(
                source["resolved_outputs"]["audio"], str(staging / "tracks"), video.video_id
            )
            cached = manual_artifacts.publish(
                video.video_id,
                "separation",
                expected,
                staging,
                {
                    "vocals": str(Path(vocals).relative_to(staging)),
                    "no_vocals": str(Path(no_vocals).relative_to(staging)),
                },
                inputs=[source["artifact_id"]],
                config_fingerprint=DEMUCS_MODEL_SIGNATURE,
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    else:
        manual_artifacts.activate(video.video_id, "separation", expected)
    outputs = cached["resolved_outputs"]
    _update_files(video.video_id, speech_audio=outputs["vocals"], background_audio=outputs["no_vocals"])


def _run_recognition(video, reporter) -> None:
    source = None
    if video.enable_audio_separation:
        source = manual_artifacts.resolve(video.video_id, "separation", separation_signature(video))
        if not source:
            raise RuntimeError("Hãy tách giọng trước khi nhận dạng bằng track giọng nói.")
        audio_path = source["resolved_outputs"]["vocals"]
    else:
        # Whisper/FFmpeg can decode the source container directly.  Extracting
        # a WAV is an optional cached source operation, not a fake prerequisite.
        source = manual_artifacts.resolve(video.video_id, "source_audio", source_signature(video))
        audio_path = source["resolved_outputs"]["audio"] if source else _video_input(video)
    expected = recognition_signature(video)
    cached = manual_artifacts.resolve(video.video_id, "recognition", expected)
    if not cached:
        staging = manual_artifacts.create_staging_directory(video.video_id, "recognition")
        try:
            # Translation may have left HY-MT2 resident from an earlier run.
            # Whisper Turbo needs that VRAM/commit back before model loading.
            shutdown_hymt2_worker()
            reporter.update(5, "manual_recognition", "Đang nhận dạng lời thoại")
            transcribe(
                audio_path,
                str(staging / "source-segments.json"),
                getattr(video, "source_language", "auto"),
                video.video_id,
                progress_callback=lambda _event, detail: reporter.update(30, "manual_recognition", detail),
                model_name=getattr(video, "speech_recognition_model", "small"),
            )
            cached = manual_artifacts.publish(
                video.video_id,
                "recognition",
                expected,
                staging,
                {"segments": "source-segments.json"},
                inputs=[source["artifact_id"]] if source else [],
                config_fingerprint=manual_artifacts.signature(
                    getattr(video, "speech_recognition_model", "small"), TIMING_SOURCE
                ),
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    else:
        manual_artifacts.activate(video.video_id, "recognition", expected)
    _update_files(video.video_id, source_segments=cached["resolved_outputs"]["segments"])


def _run_translation(video, reporter) -> None:
    recognition = manual_artifacts.resolve(video.video_id, "recognition", recognition_signature(video))
    if not recognition:
        _run_recognition(video, reporter)
        recognition = manual_artifacts.resolve(video.video_id, "recognition", recognition_signature(video))
    if not recognition:
        raise RuntimeError("Không nhận dạng được lời thoại trong video.")
    expected = translation_signature(video)
    cached = manual_artifacts.resolve(video.video_id, "translation", expected)
    if not cached:
        staging = manual_artifacts.create_staging_directory(video.video_id, "translation")
        try:
            reporter.update(5, "manual_translation", "Đang dịch phụ đề")
            # Recognition has already published its immutable output. On 16 GB
            # systems retaining Whisper while HY-MT2 maps its weights can
            # exhaust Windows commit even though CUDA VRAM was released.
            _release_recognition_runtime()
            translate_segments(
                recognition["resolved_outputs"]["segments"],
                str(staging / "translated-segments.json"),
                video.video_id,
                getattr(video, "target_language", "vi"),
                source_language="auto",
                provider="hymt2",
                progress_callback=lambda current, total, detail: reporter.update(
                    5 + round(90 * current / max(1, total)), "manual_translation", detail, current, total
                ),
            )
            cached = manual_artifacts.publish(
                video.video_id,
                "translation",
                expected,
                staging,
                {"segments": "translated-segments.json"},
                inputs=[recognition["artifact_id"]],
                config_fingerprint=manual_artifacts.signature(
                    getattr(video, "target_language", "vi"), HYMT2_MODEL_REVISION
                ),
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    else:
        manual_artifacts.activate(video.video_id, "translation", expected)
    _replace_subtitles_from_translation(video.video_id, cached["resolved_outputs"]["segments"])


def _run_subtitle(video, _reporter) -> None:
    translation = manual_artifacts.resolve(video.video_id, "translation", translation_signature(video))
    if not translation:
        raise RuntimeError("Hãy chạy Dịch trước khi chuẩn bị phụ đề.")
    _replace_subtitles_from_translation(video.video_id, translation["resolved_outputs"]["segments"])


def _run_image(video, reporter) -> None:
    if not video.remove_original_subtitles:
        return
    expected = ocr_signature(video)
    cached = manual_artifacts.resolve(video.video_id, "ocr_region", expected)
    if not cached:
        staging = manual_artifacts.create_staging_directory(video.video_id, "ocr_region")
        try:
            reporter.update(5, "manual_image", "Đang phân tích vùng phụ đề gốc")
            region = detect_original_subtitle_region(
                _video_input(video),
                str(staging),
                video.video_id,
                progress_callback=lambda current, total: reporter.update(
                    5 + round(90 * current / max(1, total)),
                    "manual_image",
                    f"Đang phân tích khung hình {current}/{total}",
                    current,
                    total,
                ),
            )
            (staging / "region.json").write_text(
                json.dumps(region, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            cached = manual_artifacts.publish(
                video.video_id,
                "ocr_region",
                expected,
                staging,
                {"region": "region.json"},
                config_fingerprint=str(DETECTOR_CACHE_VERSION),
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    else:
        manual_artifacts.activate(video.video_id, "ocr_region", expected)
    _update_files(video.video_id, ocr_region=cached["resolved_outputs"]["region"])


def _run_voice(video, reporter) -> None:
    segments = _load_segments(video)
    subtitle = _current_subtitle_record(video)
    if not segments or not subtitle:
        raise RuntimeError("Hãy chuẩn bị phụ đề trước khi tạo giọng đọc.")
    narrator_anchor = ensure_narrator_anchor(video.video_id)
    video = video_store.get_video(video.video_id) or video
    clip_signatures = _voice_clip_signatures(video, segments)
    expected = manual_artifacts.signature(clip_signatures, VOICE_MANIFEST_CACHE_VERSION)
    cached = manual_artifacts.resolve(video.video_id, "tts_manifest", expected)
    if not cached:
        staging = manual_artifacts.create_staging_directory(video.video_id, "tts_manifest")
        parts_dir = staging / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        try:
            missing_clip_indices = []
            for index, clip_signature in enumerate(clip_signatures, 1):
                clip = manual_artifacts.resolve(video.video_id, "tts_clip", clip_signature)
                if clip:
                    shutil.copy2(clip["resolved_outputs"]["audio"], parts_dir / f"voice_{index:04d}.mp3")
                else:
                    missing_clip_indices.append(index)
            if missing_clip_indices:
                missing_clip_count = len(missing_clip_indices)
                detail = (
                    "Đang tạo lại câu đã chỉnh"
                    if missing_clip_count == 1
                    else f"Đang tạo {missing_clip_count} câu đã thay đổi"
                )
                reporter.update(5, "manual_voice", detail, 0, missing_clip_count)
                generation_groups = _voice_generation_groups(video, segments)
                requested_groups = [
                    (provider, voice, [index for index in indices if index in missing_clip_indices])
                    for (provider, voice), indices in generation_groups.items()
                ]
                requested_groups = [item for item in requested_groups if item[2]]
                if any(
                    resolve_tts_provider(provider, video.target_language) == "omnivoice"
                    for provider, _voice, _indices in requested_groups
                ):
                    shutdown_hymt2_worker()
                    _release_recognition_runtime()

                completed_before = 0

                def report_voice_status(stage: str, current: int, _total: int) -> None:
                    preparing_details = {
                        "loading_model": "Đang nạp model giọng đọc",
                        "reusing_model": "Đang dùng model giọng đọc đã nạp",
                        "creating_voice_anchor": "Đang ổn định chất giọng",
                        "launching_worker": "Đang khởi tạo bộ tạo giọng",
                    }
                    if stage in preparing_details:
                        percent = 5 + round(90 * completed_before / max(1, missing_clip_count))
                        status_detail = preparing_details[stage]
                    else:
                        overall = completed_before + current
                        percent = 5 + round(90 * overall / max(1, missing_clip_count))
                        status_detail = (
                            f"Đã tạo {overall}/{missing_clip_count} câu"
                            if overall
                            else detail
                        )
                    reporter.update(
                        percent,
                        "manual_voice",
                        status_detail,
                        completed_before + current,
                        missing_clip_count,
                    )

                for provider, voice, group_indices in requested_groups:
                    effective = resolve_tts_provider(provider, video.target_language)

                    def report_group_progress(current: int, _total: int) -> None:
                        overall = completed_before + current
                        reporter.update(
                            5 + round(90 * overall / max(1, missing_clip_count)),
                            "manual_voice",
                            f"Đã tạo {overall}/{missing_clip_count} câu",
                            overall,
                            missing_clip_count,
                        )

                    generate_voice_parts(
                        str(
                            subtitle["resolved_outputs"].get("segments")
                            or subtitle["resolved_outputs"].get("transcript")
                        ),
                        str(parts_dir),
                        voice,
                        video.video_id,
                        progress_callback=report_group_progress,
                        provider=provider,
                        target_language=video.target_language,
                        keep_worker_warm=True,
                        segment_indices=group_indices,
                        narrator_anchor_text=narrator_anchor,
                        status_callback=report_voice_status if effective == "omnivoice" else None,
                    )
                    completed_before += len(group_indices)
            else:
                reporter.update(95, "manual_voice", "Đang khôi phục giọng đọc từ cache")
            _publish_completed_voice_clips(video, subtitle, parts_dir, clip_signatures)
            voice_configs = [
                {"provider": provider, "voice": voice, "segments": indices}
                for (provider, voice), indices in _voice_generation_groups(video, segments).items()
            ]
            (staging / "manifest.json").write_text(
                json.dumps(
                    {
                        "clips": clip_signatures,
                        "voice_configs": voice_configs,
                        "speaker_mode": video.speaker_mode,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            outputs = {"manifest": "manifest.json"}
            outputs.update({f"clip_{index}": f"parts/voice_{index:04d}.mp3" for index in range(1, len(segments) + 1)})
            cached = manual_artifacts.publish(
                video.video_id,
                "tts_manifest",
                expected,
                staging,
                outputs,
                inputs=[
                    subtitle["artifact_id"],
                    *[manual_artifacts.artifact_id("tts_clip", value) for value in clip_signatures],
                ],
                config_fingerprint=manual_artifacts.signature(voice_configs, video.speaker_mode),
                activate_artifact=False,
            )
        finally:
            # A cancelled batch may already contain several atomically
            # completed MP3 files.  Publish those clips before removing the
            # transient manifest staging directory so Resume only synthesizes
            # the genuinely missing sentences.
            _publish_completed_voice_clips(video, subtitle, parts_dir, clip_signatures)
            shutil.rmtree(staging, ignore_errors=True)
    current = video_store.get_video(video.video_id)
    if current and voice_signature(current) != expected:
        return
    manual_artifacts.activate(video.video_id, "tts_manifest", expected)
    manifest_path = cached["resolved_outputs"]["manifest"]
    _update_files(video.video_id, voice_parts_dir=str(Path(manifest_path).parent / "parts"))
    current = video_store.get_video(video.video_id) or video
    if getattr(current, "project_type", "") == "manual":
        resolved_outputs = dict(cached.get("resolved_outputs") or {})
        clip_paths = {
            str(segment.get("segment_id") or segment.get("id") or f"index:{index}"): str(
                resolved_outputs.get(f"clip_{index}") or ""
            )
            for index, segment in enumerate(segments, 1)
        }
        editor_documents.mark_voice_clips_ready(current, segments, clip_paths)


def _publish_completed_voice_clips(video, subtitle, parts_dir: Path, clip_signatures: list[str]) -> None:
    for index, clip_signature in enumerate(clip_signatures, 1):
        part_path = parts_dir / f"voice_{index:04d}.mp3"
        if not _is_valid_mp3(str(part_path)):
            continue
        manual_artifacts.register_existing(
            video.video_id,
            "tts_clip",
            clip_signature,
            {"audio": str(part_path)},
            inputs=[subtitle["artifact_id"]],
            config_fingerprint=VOICE_CLIP_CACHE_VERSION,
            activate_artifact=False,
        )


def _register_voice_manifest_from_parts(video, parts_dir: Path) -> dict[str, Any] | None:
    """Register a complete legacy/resumed set without invoking a TTS model."""
    subtitle = _current_subtitle_record(video)
    segments = _load_segments(video)
    if not subtitle or not segments:
        return None
    clip_signatures = _voice_clip_signatures(video, segments)
    if any(not _is_valid_mp3(str(parts_dir / f"voice_{index:04d}.mp3")) for index in range(1, len(segments) + 1)):
        return None
    _publish_completed_voice_clips(video, subtitle, parts_dir, clip_signatures)
    expected = manual_artifacts.signature(clip_signatures, VOICE_MANIFEST_CACHE_VERSION)
    cached = manual_artifacts.resolve(video.video_id, "tts_manifest", expected)
    if cached:
        manual_artifacts.activate(video.video_id, "tts_manifest", expected)
        return cached
    staging = manual_artifacts.create_staging_directory(video.video_id, "tts_manifest")
    staged_parts = staging / "parts"
    staged_parts.mkdir(parents=True, exist_ok=True)
    try:
        for index in range(1, len(segments) + 1):
            source = parts_dir / f"voice_{index:04d}.mp3"
            destination = staged_parts / source.name
            try:
                os.link(source, destination)
            except OSError:
                shutil.copy2(source, destination)
        (staging / "manifest.json").write_text(
            json.dumps({"clips": clip_signatures}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        outputs = {"manifest": "manifest.json"}
        outputs.update({f"clip_{index}": f"parts/voice_{index:04d}.mp3" for index in range(1, len(segments) + 1)})
        return manual_artifacts.publish(
            video.video_id,
            "tts_manifest",
            expected,
            staging,
            outputs,
            inputs=[
                subtitle["artifact_id"],
                *[manual_artifacts.artifact_id("tts_clip", value) for value in clip_signatures],
            ],
            # Legacy files become a normal current-settings variant after
            # validation.  Marking this as merely "legacy-voice" made the
            # lightweight editor state checker reject valid migrated speech.
            config_fingerprint=manual_artifacts.signature(
                video.tts_provider, video.tts_voice, video.speaker_mode
            ),
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _compose_manual_audio(video, output_path: Path, work_dir: Path, reporter=None) -> list[str]:
    """Materialize the current optional audio layers without invoking AI."""
    from haizflow.pipeline.sequence_compiler import materialize_source_sequence

    document = editor_documents.ensure(video)
    tracks = {track.track_id: track for track in document.tracks}
    audio_track_ids = {"source-audio", "voice", "music"}
    solo_tracks = {
        track.track_id
        for track in document.tracks
        if track.track_id in audio_track_ids and track.solo
    }

    def track_audible(track_id: str) -> bool:
        track = tracks.get(track_id)
        if track is None:
            return False
        return bool(
            track.visible
            and not track.muted
            and (not solo_tracks or track_id in solo_tracks)
        )

    voice = published_voice_record(video, validate=True)
    background, _background_token, input_ids = _audio_background(video)
    segments_path = work_dir / "audio-segments.json"
    voice_parts = work_dir / "editor-voice-parts"
    voice_parts.mkdir(parents=True, exist_ok=True)
    subtitle_clips = sorted(
        (
            clip for clip in document.clips
            if clip.track_id == "subtitles" and clip.enabled and clip.segment_id
        ),
        key=lambda clip: (clip.start_ms, clip.clip_id),
    )
    voice_by_segment = {
        clip.segment_id: clip
        for clip in document.clips
        if clip.track_id == "voice" and clip.segment_id
    }
    segments: list[dict[str, Any]] = []
    for subtitle_clip in subtitle_clips:
        stored = subtitle_clip.metadata.get("segment_payload")
        segment = dict(stored) if isinstance(stored, dict) else {}
        segment.update(
            segment_id=subtitle_clip.segment_id,
            text=subtitle_clip.name,
            start=subtitle_clip.start_ms / 1000,
            end=(subtitle_clip.start_ms + subtitle_clip.duration_ms) / 1000,
        )
        voice_clip = voice_by_segment.get(subtitle_clip.segment_id)
        voice_enabled = bool(
            track_audible("voice")
            and voice_clip
            and voice_clip.enabled
            and not voice_clip.muted
        )
        segment["_voice_enabled"] = voice_enabled
        if voice_clip:
            segment["_voice_volume_percent"] = voice_clip.volume_percent
            segment["_voice_fade_in_ms"] = voice_clip.fade_in_ms
            segment["_voice_fade_out_ms"] = voice_clip.fade_out_ms
            if bool(segment.get("timeline_edited")) or voice_clip.duration_ms != subtitle_clip.duration_ms:
                segment["fit_voice_to_timing"] = True
        segments.append(segment)

    published_segments = published_voice_source_segments(video, voice, validate=True) if voice else []
    published_by_id = {
        str(item.get("segment_id") or item.get("id") or ""): index
        for index, item in enumerate(published_segments, start=1)
    }
    published_parts = (
        Path(voice["resolved_outputs"]["manifest"]).parent / "parts"
        if voice else None
    )
    clip_signatures = _voice_clip_signatures(video, segments)
    usable_voice = False
    for index, (segment, signature) in enumerate(zip(segments, clip_signatures), start=1):
        if not segment.get("_voice_enabled"):
            continue
        source = ""
        clip_record = manual_artifacts.resolve(video.video_id, "tts_clip", signature)
        if clip_record:
            source = str(clip_record["resolved_outputs"].get("audio") or "")
            input_ids.append(str(clip_record.get("artifact_id") or ""))
        if not source and published_parts:
            source_index = published_by_id.get(str(segment.get("segment_id") or ""), 0)
            candidate = published_parts / f"voice_{source_index:04d}.mp3"
            if source_index and candidate.is_file() and candidate.stat().st_size > 0:
                source = str(candidate)
                input_ids.append(str(voice.get("artifact_id") or ""))
        if not source:
            segment["_voice_enabled"] = False
            continue
        destination = voice_parts / f"voice_{index:04d}.mp3"
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
        usable_voice = True

    segments_path.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")

    source_clip = next(
        (clip for clip in document.clips if clip.track_id == "source-audio" and clip.enabled),
        None,
    )
    source_volume = source_clip.volume_percent if source_clip else video.original_video_volume
    source_enabled = bool(
        track_audible("source-audio") and source_clip and not source_clip.muted
    )
    music_clip = next(
        (clip for clip in document.clips if clip.track_id == "music" and clip.enabled),
        None,
    )
    music_asset = editor_documents.asset_by_id(document, music_clip.asset_id) if music_clip else None
    music_path = str(music_asset.path) if music_asset and track_audible("music") and not music_clip.muted else ""

    # Edit the source bed first. Voice and music use sequence timestamps and
    # must never be trimmed again with source-file coordinates.
    mix_video, mix_background = materialize_source_sequence(
        _video_input(video),
        background,
        document,
        work_dir,
        video.video_id,
    )
    if reporter:
        reporter.update(5, "manual_audio", "Đang cập nhật các lớp âm thanh")
    build_audio_timeline(
        str(segments_path),
        str(voice_parts),
        mix_video,
        str(output_path),
        video.video_id,
        background_audio_path=mix_background if source_enabled else None,
        original_video_volume=source_volume,
        original_audio_fade_in_ms=source_clip.fade_in_ms if source_clip else 0,
        original_audio_fade_out_ms=source_clip.fade_out_ms if source_clip else 0,
        background_music_path=music_path or None,
        background_music_volume=music_clip.volume_percent if music_clip else video.background_music_volume,
        tts_volume=video.tts_volume,
        require_voice_parts=usable_voice,
        require_background_audio=False,
        fit_voice_to_slots=True,
        background_music_start_ms=music_clip.start_ms if music_clip else 0,
        background_music_duration_ms=music_clip.duration_ms if music_clip else None,
        background_music_source_in_ms=music_clip.source_in_ms if music_clip else 0,
        background_music_loop=music_clip.loop if music_clip else True,
        background_music_fade_in_ms=music_clip.fade_in_ms if music_clip else 0,
        background_music_fade_out_ms=music_clip.fade_out_ms if music_clip else 0,
        ducking_enabled=document.audio_ducking_enabled,
        ducking_reduction_db=document.audio_ducking_reduction_db,
        ducking_attack_ms=document.audio_ducking_attack_ms,
        ducking_release_ms=document.audio_ducking_release_ms,
    )
    return [value for value in input_ids if value]


def _run_audio(video, reporter) -> None:
    expected = audio_signature(video)
    cached = manual_artifacts.resolve(video.video_id, "audio_mix", expected)
    if not cached:
        staging = manual_artifacts.create_staging_directory(video.video_id, "audio_mix")
        try:
            inputs = _compose_manual_audio(video, staging / "mix.wav", staging, reporter)
            cached = manual_artifacts.publish(
                video.video_id,
                "audio_mix",
                expected,
                staging,
                {"audio": "mix.wav"},
                inputs=inputs,
                config_fingerprint=manual_artifacts.signature(
                    video.original_video_volume, video.background_music_volume, video.tts_volume,
                    manual_artifacts.file_state((video.files or {}).get("background_music")),
                ),
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    else:
        manual_artifacts.activate(video.video_id, "audio_mix", expected)
    _update_files(video.video_id, voice_output=cached["resolved_outputs"]["audio"])


def _ocr_region(video) -> dict[str, Any] | None:
    if not video.remove_original_subtitles:
        return None
    record = manual_artifacts.resolve(video.video_id, "ocr_region", ocr_signature(video))
    if not record:
        # Cleanup is an optional layer. Until OCR is explicitly run, the
        # current visual state is simply the unmodified source underneath any
        # translated subtitle layer.
        return None
    try:
        payload = json.loads(Path(record["resolved_outputs"]["region"]).read_text(encoding="utf-8"))
        return payload.get("region", payload) if isinstance(payload, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Cache vùng phụ đề gốc không hợp lệ.") from exc


def _run_export(video, reporter) -> None:
    from haizflow.pipeline.sequence_compiler import (
        apply_overlays,
        map_source_intervals,
        materialize_source_video,
        resolved_subtitle_style,
        subtitle_style_overrides,
        write_subtitles,
    )

    subtitle = _current_subtitle_record(video)
    audio = manual_artifacts.resolve(video.video_id, "audio_mix", audio_signature(video))
    expected = export_signature(video)
    cached = manual_artifacts.resolve(video.video_id, "export", expected)
    if not cached:
        staging = manual_artifacts.create_staging_directory(video.video_id, "export")
        try:
            reporter.update(5, "manual_export", "Đang xuất video")
            editor_document = editor_documents.ensure(video)
            export_srt = staging / "subtitles.srt"
            if write_subtitles(editor_document, export_srt):
                pass
            elif subtitle:
                outputs = subtitle["resolved_outputs"]
                generate_srt(
                    outputs["segments"],
                    str(export_srt),
                    int(_style_dict(video).get("max_chars_per_line", 32)),
                    video.video_id,
                    preserve_segment_boundaries=True,
                )
            else:
                # render_video intentionally expects a subtitle file. A
                # zero-width, 80 ms cue keeps the render path identical while
                # producing no visible subtitle layer.
                export_srt.write_text(
                    "1\n00:00:00,000 --> 00:00:00,080\n\u200b\n",
                    encoding="utf-8",
                )
            audio_path = str((audio or {}).get("resolved_outputs", {}).get("audio") or "")
            export_inputs: list[str] = []
            if audio:
                export_inputs.append(str(audio.get("artifact_id") or ""))
            else:
                audio_path = str(staging / "current-audio.wav")
                export_inputs.extend(_compose_manual_audio(video, Path(audio_path), staging))
            render_input = materialize_source_video(
                _video_input(video),
                editor_document,
                staging,
                video.video_id,
            )
            render_audio = audio_path
            source_segments = manual_artifacts.active(video, "recognition")
            intervals: list[tuple[float, float]] = []
            if source_segments:
                try:
                    source_payload = json.loads(
                        Path(source_segments["resolved_outputs"]["segments"]).read_text(encoding="utf-8")
                    )
                    intervals = [
                        (float(item.get("start") or 0), float(item.get("end") or 0))
                        for item in source_payload if isinstance(item, dict)
                    ]
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                    intervals = []
            intervals = map_source_intervals(editor_document, intervals)
            render_video(
                render_input,
                render_audio,
                str(export_srt),
                str(staging / "video-base.mp4"),
                video.output_format,
                resolved_subtitle_style(editor_document, video.subtitle_style),
                video.crop,
                video.video_id,
                _ocr_region(video),
                video.watermark_text,
                subtitle_layout_override=bool(video.subtitle_layout_override),
                progress_callback=lambda fraction: reporter.update(
                    5 + round(84 * fraction), "manual_export", f"Đang xuất video {round(100 * fraction)}%"
                ),
                original_subtitle_removal_mode=video.original_subtitle_removal_mode,
                original_subtitle_intervals=intervals,
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
                subtitle_style_overrides=subtitle_style_overrides(editor_document),
            )
            reporter.update(91, "manual_export", "Đang ghép các lớp hình ảnh")
            apply_overlays(
                str(staging / "video-base.mp4"),
                str(staging / "video.mp4"),
                editor_document,
                video.video_id,
            )
            cached = manual_artifacts.publish(
                video.video_id,
                "export",
                expected,
                staging,
                {"video": "video.mp4"},
                inputs=[
                    *([str(subtitle.get("artifact_id") or "")] if subtitle else []),
                    *export_inputs,
                    *(
                        [manual_artifacts.artifact_id("ocr_region", ocr_signature(video))]
                        if video.remove_original_subtitles
                        and _artifact_ready(video, "ocr_region", ocr_signature(video))
                        else []
                    ),
                ],
                config_fingerprint=expected,
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    else:
        manual_artifacts.activate(video.video_id, "export", expected)
    final_path = str((video.files or {}).get("final_video") or "")
    if not final_path:
        final_path = str(Path(video_store.get_video_dir(video.video_id)) / "output" / "final.mp4")
    Path(final_path).parent.mkdir(parents=True, exist_ok=True)
    source = Path(cached["resolved_outputs"]["video"])
    temporary = Path(final_path).with_suffix(".exporting.mp4")
    shutil.copy2(source, temporary)
    os.replace(temporary, final_path)
    _update_files(video.video_id, final_video=final_path)


_RUNNERS = {
    "source": _run_source,
    "separation": _run_separation,
    "recognition": _run_recognition,
    "translation": _run_translation,
    "subtitle": _run_subtitle,
    "image": _run_image,
    "voice": _run_voice,
    "audio": _run_audio,
    "export": _run_export,
}


def _requested_artifact(video, tool_id: str, *, validate: bool = True) -> tuple[str, str]:
    kind = {
        "source": "source_audio",
        "separation": "separation",
        "recognition": "recognition",
        "translation": "translation",
        "subtitle": "subtitle_document",
        "image": "ocr_region",
        "voice": "tts_manifest",
        "audio": "audio_mix",
        "export": "export",
    }[tool_id]
    expected = {
        "source": source_signature,
        "separation": separation_signature,
        "recognition": recognition_signature,
        "translation": translation_signature,
        "subtitle": lambda current: str((_current_subtitle_record(current, validate=validate) or {}).get("signature") or ""),
        "image": ocr_signature,
        "voice": lambda current: voice_signature(current, validate=validate),
        "audio": lambda current: audio_signature(current, validate=validate),
        "export": lambda current: export_signature(current, validate=validate),
    }[tool_id](video)
    return kind, expected


def prepare_manual_rerun(video_id: str, tool_id: str) -> bool:
    """Make an explicit rerun miss its prior immutable artifact safely.

    The translation button owns both recognition and translation. Advancing
    recognition invalidates both branches and every dependent voice variant,
    while a separation rerun additionally invalidates the recognition input.
    No old cache directory is deleted or overwritten before the new run ends.
    """
    generation_key = {
        "source": "source",
        "separation": "separation",
        "recognition": "recognition",
        "translation": "recognition",
        "image": "image",
        "voice": "voice",
        "audio": "audio",
        "export": "export",
    }.get(tool_id)
    if not generation_key:
        return False
    video = video_store.get_video(video_id)
    if not video or video.project_type != "manual":
        return False
    try:
        kind, expected = _requested_artifact(video, tool_id, validate=False)
        cached = bool(expected and manual_artifacts.peek(video_id, kind, expected))
        if tool_id == "translation" and not cached:
            # Translation is the visible action for both ASR and translation.
            # A missing translation must not silently reuse a cached ASR run.
            recognition = recognition_signature(video)
            cached = bool(manual_artifacts.peek(video_id, "recognition", recognition))
    except (AttributeError, FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
        return False
    if not cached:
        return False
    generations = dict(getattr(video, "manual_tool_generations", {}) or {})
    generations[generation_key] = int(generations.get(generation_key, 0) or 0) + 1
    video_store.update_video(video_id, manual_tool_generations=generations)
    video_store.log_to_video(
        video_id,
        f"Explicit rerun invalidated cached {tool_id} branch (generation {generations[generation_key]}).",
        component="MANUAL",
    )
    return True


def migrate_legacy_artifacts(video_id: str) -> bool:
    """Register safe schema-v16 Manual outputs without modifying their files."""
    video = video_store.get_video(video_id)
    if (
        not video
        or video.project_type != "manual"
        or int(getattr(video, "manual_artifact_migration_version", 0) or 0) >= 1
    ):
        return False
    changed = False
    video_dir = Path(video_store.get_video_dir(video_id))
    files = dict(video.files or {})

    source_path = str(files.get("source_audio") or video_dir / "temp" / "audio.wav")
    if manual_artifacts.file_state(source_path):
        changed = bool(manual_artifacts.register_existing(
            video_id, "source_audio", source_signature(video), {"audio": source_path},
            config_fingerprint="legacy-source-audio",
        )) or changed
    video = video_store.get_video(video_id) or video

    vocals = str(files.get("speech_audio") or "")
    no_vocals = str(files.get("background_audio") or "")
    if manual_artifacts.file_state(vocals) and manual_artifacts.file_state(no_vocals):
        changed = bool(manual_artifacts.register_existing(
            video_id,
            "separation",
            separation_signature(video),
            {"vocals": vocals, "no_vocals": no_vocals},
            inputs=[manual_artifacts.artifact_id("source_audio", source_signature(video))],
            config_fingerprint="legacy-demucs",
        )) or changed

    source_segments = str(files.get("source_segments") or video_dir / "temp" / "source_segments.json")
    if manual_artifacts.file_state(source_segments):
        changed = bool(manual_artifacts.register_existing(
            video_id,
            "recognition",
            recognition_signature(video),
            {"segments": source_segments},
            config_fingerprint="legacy-whisper",
        )) or changed
        _update_files(video_id, source_segments=source_segments)

    video = video_store.get_video(video_id) or video
    transcript = str(files.get("transcript_json") or "")
    if _recognition_ready(video) and manual_artifacts.file_state(transcript):
        translated = manual_artifacts.register_existing(
            video_id,
            "translation",
            translation_signature(video),
            {"segments": transcript},
            inputs=[manual_artifacts.artifact_id("recognition", recognition_signature(video))],
            config_fingerprint="legacy-hymt2",
        )
        if translated:
            changed = True
            _publish_subtitles(video_store.get_video(video_id) or video, translated["resolved_outputs"]["segments"])

    video = video_store.get_video(video_id) or video
    legacy_ocr = video_dir / "temp" / "original_subtitle_region.json"
    if manual_artifacts.file_state(legacy_ocr):
        changed = bool(manual_artifacts.register_existing(
            video_id, "ocr_region", ocr_signature(video), {"region": str(legacy_ocr)},
            config_fingerprint="legacy-ocr",
        )) or changed
        _update_files(video_id, ocr_region=str(legacy_ocr))

    video = video_store.get_video(video_id) or video
    completed = set(getattr(video, "manual_completed_stages", []) or [])
    legacy_parts = Path(str(files.get("voice_parts_dir") or video_dir / "temp" / "voice_parts"))
    if "voice" in completed and legacy_parts.is_dir() and not published_voice_record(video):
        voice = _register_voice_manifest_from_parts(video, legacy_parts)
        if voice:
            changed = True
            _update_files(video_id, voice_parts_dir=str(Path(voice["resolved_outputs"]["manifest"]).parent / "parts"))

    video = video_store.get_video(video_id) or video
    legacy_mix = str((video.files or {}).get("voice_output") or video_dir / "temp" / "voice_final.wav")
    expected_audio = audio_signature(video)
    if "timeline" in completed and _voice_ready(video) and expected_audio and manual_artifacts.file_state(legacy_mix):
        mixed = manual_artifacts.register_existing(
            video_id,
            "audio_mix",
            expected_audio,
            {"audio": legacy_mix},
            inputs=[manual_artifacts.artifact_id("tts_manifest", voice_signature(video))],
            config_fingerprint="legacy-audio-mix",
        )
        if mixed:
            changed = True
            _update_files(video_id, voice_output=mixed["resolved_outputs"]["audio"])

    video = video_store.get_video(video_id) or video
    legacy_export = str((video.files or {}).get("final_video") or "")
    expected_export = export_signature(video)
    if (
        "render" in completed
        and _audio_ready(video)
        and _image_ready(video)
        and expected_export
        and manual_artifacts.file_state(legacy_export)
    ):
        exported = manual_artifacts.register_existing(
            video_id,
            "export",
            expected_export,
            {"video": legacy_export},
            inputs=[
                manual_artifacts.artifact_id("subtitle_document", _active_signature(video, "subtitle_document")),
                manual_artifacts.artifact_id("audio_mix", audio_signature(video)),
            ],
            config_fingerprint="legacy-export",
        )
        if exported:
            changed = True

    video_store.update_video(video_id, manual_artifact_migration_version=1)
    return changed


def run_manual_tool_sync(video_id: str, tool_id: str) -> None:
    """Run one user-selected Manual tool and only its explicit sub-operations.

    ``translation`` intentionally combines recognition and translation, while
    ``separation`` may first extract its audio input. Neither composite tool
    crosses into OCR, TTS, mixing, or export.
    """
    tool_id = str(tool_id or "").strip().lower()
    if tool_id not in _RUNNERS:
        raise ValueError(f"Unsupported Manual tool: {tool_id}")
    from haizflow.pipeline.process_video import ProgressReporter

    reporter = None
    requested_kind = ""
    requested_signature = ""
    try:
        start_video(video_id)
        reporter = ProgressReporter(video_id)
        video = video_store.get_video(video_id)
        if not video or video.project_type != "manual":
            raise RuntimeError("Manual project is no longer available.")
        try:
            requested_kind, requested_signature = _requested_artifact(video, tool_id)
        except (AttributeError, FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
            requested_kind, requested_signature = "", ""
        try:
            cache_hit = {
                "source": _source_ready,
                "separation": _separation_ready,
                "recognition": _recognition_ready,
                "translation": _translation_ready,
                "subtitle": _subtitle_ready,
                "image": _image_ready,
                "voice": _voice_ready,
                "audio": _audio_ready,
                "export": lambda current: _artifact_ready(current, "export", export_signature(current)),
            }[tool_id](video)
        except (AttributeError, FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
            cache_hit = False
        video_store.log_to_video(
            video_id,
            f"Cache {'hit' if cache_hit else 'miss'} · {tool_id}",
            component="MANUAL",
        )
        video_store.log_to_video(video_id, f"Manual tool started: {tool_id}.", component="MANUAL")
        _RUNNERS[tool_id](video, reporter)
        refreshed = video_store.get_video(video_id) or video
        final = tool_id == "export"
        video_store.update_video(
            video_id,
            status="done" if final else "manual_ready",
            progress=100 if final else _TOOL_PROGRESS[tool_id],
            step="done" if final else f"manual_{tool_id}",
            step_detail="Video đã xuất" if final else "Đã hoàn tất công cụ",
            error=None,
            estimated_remaining_seconds=0 if final else None,
            resume_step="",
            runtime_recovery_step="",
            manual_target_tool="",
            manual_target_stage="",
            active_artifacts=dict(getattr(refreshed, "active_artifacts", {}) or {}),
        )
        video_store.log_to_video(video_id, f"Manual tool completed: {tool_id}.", component="MANUAL")
    except Exception as exc:
        if is_cancelled(video_id) or str(exc) == "Video cancelled by user.":
            if is_paused(video_id):
                video_store.update_video(
                    video_id, status="paused", error=None, step="paused",
                    step_detail=f"Đã tạm dừng {tool_id}", resume_step=tool_id,
                )
                return
            video_store.update_video(video_id, status="cancelled", error=None, step="cancelled")
            return
        if requested_kind and requested_signature:
            manual_artifacts.record_error(
                video_id,
                requested_kind,
                requested_signature,
                str(exc),
                config_fingerprint=f"manual-{tool_id}",
            )
        video_store.log_to_video(
            video_id,
            f"Manual tool failed ({tool_id}): {exc}\n{traceback.format_exc()}",
            level="ERROR",
            component="MANUAL",
        )
        video_store.update_video(
            video_id,
            status="failed",
            error=str(exc),
            step="failed",
            step_detail=str(exc),
            manual_target_tool=tool_id,
        )
    finally:
        clean_video(video_id)
        try:
            manual_artifacts.maintain(video_id)
        except (OSError, RuntimeError, ValueError):
            # Cache maintenance is opportunistic and must never change the
            # result of the user-selected Manual tool.
            pass
