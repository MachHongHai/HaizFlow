"""Real Batch pipeline/storage/media with deterministic, offline AI substitutes."""

import json
import shutil
import subprocess
import threading
import uuid
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from haizflow.pipeline import omnivoice_tts, process_registry, process_video
from haizflow.pipeline.timing_contract import TIMING_SOURCE
from haizflow.schemas.video import VideoConfig
from haizflow.services import manual_artifacts, processing_runs, project_store, video_export, video_store
from haizflow.services.processing_queue import SerialProcessingQueue
from haizflow.utils.ffmpeg import _binary, get_video_duration, validate_video_integrity

pytestmark = pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    root = tmp_path_factory.mktemp("batch-media")
    ffmpeg = _binary("ffmpeg")
    if not Path(ffmpeg).is_file() and not shutil.which(ffmpeg):
        pytest.skip("FFmpeg is required for the real-media simulation")
    commands = [
        ["-f", "lavfi", "-i", "color=c=navy:s=320x180:r=12:d=2",
         "-f", "lavfi", "-i", "sine=frequency=200:sample_rate=48000:duration=2",
         "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(root / "input.mp4")],
        ["-f", "lavfi", "-i", "sine=frequency=400:sample_rate=24000:duration=0.3",
         "-c:a", "libmp3lame", str(root / "fixture.mp3")],
    ]
    for command in commands:
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *command],
                       capture_output=True, check=True, timeout=30)
    return root


