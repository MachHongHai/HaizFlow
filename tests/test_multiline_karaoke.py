"""Multiline karaoke uses one continuous clock in preview and exported ASS."""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw
from PySide6.QtCore import QUrl

from haizflow.desktop.subtitle_overlay_renderer import (
    SubtitleOverlayRenderer, _karaoke_line_regions, export_events, rasterize,
)
from haizflow.pipeline.render import _karaoke_font_directory
from haizflow.utils.ffmpeg import _binary


def test_line_masks_follow_ass_clock_not_parallel_horizontal_progress():
    alpha = Image.new("L", (200, 120))
    draw = ImageDraw.Draw(alpha)
    for rectangle in ((40, 10, 159, 29), (20, 50, 179, 69), (60, 90, 139, 109)):
        draw.rectangle(rectangle, fill=255)
    body = r"{\kf40}Một {\kf100}dòng\N{\kf60}Hai\N{\kf100}Ba"
    lines = _karaoke_line_regions(body, alpha)
    assert [line["startCs"] for line in lines] == [0, 140, 200]
    assert [line["durationCs"] for line in lines] == [140, 60, 100]
    assert [line["width"] for line in lines] == [120, 160, 80]
    assert all(a["y"] + a["height"] <= b["y"] for a, b in zip(lines, lines[1:]))
    renderer = SubtitleOverlayRenderer()
    try:
        renderer._events = [dict(start=2, end=5, body=body)]
        renderer._cache[(0, body)] = dict(karaokeLines=lines, lineCount=3)
        with patch.object(renderer, "_submit") as submit:
            for time, expected in ((2.7, [0.5, 0, 0]), (3.7, [1, 0.5, 0]),
                                   (4.5, [1, 1, 0.5]), (2, [0, 0, 0])):
                renderer.seek(time)
                assert [line["progress"] for line in renderer.frame["karaokeLines"]] == pytest.approx(expected)
            submit.assert_not_called()  # Seeking never launches another raster job.
        assert "progress" not in lines[0]  # Static cache metadata stays immutable.
    finally:
        renderer.close()


def test_touching_outlines_still_get_disjoint_line_masks():
    alpha = Image.new("L", (200, 120), 255)
    lines = _karaoke_line_regions(r"{\kf100}A\N{\kf100}B\N{\kf100}C", alpha)
    assert [(line["y"], line["height"]) for line in lines] == [(0, 40), (40, 40), (80, 40)]


@pytest.mark.parametrize("height", [90, 180, 270])
def test_resizing_caption_preserves_sequential_line_clock_and_actual_ink_bounds(tmp_path, height):
    layout = dict(outputWidth=720, outputHeight=1280, layoutWidth=320, layoutHeight=height,
                  fontSize=60, outline=3, positionXPercent=50, positionYPercent=65,
                  fontFamily="Bangers", shadow=0)
    header, events = export_events([dict(start=1, end=7,
        text="Những người bạn đang trò chuyện trong căn phòng vào buổi tối")], layout, True, tmp_path)
    line_counts = []
    for event in events:
        frame = rasterize(header, event["body"], layout, tmp_path)
        lines = frame["karaokeLines"]
        line_counts.append(len(lines))
        assert len(lines) == frame["lineCount"] == event["body"].count(r"\N") + 1
        assert sum(line["durationCs"] for line in lines) == pytest.approx(
            (event["end"] - event["start"]) * 100, abs=1)
        assert lines[0]["startCs"] == 0
        with Image.open(Path(QUrl(frame["normal"]).toLocalFile())) as image:
            alpha = image.getchannel("A")
            for line in lines:
                assert line["width"] > 0 and line["height"] > 0
                region = (line["x"], line["y"], line["x"] + line["width"], line["y"] + line["height"])
                assert alpha.crop(region).getbbox() == (0, 0, line["width"], line["height"])
        for first, second in zip(lines, lines[1:]):
            assert second["startCs"] == first["startCs"] + first["durationCs"]
            assert first["y"] + first["height"] <= second["y"]
        assert rasterize(header, event["body"], layout, tmp_path) == frame  # Disk-cache round trip.
    assert max(line_counts) == height // 90


def test_exported_multiline_ass_highlights_later_rows_only_after_earlier_rows(tmp_path):
    layout = dict(outputWidth=720, outputHeight=1280, layoutWidth=320, layoutHeight=270,
                  fontSize=60, outline=3, positionXPercent=50, positionYPercent=65,
                  fontFamily="Bangers", shadow=0)
    header, events = export_events([dict(start=0, end=9,
        text="Những người bạn đang trò chuyện trong căn phòng vào buổi tối")], layout, True, tmp_path)
    event = next(event for event in events if event["body"].count(r"\N") == 2)
    frame = rasterize(header, event["body"], layout, tmp_path)
    lines = frame["karaokeLines"]
    ass = tmp_path / "export.ass"
    ass.write_text(header + "Dialogue: 0,0:00:00.00,0:00:09.00,Default,,0,0,0,,"
                   + event["body"] + "\n", encoding="utf-8")
    fonts = str(_karaoke_font_directory()).replace("\\", "/").replace(":", "\\:")
    counts = []
    for index, line in enumerate(lines):
        seconds = (line["startCs"] + line["durationCs"] * .65) / 100
        target = tmp_path / f"export-{index}.png"
        subprocess.run([_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
            "color=c=black:s=720x1280:r=100", "-vf",
            f"setpts=PTS+{seconds}/TB,ass=export.ass:fontsdir='{fonts}'",
            "-frames:v", "1", "-threads", "1", str(target)], cwd=tmp_path, check=True,
            capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with Image.open(target) as image:
            rgb = image.convert("RGB")
            row_counts = []
            for region in lines:
                pixels = rgb.crop((region["x"], region["y"], region["x"] + region["width"],
                                   region["y"] + region["height"])).get_flattened_data()
                row_counts.append(sum(r > 150 and g > 140 and b < 80 for r, g, b in pixels))
            counts.append(row_counts)
        assert row_counts[index] > 20
        assert all(count == 0 for count in row_counts[index + 1:])
    assert counts[1][0] >= counts[0][0]
    assert counts[2][1] >= counts[1][1]
