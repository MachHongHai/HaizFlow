"""Deterministic Windows failures; never lock or alter real project files."""

import json
import os
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.pipeline import manual_tools, process_video
from haizflow.schemas.video import VideoConfig
from haizflow.services import manual_artifacts
from haizflow.services.editor_documents import _atomic_write
from haizflow.services.translation_progress import TranslationProgress
from haizflow.utils import atomic_file

WINDOWS_ERRORS = [2, 3, 5, 32, 33, 112, 126, 145, 193, 206, 1455]


def windows_error(code):
    error = OSError(f"[WinError {code}] Simulated Windows operation failure")
    error.winerror = code
    return error


@pytest.mark.parametrize("code", [5, 32, 33])
def test_shared_metadata_writer_recovers_temporary_reader_lock(tmp_path, code):
    destination = tmp_path / "video.json"
    destination.write_text('{"checkpoint": "old"}')
    original = atomic_file.os.replace
    count = []

    def replace(source, target):
        count.append(True)
        if len(count) < 3:
            assert json.loads(destination.read_text()) == {"checkpoint": "old"}
            raise windows_error(code)
        return original(source, target)

    with patch.object(atomic_file.os, "replace", side_effect=replace), patch.object(atomic_file.time, "sleep"):
        atomic_file.atomic_json(destination, {"checkpoint": "new"})
    assert len(count) == 3
    assert json.loads(destination.read_text()) == {"checkpoint": "new"}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("code", WINDOWS_ERRORS)
def test_permanent_windows_write_failure_preserves_metadata(tmp_path, code):
    destination = tmp_path / "video.json"
    destination.write_text('{"checkpoint": "old"}')
    with patch.object(atomic_file.os, "replace", side_effect=windows_error(code)) as replace, \
         patch.object(atomic_file.time, "sleep"):
        with pytest.raises(OSError):
            atomic_file.atomic_json(destination, {"checkpoint": "new"})
    assert replace.call_count == (8 if code in {5, 32, 33} else 1)
    assert json.loads(destination.read_text()) == {"checkpoint": "old"}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("code", [5, 32, 33])
@pytest.mark.parametrize("writer", ["translation", "editor"])
def test_checkpoint_and_editor_retry_temporary_lock(tmp_path, code, writer):
    destination = tmp_path / "state.json"
    destination.write_text("{}")
    checkpoint = TranslationProgress(destination, {"source": "fixture"}, 1)
    original = atomic_file.os.replace
    calls = []

    def replace(source, target):
        calls.append(True)
        if len(calls) == 1:
            raise windows_error(code)
        return original(source, target)

    with patch.object(atomic_file.os, "replace", side_effect=replace), patch.object(atomic_file.time, "sleep"):
        if writer == "translation":
            checkpoint.save_batch([0], ["Tiếng Việt"])
            assert checkpoint.values == ["Tiếng Việt"]
            assert TranslationProgress(destination, {"source": "fixture"}, 1).values == checkpoint.values
        else:
            _atomic_write(destination, {"caption": "Tiếng Việt"})
            assert json.loads(destination.read_text(encoding="utf-8")) == {"caption": "Tiếng Việt"}
    assert len(calls) == 2
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("code", [5, 32, 33, 112, 206, 1455])
@pytest.mark.parametrize("writer", ["translation", "editor"])
def test_checkpoint_and_editor_keep_previous_state_on_permanent_failure(tmp_path, code, writer):
    destination = tmp_path / "state.json"
    checkpoint = TranslationProgress(destination, {"source": "fixture"}, 2)
    checkpoint.save_batch([0], ["kept"])
    before = destination.read_bytes()
    with patch.object(atomic_file.os, "replace", side_effect=windows_error(code)), \
         patch.object(atomic_file.time, "sleep"):
        with pytest.raises(OSError):
            if writer == "translation":
                checkpoint.save_batch([1], ["unpublished"])
            else:
                _atomic_write(destination, {"caption": "unpublished"})
    assert checkpoint.values == ["kept", None]
    assert destination.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("code,wrapped", [(code, wrapped) for code in WINDOWS_ERRORS for wrapped in (False, True)
                                        if not (wrapped and code in {126, 193})])
def test_storage_errors_with_gpu_named_paths_never_trigger_cpu_recovery(code, wrapped):
    message = f"[WinError {code}] D:/GPU/CUDA/cache/result.json"
    # Native loader errors 126/193 can be driver failures when wrapped; only
    # genuine native OS errors are categorically excluded in these two cases.
    error = RuntimeError(message) if wrapped else windows_error(code)
    if not wrapped:
        error.args = (message,)
    with patch.object(process_video, "runtime_profile", return_value=SimpleNamespace(cuda_available=True)), \
         patch.object(process_video, "get_video", return_value=SimpleNamespace(gpu_recovery_attempted=False)), \
         patch.object(process_video, "probe_runtime") as probe, \
         patch.object(process_video, "update_video") as update:
        assert not process_video._is_gpu_runtime_failure(error)
        assert not process_video._recover_gpu_to_cpu("fixture", "translation", error)
    probe.assert_not_called()
    update.assert_not_called()


def test_actual_cuda_failure_remains_eligible_for_existing_recovery():
    with patch.object(process_video, "runtime_profile", return_value=SimpleNamespace(cuda_available=True)):
        assert process_video._is_gpu_runtime_failure(RuntimeError("CUDA out of memory"))
        assert process_video._is_gpu_runtime_failure(process_video.GpuRuntimeUnavailable("GPU disconnected"))


