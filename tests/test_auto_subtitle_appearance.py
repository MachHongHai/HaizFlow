from types import SimpleNamespace
from unittest.mock import Mock

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.schemas.video import SubtitleStyle


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
        assert HaizFlowController.applySubtitleAppearance(host, patch)
        style = host._subtitle_style
        assert all(getattr(style, key) == ("Bangers" if key == "font_family" else value)
                   for key, value in patch.items())
        assert (style.position_x_percent, style.position_y_percent,
                style.box_width_percent, style.box_height_percent) == (45, 80, 64, 12)
        assert host._subtitle_layout_override is manual
        assert SubtitleStyle.model_validate(style.model_dump()) == style
        host.subtitleSettingsChanged.emit.assert_called_once()
        assert HaizFlowController.applySubtitleAppearance(host, patch)
        host.subtitleSettingsChanged.emit.assert_called_once()


def test_invalid_auto_appearance_never_partially_replaces_saved_style():
    original = SubtitleStyle()
    host = SimpleNamespace(_subtitle_style=original, subtitleSettingsChanged=Mock())
    for patch in ({"text_color": "not a color", "bold": True}, {"outline": -2},
                  {"font_size": 500}, {"position_x_percent": 5}, {"alignment": "invalid"}, {}):
        assert not HaizFlowController.applySubtitleAppearance(host, patch)
        assert host._subtitle_style == original
    host.subtitleSettingsChanged.emit.assert_not_called()