@pytest.fixture
def simulation(tmp_path, monkeypatch, media):
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "index" / "projects.json"))
    monkeypatch.setattr(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(tmp_path / "legacy"))
    monkeypatch.setattr(video_store, "_VIDEO_DIR_CACHE", {})
    monkeypatch.setattr(video_store, "_VIDEO_METADATA_CACHE", {})
    monkeypatch.setattr(manual_artifacts, "_VALIDATED_DIGESTS", {})
    monkeypatch.setattr(manual_artifacts, "_RUNTIME_PINS", {})
    for name in ("_RUNS", "_ARMED_EXPORTS", "_ARMED_EXPORT_STATES"):
        monkeypatch.setattr(processing_runs, name, {})
    monkeypatch.setattr(processing_runs, "_CHECKED", set())
    monkeypatch.setattr(processing_runs, "_CURRENT", threading.local())
    profile = SimpleNamespace(cuda_available=False, key="cpu", total_ram_gib=16, warm_hymt2_on_startup=False)
    monkeypatch.setattr(process_video, "runtime_profile", lambda: profile)
    monkeypatch.setattr(process_video, "_ensure_gpu_available", lambda *_: None)
    monkeypatch.setattr(process_video, "_recover_gpu_to_cpu", lambda *_: False)
    monkeypatch.setattr(process_video, "_release_recognition_runtime", lambda: None)
    monkeypatch.setattr(process_video, "shutdown_hymt2_worker", lambda: None)
    monkeypatch.setattr(omnivoice_tts, "clear_runtime", lambda: None)
    # The renderer itself still runs, but never probes/uses the developer GPU.
    monkeypatch.setattr("haizflow.pipeline.render.preferred_video_encoder",
                        lambda quality=23: ("libx264", ["-preset", "ultrafast", "-threads", "1", "-crf", str(quality)]))
    project = project_store.create_project("Batch mô phỏng", str(tmp_path / "projects"), "batch")
    external = tmp_path / "user-exports"
    external.mkdir()
    state = SimpleNamespace(calls=Counter(), clips=Counter(), hook=lambda *_: None,
                            ids=[], project=project, external=external)

    def before(stage, identifier):
        state.calls[identifier, stage] += 1
        state.hook(stage, identifier)
        process_registry.check_cancellation(identifier)

    def recognize(audio, output, language, identifier, **kwargs):
        before("recognition", identifier)
        rows = [{"start": 0.1, "end": 0.7, "text": "Hello friend.", "language": "en", "timing_source": TIMING_SOURCE},
                {"start": 1.0, "end": 1.7, "text": "Thank you.", "language": "en", "timing_source": TIMING_SOURCE}]
        Path(output).write_text(json.dumps(rows), encoding="utf-8")
        return rows, "en"

    def translate(source, output, identifier, *args, **kwargs):
        before("translation", identifier)
        rows = json.loads(Path(source).read_text(encoding="utf-8"))
        for row, text in zip(rows, ["Chào bạn.", "Cảm ơn."], strict=True):
            row["text"] = text
        Path(output).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def voices(source, output, voice, identifier, **kwargs):
        before("voice", identifier)
        rows = json.loads(Path(source).read_text(encoding="utf-8"))
        Path(output).mkdir(parents=True, exist_ok=True)
        for index, _row in enumerate(rows, 1):
            part = Path(output) / f"voice_{index:04d}.mp3"
            if not part.exists():
                shutil.copyfile(media / "fixture.mp3", part)
                state.clips[identifier, index] += 1
            kwargs["progress_callback"](index, len(rows))
            state.hook(f"voice_{index}_complete", identifier)
            process_registry.check_cancellation(identifier)

    def separate(audio, output, identifier):
        before("separation", identifier)
        Path(output).mkdir(parents=True, exist_ok=True)
        paths = [Path(output) / name for name in ("vocals.wav", "no_vocals.wav")]
        for path in paths:
            shutil.copy2(audio, path)
        return tuple(map(str, paths))

    def detect(source, output, identifier, **kwargs):
        before("ocr", identifier)
        return {"x_percent": 10, "y_percent": 75, "width_percent": 80, "height_percent": 15}

    monkeypatch.setattr(process_video, "transcribe", recognize)
    monkeypatch.setattr(process_video, "translate_segments", translate)
    monkeypatch.setattr(process_video, "generate_voice_parts", voices)
    monkeypatch.setattr(process_video, "separate_audio", separate)
    monkeypatch.setattr(process_video, "detect_original_subtitle_region", detect)
    for attribute, stage, id_position in [("extract_audio", "extraction", 2),
                                           ("build_audio_timeline", "timeline", 4),
                                           ("render_video", "render", 7)]:
        original = getattr(process_video, attribute)

        def wrap(*args, _original=original, _stage=stage, _position=id_position, **kwargs):
            before(_stage, args[_position])
            return _original(*args, **kwargs)

        monkeypatch.setattr(process_video, attribute, wrap)

    def create(**changes):
        config = VideoConfig(**dict(project_type="batch", project_name=project["project_name"],
                             project_id=project["project_id"], project_key=project["key"],
                             project_directory=project["project_directory"], tts_provider="edge",
                             tts_voice="vi-VN-NamMinhNeural", translation_model="gemini-3.1-flash-lite",
                             speech_recognition_model="small-cpu", enable_audio_separation=False,
                             remove_original_subtitles=False) | changes)
        video = video_store.create_video(str(uuid.uuid4()), "Nguồn thử nghiệm.mp4", config)
        shutil.copy2(media / "input.mp4", video.files["video_input"])
        state.ids.append(video.video_id)
        return video.video_id

    def run(identifier):
        process_registry.prepare_video_resume(identifier)
        processing_runs.begin(identifier, resuming=bool(video_store.get_video(identifier).resume_step))
        try:
            process_video.process_video_sync(identifier)
        finally:
            processing_runs.finish(identifier)
        return video_store.get_video(identifier)

    state.create, state.run = create, run
    yield state
    for identifier in state.ids:
        process_registry.clean_video(identifier)


def assert_complete(identifier):
    video = video_store.get_video(identifier)
    assert video.status == "done", video.error
    assert video.progress == 100 and video.resume_step == ""
    render = video_export.current_render(video)
    assert render is not None
    path = render["resolved_outputs"]["video"]
    validate_video_integrity(path)
    assert 1.8 <= get_video_duration(path) <= 2.3
    assert Path(video.files["srt_output"]).is_file()
    assert {"recognition", "translation", "voice", "timeline", "render"} <= video.checkpoints.keys()
    return path


