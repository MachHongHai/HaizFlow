"""Deterministic caption fonts shared by libass, layout measurement and Qt.

No Qt/fontTools imports, system-font search or online requests in this module.
Coverage is indexed offline from the unmodified bundled font files.
"""
from __future__ import annotations

import json
import re
import unicodedata
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path

FONT_DIRECTORY = Path(__file__).resolve().parents[1] / "assets/fonts"
FONT_POLICY_VERSION = "caption-fonts-v1-regional-cjk"
FONT_FILES = {
    "Bangers": "Bangers-Regular.ttf",
    "Noto Sans SC Black": "NotoSansSC-Black.otf",
    "Noto Sans TC Black": "NotoSansTC-Black.otf",
    "Noto Sans JP Black": "NotoSansJP-Black.otf",
    "Noto Sans KR Black": "NotoSansKR-Black.otf",
    "Dela Gothic One": "DelaGothicOne-Regular.ttf",
    "Pretendard ExtraBold": "Pretendard-ExtraBold.otf",
}
_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
_HANGUL = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")
_HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0003134f]")
_REGIONS = {"ja": ("Dela Gothic One", "Noto Sans JP Black"),
            "ko": ("Pretendard ExtraBold", "Noto Sans KR Black"),
            "zh": ("Noto Sans SC Black", "Noto Sans SC Black"),
            "zh-tw": ("Noto Sans TC Black", "Noto Sans TC Black")}
_FAMILY_REGIONS = {family: language for language, families in _REGIONS.items() for family in families}


def normalise_subtitle_font(family: str) -> str:
    family = str(family or "").strip()
    return next((name for name in FONT_FILES if name.casefold() == family.casefold()), "Bangers")


@lru_cache(maxsize=1)
def font_catalog() -> dict:
    return json.loads((FONT_DIRECTORY.parent / "subtitle-fonts.json").read_text("utf-8"))["fonts"]


@lru_cache(maxsize=7)
def _coverage(family):
    ranges = font_catalog()[family]["coverage"]
    return tuple(start for start, _end in ranges), tuple(end for _start, end in ranges)


def covers_text(family: str, text: str) -> bool:
    starts, ends = _coverage(family)
    for char in unicodedata.normalize("NFC", text):
        if char.isspace() or unicodedata.category(char).startswith("C"):
            continue
        point = ord(char)
        index = bisect_right(starts, point) - 1
        if index < 0 or point > ends[index]:
            return False
    return True


def caption_region(text: str = "", language: str = "", requested: str = "Bangers") -> str:
    hint = str(language or "").lower().replace("_", "-")
    if hint in {"zh-hant", "zh-hk", "zh-mo", "tc"}:
        hint = "zh-tw"
    elif hint.startswith("zh") and hint != "zh-tw":
        hint = "zh"
    else:
        hint = hint.split("-")[0] if hint != "zh-tw" else hint
    if _HANGUL.search(text):
        return "ko"
    if _KANA.search(text):
        return "ja"
    if _HAN.search(text):
        return hint if hint in _REGIONS else _FAMILY_REGIONS.get(requested, "zh")
    return hint if hint in _REGIONS else _FAMILY_REGIONS.get(requested, "")


def subtitle_font_for_text(text: str = "", language: str = "", requested: str = "Bangers") -> str:
    primary, fallback = _REGIONS.get(caption_region(text, language, requested), ("Bangers", "Bangers"))
    # Keep one coherent face for the entire cue rather than mixing visible
    # system fallbacks in the middle of a word. Include Latin in this check.
    return primary if covers_text(primary, text) else fallback


def resolved_subtitle_style(style, text: str = "", language: str = ""):
    return style.model_copy(update={"font_family": subtitle_font_for_text(text, language, style.font_family)})


def bundled_font_path(family: str) -> Path | None:
    filename = next((filename for name, filename in FONT_FILES.items() if name.casefold() == family.casefold()), None)
    return FONT_DIRECTORY / filename if filename else None
