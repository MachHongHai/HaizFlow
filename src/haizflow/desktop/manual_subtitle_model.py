"""Revisioned Manual subtitle editing, independent of project-list refreshes."""
from __future__ import annotations

import copy
import json
import os
import uuid
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Property, QAbstractListModel, QModelIndex, Qt, Signal, Slot

from haizflow.services import video_store


def identify_segments(video_id: str, segments: list[dict]) -> list[dict]:
    result = copy.deepcopy(segments)
    for index, item in enumerate(result):
        item.setdefault("segment_id", uuid.uuid5(uuid.NAMESPACE_URL,
            f"haizflow:{video_id}:{index}:{item.get('start', 0)}:{item.get('end', 0)}").hex)
        item.setdefault("revision", 0)
    return result


def write_document(path: Path, segments: list[dict], revision: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump({"schema_version": 2, "revision": revision, "segments": segments},
                  stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class ManualSubtitleModel(QAbstractListModel):
    changed = Signal()
    saved = Signal(str, int, str)
    saveFailed = Signal(str, str, str)
    published = Signal(str, int, bool)
    _completed = Signal(object)
    _roles = ("segmentId", "text", "startMs", "endMs", "revision", "saveState", "voiceState")

    def __init__(self, parent=None, history=None):
        super().__init__(parent)
        self.video_id = ""
        self._segments = []
        self._revision = 0
        self._states = {}
        self._history = history
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="subtitle-save")
        self._completed.connect(self._accept_result)

    def roleNames(self):
        return {Qt.UserRole + i + 1: name.encode() for i, name in enumerate(self._roles)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._segments)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._segments):
            return None
        item = self._segments[index.row()]
        values = (item["segment_id"], item.get("text", ""), round(item.get("start", 0) * 1000),
                  round(item.get("end", 0) * 1000), item.get("revision", 0),
                  self._states.get(item["segment_id"], "saved"), "ready")
        offset = role - Qt.UserRole - 1
        return values[offset] if 0 <= offset < len(values) else None

    @Property("QVariantList", notify=changed)
    def segments(self):
        return copy.deepcopy(self._segments)

    @Property(int, notify=changed)
    def revision(self):
        return self._revision

    def load(self, video_id: str, segments: list[dict]):
        identified = identify_segments(video_id, segments)
        # A background cache/status notification must never replace a live draft.
        if video_id == self.video_id and any(s in {"saving", "error"} for s in self._states.values()):
            return
        if video_id == self.video_id and identified == self._segments:
            return
        if self._history is not None:
            self._history.select_video(video_id)
        self.beginResetModel()
        self.video_id = video_id
        self._segments = identified
        self._revision = max((int(s.get("revision", 0)) for s in identified), default=0)
        self._states.clear()
        self.endResetModel()
        self.changed.emit()

    @Slot(str, str, int, str, result=bool)
    def saveText(self, segment_id, text, expected_revision, request_id):
        for index, current in enumerate(self._segments):
            if current["segment_id"] != segment_id:
                continue
            if int(current.get("revision", 0)) != expected_revision:
                self.saveFailed.emit(segment_id, request_id, "Nội dung đã thay đổi. Bản đang nhập vẫn được giữ.")
                return False
            if text == current.get("text", "") and self._states.get(segment_id, "saved") != "error":
                self.saved.emit(segment_id, expected_revision, request_id)
                return True
            next_segments = copy.deepcopy(self._segments)
            next_segments[index]["text"] = text
            return self._submit(next_segments, index, request_id, True, "subtitle_text")
        self.saveFailed.emit(segment_id, request_id, "Không tìm thấy đoạn phụ đề.")
        return False

    @Slot(str, float, float, result=bool)
    def saveTiming(self, segment_id, start, end):
        if start < 0 or end - start < 0.12:
            return False
        for index, current in enumerate(self._segments):
            if current["segment_id"] == segment_id:
                items = copy.deepcopy(self._segments)
                items[index].update(start=start, end=end, timeline_edited=True)
                if abs(end - start - (current["end"] - current["start"])) > .001:
                    items[index]["fit_voice_to_timing"] = True
                return self._submit(items, index, "timing", False, "subtitle_timing")
        return False

    def _submit(self, items, index, request_id, text_changed, history_label="", record_history=True):
        if self._closed:
            return False
        before = copy.deepcopy(self._segments[index])
        after = copy.deepcopy(items[index])
        if record_history and self._history is not None and not self._history.replaying:
            segment_id = str(before["segment_id"])
            kind = "text" if text_changed else "timing"
            merge_key = f"{kind}:{segment_id}"
            self._history.record(
                history_label,
                lambda: self._restore_segment(segment_id, before, text_changed),
                lambda: self._restore_segment(segment_id, after, text_changed),
                merge_key=merge_key,
                context_id=f"video:{self.video_id}",
            )
        self._revision += 1
        items[index]["revision"] = self._revision
        self._segments = items
        segment_id = items[index]["segment_id"]
        revision = self._revision
        self._states[segment_id] = "saving"
        self.dataChanged.emit(self.index(index), self.index(index))
        self.changed.emit()
        video_id = self.video_id
        snapshot = copy.deepcopy(items)

        def persist():
            try:
                from haizflow.pipeline.manual_tools import publish_edited_subtitles
                from haizflow.services.manual_artifacts import cache_root
                path = cache_root(video_id) / "working" / "document.json"
                video = video_store.get_video(video_id)
                old_path = Path(str((video.files or {}).get("transcript_json", ""))) if video else None
                if not path.exists() and old_path and old_path.is_file():
                    backup = path.parent / "pre-migration-segments.json"
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    if not backup.exists():
                        backup.write_bytes(old_path.read_bytes())
                write_document(path, snapshot, revision)
                publish_edited_subtitles(video_id, snapshot)
                return (video_id, segment_id, revision, request_id, text_changed, "")
            except Exception as exc:
                return (video_id, segment_id, revision, request_id, text_changed, str(exc))

        def complete(future):
            try:
                result = future.result()
            except CancelledError:
                return
            if not self._closed:
                self._completed.emit(result)

        self._executor.submit(persist).add_done_callback(complete)
        return True

    def _restore_segment(self, segment_id: str, snapshot: dict, text_changed: bool) -> bool:
        for index, current in enumerate(self._segments):
            if current["segment_id"] != segment_id:
                continue
            items = copy.deepcopy(self._segments)
            restored = copy.deepcopy(snapshot)
            restored["segment_id"] = segment_id
            # Revisions are monotonic even when document content moves backward.
            restored["revision"] = int(current.get("revision", 0))
            items[index] = restored
            return self._submit(
                items,
                index,
                f"history-{uuid.uuid4().hex}",
                text_changed,
                record_history=False,
            )
        return False

    @Slot(object)
    def _accept_result(self, result):
        video_id, segment_id, revision, request_id, text_changed, error = result
        if video_id != self.video_id:
            return
        current = next((s for s in self._segments if s["segment_id"] == segment_id), None)
        is_current = bool(current and current["revision"] == revision)
        if is_current:
            self._states[segment_id] = "error" if error else "saved"
            index = self._segments.index(current)
            self.dataChanged.emit(self.index(index), self.index(index))
            self.changed.emit()
        if not is_current:
            return
        if error:
            index = next((i for i, s in enumerate(self._segments) if s["segment_id"] == segment_id), -1)
            if index >= 0:
                self.dataChanged.emit(self.index(index), self.index(index))
            self.saveFailed.emit(segment_id, request_id, error)
        else:
            self.saved.emit(segment_id, revision, request_id)
            self.published.emit(video_id, revision, text_changed)

    def close(self):
        if self._closed:
            return
        self._closed = True
        # A save owns an atomic ``.partial`` file until publication finishes.
        # Waiting here is intentional: leaving the executor detached can keep
        # project/cache files locked after the editor or application closes.
        self._executor.shutdown(wait=True, cancel_futures=True)