@pytest.mark.parametrize("failed_stage", ["extraction", "recognition", "translation", "voice", "timeline", "render"])
def test_real_queue_media_and_publication_survive_one_failed_video(simulation, failed_stage):
    ids = [simulation.create() for _ in range(3)]

    def fault(stage, identifier):
        if identifier == ids[1] and stage == failed_stage:
            raise RuntimeError("Simulated provider 503")

    simulation.hook = fault
    idle = threading.Event()
    completed = []
    queue = SerialProcessingQueue(simulation.run, on_finished=completed.append, on_idle=idle.set)
    try:
        for identifier in ids:
            assert queue.enqueue(identifier)
        assert idle.wait(60)
        assert completed == ids
        assert_complete(ids[0])
        assert_complete(ids[2])
        for index in (0, 2):
            video = video_store.get_video(ids[index])
            original = Path(video_export.current_render(video)["resolved_outputs"]["video"])
            target = simulation.external / f"batch-{index}.mp4"
            video_export.export_video(video, target)
            assert target.read_bytes() == original.read_bytes()
        failed = video_store.get_video(ids[1])
        assert failed.status == "failed" and failed.error == "Simulated provider 503"
        assert video_export.current_render(failed) is None
        simulation.hook = lambda *_: None
        simulation.run(ids[1])
        assert_complete(ids[1])
    finally:
        assert queue.shutdown(timeout_seconds=10)


@pytest.mark.parametrize("stage", ["extraction", "recognition", "translation", "voice", "voice_1_complete", "timeline", "render"])
def test_pause_resume_runs_real_remaining_pipeline_and_preserves_finished_clips(simulation, stage):
    identifier = simulation.create()

    def pause(current, key):
        if current == stage:
            video = video_store.get_video(key)
            video_store.update_video(key, resume_step=video.step)
            process_registry.pause_video(key)

    simulation.hook = pause
    paused = simulation.run(identifier)
    assert paused.status == "paused" and paused.error is None
    if stage == "voice_1_complete":
        part = Path(video_store.get_video_dir(identifier)) / "temp" / "voice_parts" / "voice_0001.mp3"
        before = part.stat().st_mtime_ns
    simulation.hook = lambda *_: None
    simulation.run(identifier)
    assert_complete(identifier)
    if stage == "voice_1_complete":
        assert part.stat().st_mtime_ns == before
        assert simulation.clips[identifier, 1] == 1
    if stage in {"voice", "voice_1_complete", "timeline", "render"}:
        assert simulation.calls[identifier, "recognition"] == 1
        assert simulation.calls[identifier, "translation"] == 1


def test_restart_removes_previous_run_cache_but_keeps_source_and_external_copy(simulation, tmp_path):
    identifier = simulation.create()
    simulation.run(identifier)
    old_render = Path(assert_complete(identifier))
    external = tmp_path / "user-export.mp4"
    shutil.copy2(old_render, external)
    source = Path(video_store.get_video(identifier).files["video_input"])
    original = source.read_bytes()
    video_store.prepare_video_restart(identifier)
    assert not old_render.exists() and external.is_file()
    assert source.read_bytes() == original
    assert video_store.get_video(identifier).checkpoints == {}
    simulation.run(identifier)
    assert_complete(identifier)
    assert simulation.calls[identifier, "recognition"] == 2
    assert simulation.calls[identifier, "translation"] == 2
    assert simulation.clips[identifier, 1] == 2


def test_cancel_new_run_removes_only_its_generated_files(simulation):
    identifier = simulation.create()
    source = Path(video_store.get_video(identifier).files["video_input"])
    original = source.read_bytes()
    processing_runs.arm_export(identifier)

    def cancel(stage, key):
        if stage == "voice_1_complete":
            processing_runs.request_discard(key, processing_runs.current_id(key))
            process_registry.cancel_video(key)

    simulation.hook = cancel
    cancelled = simulation.run(identifier)
    assert cancelled.status == "cancelled"
    assert not list((Path(video_store.get_video_dir(identifier)) / "temp").rglob("*.*"))
    assert not cancelled.active_artifacts and not cancelled.checkpoints
    assert source.read_bytes() == original
    assert processing_runs.current_id(identifier) is None
    simulation.hook = lambda *_: None
    simulation.run(identifier)
    assert_complete(identifier)


