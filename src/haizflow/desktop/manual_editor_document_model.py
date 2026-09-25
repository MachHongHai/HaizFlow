from __future__ import annotations

from copy import deepcopy
from concurrent.futures import CancelledError, ThreadPoolExecutor

from PySide6.QtCore import Property, QObject, Signal, Slot

from haizflow.schemas.editor import EditorDocument
from haizflow.services import desktop_videos, editor_documents


class ManualEditorDocumentModel(QObject):
    changed = Signal()
    selectionChanged = Signal()
    _waveformReady = Signal(str, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_id = ""
        self._document: EditorDocument | None = None
        self._selected_clip_ids: list[str] = []
        self._selected_track_id = ""
        self._waveforms: dict[str, list[float]] = {}
        self._waveform_pending: set[str] = set()
        self._waveform_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="editor-waveform"
        )
        self._closed = False
        self._waveformReady.connect(self._accept_waveform)

    @property
    def document_object(self) -> EditorDocument | None:
        return self._document

    @property
    def video_id(self) -> str:
        return self._video_id

    def load(self, video) -> None:
        video_id = str(getattr(video, "video_id", "") or "") if video else ""
        document = editor_documents.ensure(video) if video_id else None
        selection_changed = video_id != self._video_id
        self._video_id = video_id
        self._document = document
        if selection_changed:
            self._selected_clip_ids = []
            self._selected_track_id = ""
            self.selectionChanged.emit()
        self._schedule_waveforms()
        self.changed.emit()

    def clear(self) -> None:
        if not self._video_id and self._document is None:
            return
        self._video_id = ""
        self._document = None
        self._selected_clip_ids = []
        self._selected_track_id = ""
        self.selectionChanged.emit()
        self.changed.emit()

    def set_document(self, document: EditorDocument | None) -> None:
        self._document = document
        selection_payload_changed = bool(self._selected_clip_ids)
        if document is not None:
            self._video_id = document.video_id
            existing = {clip.clip_id for clip in document.clips}
            selected = [clip_id for clip_id in self._selected_clip_ids if clip_id in existing]
            if selected != self._selected_clip_ids:
                self._selected_clip_ids = selected
                self.selectionChanged.emit()
                selection_payload_changed = False
        if selection_payload_changed:
            self.selectionChanged.emit()
        self._schedule_waveforms()
        self.changed.emit()

    @Property(str, notify=changed)
    def videoId(self) -> str:
        return self._video_id

    @Property("QVariantMap", notify=changed)
    def document(self) -> dict:
        return self._document.model_dump() if self._document else {}

    @Property("QVariantList", notify=changed)
    def tracks(self) -> list[dict]:
        if not self._document:
            return []
        return [item.model_dump() for item in sorted(self._document.tracks, key=lambda value: value.order)]

    @Property("QVariantList", notify=changed)
    def clips(self) -> list[dict]:
        if not self._document:
            return []
        order = {item.track_id: item.order for item in self._document.tracks}
        values = sorted(
            self._document.clips,
            key=lambda item: (order.get(item.track_id, 999), item.start_ms, item.clip_id),
        )
        result: list[dict] = []
        for item in values:
            payload = item.model_dump()
            asset = editor_documents.asset_by_id(self._document, item.asset_id)
            if asset is not None:
                key = self._waveform_key(asset)
                if key in self._waveforms:
                    payload["waveform"] = list(self._waveforms[key])
            result.append(payload)
        return result

    @staticmethod
    def _waveform_key(asset) -> str:
        return str(asset.fingerprint or asset.path or asset.asset_id)

    def _schedule_waveforms(self) -> None:
        if self._closed or self._document is None:
            return
        video_id = self._document.video_id
        for asset in self._document.assets:
            if asset.kind not in {"source", "audio"} or not asset.path:
                continue
            key = self._waveform_key(asset)
            if key in self._waveforms or key in self._waveform_pending:
                continue
            self._waveform_pending.add(key)
            future = self._waveform_executor.submit(
                desktop_videos.analyze_voice_reference, asset.path, 96
            )

            def deliver(completed, *, expected_video=video_id, expected_key=key):
                try:
                    analysis = completed.result()
                except (CancelledError, OSError, RuntimeError, ValueError):
                    analysis = {"peaks": []}
                if not self._closed:
                    self._waveformReady.emit(expected_video, expected_key, analysis)

            future.add_done_callback(deliver)

    @Slot(str, str, object)
    def _accept_waveform(self, video_id: str, key: str, analysis) -> None:
        self._waveform_pending.discard(key)
        if self._closed or self._document is None or self._document.video_id != video_id:
            return
        peaks = analysis.get("peaks", []) if isinstance(analysis, dict) else []
        if peaks:
            self._waveforms[key] = [max(0.0, min(1.0, float(value))) for value in peaks]
            self.changed.emit()

    def close(self) -> None:
        self._closed = True
        self._waveform_pending.clear()
        self._waveform_executor.shutdown(wait=False, cancel_futures=True)

    @Property("QVariantList", notify=changed)
    def assets(self) -> list[dict]:
        return [item.model_dump() for item in self._document.assets] if self._document else []

    @Property("QVariantList", notify=changed)
    def styles(self) -> list[dict]:
        return [item.model_dump() for item in self._document.styles] if self._document else []

    @Property("QVariantMap", notify=changed)
    def defaultSubtitleStyle(self) -> dict:
        if not self._document:
            return {}
        style = next(
            (
                item for item in self._document.styles
                if item.style_id == self._document.default_subtitle_style_id
            ),
            None,
        )
        return style.model_dump() if style else {}

    @Property("QVariantList", notify=changed)
    def subtitleSegments(self) -> list[dict]:
        if not self._document:
            return []
        clips = sorted(
            (
                clip for clip in self._document.clips
                if clip.track_id == "subtitles" and clip.enabled and clip.segment_id
            ),
            key=lambda clip: (clip.start_ms, clip.clip_id),
        )
        result: list[dict] = []
        for clip in clips:
            stored = clip.metadata.get("segment_payload")
            segment = deepcopy(stored) if isinstance(stored, dict) else {}
            segment.update(
                segment_id=clip.segment_id,
                text=clip.name,
                start=clip.start_ms / 1000,
                end=(clip.start_ms + clip.duration_ms) / 1000,
                _style=editor_documents.resolved_text_style(self._document, clip).model_dump(),
                _uses_style_override=bool(clip.style_override),
            )
            result.append(segment)
        return result

    @Property("QVariantList", notify=changed)
    def markers(self) -> list[dict]:
        return [item.model_dump() for item in self._document.markers] if self._document else []

    @Property(int, notify=changed)
    def durationMs(self) -> int:
        return int(self._document.sequence.duration_ms) if self._document else 0

    @Property("QVariantList", notify=selectionChanged)
    def selectedClipIds(self) -> list[str]:
        return list(self._selected_clip_ids)

    @Property(str, notify=selectionChanged)
    def selectedTrackId(self) -> str:
        return self._selected_track_id

    @Property("QVariantMap", notify=selectionChanged)
    def selectedClip(self) -> dict:
        if not self._document or len(self._selected_clip_ids) != 1:
            return {}
        clip = editor_documents.clip_by_id(self._document, self._selected_clip_ids[0])
        if clip is None:
            return {}
        payload = clip.model_dump()
        if clip.kind in {"text", "subtitle"}:
            style = editor_documents.resolved_text_style(self._document, clip)
            payload["resolved_style"] = style.model_dump()
            if clip.kind == "subtitle":
                payload["warnings"] = self._subtitle_warnings(clip)
        return payload

    def _subtitle_warnings(self, clip) -> list[dict[str, str]]:
        if self._document is None:
            return []
        warnings: list[dict[str, str]] = []
        duration_seconds = max(0.001, clip.duration_ms / 1000)
        characters = len("".join(str(clip.name or "").split()))
        cps = characters / duration_seconds
        if cps > 20:
            warnings.append({
                "code": "reading_speed",
                "message": f"Tốc độ đọc {cps:.1f} ký tự/giây; nên dưới 20.",
            })
        clip_end = clip.start_ms + clip.duration_ms
        overlaps = any(
            other.clip_id != clip.clip_id
            and other.track_id == "subtitles"
            and other.enabled
            and clip.start_ms < other.start_ms + other.duration_ms
            and other.start_ms < clip_end
            for other in self._document.clips
        )
        if overlaps:
            warnings.append({
                "code": "overlap",
                "message": "Đoạn này đang chồng thời gian với một phụ đề khác.",
            })

        # The renderer shows long cues as successive phrases, not simultaneous
        # wrapped lines. Counting the full paragraph here reported impossible
        # 30+ line layouts even when every visible phrase fits the safe area.
        return warnings

    @Slot(str, bool)
    def selectClip(self, clip_id: str, additive: bool = False) -> None:
        clip_id = str(clip_id or "")
        if not clip_id:
            self.clearSelection()
            return
        selected = list(self._selected_clip_ids) if additive else []
        if clip_id in selected:
            selected.remove(clip_id)
        else:
            selected.append(clip_id)
        if selected == self._selected_clip_ids:
            return
        self._selected_clip_ids = selected
        if self._document:
            clip = editor_documents.clip_by_id(self._document, clip_id)
            self._selected_track_id = clip.track_id if clip else ""
        self.selectionChanged.emit()

    @Slot(str)
    def selectTrack(self, track_id: str) -> None:
        track_id = str(track_id or "")
        if track_id == self._selected_track_id and not self._selected_clip_ids:
            return
        self._selected_track_id = track_id
        self._selected_clip_ids = []
        self.selectionChanged.emit()

    @Slot()
    def clearSelection(self) -> None:
        if not self._selected_clip_ids and not self._selected_track_id:
            return
        self._selected_clip_ids = []
        self._selected_track_id = ""
        self.selectionChanged.emit()
