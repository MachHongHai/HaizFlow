"""Export optimizations must retain integrity, ownership and cancellation."""

import hashlib
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hflow.pipeline import sequence_compiler
from hflow.services import manual_artifacts, video_export
import test_render_export_storage as storage_tests


@pytest.fixture
def storage():
    fixture = storage_tests.RenderExportStorageTests()
    fixture.setUpClass()
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.tearDown()


def test_full_copy_verifies_in_stream_without_pre_reading_render(storage, monkeypatch):
    data = b"test-export" * 100000
    _, video = storage.make_video(content=data)
    monkeypatch.setattr(manual_artifacts, "_sha256", Mock(side_effect=AssertionError("Redundant media hash")))
    output = storage.external / "fast.mp4"
    progress = []
    video_export.export_video(video, output, progress=progress.append)
    assert output.read_bytes() == data
    assert progress == sorted(set(progress))
    assert progress[-1] == 100
    assert not manual_artifacts._RUNTIME_PINS


def test_desktop_copy_worker_does_not_pre_hash_the_render(storage, monkeypatch):
    _, video = storage.make_video(content=b"desktop export")
    output = storage.external / "desktop.mp4"
    monkeypatch.setattr(manual_artifacts, "_sha256", Mock(side_effect=AssertionError("Pre-read in desktop worker")))
    storage.exporter.copy_jobs([{"videoId": video.video_id, "path": str(output), "overwrite": False}])
    assert output.read_bytes() == b"desktop export"
    assert not manual_artifacts._RUNTIME_PINS


def test_same_size_corruption_is_rejected_even_without_pre_hash(storage):
    _, video = storage.make_video(content=b"original")
    Path(video.files["final_video"]).write_bytes(b"modified")
    output = storage.external / "old.mp4"
    output.write_bytes(b"prior export")
    with pytest.raises(OSError, match="verification"):
        video_export.export_video(video, output, overwrite=True)
    assert output.read_bytes() == b"prior export"
    assert not list(storage.external.glob(".hflow-export-*"))
    assert not manual_artifacts._RUNTIME_PINS
    assert video_export.current_render(video, verify=False) is None


def test_written_copy_corruption_is_rejected(storage, monkeypatch):
    _, video = storage.make_video()
    original = video_export._export_digest

    def corrupt(path, cancel, progress):
        path.write_bytes(b"bad copy")
        return original(path, cancel, progress)

    monkeypatch.setattr(video_export, "_export_digest", corrupt)
    output = storage.external / "out.mp4"
    with pytest.raises(OSError, match="verification"):
        video_export.export_video(video, output)
    assert not output.exists()
    assert video_export.current_render(video)


def test_cancel_during_final_verification_keeps_old_output_and_render(storage):
    _, video = storage.make_video(content=b"x" * (12 * 1024**2))
    output = storage.external / "old.mp4"
    output.write_bytes(b"old output")
    token = threading.Event()

    def progress(value):
        if value > 95:
            token.set()

    with pytest.raises(video_export.ExportCancelled):
        video_export.export_video(video, output, overwrite=True, cancel=token, progress=progress)
    assert output.read_bytes() == b"old output"
    assert video_export.current_render(video)
    assert not list(storage.external.glob(".hflow-export-*"))
    assert not manual_artifacts._RUNTIME_PINS


def test_source_replacement_during_copy_is_rejected(storage):
    _, video = storage.make_video(content=b"first version")
    source = Path(video.files["final_video"])
    output = storage.external / "out.mp4"

    def progress(value):
        if value == 95:
            source.write_bytes(b"other version")

    with pytest.raises(OSError, match="verification"):
        video_export.export_video(video, output, progress=progress)
    assert not output.exists()


def test_copy_progress_is_throttled_and_verification_is_complete(tmp_path):
    path = tmp_path / "verify.mp4"
    data = b"y" * (24 * 1024**2)
    path.write_bytes(data)
    progress = []
    assert video_export._export_digest(path, threading.Event(), progress.append) == hashlib.sha256(data).hexdigest()
    assert progress == sorted(set(progress)) and progress[-1] == 99
    assert len(progress) <= 5


