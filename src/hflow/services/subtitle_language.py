"""Published Manual subtitle language is independent of the next translation."""

import re


def compatible_manual_voice(language, provider, voice):
    """Preserve the chosen device, replacing only unsupported VieNeu Chinese."""
    from hflow.core.vieneu_voices import unsupported_language_notice

    provider = str(provider or "omnivoice")
    voice = str(voice or "")
    if unsupported_language_notice(provider, language):
        return ("omnivoice-gpu" if provider.endswith("-gpu") else "omnivoice", "omnivoice:female_gentle")
    return provider, voice


def manual_subtitle_language(video, segments=None):
    stored = str(getattr(video, "subtitle_language", "") or "").lower()
    imported = bool((getattr(video, "files", {}) or {}).get("imported_source_srt"))
    if stored and stored != "und":
        return stored
    requested = str(getattr(video, "target_language", "vi") or "vi")
    if segments is None and requested != "zh" and not imported:
        return requested  # Keep legacy cache keys and avoid unnecessary I/O.
    if segments is None:
        from hflow.pipeline.manual_tools import _load_segments

        segments = _load_segments(video, validate=False)
    text = " ".join(str(item.get("text") or "") for item in segments)
    if not text.strip():
        return "vi"  # No published Chinese result yet.
    han = len(re.findall(r"[\u3400-\u9fff]", text))
    letters = sum(character.isalpha() for character in text)
    if han >= 2 and han / max(1, letters) >= .2:
        return "zh"
    if imported and stored == "und":
        return "und"
    if requested != "zh":
        return requested
    return "vi" if any(ord(character) > 127 for character in text if character.isalpha()) else "en"
