"""The retained preview optimisation must not enable GPU encoders or alter cache keys."""

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.pipeline import render
from haizflow.schemas.video import CropSettings, SubtitleStyle, VideoConfig, VideoInfo
from haizflow.utils import ffmpeg


@pytest.mark.parametrize("device", ["cpu", "gpu"])
def test_preview_request_keeps_existing_cpu_cache_contract_for_either_app_device(tmp_path, device):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    video = VideoInfo(video_id="owner", original_filename="source.mp4", status="manual_ready",
        created_at="2026-11-13", updated_at="2026-11-13", **VideoConfig(project_type="manual").model_dump())
    host = SimpleNamespace(_selected_video=lambda: video, _resolve_video_file=lambda *_: str(source),
        _settings_processing_device=device, manualPreviewAudio=object(), editorPreviewChanged=Mock())
    controller = EditorPreviewController(host)
    with (patch.object(controller, "_ocr_region", return_value={}),
          patch.object(controller, "_source_subtitle_intervals", return_value=[]),
          patch.object(controller, "_manual_voice_artifact", return_value=None),
          patch.object(controller, "_restore_manual_disk_cache"),
          patch("haizflow.services.video_store.get_video_dir", return_value=str(tmp_path)),
          patch("haizflow.services.ocr_layers.render_region", return_value={}),
          patch("haizflow.services.editor_documents.load", return_value=None),
          patch("haizflow.desktop.editor_preview_controller.threading.Thread") as worker):
        assert controller.request("[]", 0)
    captured = worker.call_args.kwargs["args"][3]
    assert "preview_gpu" not in captured
    assert "preview_gpu" not in controller._base_visual_cache_payload(captured)


def test_real_preview_uses_compatible_cpu_encoder_without_probing_gpu(tmp_path, monkeypatch):
    source, voice, subtitles, output = [tmp_path / name for name in
        ("source.mp4", "voice.wav", "captions.srt", "preview.mp4")]
    subprocess.run([ffmpeg._binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
        "testsrc2=s=320x180:r=10:d=1", "-c:v", "libx264", "-preset", "ultrafast", str(source)],
        check=True, capture_output=True, timeout=30)
    EditorPreviewController._write_silent_wav(voice, 1)
    EditorPreviewController._write_window_srt(subtitles, [], 0, 1)
    monkeypatch.setattr(render, "preferred_video_encoder", Mock(side_effect=AssertionError("No GPU probe for preview")))
    monkeypatch.setattr(render, "log_to_video", Mock())
    commands = []
    launch = subprocess.Popen
    def capture(command, **kwargs):
        commands.append(command)
        return launch(command, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", capture)
    render.render_video(str(source), str(voice), str(subtitles), str(output), "keep_ratio",
        SubtitleStyle(), CropSettings(), "cpu-preview-fixture", compatibility_preview=True)
    encodes = [command for command in commands if "-c:v" in command]
    assert len(encodes) == 1
    assert encodes[0][encodes[0].index("-c:v") + 1] == "libx264"
    assert encodes[0][encodes[0].index("-preset") + 1] == "superfast"
    duration, streams = ffmpeg.inspect_preview_media(str(output))
    assert duration >= .9 and {"video", "audio"}.issubset(streams)
    assert not list(tmp_path.glob(".render-*.mp4"))