@pytest.mark.parametrize("operation", ["overlays", "resolution"])
def test_passthrough_never_copies_or_mutates_input(tmp_path, monkeypatch, operation):
    source, output = tmp_path / "base.mp4", tmp_path / "output.mp4"
    source.write_bytes(b"original video")
    no_copy = Mock(side_effect=AssertionError("No full file copy expected"))
    monkeypatch.setattr(sequence_compiler, "_copy_video", no_copy)
    monkeypatch.setattr("hflow.utils.ffmpeg.get_video_dimensions", lambda _: (96, 64))
    progress = []
    if operation == "overlays":
        result = sequence_compiler.apply_overlays(str(source), str(output), None, "test",
                                                 passthrough=True, progress_callback=progress.append)
    else:
        result = sequence_compiler.finish_export_resolution(str(source), str(output), "source", "test",
                                                           passthrough=True, progress_callback=progress.append)
    assert result == str(source)
    assert source.read_bytes() == b"original video"
    assert not output.exists()
    assert progress == [1.0]


def test_gpu_encode_falls_back_once_and_progress_does_not_regress(monkeypatch):
    monkeypatch.setattr("hflow.utils.ffmpeg.preferred_video_encoder", lambda quality: (
        "h264_nvenc", ["-preset", "p4", "-cq", str(quality)]))
    commands, progress = [], []

    def run(command, **kwargs):
        commands.append(command)
        if "h264_nvenc" in command:
            kwargs["progress_callback"](.4)
            raise RuntimeError("encoder memory exhausted")
        kwargs["progress_callback"](.1)
        kwargs["progress_callback"](1)

    monkeypatch.setattr(sequence_compiler, "_run", run)
    sequence_compiler._run_video_encode(["ffmpeg", "-i", "base.mp4"], ["out.mp4"], quality=18,
        process_id="test", progress_callback=progress.append, cwd=".", label="test", duration=10)
    assert len(commands) == 2
    assert "h264_nvenc" in commands[0] and "libx264" in commands[1]
    assert commands[1][-6:] == ["libx264", "-preset", "veryfast", "-crf", "18", "out.mp4"]
    assert progress == sorted(progress) and progress[-1] == 1


def test_cancelled_gpu_encode_never_starts_cpu_fallback(monkeypatch):
    from hflow.pipeline import process_registry

    identifier = "cancel-gpu-export-test"
    process_registry.start_video(identifier)
    monkeypatch.setattr("hflow.utils.ffmpeg.preferred_video_encoder", lambda _: ("h264_nvenc", []))

    def cancelled(*_args, **_kwargs):
        process_registry.cancel_video(identifier)
        process_registry.check_cancellation(identifier)

    run = Mock(side_effect=cancelled)
    monkeypatch.setattr(sequence_compiler, "_run", run)
    try:
        with pytest.raises(RuntimeError, match="cancel"):
            sequence_compiler._run_video_encode(["ffmpeg"], ["out.mp4"], quality=18,
                                               process_id=identifier, cwd=".", label="test")
        assert run.call_count == 1
    finally:
        process_registry.clean_video(identifier)


@pytest.mark.parametrize("dimensions,duration,hardware", [
    ((1280, 720), 10, False), ((640, 360), 30, False),
    ((1280, 720), 180, True), ((1920, 1080), 10, True),
    ((1080, 1920), 10, True), (None, 10, True),
])
def test_small_short_passes_avoid_gpu_startup_but_long_hd_keeps_gpu(monkeypatch, dimensions, duration, hardware):
    from hflow.utils import ffmpeg

    gpu = Mock(return_value=("h264_nvenc", ["-cq", "18"]))
    monkeypatch.setattr(ffmpeg, "preferred_video_encoder", gpu)
    encoder, options = ffmpeg.preferred_export_encoder(18, dimensions=dimensions, duration=duration)
    assert encoder == ("h264_nvenc" if hardware else "libx264")
    assert gpu.call_count == int(hardware)
    assert "18" in options


