"""Real bounded media previews and non-mutating layout planning, in private test roots."""
import asyncio
import io
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from haizflow.mcp import visuals
from haizflow.mcp.server import create_server
from haizflow.schemas.video import CropSettings, SubtitleStyle


@pytest.fixture
def context():
    value = {"video_id": "visual-test", "width": 720, "height": 1280, "style": SubtitleStyle().model_dump(),
             "crop": CropSettings().model_dump(), "output_format": "keep_ratio", "output_speed": 1.0,
             "cues": [{"start": 0, "end": 3, "text": "Xin chào thế giới"}],
             "source_path": "", "render_path": "", "source_key": "source-v1"}
    value["revision"] = visuals.revision(value)
    return value


def test_proposal_is_readonly_and_avoids_supplied_subject_region(context):
    before = json.dumps(context, sort_keys=True)
    result = visuals.suggest(context, [{"x": 0, "y": 60, "width": 100, "height": 40}])
    assert result["candidates"][0]["style_patch"]["position_y_percent"] < 60
    assert result["candidates"][0]["report"]["overlap_area"] == 0
    assert json.dumps(context, sort_keys=True) == before


@pytest.mark.parametrize("patch", [{"position_y_percent": 100}, {"position_x_percent": 0}])
def test_layout_reports_clipping(context, patch):
    assert any("outside" in issue for issue in visuals.layout_report(context, patch)["issues"])


def test_invalid_regions_are_rejected(context):
    with pytest.raises(ValueError):
        visuals.suggest(context, [{"x": float("nan"), "y": 0, "width": 10, "height": 10}])
    with pytest.raises(ValueError):
        visuals.suggest(context, [{"x": 95, "y": 0, "width": 10, "height": 10}])


@pytest.fixture
def media(context, tmp_path, monkeypatch):
    binaries = Path(__file__).parents[1] / "runtime" / "bin"
    if not (binaries / "ffmpeg.exe").exists():
        pytest.skip("Native FFmpeg not installed")
    monkeypatch.setattr(visuals, "_binary", lambda name: str(binaries / (name + ".exe")))
    video = tmp_path / "input.mp4"
    subprocess.run([visuals._binary("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=320x180:r=5:d=4", "-c:v", "libx264", str(video)],
                   check=True, capture_output=True, timeout=20)
    context.update(source_path=str(video), render_path=str(video), width=320, height=180)
    context["revision"] = visuals.revision(context)
    return context


def test_real_source_and_ass_layout_previews_leave_no_project_files(media):
    folder = Path(media["source_path"]).parent
    before = list(folder.iterdir())
    source = visuals.frames(media, [1.0], "source")[0][1]
    draft = visuals.frames(media, [1.0], "layout", {"font_size": 20, "position_y_percent": 70})[0][1]
    assert source != draft
    for data in (source, draft):
        assert max(Image.open(io.BytesIO(data)).size) <= 640
    assert list(folder.iterdir()) == before


@pytest.mark.parametrize("times", [[float("nan")], [-1.0], [4.0], [0.0] * 5])
def test_timestamp_bounds(media, times):
    with pytest.raises(ValueError):
        visuals.frames(media, times)


def test_sdk_delivers_images_and_checks_revision(media):
    from mcp import Client

    client = Mock()
    client.call.return_value = media

    async def run():
        async with Client(create_server(client), raise_exceptions=True) as session:
            result = await session.call_tool("haizflow_preview_frames", {
                "video_id": "visual-test", "times_seconds": [1.0], "view": "source",
            })
            assert any(item.type == "image" for item in result.content)

    asyncio.run(run())
    assert client.call.call_count == 2
    assert all(call.args[0] == "visual_context" for call in client.call.call_args_list)


def test_timeout_cleans_all_scratch_files(media, tmp_path, monkeypatch):
    original_directory = tempfile.TemporaryDirectory
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(visuals.tempfile, "TemporaryDirectory",
                        lambda **kwargs: original_directory(dir=scratch, **kwargs))
    original_run = visuals._run

    def timeout_on_decode(args, cwd=None):
        if "image2pipe" in args:
            raise subprocess.TimeoutExpired(args[0], 30)
        return original_run(args, cwd)

    monkeypatch.setattr(visuals, "_run", timeout_on_decode)
    with pytest.raises(subprocess.TimeoutExpired):
        visuals.frames(media, [1.0], "layout", {"font_size": 20})
    assert not list(scratch.iterdir())


def test_sdk_rejects_images_from_stale_context(media):
    from mcp import Client

    client = Mock()
    client.call.side_effect = [media, {**media, "revision": "changed"}]

    async def run():
        async with Client(create_server(client), raise_exceptions=False) as session:
            result = await session.call_tool("haizflow_preview_frames", {
                "video_id": "visual-test", "times_seconds": [1.0],
            })
            assert result.is_error
            assert not any(item.type == "image" for item in result.content)

    asyncio.run(run())
