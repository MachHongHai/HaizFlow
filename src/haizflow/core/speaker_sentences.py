"""Conservative sentence boundaries for source/translated speaker turns."""

import re

_CASELESS = r"\u1100-\u11ff\u3130-\u318f\uac00-\ud7af\u3040-\u30ff\u3400-\u9fff"
_BOUNDARY = re.compile(r"(?<=[!?。！？])\s*|(?<=[.．])\s+(?=[A-ZÀ-Ỹ¿¡\"“'" + _CASELESS
                       + r"])|(?<=[.．])(?=[" + _CASELESS + r"])")
_TITLE = re.compile(r"\b(?:mr|mrs|ms|dr|prof|sr|jr|st)\.$", re.IGNORECASE)


def split_speaker_sentences(text: str) -> list[str]:
    text = str(text or "").strip()
    parts, start = [], 0
    for boundary in _BOUNDARY.finditer(text):
        prefix = text[start:boundary.start()].rstrip()
        # Honorifics and initials belong to their following name, not an actor.
        if _TITLE.search(prefix) or re.search(r"(?:\b[A-Z]\.)+$", prefix):
            continue
        if prefix:
            parts.append(prefix)
            start = boundary.end()
    if tail := text[start:].strip():
        parts.append(tail)
    return parts