def test_cancel_regeneration_restores_previous_render_clips_and_timeline(simulation):
    identifier = simulation.create()
    simulation.run(identifier)
    rendered = Path(assert_complete(identifier))
    before = video_store.get_video(identifier)
    root = Path(video_store.get_video_dir(identifier))
    old_bytes = {path: path.read_bytes() for path in (root / "temp").rglob("*") if path.is_file()}
    old_render = rendered.read_bytes()
    video_store.update_video(identifier, tts_voice="vi-VN-HoaiMyNeural", resume_step="creating_voice")
    processing_runs.arm_export(identifier)

    def cancel(stage, key):
        if stage == "voice_1_complete":
            processing_runs.request_discard(key, processing_runs.current_id(key))
            process_registry.cancel_video(key)

    simulation.hook = cancel
    after = simulation.run(identifier)
    assert after.status == "cancelled"
    assert after.checkpoints == before.checkpoints
    assert after.active_artifacts == before.active_artifacts
    assert rendered.read_bytes() == old_render
    assert all(path.read_bytes() == value for path, value in old_bytes.items())
    assert processing_runs.current_id(identifier) is None


@pytest.mark.parametrize("changed", ["none", "source", "missing_master", "missing_stem"])
def test_pause_during_translation_reuses_only_current_complete_separation(simulation, changed):
    identifier = simulation.create(enable_audio_separation=True)

    def pause(stage, key):
        if stage == "translation":
            video_store.update_video(key, resume_step="translating")
            process_registry.pause_video(key)

    simulation.hook = pause
    assert simulation.run(identifier).status == "paused"
    background = Path(video_store.get_video(identifier).files["background_audio"])
    modified = background.stat().st_mtime_ns
    root = Path(video_store.get_video_dir(identifier))
    if changed == "source":
        import os

        source = Path(video_store.get_video(identifier).files["video_input"])
        stat = source.stat()
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    elif changed == "missing_master":
        (root / "temp" / "audio.wav").unlink()
    elif changed == "missing_stem":
        background.unlink()
    simulation.hook = lambda *_: None
    simulation.run(identifier)
    assert_complete(identifier)
    assert simulation.calls[identifier, "separation"] == (1 if changed == "none" else 2)
    if changed == "none":
        assert background.stat().st_mtime_ns == modified
        assert simulation.calls[identifier, "extraction"] == 1


def test_resume_recreates_only_missing_voice_clip(simulation):
    identifier = simulation.create()
    simulation.run(identifier)
    assert_complete(identifier)
    parts = Path(video_store.get_video_dir(identifier)) / "temp" / "voice_parts"
    first = parts / "voice_0001.mp3"
    before = first.stat().st_mtime_ns
    (parts / "voice_0002.mp3").unlink()
    video_store.update_video(identifier, status="paused", step="paused", resume_step="creating_voice")
    simulation.run(identifier)
    assert_complete(identifier)
    assert first.stat().st_mtime_ns == before
    assert simulation.clips[identifier, 1] == 1
    assert simulation.clips[identifier, 2] == 2
    assert simulation.calls[identifier, "translation"] == 1
    assert simulation.calls[identifier, "timeline"] == 2
    assert simulation.calls[identifier, "render"] == 2


def test_output_speed_is_applied_to_real_batch_render(simulation):
    identifier = simulation.create(output_speed=2)
    simulation.run(identifier)
    video = video_store.get_video(identifier)
    assert video.status == "done", video.error
    result = video_export.current_render(video)
    assert result is not None
    assert 0.8 <= get_video_duration(result["resolved_outputs"]["video"]) <= 1.3


def test_batch_review_waits_for_approval_without_retranslating(simulation):
    identifier = simulation.create(mode="review")
    waiting = simulation.run(identifier)
    assert waiting.status == "awaiting_review"
    assert simulation.calls[identifier, "voice"] == 0
    assert video_export.current_render(waiting) is None
    video_store.update_video(identifier, review_approved=True)
    simulation.run(identifier)
    assert_complete(identifier)
    assert simulation.calls[identifier, "recognition"] == 1
    assert simulation.calls[identifier, "translation"] == 1


@pytest.mark.parametrize("mode", ["blur", "patch"])
def test_batch_cover_uses_detected_region_in_real_renderer(simulation, mode):
    identifier = simulation.create(remove_original_subtitles=True, original_subtitle_removal_mode=mode)
    simulation.run(identifier)
    assert_complete(identifier)
    assert simulation.calls[identifier, "ocr"] == 1
