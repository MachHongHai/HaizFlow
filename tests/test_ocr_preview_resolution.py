"""The editor's faster OCR proxy must not lower export resolution."""
import subprocess
import time
from unittest.mock import patch

import pytest

from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.pipeline import render
from haizflow.schemas.video import CropSettings, SubtitleStyle
from haizflow.utils.ffmpeg import _binary, get_video_dimensions, get_video_duration


@pytest.mark.parametrize("mode", ["blur", "patch"])
def test_real_proxy_scales_before_ocr_but_export_remains_full_size(tmp_path, mode):
    source = tmp_path / "source.mp4"
    subprocess.run([_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=1920x1080:rate=10:duration=1", "-c:v", "libx264", "-preset", "ultrafast",
        str(source)], check=True, capture_output=True)
    silent = tmp_path / "silence.wav"
    subtitles = tmp_path / "empty.srt"
    EditorPreviewController._write_silent_wav(silent, 1)
    EditorPreviewController._write_window_srt(subtitles, [], 0, 1)
    region = dict(x_percent=20, y_percent=70, width_percent=60, height_percent=10)
    output = tmp_path / "preview.mp4"
    prefix = render._ordered_subtitle_removal_prefix
    with patch.object(render, "_ordered_subtitle_removal_prefix", wraps=prefix) as treatment, \
         patch.object(render, "log_to_video"):
        started = time.perf_counter()
        render.render_video(str(source), str(silent), str(subtitles), str(output), "keep_ratio",
            SubtitleStyle(), CropSettings(), "resolution-test", region,
            original_subtitle_removal_mode=mode, compatibility_preview=True, preview_source_scale=True)
        preview_seconds = time.perf_counter() - started
    assert treatment.call_args.args[1:3] == (864, 486)
    assert get_video_dimensions(str(output)) == (864, 486)
    assert get_video_duration(str(output)) >= .9

    exported = tmp_path / "export.mp4"
    with patch.object(render, "_ordered_subtitle_removal_prefix", wraps=prefix) as treatment, \
         patch.object(render, "log_to_video"), \
         patch.object(render, "preferred_video_encoder", return_value=("libx264", ["-preset", "ultrafast"])):
        # Even if a caller accidentally sets the proxy flag, export cannot
        # enter that path without compatibility_preview=True.
        render.render_video(str(source), str(silent), str(subtitles), str(exported), "keep_ratio",
            SubtitleStyle(), CropSettings(), "resolution-test", region,
            original_subtitle_removal_mode=mode, preview_source_scale=True)
    assert treatment.call_args.args[1:3] == (1920, 1080)
    assert get_video_dimensions(str(exported)) == (1920, 1080)
    assert preview_seconds > 0
