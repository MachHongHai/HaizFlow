"""Caption clocks derived from the audible, silence-trimmed narration."""

from functools import lru_cache
from pathlib import Path


def fitted_speech_duration_ms(raw_ms: int, slot_ms: int) -> int:
    """Use the same 20 ms safety margin as audio_timeline.compress_to_fit."""
    return min(raw_ms, max(1, slot_ms - 20)) if raw_ms > slot_ms else raw_ms


@lru_cache(maxsize=512)
def _trimmed_duration(path: str, size: int, modified_ns: int) -> int:
    from haizflow.utils.audio import AudioSegment
    from haizflow.pipeline.audio_timeline import trim_silence

    return len(trim_silence(AudioSegment.from_file(path)))


def voiced_subtitle_segments(segments: list[dict], paths: list[str]) -> list[dict]:
    """Resolve presentation timing without changing editable/source timing."""
    resolved = [dict(segment) for segment in segments]
    for index, segment in enumerate(resolved):
        path = Path(paths[index]) if index < len(paths) and paths[index] else None
        if path is None or not path.is_file():
            continue
        start = float(segment.get("start", 0))
        end = float(segment.get("end", start))
        if index + 1 < len(resolved):
            following = float(resolved[index + 1].get("start", end))
            if following > start:
                end = min(end, following)
        slot_ms = round((end - start) * 1000)
        if slot_ms <= 0:
            continue
        stat = path.stat()
        duration = _trimmed_duration(str(path.resolve()), stat.st_size, stat.st_mtime_ns)
        if duration > 0:
            segment["end"] = start + fitted_speech_duration_ms(duration, slot_ms) / 1000
    return resolved