@pytest.fixture
def real_media(tmp_path):
    from hflow.utils.ffmpeg import _binary

    path = tmp_path / "source.mp4"
    subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=96x64:rate=20:duration=4", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)], check=True, capture_output=True)
    return path


def test_real_uncached_segment_skips_both_noop_copies_and_preserves_source(real_media, tmp_path, monkeypatch):
    from hflow.pipeline import manual_tools, segment_export
    from hflow.schemas.video import VideoConfig
    from hflow.services import video_store
    from hflow.utils.ffmpeg import get_video_duration, validate_video_integrity
    from test_segment_export_window import document_for

    config = VideoConfig(project_type="manual")
    video = SimpleNamespace(**{name: getattr(config, name) for name in VideoConfig.model_fields}, video_id="bounded-export",
        files={"video_input": str(real_media)}, active_artifacts={}, export_preset="source")
    document = document_for()
    before = real_media.read_bytes()
    monkeypatch.setattr(video_store, "get_video_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(manual_tools.manual_artifacts, "resolve", lambda *_args: None)
    monkeypatch.setattr(manual_tools, "published_voice_record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(manual_tools, "_audio_background", lambda *_args, **_kwargs: (str(real_media), "", []))
    monkeypatch.setattr(manual_tools, "audio_signature", lambda _: "missing-mix")
    monkeypatch.setattr(manual_tools, "_ocr_region", lambda _: None)
    monkeypatch.setattr(sequence_compiler, "_copy_video", Mock(side_effect=AssertionError("Redundant video copy")))
    output = tmp_path / "segment.mp4"
    progress = []
    segment_export.render_segment(video, document, (1000, 2500), output, threading.Event(), progress.append)
    validate_video_integrity(str(output))
    assert abs(get_video_duration(str(output)) - 1.5) < .1
    assert real_media.read_bytes() == before
    assert not (tmp_path / "overlays.mp4").exists()
    assert not (tmp_path / "base.mp4").exists()
    assert progress == sorted(progress) and progress[-1] == 98


def test_real_cached_segment_hardware_failure_retries_cpu_only_for_window(real_media, tmp_path, monkeypatch):
    from hflow.utils import ffmpeg

    monkeypatch.setattr(ffmpeg, "preferred_export_encoder", lambda *_args, **_kwargs: ("unavailable_encoder", []))
    original = video_export.subprocess.Popen
    commands = []

    def capture(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(video_export.subprocess, "Popen", capture)
    directory = tmp_path / ".hflow-segment-test"
    directory.mkdir()
    output = directory / "segment.mp4"
    video_export._render_range(real_media, output, (1500, 2500), "source", threading.Event(), None)
    encodes = [command for command in commands if "-c:v" in command]
    assert len(encodes) == 2
    assert "unavailable_encoder" in encodes[0] and "libx264" in encodes[1]
    for command in encodes:
        assert command[command.index("-ss") + 1] == "1.5"
        assert command[command.index("-t") + 1] == "1.0"
    assert abs(ffmpeg.get_video_duration(str(output)) - 1) < .1
    assert not output.with_suffix(".progress").exists()


def test_cancelled_cached_segment_does_not_start_fallback(real_media, tmp_path, monkeypatch):
    from hflow.utils import ffmpeg

    monkeypatch.setattr(ffmpeg, "preferred_export_encoder", lambda *_args, **_kwargs: ("h264_nvenc", []))
    token = threading.Event()
    real_popen = video_export.subprocess.Popen
    encodes = []

    def launch(command, **kwargs):
        if "-c:v" not in command:
            return real_popen(command, **kwargs)
        encodes.append(command)
        process = Mock(returncode=1)

        def failed(**_kwargs):
            token.set()
            return "", "GPU encoder failed"

        process.communicate.side_effect = failed
        process.poll.return_value = 1
        return process

    monkeypatch.setattr(video_export.subprocess, "Popen", launch)
    output = tmp_path / "cancelled.mp4"
    with pytest.raises(video_export.ExportCancelled):
        video_export._render_range(real_media, output, (1000, 2000), "source", token, None)
    assert len(encodes) == 1
    assert not output.with_suffix(".progress").exists()
