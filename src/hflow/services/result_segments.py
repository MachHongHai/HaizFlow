"""Non-destructive export ranges, independent of media and inference caches."""

from hflow.schemas.editor import EditorClip, EditorTrack

TRACK = "result"


def ensure(document) -> bool:
    if any(track.track_id == TRACK for track in document.tracks):
        return False  # An intentionally empty track stays empty.
    document.tracks.append(EditorTrack(track_id=TRACK, kind="result", name="Kết quả", order=-1000))
    document.clips.append(EditorClip(clip_id="result-1", track_id=TRACK, kind="result",
                                    name="Đoạn 1", duration_ms=max(1, document.sequence.duration_ms)))
    return True


def ranges(document) -> list[dict]:
    return [{"id": clip.clip_id, "startMs": clip.start_ms,
             "endMs": min(document.sequence.duration_ms, clip.start_ms + clip.duration_ms)}
            for clip in sorted(document.clips, key=lambda item: (item.start_ms, item.clip_id))
            if clip.kind == "result" and clip.enabled and clip.duration_ms >= 80
            and clip.start_ms < document.sequence.duration_ms]


def render_payload(document) -> dict:
    if document is None:
        return {}
    payload = document.model_dump()
    payload["revision"] = 1
    payload["tracks"] = [item for item in payload["tracks"] if item["kind"] != "result"]
    payload["clips"] = [item for item in payload["clips"] if item["kind"] != "result"]
    return payload


def split(document, clip_id, position, new_id) -> bool:
    clip = next((item for item in document.clips if item.clip_id == clip_id and item.kind == "result"), None)
    if clip is None or not clip.start_ms + 80 <= position <= clip.start_ms + clip.duration_ms - 80:
        return False
    right = clip.model_copy(deep=True)
    right.clip_id = new_id
    right.start_ms = position
    right.duration_ms = clip.start_ms + clip.duration_ms - position
    clip.duration_ms = position - clip.start_ms
    document.clips.append(right)
    for index, item in enumerate(sorted((item for item in document.clips if item.kind == "result"),
                                        key=lambda item: (item.start_ms, item.clip_id)), 1):
        item.name = f"Đoạn {index}"
    return True


def split_at(document, position, new_id) -> bool:
    """Split the result range under the playhead without requiring selection."""
    clip = next((item for item in document.clips if item.kind == "result" and item.enabled
                 and item.start_ms + 80 <= position <= item.start_ms + item.duration_ms - 80), None)
    return split(document, clip.clip_id, position, new_id) if clip else False
