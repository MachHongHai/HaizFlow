"""Project-owned source captions; never depend on the user's external SRT file."""

import hashlib
import json
import html
import re
import unicodedata
import uuid
from copy import deepcopy
from pathlib import Path

import srt

from haizflow.services import manual_artifacts, video_store

MAX_BYTES = 8 * 1024 * 1024
TEXT_KINDS = {"recognition", "translation", "subtitle_document", "tts_manifest", "audio_mix", "export"}
TEXT_FILES = {"source_segments", "transcript_json", "srt_output", "voice_output", "voice_parts_dir",
              "manual_voice_overrides", "translation_review_draft", "final_video",
              "tts_narrator_anchors", "tts_narrator_anchor_text", "tts_narrator_anchor_config"}


def detect_language(segments) -> str:
    """Identify a predominant script, not a lone foreign name in captions."""
    text = unicodedata.normalize("NFC", " ".join(str(item.get("text") or "") for item in segments))
    letters = sum(character.isalpha() for character in text)
    if not letters:
        return "und"
    han = len(re.findall(r"[\u3400-\u9fff]", text))
    kana = len(re.findall(r"[\u3040-\u30ff]", text))
    if kana and (han + kana) / letters >= .5:
        return "ja"  # Japanese captions commonly mix kana and kanji.
    for code, pattern in (("ja", r"[\u3040-\u30ff]"), ("ko", r"[\uac00-\ud7af]"),
                          ("ar", r"[\u0600-\u06ff]"), ("ru", r"[\u0400-\u04ff]"),
                          ("th", r"[\u0e00-\u0e7f]"), ("hi", r"[\u0900-\u097f]"),
                          ("zh", r"[\u3400-\u9fff]")):
        count = sum(character.isalpha() for character in re.findall(pattern, text))
        if count / letters >= .5:
            return code
    latin = sum("LATIN" in unicodedata.name(character, "") for character in text if character.isalpha())
    if latin / letters >= .5 and re.search(
        r"[đĐăĂơƠưƯạảấầẩẫậắằẳẵặẹẻẽếềểễệỉĩịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", text,
    ):
        return "vi"
    return "und"


