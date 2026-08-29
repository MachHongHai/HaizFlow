"""Qt list models used by the QML presentation layer."""

from __future__ import annotations

import re

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    Property,
    QSortFilterProxyModel,
    Qt,
    Signal,
)

from haizflow.desktop.media import thumbnail_source


class ActivityEventModel(QAbstractListModel):
    """Bounded, user-facing activity stream derived from technical logs.

    Raw logs remain available for diagnostics.  This model deliberately keeps
    only short, stable events suitable for the compact activity tray.
    """

    TimestampRole = Qt.ItemDataRole.UserRole + 1
    SeverityRole = Qt.ItemDataRole.UserRole + 2
    StageRole = Qt.ItemDataRole.UserRole + 3
    TitleRole = Qt.ItemDataRole.UserRole + 4
    DetailRole = Qt.ItemDataRole.UserRole + 5
    ProgressRole = Qt.ItemDataRole.UserRole + 6
    CodeRole = Qt.ItemDataRole.UserRole + 7

    _LOG_PATTERN = re.compile(
        r"^(?P<time>\d{1,2}:\d{2}:\d{2})?\s*"
        r"(?:\[(?P<severity>INFO|WARNING|WARN|ERROR|DEBUG)\])?\s*"
        r"(?:\[(?P<stage>[^\]]+)\])?\s*(?P<detail>.*)$",
        re.IGNORECASE,
    )
    _PROGRESS_PATTERN = re.compile(r"(?P<done>\d+)\s*(?:/|of)\s*(?P<total>\d+)", re.IGNORECASE)
    _STAGE_TITLES = {
        "WHISPER": "Nhận dạng giọng nói",
        "WHISPERX": "Nhận dạng giọng nói",
        "TRANSCRIBE": "Nhận dạng giọng nói",
        "TRANSLATE": "Dịch phụ đề",
        "HYMT2": "Dịch phụ đề",
        "TTS": "Tạo giọng",
        "OMNIVOICE": "Tạo giọng",
        "EDGE_TTS": "Tạo giọng",
        "AUDIO": "Xử lý âm thanh",
        "SEPARATE": "Tách giọng",
        "OCR": "Nhận diện phụ đề gốc",
        "RENDER": "Dựng video",
        "FFMPEG": "Dựng video",
        "PIPELINE": "Xử lý video",
        "MODEL": "Tải model",
    }
    _STAGE_TITLES_EN = {
        "Nhận dạng giọng nói": "Speech recognition",
        "Dịch phụ đề": "Subtitle translation",
        "Tạo giọng": "Voice generation",
        "Xử lý âm thanh": "Audio processing",
        "Tách giọng": "Voice separation",
        "Nhận diện phụ đề gốc": "Original subtitle detection",
        "Dựng video": "Video rendering",
        "Xử lý video": "Video processing",
        "Tải model": "Model download",
    }

    def __init__(self, *, max_events: int = 120):
        super().__init__()
        self._max_events = max(20, int(max_events))
        self._events: list[dict] = []
        self._language = "vi"

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._events)

    def roleNames(self):
        return {
            self.TimestampRole: b"timestamp",
            self.SeverityRole: b"severity",
            self.StageRole: b"stage",
            self.TitleRole: b"title",
            self.DetailRole: b"detail",
            self.ProgressRole: b"progress",
            self.CodeRole: b"code",
        }

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._events):
            return None
        event = self._events[index.row()]
        role_key = {
            self.TimestampRole: "timestamp",
            self.SeverityRole: "severity",
            self.StageRole: "stage",
            self.TitleRole: "title",
            self.DetailRole: "detail",
            self.ProgressRole: "progress",
            self.CodeRole: "code",
        }.get(role)
        value = event.get(role_key) if role_key else None
        if role == self.TitleRole and self._language == "en":
            return self._STAGE_TITLES_EN.get(str(value), str(value))
        return value

    def set_language(self, language: str) -> None:
        normalized = "vi" if str(language or "").lower().startswith("vi") else "en"
        if normalized == self._language:
            return
        self._language = normalized
        if not self._events:
            return
        first = self.index(0, 0)
        last = self.index(len(self._events) - 1, 0)
        self.dataChanged.emit(first, last, [self.TitleRole])

    def clear(self) -> None:
        if not self._events:
            return
        self.beginResetModel()
        self._events.clear()
        self.endResetModel()

    def replace_text(self, text: str) -> None:
        events = [event for line in str(text or "").splitlines() if (event := self._parse_line(line))]
        self.beginResetModel()
        self._events = events[-self._max_events :]
        self.endResetModel()

    def append_lines(self, lines) -> None:
        for raw_line in lines:
            for line in str(raw_line or "").splitlines():
                event = self._parse_line(line)
                if event:
                    self._append_event(event)

    def _append_event(self, event: dict) -> None:
        # Heartbeat lines should update one row instead of creating a noisy feed.
        if self._events and event["code"] == self._events[-1]["code"] and event["code"].endswith(".working"):
            self._events[-1] = event
            row = len(self._events) - 1
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, list(self.roleNames()))
            return
        if len(self._events) >= self._max_events:
            remove_count = len(self._events) - self._max_events + 1
            self.beginRemoveRows(QModelIndex(), 0, remove_count - 1)
            del self._events[:remove_count]
            self.endRemoveRows()
        row = len(self._events)
        self.beginInsertRows(QModelIndex(), row, row)
        self._events.append(event)
        self.endInsertRows()

    @classmethod
    def _parse_line(cls, line: str) -> dict | None:
        text = str(line or "").strip()
        if not text or text.startswith("__"):
            return None
        match = cls._LOG_PATTERN.match(text)
        if not match:
            return None
        severity = (match.group("severity") or "INFO").lower()
        if severity == "warn":
            severity = "warning"
        stage = (match.group("stage") or "PIPELINE").strip().upper().replace(" ", "_")
        detail = match.group("detail").strip()
        if severity == "debug" or not detail:
            return None
        title = cls._STAGE_TITLES.get(stage, cls._STAGE_TITLES.get(stage.split("_")[0], "Xử lý video"))
        progress_match = cls._PROGRESS_PATTERN.search(detail)
        progress = -1
        if progress_match:
            done = int(progress_match.group("done"))
            total = max(1, int(progress_match.group("total")))
            progress = max(0, min(100, round(done * 100 / total)))
        lowered = detail.casefold()
        suffix = ".working" if "still working" in lowered or "đang xử lý" in lowered else ".event"
        return {
            "timestamp": match.group("time") or "",
            "severity": "error" if severity == "error" else "warning" if severity == "warning" else "info",
            "stage": stage,
            "title": title,
            "detail": cls._friendly_detail(detail, severity),
            "progress": progress,
            "code": f"{stage.lower()}{suffix}",
        }

    @staticmethod
    def _friendly_detail(detail: str, severity: str) -> str:
        compact = " ".join(str(detail or "").split())
        if len(compact) > 180:
            compact = compact[:177].rstrip() + "…"
        if severity == "error" and not compact.lower().startswith(("lỗi", "error")):
            return f"Lỗi: {compact}"
        return compact

