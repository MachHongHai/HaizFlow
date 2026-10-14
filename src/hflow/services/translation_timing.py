"""Soft speech-length guidance, never a text truncation or timing mutation."""

from __future__ import annotations

import math

POLICY_VERSION = "speech-length-v1"

# Product heuristics for ordinary narration, not measured voice durations.
# Vietnamese space-separated units are usually syllables; CJK characters and
# English words are deliberately not compared by raw string length.
_PROFILES = {
    "vietnamese": (4.5, "space-separated spoken syllables"),
    "vi": (4.5, "space-separated spoken syllables"),
    "english": (2.8, "words"),
    "en": (2.8, "words"),
    "chinese": (4.5, "spoken characters"),
    "zh": (4.5, "spoken characters"),
    "japanese": (5.0, "spoken characters"),
    "ja": (5.0, "spoken characters"),
    "korean": (5.0, "spoken characters"),
    "ko": (5.0, "spoken characters"),
}


def speech_duration(segment: dict) -> float:
    """Use a reliable aligned word span when present, otherwise the cue span."""
    start, end = float(segment["start"]), float(segment["end"])
    duration = end - start
    if not math.isfinite(duration) or not math.isfinite(start) or start < 0 or duration <= 0:
        raise ValueError("Source sentence has invalid timestamps.")
    words = segment.get("words")
    if not isinstance(words, list) or not words:
        return duration
    spans = []
    labels = []
    for word in words:
        try:
            label = str(word.get("word") or "").strip()
            left, right = float(word["start"]), float(word["end"])
        except (AttributeError, KeyError, TypeError, ValueError):
            return duration
        if not label or not math.isfinite(left) or not math.isfinite(right) or right <= left:
            return duration
        spans.append((max(start, left), min(end, right)))
        labels.append(label)
    # Incomplete alignment must not invent an artificially tiny speaking slot.
    normalized = lambda text: "".join(char.casefold() for char in text if char.isalnum())
    if normalized("".join(labels)) != normalized(str(segment.get("text") or "")):
        return duration
    left, right = min(span[0] for span in spans), max(span[1] for span in spans)
    if any(right_edge <= left_edge for left_edge, right_edge in spans) or right <= left:
        return duration
    return right - left


def timing_budget(duration: float | None, language: str) -> dict:
    if duration is None:
        return {}
    seconds = float(duration)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Speech duration must be finite and positive.")
    result = {"speech_seconds": max(.001, round(seconds, 3))}
    profile = _PROFILES.get(str(language).casefold().strip())
    if profile:
        rate, label = profile
        result.update(target_spoken_units=max(1, math.ceil(seconds * rate)), spoken_unit=label)
    return result


def timing_instruction(duration: float | None, language: str) -> str:
    budget = timing_budget(duration, language)
    if not budget:
        return ""
    target = budget.get("target_spoken_units")
    length = f" Aim for about {target} {budget['spoken_unit']} or fewer." if target else ""
    return (
        f"This subtitle is spoken in about {budget['speech_seconds']:.3f} seconds.{length}"
        " Use concise, natural spoken phrasing that fits a similar speaking duration, not a word-for-word expansion."
        " Preserve all essential meaning, negation, names, numbers, relationships and speaker tone."
        " Do not add explanations, repeated ideas or filler; never pad a short original to fill the time."
        " The length target is approximate: accuracy takes priority if a faithful translation needs more words."
        "\n\n"
    )
