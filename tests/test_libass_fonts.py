"""Real FFmpeg regression for packaged Manual export's deep cache directories."""
import subprocess
import sys

import pytest

from haizflow.pipeline.render import _karaoke_font_directory
from haizflow.utils.ffmpeg import _binary


@pytest.mark.skipif(sys.platform != "win32", reason="Windows libass relative directory regression")
def test_bangers_is_loaded_in_deep_export_cache(tmp_path):
    work = tmp_path
    while len(str(work)) < 220:
        work = work / "export-cache"
    work.mkdir(parents=True)
    ass = work / "captions.ass"
    ass.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 320\nPlayResY: 240\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Bangers,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,1,0,2,0,0,20,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,HaizFlow\n", encoding="utf-8")
    fonts = _karaoke_font_directory().resolve().as_posix().replace(":", "\\:")
    result = subprocess.run([_binary("ffmpeg"), "-hide_banner", "-f", "lavfi", "-i",
                             "color=s=320x240:d=1:r=1", "-vf",
                             f"ass=captions.ass:fontsdir='{fonts}'", "-frames:v", "1", "-f", "null", "-"],
                            cwd=work, capture_output=True, text=True, timeout=20,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, result.stderr
    assert "-> Bangers-Regular" in result.stderr
    assert "-> ArialMT" not in result.stderr
