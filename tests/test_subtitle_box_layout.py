"""Caption-box dimensions affect phrase capacity, never source speech timing."""
from datetime import timedelta
from unittest.mock import patch

import srt

from haizflow.pipeline import render
from haizflow.schemas.video import SubtitleStyle


def test_width_and_height_change_phrases_but_preserve_the_word_clock(tmp_path):
    cue = srt.Subtitle(1, timedelta(seconds=2), timedelta(seconds=8),
                      "Một câu phụ đề khá dài để kiểm tra khả năng thay đổi chiều rộng và chiều cao của khung chữ")
    style = SubtitleStyle(font_size=60)
    narrow = render._subtitle_parts_for_region(cue, render.SubtitleRegionLayout(0, 0, 360, 90), style,
                                               fixed_font_size=True)
    wide = render._subtitle_parts_for_region(cue, render.SubtitleRegionLayout(0, 0, 720, 90), style,
                                             fixed_font_size=True)
    tall = render._subtitle_parts_for_region(cue, render.SubtitleRegionLayout(0, 0, 360, 270), style,
                                             fixed_font_size=True)
    assert len(narrow) > len(wide)
    assert len(narrow) > len(tall)
    assert all("\n" not in part[2] for part in narrow)
    assert any("\n" in part[2] for part in tall)
    clocks = []
    for parts in (narrow, wide, tall):
        assert parts[0][0] == cue.start and parts[-1][1] == cue.end
        assert all(part[3] == 60 and part[4] == 100 for part in parts)
        clocks.append([duration for _, durations in render._karaoke_part_timelines(cue.content,
                      [part[2] for part in parts], 6) for duration in durations])
    assert clocks[0] == clocks[1] == clocks[2]
    source = tmp_path / "subtitles.srt"
    source.write_text(srt.compose([cue]), encoding="utf-8")
    target = tmp_path / "captions.ass"
    render._write_positioned_ass(str(source), str(target), style, 1080, 1920,
                                render.SubtitleRegionLayout(0, 0, 360, 270), fixed_font_size=True)
    assert r"\N" in target.read_text(encoding="utf-8-sig")
    shallow = render._subtitle_parts_for_region(cue, render.SubtitleRegionLayout(0, 0, 360, 28), style,
                                                fixed_font_size=True)
    assert all(10 <= part[3] < 60 for part in shallow)
    assert all(part[4] == 100 for part in shallow)


def test_overlay_keeps_visible_frame_while_reconfiguring():
    from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer

    renderer = SubtitleOverlayRenderer()
    try:
        renderer._frame = {"normal": "file:///existing.png", "text": "previous"}
        renderer._frame_window = (0, 2)
        with patch.object(renderer, "_submit"):
            renderer.configure("[]", '{"outputWidth":1080,"outputHeight":1920}', True, True)
        renderer.seek(1)
        assert renderer.frame["normal"] == "file:///existing.png"
        renderer._accept(("events", renderer._generation, "", []))
        assert not renderer.frame
    finally:
        renderer.close()


def test_horizontal_capacity_packs_more_words_without_changing_font_or_speech_clock():
    cue = srt.Subtitle(1, timedelta(0), timedelta(seconds=8),
                      "Những người bạn đang trò chuyện vui vẻ trong căn phòng vào buổi tối")
    style = SubtitleStyle(font_size=65, uppercase=True)
    counts = []
    clocks = []
    for width in (180, 300, 450, 640):
        parts = render._subtitle_parts_for_region(
            cue, render.SubtitleRegionLayout(0, 0, width, 100), style, fixed_font_size=True)
        counts.append(len(parts[0][2].split()))
        assert all(part[3:] == (65, 100) for part in parts)
        assert " ".join(part[2] for part in parts) == cue.content
        clocks.append([duration for _, durations in render._karaoke_part_timelines(
            cue.content, [part[2] for part in parts], 8) for duration in durations])
    assert counts == sorted(counts)
    assert counts[-1] > counts[0]
    assert all(clock == clocks[0] for clock in clocks)


def test_caption_capacity_measures_glyph_width_not_character_count():
    style = SubtitleStyle(font_size=65, uppercase=True, letter_spacing=2)
    narrow_glyphs = render._split_caption_lines_by_width("iiii iiii iiii iiii", 220, 65, style)
    wide_glyphs = render._split_caption_lines_by_width("WWWW WWWW WWWW WWWW", 220, 65, style)
    assert len(narrow_glyphs) < len(wide_glyphs)


def test_caption_width_measurement_matches_libass_font_metrics(tmp_path):
    from haizflow.desktop.subtitle_overlay_renderer import export_events, rasterize

    text = "NHUNG NGUOI BAN DANG NOI CHUYEN"
    path, _exact = render._font_path_details("Bangers", False, False)
    font = render._caption_measurement_font(str(path), 1024)
    measured = font.getlength(text) * 112 * render._ass_font_em_scale(str(path)) / 1024
    layout = dict(outputWidth=1920, outputHeight=1080, layoutWidth=1800, layoutHeight=200,
                  fontSize=112, outline=5, positionXPercent=50, positionYPercent=70,
                  fontFamily="Bangers", letterSpacing=0)
    header, events = export_events([dict(start=0, end=3, text=text)], layout, True, tmp_path)
    assert len(events) == 1
    frame = rasterize(header, events[0]["body"], layout, tmp_path)
    # Raster bounds also include outline, italic overshoot and integer rounding.
    assert abs(frame["width"] - measured) < measured * .05 + layout["outline"] * 4
    broken_font = tmp_path / "broken.ttf"
    broken_font.write_bytes(b"invalid")
    assert render._ass_font_em_scale(str(broken_font)) == 1
