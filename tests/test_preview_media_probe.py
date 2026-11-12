"""One generated-proxy probe retains both validation and file-identity guards."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.utils import ffmpeg


def test_preview_probe_checks_duration_and_streams_and_reuses_validated_duration(tmp_path):
    source = tmp_path / "rendering.mp4"
    source.write_bytes(b"complete proxy")
    result = SimpleNamespace(stdout=json.dumps({"format": {"duration": "12.032"},
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}))
    with patch.object(ffmpeg.subprocess, "run", return_value=result) as run, ffmpeg.media_probe_batch():
        assert ffmpeg.inspect_preview_media(str(source)) == (12.032, {"video", "audio"})
        assert ffmpeg.get_video_duration(str(source)) == 12.032
        assert run.call_count == 1
        command = run.call_args.args[0]
        assert command[command.index("-show_entries") + 1] == "format=duration:stream=codec_type"
        run.return_value = SimpleNamespace(stdout="13.0")
        source.write_bytes(b"changed proxy contents")
        assert ffmpeg.get_video_duration(str(source)) == 13
        assert run.call_count == 2


@pytest.mark.parametrize("duration", ["0", "-1", "nan", "inf", "-inf"])
def test_invalid_duration_is_not_cached_as_a_completed_preview(tmp_path, duration):
    source = tmp_path / "preview.mp4"
    source.write_bytes(b"incomplete")
    run = Mock(side_effect=[SimpleNamespace(stdout=json.dumps({"format": {"duration": duration},
        "streams": [{"codec_type": "video"}]})), SimpleNamespace(stdout="12.0")])
    with patch.object(ffmpeg.subprocess, "run", run), ffmpeg.media_probe_batch():
        assert ffmpeg.inspect_preview_media(str(source)) == (0, {"video"})
        assert ffmpeg.get_video_duration(str(source)) == 12
        assert run.call_count == 2


def test_missing_audio_is_reported_to_renderer_instead_of_being_accepted(tmp_path):
    source = tmp_path / "preview.mp4"
    source.write_bytes(b"video only")
    with patch.object(ffmpeg.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(
        {"format": {"duration": "12"}, "streams": [{"codec_type": "video"}]}))):
        assert ffmpeg.inspect_preview_media(str(source)) == (12, {"video"})


def test_bounded_probe_errors_do_not_populate_the_render_transaction_cache(tmp_path):
    source = tmp_path / "preview.mp4"
    source.write_bytes(b"data")
    with patch.object(ffmpeg.subprocess, "run", side_effect=[OSError("locked"),
            SimpleNamespace(stdout="8.0")]), ffmpeg.media_probe_batch():
        with pytest.raises(OSError, match="locked"):
            ffmpeg.inspect_preview_media(str(source))
        assert ffmpeg.get_video_duration(str(source)) == 8
