from __future__ import annotations

from concurrent.futures import CancelledError, ThreadPoolExecutor
from bisect import bisect_right

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from haizflow.pipeline.text_overlay_sprite import render_text_overlay_sprite, sprite_key
from haizflow.core.interval_index import IntervalIndex
from haizflow.services import editor_documents


class ManualPreviewCompositionController(QObject):
    frameChanged = Signal()
    overlaysChanged = Signal()
    _spriteReady = Signal(str, object)

    def __init__(self, document_model, parent=None):
        super().__init__(parent)
        self._model = document_model
        self._time_ms = 0
        self._frame: dict = {"timeMs": 0, "overlays": [], "sourceTimeMs": 0}
        self._overlay_clips = []
        self._assets = {}
        self._sprites: dict[str, dict] = {}
        self._sprite_pending: set[str] = set()
        self._sprite_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="editor-text-sprite",
        )
        self._closed = False
        self._spriteReady.connect(self._accept_sprite)
        document_model.changed.connect(self.refresh)
        # The model may already contain a document when a workspace is
        # reconstructed (for example after returning from another page).
        # Populate the first frame immediately instead of waiting for an
        # unrelated edit to emit changed.
        self.refresh()

    @Property("QVariantMap", notify=frameChanged)
    def frame(self) -> dict:
        return dict(self._frame)

    @Property(int, notify=frameChanged)
    def timeMs(self) -> int:
        return self._time_ms

    @Property("QVariantList", notify=overlaysChanged)
    def overlays(self) -> list:
        return list(self._frame["overlays"])

    @Slot(float)
    def setTime(self, seconds: float) -> None:
        next_time = max(0, round(float(seconds or 0) * 1000))
        if next_time == self._time_ms:
            return
        self._time_ms = next_time
        self._update_frame()

    @Slot()
    def refresh(self) -> None:
        # Index document edits, not every playback tick. Long projects can
        # contain thousands of captions/voice clips that never render here.
        document = self._model.document_object
        visible_tracks = {track.track_id for track in document.tracks if track.visible} if document else set()
        self._overlay_clips = [
            clip for clip in document.clips
            if clip.track_id == "overlays" and clip.track_id in visible_tracks and clip.enabled
        ] if document else []
        self._assets = {asset.asset_id: asset for asset in document.assets} if document else {}
        self._decisions = sorted(
            (item for item in document.sequence.edit_decisions if item.source_end_ms > item.source_start_ms),
            key=lambda item: item.sequence_start_ms,
        ) if document else []
        self._decision_starts = [item.sequence_start_ms for item in self._decisions]
        self._decisions_disjoint = all(
            current.sequence_start_ms >= previous.sequence_start_ms + previous.source_end_ms - previous.source_start_ms
            for previous, current in zip(self._decisions, self._decisions[1:])
        )
        self._overlay_payloads = []
        self._keyframe_indices = {}
        if document:
            source = self._assets.get(document.sequence.source_asset_id)
            width = max(1, int(source.width if source else 0) or 1920)
            height = max(1, int(source.height if source else 0) or 1080)
            for clip in self._overlay_clips:
                asset = self._assets.get(clip.asset_id)
                asset_payload = asset.model_dump() if asset else {}
                asset_payload["sourceUrl"] = QUrl.fromLocalFile(asset.path) if asset and asset.path else QUrl()
                style = editor_documents.resolved_text_style(document, clip) if clip.kind == "text" else None
                key = sprite_key(clip.name, style, width, height) if style else ""
                payload = {
                    **clip.model_dump(exclude={"transform", "keyframes"}),
                    "asset": asset_payload,
                    "style": style.model_dump() if style else {},
                    "referenceWidth": width,
                    "referenceHeight": height,
                }
                self._overlay_payloads.append((clip, payload, clip.transform.model_dump(), key, style))
                self._keyframe_indices[clip.clip_id] = editor_documents.keyframe_index(clip)
        self._overlay_index = IntervalIndex(
            (entry[0].start_ms, entry[0].start_ms + entry[0].duration_ms, entry)
            for entry in self._overlay_payloads)
        self._update_frame()

    def _update_frame(self) -> None:
        document = self._model.document_object
        if document is None:
            next_frame = {"timeMs": self._time_ms, "overlays": [], "sourceTimeMs": self._time_ms}
        else:
            overlays = []
            for clip, payload, base_transform, key, style in self._overlay_index.intersect(self._time_ms, self._time_ms + 1):
                keyframes = self._keyframe_indices[clip.clip_id]
                transform = dict(base_transform)
                transform["position_x_percent"] = editor_documents.evaluate_keyframes(
                    clip, "position_x", self._time_ms, clip.transform.position_x_percent, index=keyframes
                )
                transform["position_y_percent"] = editor_documents.evaluate_keyframes(
                    clip, "position_y", self._time_ms, clip.transform.position_y_percent, index=keyframes
                )
                scale = editor_documents.evaluate_keyframes(
                    clip, "scale", self._time_ms, clip.transform.scale_x_percent, index=keyframes
                )
                transform["scale_x_percent"] = scale
                transform["scale_y_percent"] = scale if clip.transform.lock_aspect_ratio else clip.transform.scale_y_percent
                transform["rotation_degrees"] = editor_documents.evaluate_keyframes(
                    clip, "rotation", self._time_ms, clip.transform.rotation_degrees, index=keyframes
                )
                transform["opacity_percent"] = editor_documents.evaluate_keyframes(
                    clip, "opacity", self._time_ms, clip.transform.opacity_percent, index=keyframes
                )
                sprite_payload = {}
                if key:
                    sprite_payload = dict(self._sprites.get(key) or {})
                    if sprite_payload:
                        sprite_payload["sourceUrl"] = QUrl.fromLocalFile(
                            str(sprite_payload.get("path") or "")
                        )
                    else:
                        self._request_sprite(key, clip.name, style,
                                             payload["referenceWidth"], payload["referenceHeight"])
                overlays.append(
                    {
                        **payload,
                        "transform": transform,
                        "sprite": sprite_payload,
                    }
                )
            source_time = self._time_ms
            if self._decisions_disjoint:
                index = bisect_right(self._decision_starts, self._time_ms) - 1
                decisions = self._decisions[index:index + 1] if index >= 0 else []
            else:
                decisions = document.sequence.edit_decisions
            for decision in decisions:
                duration = max(0, decision.source_end_ms - decision.source_start_ms)
                if decision.sequence_start_ms <= self._time_ms < decision.sequence_start_ms + duration:
                    source_time = decision.source_start_ms + self._time_ms - decision.sequence_start_ms
                    break
            next_frame = {"timeMs": self._time_ms, "overlays": overlays, "sourceTimeMs": source_time}
        if next_frame == self._frame:
            return
        overlays_changed = next_frame["overlays"] != self._frame["overlays"]
        self._frame = next_frame
        if overlays_changed:
            self.overlaysChanged.emit()
        self.frameChanged.emit()

    def _request_sprite(self, key, text, style, width, height) -> None:
        if self._closed or key in self._sprite_pending:
            return
        self._sprite_pending.add(key)

        def render():
            return render_text_overlay_sprite(text, style, width, height)

        future = self._sprite_executor.submit(render)

        def complete(completed):
            try:
                payload = completed.result()
            except (CancelledError, OSError, RuntimeError, ValueError):
                payload = {}
            if not self._closed:
                self._spriteReady.emit(key, payload)

        future.add_done_callback(complete)

    @Slot(str, object)
    def _accept_sprite(self, key: str, payload) -> None:
        self._sprite_pending.discard(key)
        if self._closed:
            return
        if isinstance(payload, dict) and payload.get("path"):
            self._sprites[key] = dict(payload)
            self._update_frame()

    def close(self) -> None:
        self._closed = True
        self._sprite_pending.clear()
        self._sprite_executor.shutdown(wait=False, cancel_futures=True)