class VideoListModel(QAbstractListModel):
    VideoIdRole = Qt.ItemDataRole.UserRole + 1
    FileRole = Qt.ItemDataRole.UserRole + 2
    ModeRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    StepRole = Qt.ItemDataRole.UserRole + 5
    UpdatedRole = Qt.ItemDataRole.UserRole + 6
    ProgressRole = Qt.ItemDataRole.UserRole + 7
    ThumbnailRole = Qt.ItemDataRole.UserRole + 8
    ProjectNameRole = Qt.ItemDataRole.UserRole + 9
    VideoSizeRole = Qt.ItemDataRole.UserRole + 10

    def __init__(self):
        super().__init__()
        self._videos = []
        self._role_snapshots = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._videos)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._videos):
            return None
        return self._role_snapshots[index.row()].get(role)

    def _role_values(self, video):
        return {
            self.VideoIdRole: video.video_id,
            self.FileRole: video.original_filename,
            self.ModeRole: "Full Auto",
            self.StatusRole: video.status,
            self.StepRole: video.step,
            self.UpdatedRole: video.updated_at,
            self.ProgressRole: video.progress,
            self.ThumbnailRole: self._thumbnail_source(video),
            self.ProjectNameRole: video.project_name or video.original_filename,
            self.VideoSizeRole: self._video_size(video),
        }

    def roleNames(self):
        return {
            self.VideoIdRole: b"videoId",
            self.FileRole: b"fileName",
            self.ModeRole: b"mode",
            self.StatusRole: b"status",
            self.StepRole: b"step",
            self.UpdatedRole: b"updatedAt",
            self.ProgressRole: b"progress",
            self.ThumbnailRole: b"thumbnailSource",
            self.ProjectNameRole: b"projectName",
            self.VideoSizeRole: b"videoSize",
        }

    def set_videos(self, videos):
        current_ids = [video.video_id for video in self._videos]
        next_ids = [video.video_id for video in videos]
        if current_ids == next_ids:
            changed_rows = []
            updated_snapshots = [self._role_values(video) for video in videos]
            for row, updated_values in enumerate(updated_snapshots):
                current_values = self._role_snapshots[row]
                changed_roles = [role for role in current_values if current_values[role] != updated_values[role]]
                if changed_roles:
                    changed_rows.append((row, changed_roles))
            self._videos = videos
            self._role_snapshots = updated_snapshots
            for row, roles in changed_rows:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, roles)
            return
        self.beginResetModel()
        self._videos = videos
        self._role_snapshots = [self._role_values(video) for video in videos]
        self.endResetModel()

    def update_video(self, video) -> bool:
        """Update one visible row without rebuilding a large view model."""
        for row, existing in enumerate(self._videos):
            if existing.video_id != video.video_id:
                continue
            updated_values = self._role_values(video)
            previous_values = self._role_snapshots[row]
            changed_roles = [role for role in previous_values if previous_values[role] != updated_values[role]]
            self._videos[row] = video
            self._role_snapshots[row] = updated_values
            if changed_roles:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, changed_roles)
            return True
        return False

    def video_at(self, row: int):
        if row < 0 or row >= len(self._videos):
            return None
        return self._videos[row]

    @staticmethod
    def _thumbnail_source(video):
        path = video.files.get("thumbnail") if video else ""
        return thumbnail_source(path)

    @staticmethod
    def _video_size(video):
        width = int(getattr(video, "video_width", 0) or 0)
        height = int(getattr(video, "video_height", 0) or 0)
        return f"{width} x {height}" if width and height else ""


