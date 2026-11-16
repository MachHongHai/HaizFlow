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
FONT_POLICY_VERSION = "caption-fonts-v2-curated-selection"
FONT_FILES = {
    "Archivo Black": "ArchivoBlack-Regular.ttf",
    "Barlow": "Barlow-Bold.ttf",
    "Fira Sans": "FiraSans-Bold.ttf",
    "Saira Condensed": "SairaCondensed-Bold.ttf",
    "Chakra Petch": "ChakraPetch-Bold.ttf",
    "Kanit": "Kanit-SemiBold.ttf",
    "Sarabun": "Sarabun-Bold.ttf",
    "Bungee": "Bungee-Regular.ttf",
    "Pacifico": "Pacifico-Regular.ttf",
    "Patrick Hand": "PatrickHand-Regular.ttf",
    "Amatic SC": "AmaticSC-Bold.ttf",
    "Itim": "Itim-Regular.ttf",
    "Noto Serif SC Bold": "NotoSerifSC-Bold.otf",
    "Noto Serif TC Bold": "NotoSerifTC-Bold.otf",
    "Noto Serif JP Bold": "NotoSerifJP-Bold.otf",
    "Noto Serif KR Bold": "NotoSerifKR-Bold.otf",
    "Bangers": "Bangers-Regular.ttf",
    "Be Vietnam Pro": "BeVietnamPro-Bold.ttf",
    "Anton": "Anton-Regular.ttf",
    "Barlow Condensed": "BarlowCondensed-SemiBold.ttf",
    "Lato": "Lato-Bold.ttf",
    "Lobster": "Lobster-Regular.ttf",
    "Bree Serif": "BreeSerif-Regular.ttf",
    "Maitree": "Maitree-Bold.ttf",
    "Judson": "Judson-Bold.ttf",
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
_FAMILY_REGIONS.update({"Noto Serif SC Bold": "zh", "Noto Serif TC Bold": "zh-tw",
                        "Noto Serif JP Bold": "ja", "Noto Serif KR Bold": "ko"})
FONT_SAMPLES = {"vi": "Xin bạn 1 star GitHub", "en": "Every word tells a story.",
                "es": "Cada palabra cuenta una historia.", "zh": "一起开始新的故事。",
                "zh-tw": "一起開始新的故事。", "ja": "新しい物語を始めよう！", "ko": "오늘도 좋은 하루!"}
_VIETNAMESE = "ĐđĂăÂâÊêÔôƠơƯư" + "".join(chr(point) for point in range(0x1EA0, 0x1EFA))
_FONT_CATEGORIES = {"Bangers": "display", "Lobster": "display", "Bree Serif": "serif",
                    "Maitree": "serif", "Judson": "serif", "Bungee": "display",
                    "Pacifico": "display", "Patrick Hand": "display", "Amatic SC": "display",
                    "Itim": "display", "Chakra Petch": "display"}
_FONT_CATEGORIES.update({family: "serif" for family in FONT_FILES if family.startswith("Noto Serif")})
_LANGUAGE_PROBES = {"vi": _VIETNAMESE, "es": "ÁÉÍÓÚÜÑáéíóúüñ¿¡"}


def font_language(language: str) -> str:
    code = str(language or "vi").lower().replace("_", "-")
    if code in {"zh-tw", "zh-hant", "zh-hk", "zh-mo"}:
        return "zh-tw"
    return code.split("-")[0]


def font_supports_language(family: str, language: str) -> bool:
    language = font_language(language)
    return covers_text(family, _LANGUAGE_PROBES.get(language, FONT_SAMPLES.get(language, FONT_SAMPLES["en"])))


def font_choices(language: str = "vi", sample: str = "") -> list[dict]:
    """Small curated catalogue; do not enumerate machine-dependent system fonts."""
    language = font_language(language)
    text = sample or FONT_SAMPLES.get(language, FONT_SAMPLES["en"])
    families = ["Bangers"] + [family for family in FONT_FILES if family != "Bangers"
        and _FAMILY_REGIONS.get(family, language) == language
        and font_supports_language(family, language) and covers_text(family, text)]
    return [{"family": family, "effective": subtitle_font_for_text(text, language, family),
             "sample": text, "category": _FONT_CATEGORIES.get(family, "sans")}
            for family in families]


def normalise_subtitle_font(family: str) -> str:
    family = str(family or "").strip()
    return next((name for name in FONT_FILES if name.casefold() == family.casefold()), "Bangers")


@lru_cache(maxsize=1)
def font_catalog() -> dict:
    return json.loads((FONT_DIRECTORY.parent / "subtitle-fonts.json").read_text("utf-8"))["fonts"]


@lru_cache(maxsize=32)
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
    requested = normalise_subtitle_font(requested)
    region = caption_region(text, language, requested)
    # Bangers remains the automatic default for Latin and a regional default
    # for CJK. Explicit choices must survive preview, save and export.
    if (requested != "Bangers" and (not language or font_supports_language(requested, language))
            and covers_text(requested, text)):
        # Empty samples still need the target script's coverage check.
        probe = text or {"ja": "物語を始めよう", "ko": "새로운 이야기", "zh": "新的故事",
                         "zh-tw": "新的故事"}.get(region, "")
        if covers_text(requested, probe):
            return requested
    primary, fallback = _REGIONS.get(region, ("Bangers", "Bangers"))
    # Keep one coherent face for the entire cue rather than mixing visible
    # system fallbacks in the middle of a word. Include Latin in this check.
    return primary if covers_text(primary, text) else fallback


def resolved_subtitle_style(style, text: str = "", language: str = ""):
    return style.model_copy(update={"font_family": subtitle_font_for_text(text, language, style.font_family)})


def ass_font_family(family: str) -> str:
    """libass/DirectWrite uses the legacy English family, unlike Qt's name ID 16."""
    spec = font_catalog().get(family)
    return spec.get("ass_family", family) if spec else family


def bundled_font_path(family: str) -> Path | None:
    filename = next((filename for name, filename in FONT_FILES.items() if name.casefold() == family.casefold()), None)
    return FONT_DIRECTORY / filename if filename else None
