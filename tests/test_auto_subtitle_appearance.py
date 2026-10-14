from types import SimpleNamespace
from unittest.mock import Mock

from hflow.desktop.qml_controller import HFlowController
from hflow.schemas.video import SubtitleStyle


def test_auto_appearance_is_atomic_and_preserves_cover_alignment_and_geometry():
    original = SubtitleStyle(position_x_percent=45, position_y_percent=80,
                             box_width_percent=64, box_height_percent=12)
    patch = dict(font_family="Arial", font_size=84, text_color="#EF5350",
                 karaoke_color="#FFEF00", outline_color="#FFFFFF", outline=8,
                 bold=True, italic=True, uppercase=True, shadow=4,
                 letter_spacing=1.5, alignment="left")
    for manual in (False, True):
        host = SimpleNamespace(_subtitle_style=original, _subtitle_layout_override=manual,
                               subtitleSettingsChanged=Mock())
        assert HFlowController.applySubtitleAppearance(host, patch)
        style = host._subtitle_style
        assert all(getattr(style, key) == ("Bangers" if key == "font_family" else value)
                   for key, value in patch.items())
        assert (style.position_x_percent, style.position_y_percent,
                style.box_width_percent, style.box_height_percent) == (45, 80, 64, 12)
        assert host._subtitle_layout_override is manual
        assert SubtitleStyle.model_validate(style.model_dump()) == style
        host.subtitleSettingsChanged.emit.assert_called_once()
        assert HFlowController.applySubtitleAppearance(host, patch)
        host.subtitleSettingsChanged.emit.assert_called_once()


def test_invalid_auto_appearance_never_partially_replaces_saved_style():
    original = SubtitleStyle()
    host = SimpleNamespace(_subtitle_style=original, subtitleSettingsChanged=Mock())
    for patch in ({"text_color": "not a color", "bold": True}, {"outline": -2},
                  {"font_size": 500}, {"position_x_percent": 5}, {"alignment": "invalid"}, {}):
        assert not HFlowController.applySubtitleAppearance(host, patch)
        assert host._subtitle_style == original
    host.subtitleSettingsChanged.emit.assert_not_called()


def test_auto_ocr_font_outgrows_thin_box_without_changing_cover_or_manual_style():
    from hflow.pipeline import render
    from hflow.schemas.video import CropSettings

    for width, height, expected_size in ((1920, 1080, 80), (1080, 1920, 92), (2160, 3840, 184)):
        region = dict(x_percent=20, y_percent=88, width_percent=60, height_percent=2, line_height_percent=1)
        original = dict(region)
        layout = render._output_subtitle_region_layout(region, width, height, "keep_ratio", CropSettings(), width, height)
        style = render._style_for_original_subtitle_region(SubtitleStyle(), layout, width, height)
        enlarged = render._readable_auto_subtitle_layout(layout, style, height)
        assert style.font_size == expected_size
        assert enlarged.height > layout.height
        assert enlarged.x == layout.x and enlarged.width == layout.width
        assert 0 <= enlarged.y <= height - enlarged.height
        cue = SimpleNamespace(content="Phụ đề đủ lớn để đọc rõ trên video", start=render.timedelta(),
                              end=render.timedelta(seconds=5))
        parts = render._subtitle_parts_for_region(cue, enlarged, style, fixed_font_size=True)
        assert all(part[3] == expected_size for part in parts)
        preview = render.resolve_subtitle_preview_layout(region, width, height, "keep_ratio", CropSettings(), SubtitleStyle(), False)
        assert preview["fontSize"] == expected_size and preview["layoutHeight"] == round(enlarged.height)
        manual = render.resolve_subtitle_preview_layout(region, width, height, "keep_ratio", CropSettings(), SubtitleStyle(font_size=40), True)
        assert manual["fontSize"] == 40
        assert region == original
