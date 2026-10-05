from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.smart_warmup_controller import SmartWarmupController
from haizflow.services import hymt2_worker


def test_gpu_load_uses_commit_headroom_not_only_physical_memory(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"fixture")
    with (
        patch.object(hymt2_worker, "os", SimpleNamespace(name="nt")),
        patch.object(hymt2_worker, "available_commit_bytes", return_value=1 * 1024**3),
    ):
        with pytest.raises(RuntimeError, match="bộ nhớ hệ thống"):
            hymt2_worker._require_cuda_commit_memory(str(tmp_path))
    with (
        patch.object(hymt2_worker, "os", SimpleNamespace(name="nt")),
        patch.object(hymt2_worker, "available_commit_bytes", return_value=3 * 1024**3),
    ):
        hymt2_worker._require_cuda_commit_memory(str(tmp_path))


def test_commit_pressure_releases_idle_models_even_if_ram_telemetry_is_unavailable():
    host = SimpleNamespace(_processing_queue=SimpleNamespace(has_work=False))
    with patch("haizflow.desktop.smart_warmup_controller.shared_external_engine_pool"):
        controller = SmartWarmupController(host, Mock())
    controller._resident.add("recognition")
    controller._release_now = Mock()
    with (
        patch("haizflow.desktop.smart_warmup_controller.runtime_profile", return_value=SimpleNamespace(total_ram_bytes=16 * 1024**3)),
        patch("haizflow.desktop.smart_warmup_controller.available_memory_bytes", return_value=0),
        patch("haizflow.desktop.smart_warmup_controller.available_commit_bytes", return_value=1 * 1024**3),
    ):
        controller._expire_idle_residents()
    controller._release_now.assert_called_once_with("memory-pressure")