class ProjectListModel(QAbstractListModel):
    ProjectNameRole = Qt.ItemDataRole.UserRole + 1
    ProjectTypeRole = Qt.ItemDataRole.UserRole + 2
    VideoCountRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    ThumbnailRole = Qt.ItemDataRole.UserRole + 6
    VideoSizeRole = Qt.ItemDataRole.UserRole + 7
    UpdatedAtRole = Qt.ItemDataRole.UserRole + 8
    ActivityAtRole = Qt.ItemDataRole.UserRole + 9

    def __init__(self):
        super().__init__()
        self._projects = []
        self._role_snapshots = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._projects)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._projects):
            return None
        return self._role_snapshots[index.row()].get(role)

    def _role_values(self, project):
        return {
            self.ProjectNameRole: project["project_name"],
            self.ProjectTypeRole: project["project_type"],
            self.VideoCountRole: project["video_count"],
            self.StatusRole: project["status"],
            self.ProgressRole: project["progress"],
            self.ThumbnailRole: project["thumbnail_source"],
            self.VideoSizeRole: project.get("video_size", ""),
            self.UpdatedAtRole: project.get("updated_at", ""),
            self.ActivityAtRole: project.get("activity_at", project.get("updated_at", "")),
        }

    def roleNames(self):
        return {
            self.ProjectNameRole: b"projectName",
            self.ProjectTypeRole: b"projectType",
            self.VideoCountRole: b"videoCount",
            self.StatusRole: b"status",
            self.ProgressRole: b"progress",
            self.ThumbnailRole: b"thumbnailSource",
            self.VideoSizeRole: b"videoSize",
            self.UpdatedAtRole: b"updatedAt",
            self.ActivityAtRole: b"activityAt",
        }

    def set_projects(self, projects):
        next_keys = [project["key"] for project in projects]
        current_keys = [project["key"] for project in self._projects]
        if current_keys == next_keys:
            changed_rows = []
            updated_snapshots = [self._role_values(project) for project in projects]
            for row, updated_values in enumerate(updated_snapshots):
                current_values = self._role_snapshots[row]
                changed_roles = [role for role in current_values if current_values[role] != updated_values[role]]
                if changed_roles:
                    changed_rows.append((row, changed_roles))
            self._projects = projects
            self._role_snapshots = updated_snapshots
            for row, roles in changed_rows:
                index = self.index(self._project_row_to_model_row(row), 0)
                self.dataChanged.emit(index, index, roles)
            return
        self.beginResetModel()
        self._projects = projects
        self._role_snapshots = [self._role_values(project) for project in projects]
        self.endResetModel()

    def update_project(self, project) -> bool:
        for row, existing in enumerate(self._projects):
            if existing["key"] != project["key"]:
                continue
            updated_values = self._role_values(project)
            previous_values = self._role_snapshots[row]
            changed_roles = [role for role in previous_values if previous_values[role] != updated_values[role]]
            self._projects[row] = project
            self._role_snapshots[row] = updated_values
            if changed_roles:
                index = self.index(self._project_row_to_model_row(row), 0)
                self.dataChanged.emit(index, index, changed_roles)
            return True
        return False

    def _project_row_to_model_row(self, row: int) -> int:
        """Map a persisted-project row to the row exposed to a view."""
        return row

    def project_at(self, row: int):
        if row < 0 or row >= len(self._projects):
            return None
        return self._projects[row]


