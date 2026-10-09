"""Mock admission/routing tests, not real inference or hardware benchmarks."""

import sys
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from haizflow.core import hardware, memory, runtime_probe
from haizflow.core.model_choices import recognition_context
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.resource_pack_controller import ResourcePackController
from haizflow.services.resource_packs import ResourcePackManager

GIB = memory.GIB


@dataclass(frozen=True)
class Machine:
    name: str
    installed: float | None
    usable: float
    vram: float
    cuda: bool
    capability: tuple[int, int]
    cpu_ok: bool
    gpu_ok: bool
    batch: int

    def caps(self):
        return hardware.HardwareCapabilities(self.cuda, self.name if self.cuda else "", int(self.vram * GIB),
            int(self.vram * GIB), int(self.usable * GIB), 12, True, None,
            cuda_compute_capability=self.capability, cuda_bf16_supported=self.capability[0] >= 8,
            installed_ram_bytes=None if self.installed is None else int(self.installed * GIB))


MACHINES = [
    Machine("CPU-16-reserved", 16, 13.9, 0, False, (0, 0), True, False, 2),
    Machine("CPU-32", 32, 31, 0, False, (0, 0), True, False, 4),
    Machine("CPU-8", 8, 7.8, 0, False, (0, 0), False, False, 2),
    Machine("reserved-too-much", 16, 6, 0, False, (0, 0), False, False, 1),
    Machine("unknown-installed", None, 13.9, 0, False, (0, 0), False, False, 2),
    Machine("unknown-all", None, 0, 0, False, (0, 0), False, False, 1),
    Machine("usable-proves-capacity", None, 32, 0, False, (0, 0), True, False, 4),
    Machine("GTX-1070", 128, 127, 8, True, (6, 1), True, True, 4),
    Machine("RTX-2060-6", 16, 13.9, 6, True, (7, 5), True, True, 2),
    Machine("RTX-4090-24", 64, 63, 24, True, (8, 9), True, True, 4),
    Machine("GPU-4", 32, 31, 4, True, (7, 5), True, False, 4),
    Machine("driver-unavailable", 32, 31, 8, False, (8, 6), True, False, 4),
    Machine("GPU-but-insufficient-RAM", 8, 7.8, 24, True, (8, 9), False, False, 2),
]


@pytest.mark.parametrize("machine", MACHINES, ids=lambda value: value.name)
@pytest.mark.parametrize("device", ["cpu", "gpu"])
def test_admission_ui_and_resource_packs_agree(machine, device):
    caps = machine.caps()
    expected = machine.cpu_ok if device == "cpu" else machine.gpu_ok
    assert hardware.validate_processing_device(device, caps)[0] is expected
    assert hardware.recommended_processing_device(caps) == ("gpu" if machine.gpu_ok else "cpu")
    host = SimpleNamespace(_settings_processing_device=device, _settings_language="vi",
                           _startup_hardware_resolved=True, _hardware_capabilities=caps)
    controller = ResourcePackController.__new__(ResourcePackController)
    controller._host = host
    packs = ("engine-cpu-py313", "model-hymt2-cpu", "model-demucs-cpu") if device == "cpu" else (
        "engine-cuda128-py313", "model-whisper-turbo", "model-hymt2-gpu", "model-demucs-gpu")
    for pack in packs:
        assert controller._hardware_compatibility(pack)[0] is expected
    options = HaizFlowController.speechRecognitionModelOptions.fget(host)
    assert options[0]["available"]
    assert all(row["available"] is (device == "gpu" and machine.gpu_ok) for row in options[1:])
    profile = hardware.runtime_profile_for(caps, device)
    assert profile.cuda_available is (device == "gpu" and machine.gpu_ok)
    if not profile.cuda_available:
        assert profile.whisper_batch_size == machine.batch
        assert profile.hymt2_backend == "llama_cpp"
    else:
        assert profile.hymt2_dtype == ("bfloat16" if caps.cuda_bf16_supported else "float16")


@pytest.mark.parametrize("project_type", ["single", "manual", "batch"])
@pytest.mark.parametrize("device", ["cpu", "gpu"])
@pytest.mark.parametrize("machine", [MACHINES[0], MACHINES[2], MACHINES[7], MACHINES[9]], ids=lambda value: value.name)
def test_auto_manual_batch_preflight_share_hardware_admission(machine, device, project_type):
    from haizflow.schemas.video import VideoConfig

    caps = machine.caps()
    manager = ResourcePackManager.__new__(ResourcePackManager)
    manager.status = Mock(return_value="installed")
    host = SimpleNamespace(_settings_processing_device=device, _settings_language="vi",
        _startup_hardware_resolved=True, _hardware_capabilities=caps, appAlertRequested=Mock(),
        _processing_queue=SimpleNamespace(contains=lambda _: False))
    resources = ResourcePackController.__new__(ResourcePackController)
    resources._host = host
    resources.manager = manager
    host._resource_packs = SimpleNamespace(manager=manager, storageMoving=False,
                                           _hardware_compatibility=resources._hardware_compatibility)
    host._ensure_hardware_ready_for_action = lambda: hardware.validate_processing_device(device, caps)[0]
    video = SimpleNamespace(**VideoConfig(project_type=project_type, speech_recognition_model=(
        "small-gpu" if device == "gpu" else "small-cpu"), translation_model="q4", tts_provider="omnivoice",
        tts_voice="omnivoice:male").model_dump(), video_id="matrix", status="pending")
    expected = machine.cpu_ok if device == "cpu" else machine.gpu_ok
    assert ProjectCommandsController._resources_ready_for_videos(host, [video]) is expected