def test_checkpoint_preserves_raw_surrogate_for_manual_validation_instead_of_encoding_crash(tmp_path):
    path = tmp_path / "translation.json"
    checkpoint = TranslationProgress(path, {"source": "fixture"}, 1)
    raw = "Xin\ud800 chào"
    checkpoint.save_batch([0], [raw])
    assert path.read_text(encoding="ascii")
    assert TranslationProgress(path, {"source": "fixture"}, 1).values == [raw]


@pytest.mark.skipif(os.name != "nt", reason="Native Windows sharing-mode test")
@pytest.mark.parametrize("writer", ["translation", "editor"])
def test_checkpoint_editor_publish_after_real_windows_reader_releases_file(tmp_path, writer):
    import ctypes
    from ctypes import wintypes

    target = tmp_path / "state.json"
    target.write_text("{}")
    checkpoint = TranslationProgress(target, {"source": "fixture"}, 1)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # Read/write sharing deliberately excludes FILE_SHARE_DELETE.
    handle = kernel.CreateFileW(str(target), 0x80000000, 3, None, 3, 0x80, None)
    assert handle != wintypes.HANDLE(-1).value
    release = threading.Timer(.15, lambda: kernel.CloseHandle(handle))
    release.start()
    try:
        if writer == "translation":
            checkpoint.save_batch([0], ["saved"])
            assert TranslationProgress(target, {"source": "fixture"}, 1).values == ["saved"]
        else:
            _atomic_write(target, {"saved": True})
            assert json.loads(target.read_text()) == {"saved": True}
    finally:
        release.join()


@pytest.mark.parametrize("code", WINDOWS_ERRORS)
@pytest.mark.parametrize("workflow", ["auto", "manual"])
def test_stage_windows_failure_releases_runtime_and_retains_durable_results(tmp_path, code, workflow):
    source = tmp_path / "input" / "video.mp4"
    source.parent.mkdir()
    source.write_bytes(b"source fixture")
    transcript = tmp_path / "transcript.json"
    transcript.write_text("[]")
    files = {"video_input": str(source), "transcript_json": str(transcript)}
    checkpoints = {"translation": "kept-checkpoint"}
    active = {"recognition": "kept-recognition", "tts_manifest": "kept-voice"}
    video = SimpleNamespace(**VideoConfig(project_type="manual" if workflow == "manual" else "single").model_dump(),
        video_id="fixture", status="processing", step="transcribing", resume_step="", runtime_recovery_step="",
        gpu_recovery_attempted=False, files=dict(files), checkpoints=dict(checkpoints), active_artifacts=dict(active))

    def update(_identifier, **values):
        video.__dict__.update(values)
        return video

    error = windows_error(code)
    if workflow == "auto":
        with (
            patch.object(process_video, "get_video", return_value=video),
            patch.object(process_video, "update_video", side_effect=update),
            patch.object(process_video, "log_to_video"),
            patch.object(process_video, "start_video"),
            patch.object(process_video, "clean_video") as cleanup,
            patch.object(process_video, "is_cancelled", return_value=False),
            patch.object(process_video, "validate_video_integrity"),
            patch.object(process_video, "_translation_signature", return_value="kept-checkpoint"),
            patch.object(process_video, "_checkpoint_valid", return_value=True),
            patch.object(process_video, "_finish_after_translation", side_effect=error),
            patch.object(process_video, "runtime_profile", return_value=SimpleNamespace(cuda_available=True)),
            patch.object(process_video, "processing_device_preference", return_value="gpu"),
            patch.object(process_video, "translation_model_preference", return_value="full"),
            patch.object(process_video, "probe_runtime") as probe,
            patch.object(process_video, "configure_processing_device") as change_device,
        ):
            process_video.process_video_sync("fixture", _reporter=Mock())
        probe.assert_not_called()
        change_device.assert_not_called()
    else:
        with (
            patch.object(manual_tools.video_store, "get_video", return_value=video),
            patch.object(manual_tools.video_store, "get_video_dir", return_value=str(tmp_path)),
            patch.object(manual_tools.video_store, "update_video", side_effect=update),
            patch.object(manual_tools.video_store, "log_to_video"),
            patch.object(manual_tools, "start_video"),
            patch.object(manual_tools, "clean_video") as cleanup,
            patch.object(manual_tools, "is_cancelled", return_value=False),
            patch.object(manual_tools, "_requested_artifact", return_value=("recognition", "new-attempt")),
            patch.object(manual_tools, "_recognition_ready", return_value=False),
            patch.dict(manual_tools._RUNNERS, recognition=Mock(side_effect=error)),
            patch.object(manual_artifacts, "maintain"),
            patch.object(process_video, "ProgressReporter", return_value=Mock()),
        ):
            manual_tools.run_manual_tool_sync("fixture", "recognition")
            record = manual_artifacts.load_manifest("fixture")["artifacts"]["recognition:new-attempt"]
        assert record["status"] == "error" and record["outputs"] == {}
    cleanup.assert_called_once_with("fixture")
    assert video.status == "failed"
    assert f"WinError {code}" in video.error
    assert video.files == files
    assert video.checkpoints == checkpoints
    assert video.active_artifacts == active
    assert source.read_bytes() == b"source fixture"
    assert transcript.read_text() == "[]"