class ProjectGridModel(ProjectListModel):
    """Project model with a synthetic first cell for creating a project."""

    IsCreateCardRole = Qt.ItemDataRole.UserRole + 10

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._projects) + 1

    def _project_row_to_model_row(self, row: int) -> int:
        # Row zero is the synthetic "create project" card.
        return row + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= self.rowCount():
            return None
        if role == self.IsCreateCardRole:
            return index.row() == 0
        if index.row() == 0:
            return {
                self.ProjectNameRole: "",
                self.ProjectTypeRole: "",
                self.VideoCountRole: 0,
                self.StatusRole: "",
                self.ProgressRole: 0,
                self.ThumbnailRole: "",
                self.VideoSizeRole: "",
                self.UpdatedAtRole: "",
                self.ActivityAtRole: "",
            }.get(role)
        return super().data(self.index(index.row() - 1, 0), role)

    def roleNames(self):
        roles = super().roleNames()
        roles[self.IsCreateCardRole] = b"isCreateCard"
        return roles


class ProjectBrowserProxyModel(QSortFilterProxyModel):
    """Search, filter and activity-sort projects without copying QML data.

    The source model remains the canonical aggregate project catalog.  Keeping
    filtering here avoids transient QML ListModels and preserves stable source
    rows for project selection.
    """

    queryChanged = Signal()
    typeFilterChanged = Signal()
    statusFilterChanged = Signal()
    sortModeChanged = Signal()

    def __init__(self, source_model: ProjectListModel):
        super().__init__()
        self._query = ""
        self._type_filter = "all"
        self._status_filter = "all"
        self._sort_mode = "activity"
        self.setSourceModel(source_model)
        self.setDynamicSortFilter(True)
        self.sort(0, Qt.SortOrder.DescendingOrder)

    def _refilter(self) -> None:
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    @Property(str, notify=queryChanged)
    def query(self) -> str:
        return self._query

    @query.setter
    def query(self, value: str) -> None:
        normalized = str(value or "").strip().casefold()
        if normalized == self._query:
            return
        self._query = normalized
        self.queryChanged.emit()
        self._refilter()

    @Property(str, notify=typeFilterChanged)
    def typeFilter(self) -> str:
        return self._type_filter

    @typeFilter.setter
    def typeFilter(self, value: str) -> None:
        normalized = str(value or "all").strip().lower()
        if normalized == self._type_filter:
            return
        self._type_filter = normalized
        self.typeFilterChanged.emit()
        self._refilter()

    @Property(str, notify=statusFilterChanged)
    def statusFilter(self) -> str:
        return self._status_filter

    @statusFilter.setter
    def statusFilter(self, value: str) -> None:
        normalized = str(value or "all").strip().lower()
        if normalized == self._status_filter:
            return
        self._status_filter = normalized
        self.statusFilterChanged.emit()
        self._refilter()

    @Property(str, notify=sortModeChanged)
    def sortMode(self) -> str:
        return self._sort_mode

    @sortMode.setter
    def sortMode(self, value: str) -> None:
        normalized = str(value or "activity").strip().lower()
        if normalized == self._sort_mode:
            return
        self._sort_mode = normalized
        self.sortModeChanged.emit()
        self.invalidate()
        self.sort(0, Qt.SortOrder.AscendingOrder if normalized == "name" else Qt.SortOrder.DescendingOrder)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        project_name = str(model.data(index, ProjectListModel.ProjectNameRole) or "")
        project_type = str(model.data(index, ProjectListModel.ProjectTypeRole) or "").lower()
        status = str(model.data(index, ProjectListModel.StatusRole) or "").lower()
        if project_type not in {"single", "manual", "batch", "download", "publish"}:
            return False
        if self._query and self._query not in project_name.casefold():
            return False
        if self._type_filter != "all" and project_type != self._type_filter:
            return False
        if self._status_filter != "all" and status != self._status_filter:
            return False
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        model = self.sourceModel()
        if self._sort_mode == "name":
            left_value = str(model.data(left, ProjectListModel.ProjectNameRole) or "").casefold()
            right_value = str(model.data(right, ProjectListModel.ProjectNameRole) or "").casefold()
        else:
            left_value = str(model.data(left, ProjectListModel.ActivityAtRole) or "")
            right_value = str(model.data(right, ProjectListModel.ActivityAtRole) or "")
        return left_value < right_value

    def project_at(self, row: int):
        proxy_index = self.index(row, 0)
        if not proxy_index.isValid():
            return None
        source_index = self.mapToSource(proxy_index)
        source = self.sourceModel()
        return source.project_at(source_index.row())


