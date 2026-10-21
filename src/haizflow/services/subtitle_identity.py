"""Stable links between working subtitles and immutable legacy voice rows."""

import uuid
from collections import defaultdict


def legacy_segment_id(video_id: str, index: int, segment: dict) -> str:
    """Keep the exact ID contract originally used by the Manual editor."""
    return uuid.uuid5(uuid.NAMESPACE_URL,
        f"haizflow:{video_id}:{index}:{segment.get('start', 0)}:{segment.get('end', 0)}").hex


def voice_source_indices(video_id: str, current: list[dict], source: list[dict]) -> dict[int, int]:
    """Match unchanged speech without assuming the two lists have equal order.

    Older voice manifests reference subtitles without IDs. Reconstruct their
    original editor IDs before matching, not IDs based on the edited list's
    new positions. Text/timing is a conservative migration fallback for older
    editor documents; ambiguous repeated lines must never borrow another voice.
    Explicit IDs always remain authoritative, even when the words are equal.
    """
    by_id = defaultdict(list)
    legacy_by_content_time = defaultdict(list)

    def content_time(row):
        try:
            return (" ".join(str(row.get("text") or "").split()),
                    round(float(row.get("start") or 0) * 1000),
                    round(float(row.get("end") or 0) * 1000))
        except (TypeError, ValueError, OverflowError):
            return None

    for index, row in enumerate(source):
        identity = str(row.get("segment_id") or row.get("id") or "")
        if identity:
            by_id[identity].append(index)
        else:
            by_id[legacy_segment_id(video_id, index, row)].append(index)
            by_id[f"segment-{index + 1}"].append(index)
            key = content_time(row)
            if key is not None:
                legacy_by_content_time[key].append(index)
    result = {}
    used = set()
    for index, row in enumerate(current):
        identity = str(row.get("segment_id") or row.get("id") or "")
        candidates = by_id.get(identity, []) if identity else []
        if not candidates:
            candidates = legacy_by_content_time.get(content_time(row), [])
        if len(candidates) != 1:
            continue
        source_index = candidates[0]
        if source_index in used or " ".join(str(row.get("text") or "").split()) != " ".join(
            str(source[source_index].get("text") or "").split()
        ):
            continue
        result[index] = source_index
        used.add(source_index)
    return result
