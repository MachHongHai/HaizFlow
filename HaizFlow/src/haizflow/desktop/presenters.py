"""Pure presentation mapping shared by the desktop controller and tests."""

import os

from haizflow.desktop.catalog import (
    EDGE_TTS_VOICES_BY_LANGUAGE,
    POPULAR_TARGET_LANGUAGES,
    OMNIVOICE_TTS_VOICES,
)
from haizflow.desktop.models import VideoListModel
from haizflow.services import project_store


VIETNAMESE_LANGUAGE_NAMES = {
    "vi": "Tiếng Việt",
    "en": "Tiếng Anh",
    "zh": "Tiếng Trung",
    "hi": "Tiếng Hindi",
    "es": "Tiếng Tây Ban Nha",
    "fr": "Tiếng Pháp",
    "ar": "Tiếng Ả Rập",
    "pt": "Tiếng Bồ Đào Nha",
    "ru": "Tiếng Nga",
    "id": "Tiếng Indonesia",
    "de": "Tiếng Đức",
    "ja": "Tiếng Nhật",
    "ko": "Tiếng Hàn",
    "it": "Tiếng Ý",
    "th": "Tiếng Thái",
    "fil": "Tiếng Filipino",
}


def build_project_summaries(videos, persisted_projects=None):
    grouped = {}
    for persisted in persisted_projects or []:
        key = persisted.get("key")
        if not key:
            continue
        grouped[key] = {
            "key": key,
            "project_name": persisted["project_name"],
            "project_directory": persisted.get("project_directory", ""),
            "project_type": project_store.normalize_project_type(persisted.get("project_type")),
            "videos": [],
            "updated_at": persisted.get("updated_at", ""),
            "activity_at": persisted.get("activity_at") or persisted.get("created_at", ""),
        }
    for video in videos:
        project_type = "batch" if getattr(video, "project_type", "single") == "batch" else "single"
        project_name = video.project_name or os.path.splitext(video.original_filename)[0]
        project_directory = video.project_directory or ""
        key = str(getattr(video, "project_key", "") or "")
        # A persisted video is migrated to an immutable project key when it is
        # read.  Plain presenter test data and truly legacy videos still need a
        # deterministic grouping key without consulting unrelated app data.
        if not key and project_directory:
            key = project_store.project_key(project_name, project_directory, project_type)
        if not key:
            key = f"legacy:{video.video_id}"
        project = grouped.setdefault(
            key,
            {
                "key": key,
                "project_name": project_name,
                "project_directory": project_directory,
                "project_type": project_type,
                "videos": [],
                "updated_at": video.updated_at,
                # A video-only summary is a legacy compatibility path.  Its
                # mutable metadata timestamp also changes when users merely
                # edit settings, so use the immutable import timestamp for
                # recent-project ordering until migration creates a project
                # record with its own activity_at value.
                "activity_at": getattr(video, "created_at", "") or video.updated_at,
            },
        )
        project["videos"].append(video)

    summaries = []
    for project in grouped.values():
        project_videos = project["videos"]
        if project["project_type"] == "batch":
            # The visual batch queue is defined by import order, never by a
            # volatile timestamp such as a processing completion.  Videos
            # created by older versions have no persisted order yet, so keep
            # their original creation order as a deterministic fallback.
            project_videos.sort(
                key=lambda video: (
                    0 if int(getattr(video, "batch_import_order", 0) or 0) > 0 else 1,
                    int(getattr(video, "batch_import_order", 0) or 0),
                    str(getattr(video, "created_at", "")),
                )
            )
        if not project_videos:
            summaries.append(
                {
                    **project,
                    "video_count": 0,
                    "status": "ready" if project["project_type"] in {"download", "publish"} else "empty",
                    "progress": 0,
                    "thumbnail_source": "",
                    "video_size": "",
                    "updated_at": project.get("updated_at", ""),
                }
            )
            continue
        statuses = {video.status for video in project_videos}
        if "processing" in statuses:
            status = "processing"
        elif "awaiting_review" in statuses:
            status = "awaiting_review"
        elif "paused" in statuses:
            status = "paused"
        elif "pending" in statuses:
            status = "pending"
        elif all(video.status == "done" for video in project_videos):
            status = "done"
        elif "failed" in statuses:
            status = "failed"
        elif "cancelled" in statuses:
            status = "cancelled"
        else:
            status = project_videos[0].status
        thumbnail_source = ""
        for video in project_videos:
            thumbnail_source = VideoListModel._thumbnail_source(video)
            if thumbnail_source:
                break
        summaries.append(
            {
                **project,
                "video_count": len(project_videos),
                "status": status,
                "progress": round(sum(video.progress for video in project_videos) / len(project_videos)),
                "thumbnail_source": thumbnail_source,
                "video_size": VideoListModel._video_size(project_videos[0]),
                "updated_at": max(video.updated_at for video in project_videos),
            }
        )
    return sorted(
        summaries,
        key=lambda project: project.get("activity_at") or project.get("updated_at", ""),
        reverse=True,
    )