class SocialPublishListModel(QAbstractListModel):
    """Stable ordered queue for project-owned Zernio social posts."""

    ItemIdRole = Qt.ItemDataRole.UserRole + 1
    FileNameRole = Qt.ItemDataRole.UserRole + 2
    FilePathRole = Qt.ItemDataRole.UserRole + 3
    CaptionRole = Qt.ItemDataRole.UserRole + 4
    HashtagsRole = Qt.ItemDataRole.UserRole + 5
    PostTextRole = Qt.ItemDataRole.UserRole + 6
    StatusRole = Qt.ItemDataRole.UserRole + 7
    ErrorRole = Qt.ItemDataRole.UserRole + 8
    ThumbnailRole = Qt.ItemDataRole.UserRole + 9
    ProgressRole = Qt.ItemDataRole.UserRole + 10
    PostIdRole = Qt.ItemDataRole.UserRole + 11
    PlatformUrlRole = Qt.ItemDataRole.UserRole + 12
    TargetPlatformRole = Qt.ItemDataRole.UserRole + 13
    PlatformUrlVerifiedRole = Qt.ItemDataRole.UserRole + 14

    _ROLE_FIELDS = {
        ItemIdRole: "id",
        FileNameRole: "file_name",
        FilePathRole: "file_path",
        CaptionRole: "caption",
        HashtagsRole: "hashtags",
        PostTextRole: "post_text",
        StatusRole: "status",
        ErrorRole: "error",
        ThumbnailRole: "thumbnail_source",
        ProgressRole: "upload_progress",
        PostIdRole: "zernio_post_id",
        PlatformUrlRole: "platform_post_url",
        TargetPlatformRole: "target_platform",
        PlatformUrlVerifiedRole: "platform_post_url_verified",
    }

    def __init__(self):
        super().__init__()
        self._items = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        return {
            self.ItemIdRole: item["id"],
            self.FileNameRole: item["file_name"],
            self.FilePathRole: item["file_path"],
            self.CaptionRole: item["caption"],
            self.HashtagsRole: item["hashtags"],
            self.PostTextRole: item["post_text"],
            self.StatusRole: item["status"],
            self.ErrorRole: item["error"],
            self.ThumbnailRole: item["thumbnail_source"],
            self.ProgressRole: item.get("upload_progress", 0),
            self.PostIdRole: item.get("zernio_post_id", ""),
            self.PlatformUrlRole: item.get("platform_post_url", ""),
            self.TargetPlatformRole: item.get("target_platform", ""),
            self.PlatformUrlVerifiedRole: bool(item.get("platform_post_url_verified", False)),
        }.get(role)

    def roleNames(self):
        return {
            self.ItemIdRole: b"itemId",
            self.FileNameRole: b"fileName",
            self.FilePathRole: b"filePath",
            self.CaptionRole: b"caption",
            self.HashtagsRole: b"hashtags",
            self.PostTextRole: b"postText",
            self.StatusRole: b"publishStatus",
            self.ErrorRole: b"publishError",
            self.ThumbnailRole: b"thumbnailSource",
            self.ProgressRole: b"uploadProgress",
            self.PostIdRole: b"zernioPostId",
            self.PlatformUrlRole: b"platformPostUrl",
            self.TargetPlatformRole: b"targetPlatform",
            self.PlatformUrlVerifiedRole: b"platformPostUrlVerified",
        }

    def set_items(self, items) -> None:
        updated_items = [dict(item) for item in items]
        current_ids = [str(item.get("id") or "") for item in self._items]
        updated_ids = [str(item.get("id") or "") for item in updated_items]
        if current_ids != updated_ids:
            self.beginResetModel()
            self._items = updated_items
            self.endResetModel()
            return

        for row, updated in enumerate(updated_items):
            previous = self._items[row]
            changed_roles = [
                role for role, field in self._ROLE_FIELDS.items()
                if previous.get(field) != updated.get(field)
            ]
            if not changed_roles:
                continue
            self._items[row] = updated
            model_index = self.index(row, 0)
            self.dataChanged.emit(model_index, model_index, changed_roles)

    def update_item(self, item_id: str, item) -> bool:
        """Update one queue row without resetting the whole GridView."""
        row = next(
            (index for index, candidate in enumerate(self._items) if candidate.get("id") == item_id),
            -1,
        )
        if row < 0:
            return False
        updated = dict(item)
        previous = self._items[row]
        changed_roles = [
            role for role, field in self._ROLE_FIELDS.items()
            if previous.get(field) != updated.get(field)
        ]
        if not changed_roles:
            return True
        self._items[row] = updated
        model_index = self.index(row, 0)
        self.dataChanged.emit(model_index, model_index, changed_roles)
        return True

    def item_at(self, row: int):
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]