def inspect_srt(path, *, duration_ms=0):
    with open(path, "rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    segments = parse_srt(data, duration_ms=duration_ms)
    return data, segments


def chinese_text_notice(video, segments, ui_language="vi"):
    """Explain actual imported-caption content, not the source video's language."""
    if not has_import(video):
        return None
    from haizflow.core.vieneu_voices import han_text_notice

    return han_text_notice(segments, ui_language, imported=True)


def voice_notice(video, provider, segments, ui_language="vi"):
    if str(provider).startswith("vieneu"):
        from haizflow.core.vieneu_voices import han_text_notice

        notice = han_text_notice(segments, ui_language, imported=has_import(video))
        if notice:
            return notice
    if not has_import(video):
        return None
    language = str(getattr(video, "subtitle_language", "") or "und")
    script = detect_language(segments)
    if language not in {"vi", "en", "zh"} or script not in {"vi", "zh", "und"}:
        return ("Ngôn ngữ SRT chưa được cấu hình", "Chọn ngôn ngữ SRT phù hợp khi nhập hoặc dịch sang ngôn ngữ được hỗ trợ trước khi tạo giọng.") if ui_language == "vi" else (
            "SRT language is not configured", "Choose a supported SRT language when importing, or translate before generating speech.")
    if str(provider).startswith("vieneu") and (language == "zh" or script == "zh"):
        notice = chinese_text_notice(video, segments, ui_language)
        if notice:
            return notice
        return ("Ngôn ngữ SRT là tiếng Trung", (
            "SRT đã nhập đang được gán ngôn ngữ tiếng Trung. VieNeu không hỗ trợ đọc tiếng Trung. "
            "Nếu nội dung thực tế là tiếng Việt, hãy nhập lại SRT và chọn đúng ngôn ngữ; "
            "nếu là tiếng Trung, hãy dịch SRT sang tiếng Việt hoặc chọn OmniVoice/Edge TTS."
        )) if ui_language == "vi" else ("SRT language is Chinese", (
            "The imported SRT is marked as Chinese, which VieNeu does not support. "
            "If its actual content is Vietnamese, reimport it with the correct language; otherwise translate "
            "the captions into Vietnamese or choose OmniVoice/Edge TTS."
        ))
    return None


def _discard_input(video_id, record):
    """Retire only the exact app-owned SRT revision, never the external file."""
    if not isinstance(record, dict) or not record.get("segments"):
        return
    from haizflow.core.storage_ownership import owned_path, safe_tree
    from haizflow.services.temporary_cleanup import discard_tree

    owner = Path(video_store.get_video_dir(video_id)) / "input" / "subtitles"
    try:
        path = owned_path(Path(record["segments"]), owner)
        directory = path.parent
        if directory.parent != owner.resolve() or not re.fullmatch(r"[0-9a-f]{32}", directory.name):
            return
        safe_tree(directory)
    except (OSError, ValueError, RuntimeError):
        return
    discard_tree(directory)


def _clear_translation_progress(video_id):
    from haizflow.services.translation_progress import clear_manual_progress

    try:
        clear_manual_progress(video_id)
    except OSError:
        # Source/generation signatures reject the stale checkpoint even while locked.
        video_store.log_to_video(video_id, "SRT changed; stale translation checkpoint cleanup deferred.")


def _reset_text_branch(video):
    generations = dict(video.manual_tool_generations)
    for key in {"recognition", "translation", "voice", "audio", "export"}:
        generations[key] = int(generations.get(key, 0) or 0) + 1
    return {"manual_tool_generations": generations,
            "manual_completed_stages": [stage for stage in video.manual_completed_stages
                                        if stage not in {"translation", "subtitle", "voice", "timeline", "render"}],
            "manual_artifact_migration_version": max(1, video.manual_artifact_migration_version),
            "status": "manual_ready", "manual_target_tool": "", "resume_step": "", "error": None,
            "manual_target_stage": "", "manual_completed_stage": "",
            "progress": 0, "step": "manual_ready", "step_detail": "", "current_item": 0, "total_items": 0}


def _empty_text(document):
    from haizflow.services import editor_documents

    cleared = document.model_copy(deep=True)
    cleared.clips = [clip for clip in cleared.clips if clip.track_id not in {"subtitles", "voice"}]
    referenced = {clip.asset_id for clip in cleared.clips}
    voice_assets = {clip.asset_id for clip in document.clips if clip.track_id == "voice"}
    cleared.assets = [asset for asset in cleared.assets if asset.asset_id not in voice_assets or asset.asset_id in referenced]
    editor_documents.refresh_sequence_duration(cleared)
    return cleared


def _visible_segments(segments, document):
    from haizflow.pipeline.sequence_compiler import map_source_intervals

    result = []
    for item in segments:
        spans = map_source_intervals(document, [(item["start"], item["end"])])
        for index, (start, end) in enumerate(spans):
            mapped = deepcopy(item)
            mapped.update(start=round(start, 3), end=round(end, 3))
            if len(spans) > 1:
                mapped["segment_id"] += f"-cut-{index}"
            result.append(mapped)
    return sorted(result, key=lambda item: (item["start"], item["end"]))


def has_import(video) -> bool:
    return bool((getattr(video, "files", {}) or {}).get("imported_source_srt"))


def parse_srt(data: bytes, *, duration_ms: int = 0) -> list[dict]:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("SRT rỗng hoặc lớn hơn 8 MiB.")
    try:
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        text = data.decode(encoding)
        cues = list(srt.parse(text))
    except (UnicodeError, srt.SRTParseError, ValueError) as exc:
        raise ValueError("SRT không hợp lệ. Hãy lưu tệp dạng UTF-8 hoặc UTF-16.") from exc
    if not cues or len(cues) > 50000:
        raise ValueError("SRT phải có từ 1 đến 50.000 đoạn phụ đề.")
    segments = []
    previous_start = -1
    digest = hashlib.sha256(data).hexdigest()[:16]
    for index, cue in enumerate(cues, 1):
        start = round(cue.start.total_seconds() * 1000)
        end = round(cue.end.total_seconds() * 1000)
        content = html.unescape(re.sub(r"</?(?:b|i|u|s|font)(?:\s[^>]*)?>", "", cue.content, flags=re.IGNORECASE)).strip()
        if start < 0 or end <= start or start < previous_start or not content:
            raise ValueError(f"Đoạn SRT {index} có nội dung hoặc mốc thời gian không hợp lệ.")
        if duration_ms and end > duration_ms + 100:
            raise ValueError(f"Đoạn SRT {index} vượt quá thời lượng video nguồn.")
        previous_start = start
        segments.append({"segment_id": f"srt-{digest}-{index}", "start": start / 1000,
                         "end": end / 1000, "text": content, "timing_source": "imported-srt-v1"})
    return segments


def source_identity(video):
    return manual_artifacts.file_state((video.files or {}).get("video_input"))


def load_segments(video) -> list[dict]:
    record = (getattr(video, "files", {}) or {}).get("imported_source_srt")
    if not isinstance(record, dict) or not record.get("segments"):
        raise ValueError("Không tìm thấy SRT đã nhập. Hãy nhập lại SRT.")
    root = Path(video_store.get_video_dir(video.video_id)) / "input" / "subtitles"
    path = Path(record["segments"])
    if not path.resolve().is_relative_to(root.resolve()) or record.get("source") != source_identity(video):
        raise ValueError("SRT không khớp video nguồn hiện tại. Hãy nhập lại SRT.")
    try:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record.get("digest"):
            raise ValueError("SRT trong dự án đã bị thay đổi. Hãy nhập lại SRT.")
        payload = json.loads(data)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Không đọc được SRT trong dự án. Hãy nhập lại SRT.") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("SRT trong dự án không có phụ đề.")
    return payload


def import_srt(video_id: str, path: str, *, duration_ms: int = 0, language: str = "") -> int:
    video = video_store.get_video(video_id)
    if not video or video.project_type != "manual" or video.status in {"processing", "pending"} and video.manual_target_tool:
        raise ValueError("Chờ tác vụ hoàn tất trước khi nhập SRT.")
    if not source_identity(video):
        raise ValueError("Hãy nhập video nguồn trước khi nhập SRT.")
    raw, segments = inspect_srt(path, duration_ms=duration_ms)
    language = language or detect_language(segments)
    if language not in {"vi", "en", "zh", "und", "ja", "ko", "ar", "ru", "th", "hi"}:
        raise ValueError("Ngôn ngữ SRT không hợp lệ.")
    # Distinct Chinese text must not inherit the next translation's language.
    if detect_language(segments) == "zh":
        han = sum(len(re.findall(r"[\u3400-\u9fff]", str(item.get("text") or ""))) for item in segments)
        letters = sum(char.isalpha() for item in segments for char in str(item.get("text") or ""))
        if han / max(1, letters) >= .5:
            language = "zh"
    for item in segments:
        item["language"] = language if language != "und" else "auto"
    current = video_store.get_video(video_id)
    if not current or source_identity(current) != source_identity(video):
        raise ValueError("Video nguồn đã thay đổi. Hãy nhập lại SRT.")
    video = current
    from haizflow.services import editor_documents
    from haizflow.pipeline.manual_tools import publish_edited_subtitles
    from haizflow.services.subtitle_language import compatible_manual_voice

    document = editor_documents.load(video_id)
    original = video.model_copy(deep=True)
    retired_input = deepcopy(video.files.get("imported_source_srt"))
    visible_segments = _visible_segments(segments, document)
    if not visible_segments:
        raise ValueError("SRT không có đoạn phụ đề nào trong phần video đang giữ trên timeline.")
    directory = Path(video_store.get_video_dir(video_id)) / "input" / "subtitles" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    try:
        destination = directory / "segments.json"
        data = json.dumps(segments, ensure_ascii=False).encode("utf-8")
        destination.write_bytes(data)
        (directory / "source.srt").write_bytes(raw)
        files = dict(video.files or {})
        for key in TEXT_FILES:
            files.pop(key, None)
        files["imported_source_srt"] = {"segments": str(destination), "source": source_identity(video),
                                       "digest": hashlib.sha256(data).hexdigest(), "name": Path(path).name,
                                       "language": language}
        files["source_segments"] = str(destination)
        active = {key: value for key, value in video.active_artifacts.items() if key not in TEXT_KINDS}
        provider, voice = compatible_manual_voice(language, video.tts_provider, video.tts_voice)
        if not video_store.update_video(video_id, files=files, active_artifacts=active, subtitle_language=language,
                                         tts_provider=provider, tts_voice=voice,
                                         **_reset_text_branch(video)):
            raise ValueError("Dự án không còn khả dụng.")
        if document:
            editor_documents.save(video_store.get_video(video_id), _empty_text(document))
        publish_edited_subtitles(video_id, visible_segments)
        refreshed = video_store.get_video(video_id)
        editor_documents.sync_subtitle_clips(refreshed, visible_segments)
    except Exception:
        try:
            if document:
                editor_documents.save(original.model_copy(deep=True), document, bump_revision=False)
            else:
                editor_documents.document_path(video_id).unlink(missing_ok=True)
        finally:
            video_store.save_video(original)
            _discard_input(video_id, {"segments": str(directory / "segments.json")})
        raise
    _clear_translation_progress(video_id)
    _discard_input(video_id, retired_input)
    video_store.log_to_video(video_id, f"Imported source SRT: {len(segments)} cues; Whisper will be skipped.")
    return len(segments)


def remove_srt(video_id: str) -> bool:
    from haizflow.services import editor_documents

    video = video_store.get_video(video_id)
    if not video or not has_import(video):
        return False
    if video.project_type != "manual":
        raise ValueError("Chỉ xóa SRT trong dự án thủ công.")
    if video.status in {"processing", "pending"} and video.manual_target_tool:
        raise ValueError("Chờ tác vụ hoàn tất trước khi xóa SRT.")
    current = editor_documents.load(video_id)
    retired_input = deepcopy(video.files.get("imported_source_srt"))
    files = dict(video.files)
    files.pop("imported_source_srt", None)
    for key in TEXT_FILES:
        files.pop(key, None)
    active = {key: value for key, value in video.active_artifacts.items() if key not in TEXT_KINDS}
    original = video.model_copy(deep=True)
    try:
        if not video_store.update_video(video_id, files=files, active_artifacts=active, subtitle_language="",
                **_reset_text_branch(video)):
            raise ValueError("Dự án không còn khả dụng.")
        if current:
            editor_documents.save(video_store.get_video(video_id), _empty_text(current))
    except Exception:
        try:
            if current:
                editor_documents.save(original.model_copy(deep=True), current, bump_revision=False)
        finally:
            video_store.save_video(original)
        raise
    _clear_translation_progress(video_id)
    _discard_input(video_id, retired_input)
    video_store.log_to_video(video_id, "Removed imported SRT; subtitle/voice branches cleared. Source, OCR and music preserved.")
    return True