def language_label(code: str, ui_language: str) -> str:
    for language_code, english_name, native_name in POPULAR_TARGET_LANGUAGES:
        if language_code == code:
            if ui_language == "vi":
                return VIETNAMESE_LANGUAGE_NAMES.get(language_code, native_name)
            return english_name
    return code


def format_duration(seconds) -> str:
    seconds = max(0, round(seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def format_memory_size(value: int) -> str:
    if not value:
        return "--"
    return f"{value / (1024**3):.1f} GB"


def voice_options_for_language(language_code: str, ui_language: str, provider: str = "omnivoice"):
    effective = "omnivoice" if provider in {"omnivoice", "auto", "vieneu"} else "edge"
    voices = (
        OMNIVOICE_TTS_VOICES
        if effective == "omnivoice"
        else EDGE_TTS_VOICES_BY_LANGUAGE.get(language_code) or EDGE_TTS_VOICES_BY_LANGUAGE["en"]
    )
    options = []
    for item in voices:
        voice, label = item[:2]
        category = item[2] if len(item) > 2 else "natural"
        options.append(
            {
                "voice": voice,
                "label": localized_voice_label(label, ui_language)
                if effective == "omnivoice"
                else f"{localized_voice_label(label, ui_language)} ({voice})",
                "category": category if effective == "omnivoice" else "natural",
                "categoryLabel": (
                    {"natural": "Tự nhiên", "narration": "Kể chuyện", "style": "Phong cách"}
                    if ui_language == "vi"
                    else {"natural": "Natural", "narration": "Narration", "style": "Styles"}
                ).get(category, category),
            }
        )
    return options


def localized_voice_label(label: str, ui_language: str) -> str:
    if ui_language != "vi":
        return label
    translations = {
        "Natural female": "Nữ tự nhiên",
        "Natural male": "Nam tự nhiên",
        "Warm female": "Nữ ấm",
        "Deep male": "Nam trầm",
        "Bright female": "Nữ sáng",
        "Bright male": "Nam sáng",
        "Mature female": "Nữ trưởng thành",
        "Mature male": "Nam trưởng thành",
        "Clear high female": "Nữ cao rõ",
        "Clear high male": "Nam cao rõ",
        "Female narrator": "Nữ kể chuyện",
        "Male narrator": "Nam kể chuyện",
        "Lively elder female": "Nữ lớn tuổi sinh động",
        "Lively elder male": "Nam lớn tuổi sinh động",
        "Elder narrator": "Giọng kể lớn tuổi",
        "Deep storyteller": "Giọng kể trầm",
        "Soft whisper": "Thì thầm nhẹ",
        "Deep whisper": "Thì thầm trầm",
        "Bright whisper": "Thì thầm sáng",
        "Elder whisper": "Thì thầm lớn tuổi",
        "Young voice": "Giọng trẻ",
        "Cartoon voice": "Hoạt hình",
        "Soft child": "Trẻ em nhẹ",
        "Low child voice": "Trẻ em trầm",
    }
    return translations.get(label, label.replace("Female", "Nữ").replace("Male", "Nam"))