class SocialProjectSourceListModel(QAbstractListModel):
    """Completed single and batch outputs that can be copied into a publish project."""

    VideoIdRole = Qt.ItemDataRole.UserRole + 1
    ProjectNameRole = Qt.ItemDataRole.UserRole + 2
    ProjectTypeRole = Qt.ItemDataRole.UserRole + 3
    FileNameRole = Qt.ItemDataRole.UserRole + 4
    ThumbnailRole = Qt.ItemDataRole.UserRole + 5
    VideoSizeRole = Qt.ItemDataRole.UserRole + 6
    SelectedRole = Qt.ItemDataRole.UserRole + 7
    VideoCountRole = Qt.ItemDataRole.UserRole + 8

    def __init__(self):
        super().__init__()
        self._items = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        return {
            self.VideoIdRole: item["video_id"],
            self.ProjectNameRole: item["project_name"],
            self.ProjectTypeRole: item["project_type"],
            self.FileNameRole: item["file_name"],
            self.ThumbnailRole: item["thumbnail_source"],
            self.VideoSizeRole: item["video_size"],
            self.SelectedRole: item["selected"],
            self.VideoCountRole: item.get("video_count", 1),
        }.get(role)

    def roleNames(self):
        return {
            self.VideoIdRole: b"videoId",
            self.ProjectNameRole: b"projectName",
            self.ProjectTypeRole: b"projectType",
            self.FileNameRole: b"fileName",
            self.ThumbnailRole: b"thumbnailSource",
            self.VideoSizeRole: b"videoSize",
            self.SelectedRole: b"sourceSelected",
            self.VideoCountRole: b"sourceVideoCount",
        }

    def set_items(self, items) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def set_selected(self, row: int, selected: bool) -> bool:
        if row < 0 or row >= len(self._items):
            return False
        value = bool(selected)
        if self._items[row]["selected"] == value:
            return True
        self._items[row]["selected"] = value
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [self.SelectedRole])
        return True


