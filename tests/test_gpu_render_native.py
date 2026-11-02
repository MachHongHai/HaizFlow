"""Use a real verified hardware encoder, rather than mocking FFmpeg success."""
import subprocess
from unittest.mock import Mock

import pytest

from haizflow.pipeline import render
from haizflow.schemas.video import CropSettings, SubtitleStyle
from haizflow.utils import ffmpeg


def test_real_gpu_render_retains_subtitles_audio_and_output_speed(tmp_path, monkeypatch):
    ffmpeg._encoder_works.cache_clear()
    encoder, options = ffmpeg.preferred_video_encoder(18)
    if encoder == "libx264":
        pytest.skip("No working NVENC/QSV/AMF device on this machine")
    source, voice, subtitles, output = [tmp_path / name for name in (
        "source.mp4", "voice.wav", "captions.srt", "result.mp4")]

    def generate(*args):
        subprocess.run([ffmpeg._binary("ffmpeg"), "-y", "-v", "error", *args],
                       capture_output=True, check=True, timeout=45)

    generate("-f", "lavfi", "-i", "color=blue:size=1280x720:rate=20:duration=2",
             "-c:v", "libx264", "-preset", "ultrafast", str(source))
    generate("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2", str(voice))
    subtitles.write_text("1\n00:00:00,000 --> 00:00:01,500\nGPU render\n", encoding="utf-8")
    monkeypatch.setattr(render, "log_to_video", Mock())
    monkeypatch.setattr(render, "preferred_video_encoder", lambda *_: (encoder, options))
    original, commands = subprocess.Popen, []

    def capture(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(render.subprocess, "Popen", capture)
    progress = []
    render.render_video(str(source), str(voice), str(subtitles), str(output), "keep_ratio",
                        SubtitleStyle(), CropSettings(), "gpu-native-fixture",
                        encoding_quality=18, output_speed=2, progress_callback=progress.append)
    encodes = [command for command in commands if "-c:v" in command]
    assert len(encodes) == 1 and encodes[0][encodes[0].index("-c:v") + 1] == encoder
    assert "ass=" in str(encodes[0])
    assert ffmpeg.get_video_dimensions(str(output)) == (1280, 720)
    assert ffmpeg.get_video_duration(str(output)) == pytest.approx(1, abs=.15)
    assert {"audio", "video"}.issubset(ffmpeg.get_media_stream_types(str(output)))
    assert progress == sorted(progress) and progress[-1] == 1
    frame = subprocess.run([ffmpeg._binary("ffmpeg"), "-v", "error", "-ss", "0.2", "-i", str(output),
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                           check=True, capture_output=True, timeout=20).stdout
    # White/yellow caption pixels must survive the hardware encode on blue.
    assert sum(frame[index] > 150 and frame[index + 1] > 150
               for index in range(0, len(frame) - 2, 3)) > 50