@pytest.mark.parametrize("choice,device,expected", [
    ("small-cpu", "cpu", "engine-cpu-py313"),
    ("small-cpu", "gpu", "engine-cpu-py313"),
    ("small-gpu", "gpu", "engine-cuda128-py313"),
    ("large-v3-turbo", "gpu", "engine-cuda128-py313"),
])
def test_explicit_recognition_device_routes_matching_engine(choice, device, expected):
    manager = ResourcePackManager.__new__(ResourcePackManager)
    context = recognition_context(choice, device)
    assert manager.required_packs("recognition", context)[0] == expected


@pytest.mark.parametrize("machine,device,model,expected", [
    (MACHINES[0], "cpu", "auto", ["engine-cpu-py313", "model-hymt2-cpu"]),
    (MACHINES[7], "gpu", "auto", ["engine-cpu-py313", "model-hymt2-cpu"]),
    (MACHINES[7], "gpu", "q4", ["engine-cpu-py313", "model-hymt2-cpu"]),
    (MACHINES[7], "gpu", "full", ["engine-cuda128-py313", "model-hymt2-gpu"]),
    (MACHINES[9], "gpu", "auto", ["engine-cuda128-py313", "model-hymt2-gpu"]),
    (MACHINES[9], "gpu", "q4", ["engine-cpu-py313", "model-hymt2-cpu"]),
    (MACHINES[0], "cpu", "gemini-flash", []),
    (MACHINES[9], "gpu", "gemini-flash", []),
])
def test_translation_auto_explicit_and_cloud_routes_stay_independent(machine, device, model, expected):
    manager = ResourcePackManager.__new__(ResourcePackManager)
    profile = hardware.runtime_profile_for(machine.caps(), device)
    with patch.object(hardware, "runtime_profile", return_value=profile):
        assert manager.required_packs("translation", {"device": device, "translation_model": model}) == expected


@pytest.mark.parametrize("device,provider,engine", [
    ("cpu", "omnivoice", "engine-cpu-py313"),
    ("gpu", "omnivoice", "engine-cpu-py313"),
    ("gpu", "omnivoice-gpu", "engine-cuda128-py313"),
])
@pytest.mark.parametrize("speaker_mode", ["single", "multiple"])
def test_voice_engine_follows_provider_not_whisper_or_global_override(device, provider, engine, speaker_mode):
    manager = ResourcePackManager.__new__(ResourcePackManager)
    packs = manager.required_packs("voice", {"device": device, "provider": provider, "speaker_mode": speaker_mode})
    assert packs[:2] == [engine, "model-omnivoice"]
    assert ("model-speaker-identification" in packs) is (speaker_mode == "multiple")


@pytest.mark.parametrize("stage", memory.CPU_STAGE_RESERVES)
@pytest.mark.parametrize("available,commit,allowed", [(4.34, 6.15, True), (.2, 16, False),
    (8, .2, False), (None, 16, False), (8, None, False)])
def test_windows_live_memory_budgets(stage, available, commit, allowed):
    snapshot = memory.MemorySnapshot(16 * GIB, int(13.9 * GIB),
        None if available is None else int(available * GIB), process_commit_available_bytes=(
            None if commit is None else int(commit * GIB)))
    with patch.object(memory, "os", SimpleNamespace(name="nt")):
        if allowed:
            memory.require_cpu_memory(stage, snapshot=snapshot)
        else:
            with pytest.raises(RuntimeError):
                memory.require_cpu_memory(stage, snapshot=snapshot)


@pytest.mark.parametrize("device,supported,cuda,expected,ok", [
    ("gpu", {"int8_float32", "float32"}, True, "int8_float32", True),
    ("gpu", {"float16", "float32"}, True, "float16", True),
    ("cpu", {"int8", "float32"}, False, "int8", True),
    ("gpu", set(), True, None, False),
    ("gpu", {"float16", "float32"}, False, "float16", False),
])
def test_full_native_probe_accepts_same_precision_as_inference(device, supported, cuda, expected, ok):
    tensor = MagicMock()
    tensor.sum.return_value.item.return_value = 16
    tensor.__matmul__.return_value.sum.return_value.item.return_value = 4096
    torch = SimpleNamespace(__version__="test", version=SimpleNamespace(cuda="test"),
        float32="fp32", float16="fp16", ones=Mock(return_value=tensor), cuda=SimpleNamespace(
            is_available=lambda: cuda, synchronize=Mock(), get_device_name=lambda _: "test-GPU",
            get_device_capability=lambda _: (6, 1), is_bf16_supported=lambda: False, empty_cache=Mock()))
    modules = {name: SimpleNamespace() for name in ("torchaudio", "torchvision", "whisperx", "transformers",
               "accelerate", "llama_cpp", "torchcodec")}
    modules.update(torch=torch, ctranslate2=SimpleNamespace(get_supported_compute_types=lambda _: supported))
    with patch.dict(sys.modules, modules), patch.dict(runtime_probe.os.environ), \
         patch.object(runtime_probe, "_distribution_version", return_value="test"):
        result = runtime_probe.run_runtime_probe(device)
    assert result.ok is ok
    assert result.details.get("whisper_compute_type") == expected