class DownloadProjectSourceListModel(QAbstractListModel):
    """Videos downloaded by HaizFlow that can be copied into processing projects."""

    ItemIdRole = Qt.ItemDataRole.UserRole + 1
    ProjectNameRole = Qt.ItemDataRole.UserRole + 2
    CategoryRole = Qt.ItemDataRole.UserRole + 3
    FileNameRole = Qt.ItemDataRole.UserRole + 4
    FilePathRole = Qt.ItemDataRole.UserRole + 5
    FileSizeRole = Qt.ItemDataRole.UserRole + 6
    SelectedRole = Qt.ItemDataRole.UserRole + 7

    def __init__(self):
        super().__init__()
        self._items: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        return {
            self.ItemIdRole: item["item_id"],
            self.ProjectNameRole: item["project_name"],
            self.CategoryRole: item["category"],
            self.FileNameRole: item["file_name"],
            self.FilePathRole: item["file_path"],
            self.FileSizeRole: item["file_size"],
            self.SelectedRole: item["selected"],
        }.get(role)

    def roleNames(self):
        return {
            self.ItemIdRole: b"downloadItemId",
            self.ProjectNameRole: b"downloadProjectName",
            self.CategoryRole: b"downloadCategory",
            self.FileNameRole: b"downloadFileName",
            self.FilePathRole: b"downloadFilePath",
            self.FileSizeRole: b"downloadFileSize",
            self.SelectedRole: b"downloadSelected",
        }

    def set_items(self, items) -> None:
        self.beginResetModel()
        self._items = [{**item, "selected": bool(item.get("selected", False))} for item in items]
        self.endResetModel()

    def set_selected(self, row: int, selected: bool, *, exclusive: bool = False) -> bool:
        if row < 0 or row >= len(self._items):
            return False
        changed_rows: list[int] = []
        if exclusive and selected:
            for index, item in enumerate(self._items):
                desired = index == row
                if item["selected"] != desired:
                    item["selected"] = desired
                    changed_rows.append(index)
        else:
            value = bool(selected)
            if self._items[row]["selected"] != value:
                self._items[row]["selected"] = value
                changed_rows.append(row)
        for changed_row in changed_rows:
            model_index = self.index(changed_row, 0)
            self.dataChanged.emit(model_index, model_index, [self.SelectedRole])
        return True

    def selected_items(self) -> list[dict]:
        return [dict(item) for item in self._items if item["selected"]]

    @property
    def selected_count(self) -> int:
        return sum(1 for item in self._items if item["selected"])


