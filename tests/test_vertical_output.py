"""Portrait composition: mocked policy tests plus real, tiny FFmpeg renders."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from hflow.desktop.editor_preview_controller import EditorPreviewController
from hflow.desktop.qml_controller import HFlowController
from hflow.pipeline import render
from hflow.schemas.video import CropSettings, SubtitleStyle, VideoConfig, VideoInfo
from hflow.services import batch_settings
from hflow.services.ocr_regions import source_frame_in_output
from hflow.utils.ffmpeg import _binary, get_video_dimensions, get_video_duration, get_media_stream_types

QML_DIR = Path(__file__).parents[1] / "src/hflow/desktop/qml"


@pytest.mark.parametrize("mode", ["keep_ratio", "blur_background_9_16", "tiktok_9_16_crop"])
def test_batch_round_trip_and_override_detection(mode):
    config = VideoConfig(output_format=mode)
    video = SimpleNamespace(**config.model_dump(), files={})
    video.subtitle_style = config.subtitle_style
    values = batch_settings.values_for(video)
    assert values["outputFormat"] == mode
    assert batch_settings.config_for(values).output_format == mode
    assert batch_settings.config_for({}).output_format == "keep_ratio"
    assert batch_settings.differences(values, {**values, "outputFormat": "other"}) == ["outputFormat"]


def test_invalid_format_is_not_saved():
    host = SimpleNamespace(outputFormat="keep_ratio", _output_format="keep_ratio", outputFormatChanged=Mock())
    HFlowController.outputFormat.fset(host, "arbitrary-ffmpeg-text")
    assert host._output_format == "keep_ratio"
    host.outputFormatChanged.emit.assert_not_called()
    HFlowController.outputFormat.fset(host, "blur_background_9_16")
    assert HFlowController.outputFormat.fget(host) == "blur_background_9_16"
    host.outputFormatChanged.emit.assert_called_once()


@pytest.mark.parametrize("project_type", ["manual", "single", "batch"])
def test_manual_auto_batch_config_keeps_draft_output_format(project_type):
    config = VideoConfig(project_type=project_type, output_format="blur_background_9_16")
    host = SimpleNamespace(**{"_" + name: value for name, value in config.__dict__.items()})
    host._settings_processing_device = "cpu"
    host._crop_settings = config.crop
    host._original_volume = config.original_video_volume
    host._selected_project_key = ""
    host._background_music_path = ""
    with patch("hflow.desktop.qml_controller.project_store.get_project", return_value=None):
        result = HFlowController._build_config(host)
    assert result.output_format == "blur_background_9_16"
    assert result.project_type == project_type


def test_frame_change_deactivates_only_visual_export_not_ai_or_audio():
    video = VideoInfo(**VideoConfig(project_type="manual").model_dump(), video_id="portrait",
        original_filename="clip.mp4", status="manual_ready", created_at="", updated_at="",
        manual_completed_stages=["translation", "subtitles", "voice", "timeline", "render"])
    config = VideoConfig.model_validate(video.model_dump())
    config.output_format = "blur_background_9_16"
    with (patch("hflow.desktop.qml_controller.video_store.update_video") as update,
          patch("hflow.desktop.qml_controller.video_store.get_video", return_value=video),
          patch.object(HFlowController, "_sync_legacy_editor_visual_settings"),
          patch("hflow.desktop.qml_controller.manual_artifacts.deactivate") as deactivate):
        HFlowController._apply_config_to_video(SimpleNamespace(), video, config)
    changes = update.call_args.kwargs
    assert changes["output_format"] == "blur_background_9_16"
    assert changes["manual_completed_stages"] == ["translation", "subtitles", "voice", "timeline"]
    deactivate.assert_called_once_with("portrait", {"visual_proxy", "export"})


@pytest.mark.parametrize("width,height", [(1920, 1080), (1080, 1080), (1080, 1920), (720, 1920)])
def test_source_ocr_coordinates_fit_inside_portrait_foreground(width, height):
    frame = source_frame_in_output(width, height, "blur_background_9_16", CropSettings())
    assert frame["x_percent"] >= -1e-6 and frame["y_percent"] >= -1e-6
    assert frame["x_percent"] + frame["width_percent"] <= 100.000001
    assert frame["y_percent"] + frame["height_percent"] <= 100.000001
    assert frame["width_percent"] / frame["height_percent"] == pytest.approx(width / height / (1080 / 1920))
    region = {"x_percent": 10, "y_percent": 80, "width_percent": 80, "height_percent": 8}
    mapped = render.map_subtitle_region_to_output_percent(region, width, height, "blur_background_9_16", CropSettings())
    assert mapped["y_percent"] == pytest.approx(frame["y_percent"] + .8 * frame["height_percent"])
    assert mapped["width_percent"] == pytest.approx(.8 * frame["width_percent"])


def test_format_changes_visual_signature_but_not_preview_audio():
    settings = dict(video_id="one", source_identity={}, editor_sequence={}, segments=[],
        crop={}, output_format="keep_ratio", remove_original_subtitles=False, removal_mode="patch",
        watermark_text="", watermark_scale_percent=100, ocr_region={}, preview_encoding="stable",
        voice_state={"ready": True}, audio_inputs={}, tts_provider="edge", tts_voice="voice",
        target_language="vi", speaker_mode="single", original_video_volume=60,
        background_music_volume=30, tts_volume=100, duration=1800)
    changed = {**settings, "output_format": "blur_background_9_16"}
    assert EditorPreviewController._base_visual_cache_payload(settings) != EditorPreviewController._base_visual_cache_payload(changed)
    assert EditorPreviewController._audio_cache_payload(settings) == EditorPreviewController._audio_cache_payload(changed)


def _check_frame_settings_qml():
    from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl
    from PySide6.QtGui import QGuiApplication, QFontDatabase
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    from PySide6.QtTest import QSignalSpy, QTest

    app = QGuiApplication.instance() or QGuiApplication([])
    for font in ("SegUIVar.ttf", "SegoeIcons.ttf"):
        QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / font))
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import "{QML_DIR.as_uri()}"
OutputFrameSettings {{ width: 330 }}'''.encode(), QUrl())
    assert component.isReady(), [item.toString() for item in component.errors()]
    root = component.create()
    assert isinstance(root, QQuickItem)
    window = QQuickWindow()
    window.resize(960, 240)
    root.setParentItem(window.contentItem())
    window.show()
    try:
        combo = root.findChild(QObject, "outputFrameCombo")
        assert combo.property("count") == 3 and combo.property("currentIndex") == 0
        assert combo.property("activeFocusOnTab")
        QTest.qWait(30)
        fixed_width = combo.width()
        assert fixed_width == combo.implicitWidth() and fixed_width < root.width() * .75
        for compact in (False, True):
            root.setProperty("compact", compact)
            for width in (330, 620, 960):
                root.setWidth(width)
                for mode in ("keep_ratio", "blur_background_9_16", "tiktok_9_16_crop"):
                    root.setProperty("outputFormat", mode)
                    QTest.qWait(15)
                    assert abs(combo.width() - fixed_width) < .01
                    if compact:
                        assert combo.x() + combo.width() < 400  # No trailing full-row stretch.
        root.setProperty("outputFormat", "keep_ratio")
        spy = QSignalSpy(root.edited)
        root.setProperty("outputFormat", "blur_background_9_16")
        app.processEvents()
        assert combo.property("currentIndex") == 1
        assert spy.count() == 0  # Loading a saved choice must not re-save it.
        root.setProperty("editable", False)
        assert not combo.property("enabled")
        root.setProperty("outputFormat", "tiktok_9_16_crop")
        app.processEvents()
        assert combo.property("currentIndex") == 2
    finally:
        window.close()
        root.deleteLater()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_frame_settings_qml_is_bound_keyboard_accessible_and_locked_when_busy():
    # Other UI suites register the real controller singleton. Keep this small
    # component's engine/application lifetime isolated from those engines.
    runner = f"import runpy; runpy.run_path({str(Path(__file__).resolve())!r})['_check_frame_settings_qml']()"
    result = subprocess.run([sys.executable, "-X", "faulthandler", "-c", runner],
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr


def run_ffmpeg(*args):
    return subprocess.run([_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True, check=True, timeout=45)


@pytest.mark.parametrize("width,height,mode", [
    (192, 108, "blur_background_9_16"), (144, 144, "blur_background_9_16"),
    (108, 192, "blur_background_9_16"), (96, 240, "blur_background_9_16"),
    (108, 192, "tiktok_9_16_crop"),
    (192, 108, "keep_ratio"),
])
def test_real_portrait_render_preserves_edges_audio_and_bounded_duration(tmp_path, width, height, mode):
    source, voice, subtitles, output = [tmp_path / name for name in ("source.mp4", "voice.wav", "subtitles.srt", "out.mp4")]
    run_ffmpeg("-f", "lavfi", "-i", f"color=green:size={width}x{height}:rate=6:duration=3,"
        f"drawbox=x=0:y=0:w=iw/5:h=ih:color=red:t=fill,"
        f"drawbox=x=iw*4/5:y=0:w=iw/5:h=ih:color=blue:t=fill",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source))
    run_ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1", str(voice))
    subtitles.write_text("1\n00:00:00,000 --> 00:00:00,100\nTest\n", encoding="utf-8")
    commands = []
    popen = subprocess.Popen

    def capture(command, **kwargs):
        commands.append(command)
        return popen(command, **kwargs)

    with (patch.object(render, "log_to_video"),
          patch.object(render, "preferred_video_encoder", return_value=("libx264", ["-preset", "ultrafast", "-crf", "18"])),
          patch.object(render.subprocess, "Popen", side_effect=capture)):
        render.render_video(str(source), str(voice), str(subtitles), str(output), mode, SubtitleStyle(),
            CropSettings(), "isolated-portrait", source_start_seconds=1, source_duration_seconds=1)
    assert get_video_duration(str(output)) == pytest.approx(1, abs=.2)
    assert get_media_stream_types(str(output)) == {"video", "audio"}
    out_width, out_height = get_video_dimensions(str(output))
    assert (out_width, out_height) == ((width, height) if mode == "keep_ratio" or width * 16 == height * 9 else (1080, 1920))
    command = next(item for item in commands if "-progress" in item)
    if width * 16 == height * 9:
        assert "-filter_complex" not in command
        assert "scale=" not in command[command.index("-vf") + 1]
        assert "boxblur" not in command[command.index("-vf") + 1]
    assert command.index("-ss") < command.index("-i")
    assert command[command.index("-t") + 1] == "1.000000"
    probe = subprocess.run([_binary("ffprobe"), "-v", "error", "-show_entries", "stream=sample_aspect_ratio",
        "-select_streams", "v:0", "-of", "json", str(output)], capture_output=True, check=True, timeout=15)
    assert json.loads(probe.stdout)["streams"][0]["sample_aspect_ratio"] == "1:1"
    pixels = run_ffmpeg("-ss", "0.5", "-i", str(output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1").stdout
    frame = np.frombuffer(pixels, np.uint8).reshape(out_height, out_width, 3)
    scale = min(out_width / width, out_height / height)
    fg_width = width * scale
    left = (out_width - fg_width) / 2
    red = frame[out_height // 2, int(left + fg_width * .08)].astype(int)
    blue = frame[out_height // 2, int(left + fg_width * .92)].astype(int)
    assert red[0] > red[1] + red[2] + 80
    assert blue[2] > blue[0] + blue[1] + 80
    if mode == "blur_background_9_16" and height * scale < out_height - 20:
        assert frame[10, out_width // 2].max() > 40  # Video-derived fill, not black bars.
    audio = run_ffmpeg("-i", str(output), "-map", "0:a:0", "-f", "f32le", "pipe:1").stdout
    assert np.max(np.abs(np.frombuffer(audio, np.float32))) > .05


@pytest.mark.parametrize("mode", ["blur_background_9_16", "tiktok_9_16_crop"])
def test_mixed_batch_skips_portrait_only_without_mutating_shared_choice(mode):
    settings = batch_settings.config_for({"outputFormat": mode})
    sizes = [(720, 1280), (1920, 1080), (576, 1024), (1080, 1080), (1080, 1920)]
    effective = [render.effective_output_format(w, h, settings.output_format, settings.crop) for w, h in sizes]
    assert effective == ["keep_ratio", mode, "keep_ratio", mode, "keep_ratio"]
    assert settings.output_format == mode
    for width, height in (sizes[0], sizes[2], sizes[4]):
        original = render.resolve_subtitle_preview_layout(None, width, height, "keep_ratio", settings.crop, settings.subtitle_style, True)
        normalized = render.resolve_subtitle_preview_layout(None, width, height, mode, settings.crop, settings.subtitle_style, True)
        assert normalized == original
    assert render.effective_output_format(720, 1280, mode, CropSettings(left_percent=10)) == mode
    assert render.effective_output_format(0, 0, mode, CropSettings()) == mode
