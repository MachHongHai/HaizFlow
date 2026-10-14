"""Real FFmpeg coverage for single-pass quality/speed and constant OCR masks."""

import json
import subprocess
from unittest.mock import Mock

import numpy as np
import pytest

from hflow.pipeline import render, sequence_compiler
from hflow.schemas.editor import EditorAsset, EditorClip, EditorDocument, EditorSequence, EditorTrack
from hflow.schemas.video import CropSettings, SubtitleStyle
from hflow.utils.ffmpeg import _binary, get_video_dimensions, get_video_duration


def ffmpeg(*args):
    return subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", *args],
                          capture_output=True, check=True, timeout=45).stdout


@pytest.fixture
def media(tmp_path, monkeypatch):
    source, voice, subtitles = [tmp_path / name for name in ("source.mp4", "voice.wav", "subtitles.srt")]
    ffmpeg("-f", "lavfi", "-i", "color=blue:size=192x108:rate=20:duration=2",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source))
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2", "-ac", "2", str(voice))
    subtitles.write_text("1\n00:00:00,600 --> 00:00:01,200\nTest\n", encoding="utf-8")
    monkeypatch.setattr(render, "log_to_video", Mock())
    monkeypatch.setattr(render, "preferred_video_encoder", lambda *_: ("libx264", ["-preset", "ultrafast", "-crf", "18"]))
    return source, voice, subtitles