class ChannelCandidateListModel(QAbstractListModel):
    CandidateIdRole = Qt.ItemDataRole.UserRole + 1
    SelectedRole = Qt.ItemDataRole.UserRole + 2
    TitleRole = Qt.ItemDataRole.UserRole + 3
    PlatformRole = Qt.ItemDataRole.UserRole + 4
    UploaderRole = Qt.ItemDataRole.UserRole + 5
    DurationRole = Qt.ItemDataRole.UserRole + 6
    PublishedRole = Qt.ItemDataRole.UserRole + 7
    ViewCountRole = Qt.ItemDataRole.UserRole + 8
    ThumbnailRole = Qt.ItemDataRole.UserRole + 9
    DuplicateRole = Qt.ItemDataRole.UserRole + 10
    StatusRole = Qt.ItemDataRole.UserRole + 11
    ProgressRole = Qt.ItemDataRole.UserRole + 12
    ErrorRole = Qt.ItemDataRole.UserRole + 13

    def __init__(self):
        super().__init__()
        self._candidates = []
        self._rows_by_candidate_id = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._candidates)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._candidates):
            return None
        candidate = self._candidates[index.row()]
        return {
            self.CandidateIdRole: candidate.remote_video_id,
            self.SelectedRole: candidate.selected,
            self.TitleRole: candidate.title,
            self.PlatformRole: candidate.platform,
            self.UploaderRole: candidate.uploader,
            self.DurationRole: candidate.duration_label,
            self.PublishedRole: candidate.published_label,
            self.ViewCountRole: candidate.view_count_label,
            self.ThumbnailRole: candidate.thumbnail_url,
            self.DuplicateRole: candidate.duplicate,
            self.StatusRole: candidate.status,
            self.ProgressRole: candidate.progress,
            self.ErrorRole: candidate.error,
        }.get(role)

    def roleNames(self):
        return {
            self.CandidateIdRole: b"candidateId",
            self.SelectedRole: b"selected",
            self.TitleRole: b"title",
            self.PlatformRole: b"platform",
            self.UploaderRole: b"uploader",
            self.DurationRole: b"durationLabel",
            self.PublishedRole: b"publishedLabel",
            self.ViewCountRole: b"viewCountLabel",
            self.ThumbnailRole: b"thumbnailSource",
            self.DuplicateRole: b"duplicate",
            self.StatusRole: b"candidateStatus",
            self.ProgressRole: b"candidateProgress",
            self.ErrorRole: b"candidateError",
        }

    def set_candidates(self, candidates):
        self.beginResetModel()
        self._candidates = list(candidates)
        self._rows_by_candidate_id = {
            candidate.remote_video_id: row for row, candidate in enumerate(self._candidates)
        }
        self.endResetModel()

    def candidate_at(self, row: int):
        if row < 0 or row >= len(self._candidates):
            return None
        return self._candidates[row]

    def candidates(self):
        return list(self._candidates)

    def update_candidate(self, remote_video_id: str, roles=None) -> None:
        row = self._rows_by_candidate_id.get(remote_video_id)
        if row is None:
            return
        index = self.index(row, 0)
        changed_roles = list(self.roleNames().keys()) if roles is None else list(roles)
        self.dataChanged.emit(index, index, changed_roles)
