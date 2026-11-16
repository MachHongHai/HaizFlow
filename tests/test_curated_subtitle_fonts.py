"""Bundled font selection, language coverage and actual libass rendering."""
import subprocess
import unicodedata

import pytest

from haizflow.core.subtitle_fonts import (
    FONT_FILES,
    FONT_SAMPLES,
    ass_font_family,
    covers_text,
    font_catalog,
    font_choices,
    font_supports_language,
    subtitle_font_for_text,
)
from haizflow.pipeline.render import _karaoke_font_directory, _write_positioned_ass
from haizflow.schemas.editor import EditorClip, EditorTextStyle
from haizflow.schemas.video import SubtitleStyle
from haizflow.utils.ffmpeg import _binary


@pytest.mark.parametrize("language", FONT_SAMPLES)
def test_every_offered_font_covers_language_and_its_sample(language):
    rows = font_choices(language)
    assert len(rows) >= (19 if language in ("vi", "en", "es") else 3)
    for row in rows:
        effective = row["effective"]
        assert covers_text(effective, row["sample"])
        assert font_supports_language(effective, language)
        assert covers_text(effective, unicodedata.normalize("NFD", row["sample"]))
        assert subtitle_font_for_text(row["sample"], language, row["family"]) == effective


def test_incomplete_vietnamese_fonts_are_hidden_and_safe_after_language_change():
    assert all(row["sample"] == "Xin bạn 1 star GitHub" for row in font_choices("vi"))
    names = {row["family"] for row in font_choices("vi")}
    assert "Bree Serif" not in names and "Archivo Black" not in names
    for family in ("Bree Serif", "Archivo Black"):
        assert subtitle_font_for_text("Đừng quên những ước mơ.", "vi", family) == "Bangers"
    assert subtitle_font_for_text("今日は元気です！", "ja", "Lobster") == "Dela Gothic One"
    assert subtitle_font_for_text("오늘도 좋은 하루!", "ko", "Pacifico") == "Pretendard ExtraBold"


@pytest.mark.parametrize("family", FONT_FILES)
def test_selected_family_survives_automatic_and_manual_serialization(family):
    style = SubtitleStyle(font_family=family)
    assert SubtitleStyle.model_validate_json(style.model_dump_json()).font_family == family
    manual = EditorTextStyle(style_id="selected", font_family=family)
    assert EditorTextStyle.model_validate_json(manual.model_dump_json()).font_family == family
    cue = EditorClip(clip_id="cue", track_id="subtitles", kind="subtitle", style_override={"font_family": family})
    assert EditorClip.model_validate_json(cue.model_dump_json()).style_override["font_family"] == family


def sample_for_family(family):
    for language in ("vi", "es", "en", "zh", "zh-tw", "ja", "ko"):
        for row in font_choices(language):
            if row["family"] == family and row["effective"] == family:
                return language, row["sample"]
    raise AssertionError(f"No supported language for {family}")


@pytest.mark.parametrize("family", FONT_FILES)
def test_actual_libass_export_uses_selected_font_without_missing_glyphs(tmp_path, family):
    language, text = sample_for_family(family)
    source, target = tmp_path / "captions.srt", tmp_path / "captions.ass"
    source.write_text(f"1\n00:00:00,000 --> 00:00:02,000\n{text}\n", encoding="utf-8")
    _write_positioned_ass(str(source), str(target), SubtitleStyle(font_family=family, font_size=40),
                          320, 480, subtitle_language=language)
    assert ass_font_family(family) in target.read_text("utf-8-sig")
    fonts = _karaoke_font_directory().resolve().as_posix().replace(":", "\\:")
    result = subprocess.run([_binary("ffmpeg"), "-hide_banner", "-f", "lavfi", "-i",
        "color=s=320x480:d=1:r=1", "-vf", f"ass=captions.ass:fontsdir='{fonts}'",
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        cwd=tmp_path, capture_output=True, timeout=25,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 0, log
    selections = "\n".join(line for line in log.splitlines() if "fontselect:" in line or "Glyph" in line)
    assert "fontselect:" in selections and "Glyph" not in selections and "ArialMT" not in selections, selections
    assert max(result.stdout) > 100, log


def test_all_faces_have_the_expected_qt_family_and_weight():
    from PySide6.QtGui import QFont, QFontInfo
    from PySide6.QtWidgets import QApplication

    from haizflow.desktop.subtitle_fonts import qt_subtitle_font

    app = QApplication.instance() or QApplication([])
    for family in FONT_FILES:
        language, text = sample_for_family(family)
        spec = qt_subtitle_font(text, language, family)
        font = QFont(spec["family"])
        font.setWeight(QFont.Weight(spec["weight"]))
        actual = QFontInfo(font)
        assert actual.family() == font_catalog()[family]["qt_family"], family
        assert actual.weight() == font_catalog()[family]["weight"], family
    assert app is not None