@pytest.mark.parametrize("preset", ["source", "720p", "1080p", "1080p-high", "2160p"])
@pytest.mark.parametrize("speed", [.5, 1, 2, 3])
def test_fused_render_one_encode_correct_dimensions_duration_and_pitch(media, tmp_path, monkeypatch, preset, speed):
    source, voice, subtitles = media
    original = subprocess.Popen
    commands = []

    def capture(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(render.subprocess, "Popen", capture)
    progress, output = [], tmp_path / "output.mp4"
    render.render_video(str(source), str(voice), str(subtitles), str(output), "keep_ratio", SubtitleStyle(),
        CropSettings(), "fused-test", export_preset=preset, output_speed=speed, progress_callback=progress.append)
    assert len([command for command in commands if "-c:v" in command]) == 1
    assert get_video_dimensions(str(output)) == (192, 108)  # Never upscale a small source to 4K.
    assert abs(get_video_duration(str(output)) - 2 / speed) < .1
    assert progress == sorted(progress) and progress[-1] == 1
    samples = np.frombuffer(ffmpeg("-i", str(output), "-vn", "-ac", "1", "-ar", "48000",
        "-f", "f32le", "pipe:1"), np.float32)
    samples = samples[4800:-4800]
    dominant = np.fft.rfftfreq(len(samples), 1 / 48000)[np.argmax(np.abs(np.fft.rfft(samples)))]
    assert abs(dominant - 440) < 3


def test_4k_source_is_scaled_to_hd_in_first_encode(tmp_path, monkeypatch):
    source, voice, subtitles, output = [tmp_path / name for name in ("4k.mp4", "voice.wav", "subtitles.srt", "hd.mp4")]
    ffmpeg("-f", "lavfi", "-i", "color=blue:size=3840x2160:rate=5:duration=2", "-c:v", "libx264",
           "-preset", "ultrafast", str(source))
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2", str(voice))
    subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n", encoding="utf-8")
    original, commands = subprocess.Popen, []

    def capture(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(render.subprocess, "Popen", capture)
    monkeypatch.setattr(render, "log_to_video", Mock())
    render.render_video(str(source), str(voice), str(subtitles), str(output), "keep_ratio", SubtitleStyle(),
        CropSettings(), "4k-test", export_preset="1080p-high", output_speed=2)
    encodes = [command for command in commands if "-c:v" in command and "4k.mp4" in command]
    assert len(encodes) == 1
    assert "scale=1920:1080:flags=lanczos" in encodes[0][encodes[0].index("-vf") + 1]
    assert get_video_dimensions(str(output)) == (1920, 1080)
    assert get_video_duration(str(output)) == pytest.approx(1, abs=.2)


def test_fused_caption_clock_is_changed_only_after_drawing(media, tmp_path):
    source, voice, subtitles = media
    output = tmp_path / "clock.mp4"
    render.render_video(str(source), str(voice), str(subtitles), str(output), "keep_ratio", SubtitleStyle(),
        CropSettings(), "clock-test", output_speed=2)

    def white_pixels(at):
        frame = np.frombuffer(ffmpeg("-ss", str(at), "-i", str(output), "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"), np.uint8).reshape(108, 192, 3)
        return np.count_nonzero((frame[:, :, 0] > 150) & (frame[:, :, 1] > 150))

    assert white_pixels(.1) < 5
    assert white_pixels(.4) > 15
    assert white_pixels(.8) < 5


@pytest.mark.parametrize("mode", ["blur_background_9_16", "tiktok_9_16_crop"])
def test_portrait_patch_and_image_watermark_fuse_final_size_speed_in_one_pass(media, tmp_path, monkeypatch, mode):
    source, voice, subtitles = media
    image, output = tmp_path / "mark.bmp", tmp_path / "portrait.mp4"
    ffmpeg("-f", "lavfi", "-i", "color=red:size=24x24", "-frames:v", "1", str(image))
    original, commands = subprocess.Popen, []

    def capture(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(render.subprocess, "Popen", capture)
    region = {"x_percent": 10, "y_percent": 70, "width_percent": 80, "height_percent": 15}
    render.render_video(str(source), str(voice), str(subtitles), str(output), mode, SubtitleStyle(), CropSettings(),
        "portrait-fused", region, export_preset="720p", output_speed=2,
        watermark_kind="image", watermark_image_path=str(image))
    encodes = [command for command in commands if "-c:v" in command]
    assert len(encodes) == 1
    graph = encodes[0][encodes[0].index("-filter_complex") + 1]
    assert "scale=720:1280:flags=lanczos" in graph
    assert "setpts=(PTS-STARTPTS)/2.000000" in graph
    assert "alphamerge" in graph and "geq=r=" not in graph
    assert get_video_dimensions(str(output)) == (720, 1280)
    assert get_video_duration(str(output)) == pytest.approx(1, abs=.1)


def test_constant_patch_mask_matches_existing_feather_on_first_and_last_frames():
    decoded = []
    for static in (False, True):
        prefix = render._subtitle_patch_prefix((12, 68, 104, 18), 128, 96, static_mask=static)
        raw = ffmpeg("-f", "lavfi", "-i", "testsrc2=size=128x96:rate=10:duration=2",
            "-filter_complex", prefix + "[source_without_original]null[out]", "-map", "[out]",
            "-frames:v", "20", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1")
        decoded.append(np.frombuffer(raw, np.uint8).reshape(20, 96, 128, 3).astype(np.int16))
    for index in (0, 10, 19):
        assert np.mean(np.abs(decoded[0][index] - decoded[1][index])) < 3
        # The copied patch keeps following moving source pixels, not frame 1.
    assert not np.array_equal(decoded[1][0, 70:80], decoded[1][-1, 70:80])


@pytest.mark.parametrize("speed", [.5, 2])
def test_overlay_pass_fuses_speed_and_keeps_audio(media, tmp_path, monkeypatch, speed):
    source, _voice, _subtitles = media
    image = tmp_path / "overlay.bmp"
    ffmpeg("-f", "lavfi", "-i", "color=red:size=24x24", "-frames:v", "1", str(image))
    base = tmp_path / "base.mp4"
    ffmpeg("-i", str(source), "-i", str(_voice), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", str(base))
    document = EditorDocument(video_id="overlay-fused", sequence=EditorSequence(duration_ms=2000),
        tracks=[EditorTrack(track_id="overlays", kind="overlay", name="Overlay")],
        assets=[EditorAsset(asset_id="img", kind="image", path=str(image), width=24, height=24)],
        clips=[EditorClip(clip_id="img", track_id="overlays", kind="image", asset_id="img", start_ms=500, duration_ms=1000)])
    output, commands = tmp_path / "overlaid.mp4", []
    original = subprocess.Popen

    def capture(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(sequence_compiler.subprocess, "Popen", capture)
    sequence_compiler.apply_overlays(str(base), str(output), document, "overlay-test", export_preset="source", output_speed=speed)
    assert len([command for command in commands if "-c:v" in command]) == 1
    assert get_video_duration(str(output)) == pytest.approx(2 / speed, abs=.1)
    info = json.loads(subprocess.check_output([_binary("ffprobe"), "-v", "error", "-show_streams", "-of", "json", str(output)]))
    durations = [float(stream["duration"]) for stream in info["streams"] if stream["codec_type"] in {"audio", "video"}]
    assert max(durations) - min(durations) < .1


def test_manual_and_auto_do_not_call_extra_finishing_encoder():
    # Guard the production entry points, not just the isolated renderer API.
    import inspect
    from hflow.pipeline import manual_tools, process_video, segment_export

    for function in (manual_tools._run_export, segment_export.render_segment):
        assert "finish_export_resolution(" not in inspect.getsource(function)
    assert "finish_export_resolution(" not in inspect.getsource(process_video)
