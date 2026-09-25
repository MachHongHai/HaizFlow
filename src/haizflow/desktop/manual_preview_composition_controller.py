from __future__ import annotations

from concurrent.futures import CancelledError, ThreadPoolExecutor

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from haizflow.pipeline.text_overlay_sprite import render_text_overlay_sprite, sprite_key
from haizflow.services import editor_documents


class ManualPreviewCompositionController(QObject):
    frameChanged = Signal()
    _spriteReady = Signal(str, object)

    def __init__(self, document_model, parent=None):
        super().__init__(parent)
        self._model = document_model
        self._time_ms = 0
        self._frame: dict = {"timeMs": 0, "overlays": [], "sourceTimeMs": 0}
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

    @Slot(float)
    def setTime(self, seconds: float) -> None:
        next_time = max(0, round(float(seconds or 0) * 1000))
        if next_time == self._time_ms:
            return
        self._time_ms = next_time
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        document = self._model.document_object
        if document is None:
            next_frame = {"timeMs": self._time_ms, "overlays": [], "sourceTimeMs": self._time_ms}
        else:
            visible_tracks = {track.track_id for track in document.tracks if track.visible}
            overlays = []
            source_asset = editor_documents.asset_by_id(
                document, document.sequence.source_asset_id
            )
            reference_width = max(1, int(source_asset.width if source_asset else 0) or 1920)
            reference_height = max(1, int(source_asset.height if source_asset else 0) or 1080)
            for clip in document.clips:
                if (
                    clip.track_id not in visible_tracks
                    or clip.track_id != "overlays"
                    or not clip.enabled
                    or self._time_ms < clip.start_ms
                    or self._time_ms >= clip.start_ms + clip.duration_ms
                ):
                    continue
                transform = clip.transform.model_dump()
                transform["position_x_percent"] = editor_documents.evaluate_keyframes(
                    clip, "position_x", self._time_ms, clip.transform.position_x_percent
                )
                transform["position_y_percent"] = editor_documents.evaluate_keyframes(
                    clip, "position_y", self._time_ms, clip.transform.position_y_percent
                )
                scale = editor_documents.evaluate_keyframes(
                    clip, "scale", self._time_ms, clip.transform.scale_x_percent
                )
                transform["scale_x_percent"] = scale
                transform["scale_y_percent"] = scale if clip.transform.lock_aspect_ratio else clip.transform.scale_y_percent
                transform["rotation_degrees"] = editor_documents.evaluate_keyframes(
                    clip, "rotation", self._time_ms, clip.transform.rotation_degrees
                )
                transform["opacity_percent"] = editor_documents.evaluate_keyframes(
                    clip, "opacity", self._time_ms, clip.transform.opacity_percent
                )
                asset = editor_documents.asset_by_id(document, clip.asset_id)
                asset_payload = asset.model_dump() if asset else {}
                asset_payload["sourceUrl"] = (
                    QUrl.fromLocalFile(asset.path) if asset and asset.path else QUrl()
                )
                style_payload = (
                    editor_documents.resolved_text_style(document, clip).model_dump()
                    if clip.kind == "text"
                    else {}
                )
                sprite_payload = {}
                if clip.kind == "text":
                    style = editor_documents.resolved_text_style(document, clip)
                    key = sprite_key(clip.name, style, reference_width, reference_height)
                    sprite_payload = dict(self._sprites.get(key) or {})
                    if sprite_payload:
                        sprite_payload["sourceUrl"] = QUrl.fromLocalFile(
                            str(sprite_payload.get("path") or "")
                        )
                    else:
                        self._request_sprite(
                            key,
                            clip.name,
                            style,
                            reference_width,
                            reference_height,
                        )
                overlays.append(
                    {
                        **clip.model_dump(exclude={"transform", "keyframes"}),
                        "transform": transform,
                        "asset": asset_payload,
                        "style": style_payload,
                        "sprite": sprite_payload,
                        "referenceWidth": reference_width,
                        "referenceHeight": reference_height,
                    }
                )
            source_time = self._time_ms
            for decision in document.sequence.edit_decisions:
                duration = max(0, decision.source_end_ms - decision.source_start_ms)
                if decision.sequence_start_ms <= self._time_ms < decision.sequence_start_ms + duration:
                    source_time = decision.source_start_ms + self._time_ms - decision.sequence_start_ms
                    break
            next_frame = {"timeMs": self._time_ms, "overlays": overlays, "sourceTimeMs": source_time}
        if next_frame == self._frame:
            return
        self._frame = next_frame
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
            self.refresh()

    def close(self) -> None:
        self._closed = True
        self._sprite_pending.clear()
        self._sprite_executor.shutdown(wait=False, cancel_futures=True)
