"""Stable shared Auto settings; individual overrides never redefine the batch."""

import hashlib
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from haizflow.schemas.video import VideoConfig
from haizflow.services import project_store
from haizflow.core.storage_ownership import owned_path


FIELDS = {
    "workflowMode": "mode", "targetLanguage": "target_language",
    "speechRecognitionModel": "speech_recognition_model", "translationModel": "translation_model",
    "ttsProvider": "tts_provider", "ttsVoice": "tts_voice", "speakerMode": "speaker_mode",
    "enableAudioSeparation": "enable_audio_separation", "originalVolume": "original_video_volume",
    "backgroundMusicVolume": "background_music_volume", "ttsVolume": "tts_volume",
    "backgroundMusicLoop": "background_music_loop", "audioDuckingEnabled": "audio_ducking_enabled",
    "audioDuckingReductionDb": "audio_ducking_reduction_db", "watermarkText": "watermark_text",
    "watermarkKind": "watermark_kind", "watermarkScalePercent": "watermark_scale_percent",
    "watermarkOpacityPercent": "watermark_opacity_percent", "watermarkOutlinePercent": "watermark_outline_percent",
    "watermarkFontFamily": "watermark_font_family", "watermarkTextColor": "watermark_text_color",
    "watermarkBold": "watermark_bold", "watermarkItalic": "watermark_italic",
    "removeOriginalSubtitles": "remove_original_subtitles", "originalSubtitleRemovalMode": "original_subtitle_removal_mode",
}
ASSETS = {"backgroundMusicPath": "background_music", "voiceReferencePath": "voice_reference",
          "watermarkImagePath": "watermark_image", "watermarkVideoPath": "watermark_video"}


def values_for(video) -> dict:
    result = {key: getattr(video, field) for key, field in FIELDS.items()}
    result["workflowMode"] = "A"
    result["subtitleStyle"] = {**video.subtitle_style.model_dump(), "manual": video.subtitle_layout_override}
    result.update({key: str((video.files or {}).get(field) or "") for key, field in ASSETS.items()})
    return result


@lru_cache(maxsize=256)
def _digest(path: str, size: int, modified: int) -> str:
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def asset_identity(path) -> str:
    if not path:
        return ""
    try:
        source = Path(path)
        stat = source.stat()
        return _digest(str(source.resolve()), stat.st_size, stat.st_mtime_ns)
    except OSError:
        # Missing configured assets must remain visible as an override/error.
        return "missing:" + str(path)


def differences(actual: dict, expected: dict) -> list[str]:
    return [key for key, value in actual.items() if key in expected and (
        asset_identity(value) != asset_identity(expected[key]) if key in ASSETS else value != expected[key])]


def config_for(values: dict) -> VideoConfig:
    payload = {field: values[key] for key, field in FIELDS.items() if key in values}
    payload["mode"] = "A"
    payload["source_language"] = "auto"
    payload["project_type"] = "batch"
    payload["translator_provider"] = "gemini" if str(values.get("translationModel", "")).startswith("gemini-") else "hymt2"
    style = dict(values.get("subtitleStyle") or {})
    payload["subtitle_layout_override"] = bool(style.pop("manual", False))
    payload["subtitle_style"] = style
    payload.update({field + "_path": str(values.get(key) or "") for key, field in ASSETS.items()})
    if payload.get("target_language", "vi") not in {"vi", "en", "zh"}:
        raise ValueError("Choose English, Vietnamese or Chinese.")
    config = VideoConfig.model_validate(payload)
    if config.tts_voice == "omnivoice:clone" and not values.get("voiceReferencePath"):
        raise ValueError("Choose a reference sample before applying the cloned voice.")
    return config


def stage_asset(project_key: str, key: str, path: str) -> str:
    """Publish immutable assets so imports and undo cannot lose their source."""
    if key not in ASSETS or not path:
        return ""
    record = project_store.get_project(project_key)
    if not record or record.get("project_type") != "batch":
        raise ValueError("The batch project is no longer available.")
    source = Path(path)
    if not source.is_file() or source.stat().st_size <= 0:
        raise FileNotFoundError(str(source))
    if key == "watermarkImagePath":
        from PIL import Image
        with Image.open(source) as image:
            image.verify()
    elif key == "watermarkVideoPath":
        from haizflow.utils.ffmpeg import get_video_dimensions
        if min(get_video_dimensions(str(source))) <= 0:
            raise ValueError("No video stream in watermark.")
    root = Path(project_store.project_root_for_key(project_key))
    directory = owned_path(root / ".batch-settings-assets", root)
    directory.mkdir(parents=True, exist_ok=True)
    target = owned_path(directory / (ASSETS[key] + "-" + asset_identity(str(source)) + source.suffix.lower()), root)
    if not target.is_file():
        from haizflow.services.desktop_videos import _copy_file_atomically
        _copy_file_atomically(str(source), str(target))
    return str(target)


def stable_values(project_key: str, initial: dict, videos: list) -> dict:
    record = project_store.get_project(project_key)
    if not record or record.get("project_type") != "batch":
        return initial
    saved = record.get("batch_settings", {}).get("values")
    if isinstance(saved, dict):
        return {**initial, **saved}
    if videos:
        maps = [values_for(video) for video in videos]
        signatures = [json.dumps({key: asset_identity(value) if key in ASSETS else value
                                  for key, value in item.items()}, sort_keys=True) for item in maps]
        common = Counter(signatures).most_common(1)[0][0]
        initial = maps[signatures.index(common)]
    # Do not discard missing legacy paths: readiness will explain the problem.
    staged = {key: stage_asset(project_key, key, value) if key in ASSETS and value and Path(value).is_file() else value
              for key, value in initial.items()}
    project_store.save_batch_settings(project_key, staged)
    return staged
