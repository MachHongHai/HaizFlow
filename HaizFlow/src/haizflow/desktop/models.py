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
    SubtitleOverrideRole = Qt.ItemDataRole.UserRole + 11

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
            self.SubtitleOverrideRole: bool(getattr(video, "subtitle_override", False)),
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
            self.SubtitleOverrideRole: b"subtitleOverride",
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
        return f"{width} x {height}" if width and height else "Unknown size"


class ProjectListModel(QAbstractListModel):
    ProjectNameRole = Qt.ItemDataRole.UserRole + 1
    ProjectTypeRole = Qt.ItemDataRole.UserRole + 2
    VideoCountRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    ThumbnailRole = Qt.ItemDataRole.UserRole + 6

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
        }

    def roleNames(self):
        return {
            self.ProjectNameRole: b"projectName",
            self.ProjectTypeRole: b"projectType",
            self.VideoCountRole: b"videoCount",
            self.StatusRole: b"status",
            self.ProgressRole: b"progress",
            self.ThumbnailRole: b"thumbnailSource",
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

    IsCreateCardRole = Qt.ItemDataRole.UserRole + 7

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
            }.get(role)
        return super().data(self.index(index.row() - 1, 0), role)

    def roleNames(self):
        roles = super().roleNames()
        roles[self.IsCreateCardRole] = b"isCreateCard"
        return roles


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
        self.endResetModel()

    def candidate_at(self, row: int):
        if row < 0 or row >= len(self._candidates):
            return None
        return self._candidates[row]

    def candidates(self):
        return list(self._candidates)

    def update_candidate(self, remote_video_id: str) -> None:
        for row, candidate in enumerate(self._candidates):
            if candidate.remote_video_id == remote_video_id:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, list(self.roleNames().keys()))
                return
