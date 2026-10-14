"""One successful subtitle/voice warning per project per app session."""

from collections.abc import Callable


class SubtitleVoiceEditNotice:
    def __init__(self, show_alert: Callable[[str, str, str], None]):
        self._show_alert = show_alert
        self._warned_projects: set[str] = set()
        self._pending: dict[tuple[str, str, str], str] = {}

    def prepare(self, project_key: str, video_id: str, segment_id: str, request_id: str) -> None:
        context = str(project_key or video_id)
        if context not in self._warned_projects:
            self._pending[(video_id, segment_id, request_id)] = context

    def failed(self, video_id: str, segment_id: str, request_id: str) -> None:
        self._pending.pop((video_id, segment_id, request_id), None)

    def saved(self, video_id: str, segment_id: str, request_id: str) -> None:
        context = self._pending.pop((video_id, segment_id, request_id), None)
        if context is None or context in self._warned_projects:
            return
        self._warned_projects.add(context)
        self._show_alert(
            "Cần tạo lại giọng",
            "Hãy tạo lại giọng cho câu vừa sửa phụ đề. Giọng của các câu khác được giữ nguyên.",
            "warning",
        )
