"""Qt list models used by the QML presentation layer."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from haizflow.desktop.media import thumbnail_source

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

    IsCreateCardRole = Qt.ItemDataRole.UserRole + 8

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
            }.get(role)
        return super().data(self.index(index.row() - 1, 0), role)

    def roleNames(self):
        roles = super().roleNames()
        roles[self.IsCreateCardRole] = b"isCreateCard"
        return roles


class TikTokPublishListModel(QAbstractListModel):
    """Stable ordered queue for project-owned Zernio TikTok posts."""

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
        }

    def set_items(self, items) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def item_at(self, row: int):
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]


class TikTokProjectSourceListModel(QAbstractListModel):
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
