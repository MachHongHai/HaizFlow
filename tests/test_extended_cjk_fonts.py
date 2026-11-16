"""Extra regional faces remain selectable, licensed and deterministic."""
from pathlib import Path

import pytest

from haizflow.core.subtitle_fonts import (
    FONT_DIRECTORY,
    FONT_SAMPLES,
    covers_text,
    font_catalog,
    font_choices,
    subtitle_font_for_text,
)

EXTRA = {
    "ko": ("Black Han Sans", "Jua", "Do Hyeon", "Gowun Dodum", "Gowun Batang", "Sunflower", "Gugi", "Gaegu"),
    "ja": ("Zen Maru Gothic", "Zen Kaku Gothic New", "Yusei Magic", "Reggae One", "Klee One", "Hachi Maru Pop",
           "RocknRoll One"),
    "zh": ("ZCOOL KuaiLe", "Zhi Mang Xing", "Ma Shan Zheng", "ZCOOL QingKe HuangYou"),
    "zh-tw": ("Iansui", "LXGW WenKai TC", "Huninn"),
}


@pytest.mark.parametrize("language,families", EXTRA.items())
def test_each_added_face_is_a_real_selectable_alternative_only_in_its_region(language, families):
    rows = {row["family"]: row for row in font_choices(language)}
    for family in families:
        assert family in rows
        assert rows[family]["effective"] == family
        assert covers_text(family, FONT_SAMPLES[language])
        for other in set(EXTRA) - {language}:
            assert family not in {row["family"] for row in font_choices(other)}
        assert family not in {row["family"] for row in font_choices("vi")}


@pytest.mark.parametrize("language", EXTRA)
def test_expanded_catalogue_keeps_automatic_font_and_safe_mixed_script_fallback(language):
    defaults = {"ko": "Pretendard ExtraBold", "ja": "Dela Gothic One",
                "zh": "Noto Sans SC Black", "zh-tw": "Noto Sans TC Black"}
    assert subtitle_font_for_text(FONT_SAMPLES[language], language) == defaults[language]
    for family in EXTRA[language]:
        for text in (FONT_SAMPLES[language] + " Mateo! 2026", FONT_SAMPLES[language] + " Đặng Thị Mỹ"):
            effective = subtitle_font_for_text(text, language, family)
            assert covers_text(effective, text), (family, effective, text)
            if covers_text(family, text):
                assert effective == family


def test_new_assets_are_static_and_include_individual_redistribution_notices():
    from fontTools.ttLib import TTFont

    root = Path(__file__).resolve().parents[1]
    preparation = (root / "scripts/prepare-subtitle-fonts.ps1").read_text("utf-8")
    for families in EXTRA.values():
        for family in families:
            spec = font_catalog()[family]
            assert spec["file"] in preparation
            with TTFont(FONT_DIRECTORY / spec["file"]) as face:
                assert "fvar" not in face  # Same face and weight in Qt and libass.
            notice = root / "licenses" / (spec["file"].split("-")[0] + "-OFL.txt")
            assert "SIL OPEN FONT LICENSE" in notice.read_text("utf-8-sig")
