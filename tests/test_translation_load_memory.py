"""HY-MT2 admission decisions must not load Torch or alter project settings."""

import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow import config
from haizflow.core.memory import GIB, MemorySnapshot
from haizflow.services import translation
from haizflow.services.resource_packs import ResourcePackError


@pytest.fixture
def load_plan(tmp_path, monkeypatch):
    profile = SimpleNamespace(cuda_available=True, total_vram_bytes=6 * GIB, key="cuda_low_memory")
    snapshot = MemorySnapshot(available_bytes=8 * GIB, commit_limit_bytes=24 * GIB, commit_used_bytes=8 * GIB)
    model = tmp_path / "hymt2-gguf" / config.HYMT2_CPU_MODEL_FILE
    model.parent.mkdir()
    model.write_bytes(b"installed model fixture; verified by worker before loading")
    monkeypatch.setattr(config, "MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(translation, "translation_model_preference", lambda: "full")
    monkeypatch.setattr(translation, "runtime_profile", lambda: profile)
    monkeypatch.setattr(translation, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr("haizflow.core.memory.memory_snapshot", lambda: snapshot)
    monkeypatch.setattr("haizflow.core.hardware.live_cuda_free_memory_bytes", lambda: 6 * GIB)
    monkeypatch.setattr(translation, "_WORKER_SHUTDOWN_EVENT", Mock(wait=Mock(return_value=False)))
    command = Mock(side_effect=lambda **options: ["cpu-engine"] if options.get("model_preference") == "q4" else ["gpu-engine"])
    monkeypatch.setattr(translation, "_worker_command", command)
    return profile, model, command


@pytest.mark.parametrize("commit", [0, int(3.3 * GIB), 6 * GIB])
def test_low_commit_uses_installed_q4_before_cuda_imports(load_plan, monkeypatch, commit):
    monkeypatch.setattr("haizflow.core.memory.memory_snapshot", lambda: MemorySnapshot(
        available_bytes=3 * GIB, commit_limit_bytes=16 * GIB, commit_used_bytes=16 * GIB - commit))
    settings = dict(os.environ)
    command, effective, note = translation._worker_launch_plan()
    assert command == ["cpu-engine"] and effective == "q4"
    assert "bộ nhớ Windows" in note
    assert dict(os.environ) == settings


@pytest.mark.parametrize("free_vram", [0, 2 * GIB, 4 * GIB])
def test_live_vram_not_cached_gpu_capacity_decides_fallback(load_plan, monkeypatch, free_vram):
    monkeypatch.setattr("haizflow.core.hardware.live_cuda_free_memory_bytes", lambda: free_vram)
    command, effective, note = translation._worker_launch_plan()
    assert command == ["cpu-engine"] and effective == "q4" and "VRAM trống" in note


def test_four_gb_board_never_attempts_full_model_even_if_free_counter_is_stale(load_plan):
    profile, _, _ = load_plan
    profile.total_vram_bytes = 4 * GIB
    assert translation._worker_launch_plan()[1:] == ("q4", "HY-MT2 dùng CPU Q4 cho lượt chạy này vì VRAM dưới 5 GiB.")


def test_adequate_memory_keeps_selected_full_gpu_model(load_plan):
    assert translation._worker_launch_plan() == (["gpu-engine"], "full", "")


def test_memory_settles_after_retired_worker_without_unnecessary_cpu_fallback(load_plan, monkeypatch):
    snapshots = iter([MemorySnapshot(commit_limit_bytes=16 * GIB, commit_used_bytes=13 * GIB),
                      MemorySnapshot(commit_limit_bytes=16 * GIB, commit_used_bytes=4 * GIB)])
    monkeypatch.setattr("haizflow.core.memory.memory_snapshot", lambda: next(snapshots))
    assert translation._worker_launch_plan() == (["gpu-engine"], "full", "")


def test_vram_is_rechecked_once_after_driver_release_settles(load_plan, monkeypatch):
    query = Mock(side_effect=[0, 6 * GIB])
    monkeypatch.setattr("haizflow.core.hardware.live_cuda_free_memory_bytes", query)
    assert translation._worker_launch_plan() == (["gpu-engine"], "full", "")
    assert query.call_count == 2


@pytest.mark.parametrize("missing", ["model", "engine"])
def test_no_q4_resource_gives_actionable_error_without_trying_oom_load(load_plan, monkeypatch, missing):
    _, model, command = load_plan
    monkeypatch.setattr("haizflow.core.hardware.live_cuda_free_memory_bytes", lambda: GIB)
    if missing == "model":
        model.unlink()
    else:
        command.side_effect = ResourcePackError("not installed")
    with pytest.raises(RuntimeError, match="cài HY-MT2 CPU Q4"):
        translation._worker_launch_plan()
    if missing == "model":
        command.assert_not_called()


def test_shutdown_interrupts_memory_settle_without_loading_any_model(load_plan, monkeypatch):
    _, _, command = load_plan
    monkeypatch.setattr("haizflow.core.hardware.live_cuda_free_memory_bytes", lambda: 0)
    monkeypatch.setattr(translation, "_WORKER_SHUTDOWN_EVENT", Mock(wait=Mock(return_value=True)))
    with pytest.raises(RuntimeError, match="shutting down"):
        translation._worker_launch_plan()
    command.assert_not_called()


def test_foreground_translation_retires_idle_rpc_and_local_models_in_order(monkeypatch):
    events = []
    pool = Mock()
    pool.release.side_effect = lambda capabilities: events.append(capabilities)
    modules = {"haizflow.pipeline.transcribe": SimpleNamespace(release_warm_whisperx_model=lambda: events.append("asr")),
               "haizflow.pipeline.omnivoice_tts": SimpleNamespace(clear_runtime=lambda: events.append("tts"))}
    with (patch("haizflow.services.external_engine.shared_external_engine_pool", return_value=pool),
          patch.dict("sys.modules", modules), patch.object(translation, "check_cancellation") as cancel):
        translation._release_translation_competitors("fixture")
    assert events == [{"recognition", "separation", "ocr", "voice", "translation"}, "asr", "tts"]
    assert cancel.call_count == 2


def test_warm_q4_worker_uses_resident_budget_without_reloading(monkeypatch):
    process, output = Mock(), Mock()
    process.poll.return_value = None
    monkeypatch.setattr(translation, "_WORKER_PROCESS", process)
    monkeypatch.setattr(translation, "_WORKER_OUTPUT", output)
    monkeypatch.setattr(translation, "_WORKER_EFFECTIVE_MODEL", "q4")
    monkeypatch.setattr(translation, "_WORKER_WARM", True)
    with (patch.object(translation, "_WORKER_SHUTDOWN_EVENT", Mock(is_set=Mock(return_value=False))),
          patch.object(translation, "_cancel_worker_idle_timer"),
          patch.object(translation, "processing_device_preference", return_value="gpu"),
          patch.object(translation, "_worker_launch_plan", side_effect=AssertionError("reloaded")),
          patch("haizflow.core.memory.require_cpu_memory") as budget):
        assert translation._ensure_hymt2_worker() == (process, output)
    budget.assert_called_once_with("translation", resident=True, settle_seconds=2)


def test_q4_fallback_does_not_bypass_cpu_memory_admission(monkeypatch):
    monkeypatch.setattr(translation, "_WORKER_PROCESS", None)
    with (patch.object(translation, "_WORKER_SHUTDOWN_EVENT", Mock(is_set=Mock(return_value=False))),
          patch.object(translation, "_cancel_worker_idle_timer"),
          patch.object(translation, "_worker_launch_plan", return_value=(["cpu-engine"], "q4", "low memory")),
          patch.object(translation, "processing_device_preference", return_value="gpu"),
          patch("haizflow.core.memory.require_cpu_memory", side_effect=RuntimeError("insufficient CPU memory")),
          patch.object(translation.subprocess, "Popen") as spawn):
        with pytest.raises(RuntimeError, match="insufficient CPU memory"):
            translation._ensure_hymt2_worker()
    spawn.assert_not_called()


def test_q4_launch_is_child_only_and_uses_one_validated_command(tmp_path, monkeypatch):
    process = Mock(pid=123)
    profile = SimpleNamespace(key="cuda_low_memory", hymt2_backend="transformers", requested_device="gpu",
                              cuda_name="RTX 3050", total_vram_gib=6, total_ram_gib=16)
    monkeypatch.setattr(config, "LOGS_DIR", str(tmp_path))
    monkeypatch.setenv("HAIZFLOW_TRANSLATION_MODEL", "full")
    with (patch.multiple(translation, _WORKER_PROCESS=None, _WORKER_OUTPUT=None, _WORKER_READER=None,
                         _WORKER_DIAGNOSTIC_PATH=None, _WORKER_EFFECTIVE_MODEL="", _WORKER_MEMORY_NOTE=""),
          patch.object(translation, "_WORKER_SHUTDOWN_EVENT", Mock(is_set=Mock(return_value=False))),
          patch.object(translation, "_cancel_worker_idle_timer"),
          patch.object(translation, "_worker_launch_plan", return_value=(["cpu-engine"], "q4", "low memory")) as plan,
          patch.object(translation, "runtime_profile", return_value=profile),
          patch.object(translation, "processing_device_preference", return_value="gpu"),
          patch.object(translation.threading, "Thread"),
          patch("haizflow.core.memory.require_cpu_memory") as admission,
          patch("haizflow.core.paths.engine_environment", return_value={}),
          patch.object(translation.subprocess, "Popen", return_value=process) as spawn):
        assert translation._ensure_hymt2_worker()[0] is process
        plan.assert_called_once_with()
        admission.assert_called_once_with("translation", settle_seconds=2)
        assert spawn.call_args.args[0] == ["cpu-engine"]
        environment = spawn.call_args.kwargs["env"]
        assert environment["HAIZFLOW_TRANSLATION_MODEL"] == "q4"
        assert environment["HF_ENABLE_PARALLEL_LOADING"] == "false"
        assert os.environ["HAIZFLOW_TRANSLATION_MODEL"] == "full"
        assert translation._WORKER_EFFECTIVE_MODEL == "q4"


@pytest.mark.parametrize("raw,expected", [(["0"], 0), (["4096"], 4 * GIB), ([], None), (["N/A"], None)])
def test_live_vram_probe_preserves_unknown_vs_exhausted(raw, expected):
    from haizflow.core.hardware import live_cuda_free_memory_bytes

    with patch("haizflow.core.hardware._run_nvidia_query", return_value=raw) as query:
        assert live_cuda_free_memory_bytes() == expected
    query.assert_called_once_with(("memory.free",))
