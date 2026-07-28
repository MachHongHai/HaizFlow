"""Preview and thumbnail state kept outside the QML singleton facade."""

from __future__ import annotations

import os
import shutil

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.services import video_store


class PreviewMediaController:
    """Own thumbnail and preview-media housekeeping for one desktop controller."""

    def __init__(self, host):
        self._host = host

    def draft_thumbnail_path(self) -> str:
        host = self._host
        if not host.hasOpenProject:
            return ""
        return os.path.join(host._selected_project_root(), ".input-thumbnail.jpg")

    def assign_project_thumbnail(self, video) -> None:
        host = self._host
        input_path = (video.files or {}).get("video_input")
        if not isinstance(input_path, str) or not input_path.strip():
            raise RuntimeError("Video metadata is missing its input-video path.")
        thumbnail_path = host._create_video_thumbnail_path(
            input_path,
            host._video_thumbnail_path(video.video_id),
        )
        if thumbnail_path:
            video.files["thumbnail"] = thumbnail_path
            video_store.save_video(video)
        draft_thumbnail = self.draft_thumbnail_path()
        if draft_thumbnail and os.path.isfile(draft_thumbnail):
            try:
                os.remove(draft_thumbnail)
            except OSError:
                pass

    def migrate_legacy_project_thumbnails(self) -> None:
        host = self._host
        legacy_directory = os.path.join(RUNTIME_DATA_DIR, "cache", "thumbnails")
        video_store.migrate_legacy_thumbnails(legacy_directory)
        for video in video_store.list_videos():
            expected_path = host._video_thumbnail_path(video.video_id)
            changed = False
            if not os.path.exists(expected_path):
                source_path = host._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
                created_path = host._create_video_thumbnail_path(source_path, expected_path)
                if created_path:
                    video.files["thumbnail"] = created_path
                    changed = True
            if changed:
                video_store.save_video(video)
        if os.path.isdir(legacy_directory):
            try:
                shutil.rmtree(legacy_directory)
            except OSError:
                pass
