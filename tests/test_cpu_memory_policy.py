"""Deterministic telemetry/policy tests. These do not load real AI models."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.core import hardware, memory
from haizflow.core.model_choices import models_for_device, recognition_context
from haizflow.desktop.resource_pack_controller import ResourcePackController
from haizflow.desktop.smart_warmup_controller import SmartWarmupController
from haizflow.pipeline import manual_tools, omnivoice_tts
from haizflow.services.external_engine import ExternalEnginePool

GIB = memory.GIB


def snapshot(*, installed=16, usable=13.9, available=4.34, commit=6.15):
    return memory.MemorySnapshot(
        None if installed is None else int(installed * GIB),
        None if usable is None else int(usable * GIB),
        None if available is None else int(available * GIB),
        24 * GIB if commit is not None else None,
        int((24 - commit) * GIB) if commit is not None else None,
    )


def caps(**kwargs):
    state = snapshot(**kwargs)
    return hardware.HardwareCapabilities(False, "", 0, 0, state.usable_bytes or 0, 12, True, None,
                                         installed_ram_bytes=state.installed_bytes)


def test_installed_16gb_reserved_memory_passes_cpu_and_gpu_capacity():
    cpu = caps()
    assert hardware.validate_processing_device("cpu", cpu)[0]
    gpu = replace(cpu, cuda_available=True, cuda_name="test", total_vram_bytes=6 * GIB)
    assert hardware.validate_processing_device("gpu", gpu)[0]
    assert not hardware.validate_processing_device("gpu", replace(gpu, total_vram_bytes=4 * GIB))[0]
    profile = hardware.runtime_profile_for(cpu, "cpu")
    assert (profile.key, profile.whisper_batch_size, profile.cpu_threads) == ("cpu_low_memory", 2, 4)
    assert not profile.warm_hymt2_on_startup
    assert not profile.warm_whisper_on_startup


@pytest.mark.parametrize("installed,usable", [(8, 7.9), (12, 11.5), (16, 6), (None, None), (None, 13.9)])
def test_insufficient_or_unverified_capacity_is_not_eligible(installed, usable):
    compatible, reason = hardware.validate_processing_device("cpu", caps(installed=installed, usable=usable))
    assert not compatible
    assert "16 GB" in reason
    assert "OS-usable" in reason


def test_known_usable_ram_is_a_safe_lower_bound_when_installed_api_fails():
    assert hardware.validate_processing_device("cpu", caps(installed=None, usable=32))[0]
    assert hardware.runtime_profile_for(caps(installed=None, usable=None), "cpu").key == "cpu_minimum"


def test_windows_apis_are_distinct_and_kib_page_units_are_converted():
    native = Mock()

    def status(pointer):
        pointer._obj.ullTotalPhys = int(13.9 * GIB)
        pointer._obj.ullAvailPhys = int(4.34 * GIB)
        pointer._obj.ullAvailPageFile = int(6.15 * GIB)
        pointer._obj.ullAvailVirtual = 123  # Address-space bytes are NOT commit.
        return 1

    def installed(pointer):
        pointer._obj.value = 16 * GIB // 1024
        return 1

    def performance(pointer, _size):
        pointer._obj.PageSize = 4096
        pointer._obj.CommitLimit = 24 * GIB // 4096
        pointer._obj.CommitTotal = 16 * GIB // 4096
        return 1

    native.GlobalMemoryStatusEx.side_effect = status
    native.GetPhysicallyInstalledSystemMemory.side_effect = installed
    native.K32GetPerformanceInfo.side_effect = performance
    result = memory._windows_memory_snapshot(native)
    assert result.installed_bytes == 16 * GIB
    assert result.usable_bytes == int(13.9 * GIB)
    assert result.available_bytes == int(4.34 * GIB)
    assert result.commit_limit_bytes == 24 * GIB
    assert result.commit_used_bytes == 16 * GIB
    assert result.commit_available_bytes == int(6.15 * GIB)  # Smaller process limit wins.
    native.GlobalMemoryStatusEx.assert_called_once()


def test_api_failure_does_not_turn_unknown_into_zero_or_valid_hardware():
    native = Mock()
    native.GlobalMemoryStatusEx.return_value = 0
    native.GetPhysicallyInstalledSystemMemory.return_value = 0
    native.K32GetPerformanceInfo.return_value = 0
    result = memory._windows_memory_snapshot(native)
    assert result == memory.MemorySnapshot()
    assert result.commit_available_bytes is None
    with pytest.raises(RuntimeError, match="Không đọc được"):
        memory.require_cpu_memory("recognition", snapshot=result)


def test_zero_commit_is_exhaustion_and_uses_system_limit_when_process_limit_is_missing():
    result = memory.MemorySnapshot(commit_limit_bytes=20 * GIB, commit_used_bytes=20 * GIB)
    assert result.commit_available_bytes == 0
    with pytest.raises(RuntimeError, match="0.0 GiB"):
        memory.require_cpu_memory("recognition", snapshot=replace(result, available_bytes=5 * GIB))


def test_actual_report_passes_cpu_admission_but_lower_commit_blocks_voice():
    result = snapshot()
    memory.require_cpu_memory("recognition", snapshot=result)
    memory.require_cpu_memory("translation", snapshot=result)
    memory.require_cpu_memory("voice", snapshot=result)
    with pytest.raises(RuntimeError, match="OmniVoice.*4.0 GiB"):
        memory.require_cpu_memory("voice", snapshot=snapshot(commit=4))
    memory.require_cpu_memory("voice", resident=True, snapshot=snapshot(available=1, commit=2))


@pytest.mark.parametrize("stage", ["recognition", "translation", "separation", "voice"])
def test_low_physical_memory_rejects_each_heavy_stage_without_allocating(stage):
    with pytest.raises(RuntimeError, match="RAM trống"):
        memory.require_cpu_memory(stage, snapshot=snapshot(available=0.2, commit=16))


def test_live_pressure_lowers_batches_threads_but_not_precision():
    balanced = hardware.runtime_profile_for(caps(installed=32, usable=31), "cpu")
    normal = hardware.cpu_runtime_profile(balanced, memory=snapshot(available=12, commit=16))
    assert normal is balanced
    limited = hardware.cpu_runtime_profile(balanced, memory=snapshot(available=4, commit=6))
    assert (limited.whisper_batch_size, limited.cpu_threads) == (2, 4)
    tight = hardware.cpu_runtime_profile(balanced, memory=snapshot(available=2, commit=3))
    assert (tight.whisper_batch_size, tight.cpu_threads) == (1, 2)
    assert limited.hymt2_dtype == balanced.hymt2_dtype
    assert not limited.warm_hymt2_on_startup
    unknown = hardware.cpu_runtime_profile(balanced, memory=memory.MemorySnapshot())
    assert unknown.whisper_batch_size == 1
    gpu = hardware.runtime_profile_for(replace(caps(installed=32, usable=31), cuda_available=True,
                                                total_vram_bytes=16 * GIB), "gpu")
    assert hardware.cpu_runtime_profile(gpu, memory=snapshot(available=0, commit=0)) is gpu
    with patch.object(hardware, "hardware_capabilities", return_value=caps()):
        forced = hardware.cpu_runtime_profile(gpu, memory=snapshot(), force_cpu=True)
    assert not forced.cuda_available and forced.whisper_batch_size == 2


def test_resource_packs_share_capacity_policy_used_by_settings_auto_manual_batch():
    host = SimpleNamespace(_hardware_capabilities=caps(), _startup_hardware_resolved=True, _settings_language="vi")
    controller = ResourcePackController.__new__(ResourcePackController)
    controller._host = host
    for pack in ("engine-cpu-py313", "model-whisper-small", "model-hymt2-cpu", "model-demucs-cpu"):
        assert controller._hardware_compatibility(pack)[0]
        host._hardware_capabilities = caps(installed=8, usable=7.9)
        valid, reason = controller._hardware_compatibility(pack)
        assert not valid and "7.9 GiB" in reason and "8.0 GiB" in reason
        host._hardware_capabilities = caps()
    assert models_for_device("cpu", recognition="small-cpu", translation="q4", voice="omnivoice") == {
        "speech_recognition_model": "small-cpu", "translation_model": "q4", "tts_provider": "omnivoice",
    }
    assert recognition_context("small-cpu", "cpu") == {"model": "small", "device": "cpu"}


def test_low_capacity_cpu_does_not_speculatively_load_voice_or_translation():
    controller = SmartWarmupController.__new__(SmartWarmupController)
    with (
        patch("haizflow.desktop.smart_warmup_controller.runtime_profile", return_value=hardware.runtime_profile_for(caps(), "cpu")),
        patch("haizflow.desktop.smart_warmup_controller.available_memory_bytes", return_value=10 * GIB),
        patch("haizflow.desktop.smart_warmup_controller.available_commit_bytes", return_value=16 * GIB),
    ):
        assert not controller._has_warmup_budget("voice", {})
        assert not controller._has_warmup_budget("translation", {})
        assert controller._has_warmup_budget("recognition", {"model": "small"})
    with patch("haizflow.desktop.smart_warmup_controller.available_memory_bytes", return_value=0):
        assert not controller._has_warmup_budget("recognition", {"model": "small"})


def test_omnivoice_preflight_reuses_only_matching_resident_model_and_not_oneshot():
    request = {"model_root": "model", "device": "cpu"}
    process = Mock()
    process.poll.return_value = None
    with (
        patch.object(omnivoice_tts, "_PERSISTENT_WORKER_PROCESS", process),
        patch.object(omnivoice_tts, "_PERSISTENT_WORKER_DEVICE", "cpu"),
        patch.object(omnivoice_tts, "_PERSISTENT_MODEL_KEY", ("model", "cpu")),
        patch("haizflow.core.memory.require_cpu_memory") as preflight,
    ):
        omnivoice_tts._preflight_cpu_request(request, allow_resident=True)
        preflight.assert_called_with("voice", resident=True)
        omnivoice_tts._preflight_cpu_request(request)
        preflight.assert_called_with("voice", resident=False)


def test_asr_preflight_failure_does_not_start_engine_or_write_output(tmp_path):
    output = tmp_path / "segments.json"
    with (
        patch("haizflow.pipeline.process_registry.check_cancellation"),
        patch("haizflow.services.external_engine.shared_external_engine_pool") as pool,
        patch("haizflow.core.memory.memory_snapshot", return_value=snapshot(available=0.2)),
        patch("haizflow.services.external_tasks.run_external_task") as execute,
        patch("haizflow.core.hardware.processing_device_preference", return_value="cpu"),
    ):
        pool.return_value.is_warm.return_value = False
        with pytest.raises(RuntimeError, match="RAM trống"):
            manual_tools.transcribe("source.wav", str(output), "auto", "test", model_name="small-cpu")
        execute.assert_not_called()
    assert not output.exists()


def test_engine_warm_marker_is_bound_to_process_generation_and_released():
    manager = Mock()
    manager.warm_engine_pack.return_value = "cpu-engine"
    pool = ExternalEnginePool(manager)
    client = Mock(alive=True)
    client.generation = object()
    pool._clients["cpu-engine"] = client
    context = {"model": "small", "device": "cpu"}
    pool.warm("recognition", context)
    assert pool.is_warm("recognition", context)
    assert not pool.is_warm("recognition", {"model": "turbo", "device": "gpu"})
    client.generation = object()
    assert not pool.is_warm("recognition", context)
    pool.release({"recognition"})
    assert not pool.is_warm("recognition", context)


def test_unknown_commit_blocks_windows_admission_and_pressure_is_live():
    with patch.object(memory, "os", SimpleNamespace(name="nt")):
        with pytest.raises(RuntimeError, match="Không đọc được"):
            memory.require_cpu_memory("voice", snapshot=snapshot(commit=None))
        assert memory.cpu_memory_constrained(snapshot(commit=None))
        assert memory.cpu_memory_constrained(snapshot(installed=32, usable=31, available=2, commit=16))
        assert not memory.cpu_memory_constrained(snapshot(installed=32, usable=31, available=12, commit=16))


def test_preflight_warning_keeps_numbers_and_guidance_in_ui():
    from haizflow.core.processing_errors import describe_failure

    with pytest.raises(RuntimeError) as failure:
        memory.require_cpu_memory("voice", snapshot=snapshot(commit=4))
    display = describe_failure(str(failure.value))
    assert display["code"] == "memory_preflight_failed"
    assert "4.3 GiB" in display["message"] and "4.0 GiB" in display["message"]
    assert "Windows tự quản lý bộ nhớ ảo" in display["message"]
