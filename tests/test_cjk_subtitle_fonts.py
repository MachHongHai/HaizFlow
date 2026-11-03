import hashlib
from pathlib import Path

import pytest

from haizflow.core.subtitle_fonts import (
    FONT_DIRECTORY,
    FONT_FILES,
    covers_text,
    font_catalog,
    subtitle_font_for_text,
)
from haizflow.pipeline.render import _write_positioned_ass, resolve_subtitle_preview_layout
from haizflow.schemas.video import CropSettings, SubtitleStyle


@pytest.mark.parametrize("language,text,family", [
    ("vi", "Cảm ơn mẹ. Chúc ngủ ngon.", "Bangers"),
    ("en", "Have a wonderful day!", "Bangers"),
    ("es", "Que tengas buenas noches.", "Bangers"),
    ("zh", "今天的天气真好。", "Noto Sans SC Black"),
    ("zh-TW", "今天的天氣真好。", "Noto Sans TC Black"),
    ("ja", "一緒に始めましょう！", "Dela Gothic One"),
    ("ja", "東京", "Dela Gothic One"),
    ("ja", "丂と新しい物語", "Noto Sans JP Black"),
    ("ko", "곁에 있어 줘서 고마워요.", "Pretendard ExtraBold"),
    ("ko", "大韓民國", "Noto Sans KR Black"),
])
def test_caption_policy_selects_native_face_and_whole_cue_fallback(language, text, family):
    assert subtitle_font_for_text(text, language) == family
    assert covers_text(family, text)


def test_packaged_font_index_matches_actual_unmodified_files():
    catalog = font_catalog()
    assert set(catalog) == set(FONT_FILES)
    for family, spec in catalog.items():
        path = FONT_DIRECTORY / spec["file"]
        assert path.stat().st_size == spec["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"], family
        assert spec["copyright"]
    root = Path(__file__).resolve().parents[1]
    for name in ("NotoSansCJK", "DelaGothicOne", "Pretendard"):
        license_text = (root / "licenses" / f"{name}-OFL.txt").read_text("utf-8")
        assert "SIL OPEN FONT LICENSE" in license_text


def test_wheel_and_desktop_packaging_include_fonts_and_index():
    import glob
    import tomllib

    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
    patterns = metadata["tool"]["setuptools"]["package-data"]["haizflow"]
    package = root / "src/haizflow"
    included = {Path(path).resolve() for pattern in patterns for path in glob.glob(str(package / pattern))}
    assert (package / "assets/subtitle-fonts.json").resolve() in included
    for filename in FONT_FILES.values():
        assert (FONT_DIRECTORY / filename).resolve() in included
    desktop_script = (root / "scripts/build-exe.ps1").read_text("utf-8")
    assert "$SubtitleFontIndex;haizflow\\assets" in desktop_script
    assert "$SubtitleFontsPath;haizflow\\assets\\fonts" in desktop_script


@pytest.mark.parametrize("language,text,family", [
    ("zh", "今天的天气真好。", "Noto Sans SC Black"),
    ("ja", "東京", "Dela Gothic One"),
    ("ko", "오늘도 좋은 하루!", "Pretendard ExtraBold"),
])
def test_preview_and_export_keep_the_same_regional_font(tmp_path, language, text, family):
    from haizflow.desktop.subtitle_overlay_renderer import export_events, rasterize

    style = SubtitleStyle(font_size=65, position_y_percent=70)
    layout = resolve_subtitle_preview_layout(None, 1080, 1920, "keep_ratio", CropSettings(), style,
                                             True, subtitle_language=language)
    assert layout["fontFamily"] == family and layout["fontLanguage"] == language
    layout.update(layoutWidth=450, layoutHeight=130)
    header, events = export_events([dict(start=0, end=4, text=text)], layout, True, tmp_path / "preview")
    assert f"Style: Default,{family}," in header
    assert all(f"\\fn{family}" in event["body"] for event in events)
    frame = rasterize(header, events[0]["body"], layout, tmp_path / "raster")
    assert 15 < frame["width"] <= layout["layoutWidth"] + 12
    source, target = tmp_path / "export.srt", tmp_path / "export.ass"
    source.write_text(f"1\n00:00:00,000 --> 00:00:04,000\n{text}\n", "utf-8")
    _write_positioned_ass(str(source), str(target), style, 1080, 1920, subtitle_language=language)
    assert f"Style: Default,{family}," in target.read_text("utf-8-sig")


@pytest.mark.parametrize("language,text,fallback", [
    ("ja", "丂と新しい物語", "Noto Sans JP Black"),
    ("ko", "오늘의 大韓民國 이야기", "Noto Sans KR Black"),
])
def test_rare_glyph_fallback_is_explicit_in_ass_and_renders_without_system_fonts(tmp_path, language, text, fallback):
    from haizflow.desktop.subtitle_overlay_renderer import export_events, rasterize

    layout = dict(outputWidth=1080, outputHeight=1920, layoutWidth=520, layoutHeight=130,
                  fontSize=65, outline=4, positionXPercent=50, positionYPercent=70,
                  fontFamily="Bangers", fontLanguage=language)
    header, events = export_events([dict(start=0, end=4, text=text)], layout, True, tmp_path / "preview")
    assert events and all(f"\\fn{fallback}" in event["body"] for event in events)
    frame = rasterize(header, events[0]["body"], layout, tmp_path / "raster")
    assert 15 < frame["width"] <= layout["layoutWidth"] + 12


def test_qt_uses_registered_typographic_family_and_real_weight():
    from PySide6.QtGui import QFont, QFontInfo
    from PySide6.QtWidgets import QApplication

    from haizflow.desktop.subtitle_fonts import qt_subtitle_font

    app = QApplication.instance() or QApplication([])
    for language in ("vi", "zh", "ja", "ko"):
        spec = qt_subtitle_font(language=language)
        font = QFont(spec["family"])
        font.setWeight(QFont.Weight(spec["weight"]))
        actual = QFontInfo(font)
        assert actual.family() == spec["family"]
        assert actual.weight() == spec["weight"]
    fallback = qt_subtitle_font("大韓民國", "ko")
    assert fallback["family"] == "Noto Sans KR" and fallback["weight"] == 900
    assert app is not None
