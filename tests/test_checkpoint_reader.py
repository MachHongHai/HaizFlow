from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.services import hymt2_worker
from haizflow.schemas.video import VideoConfig
from haizflow.services.checkpoint_reader import BufferedCheckpoint


def test_windows_checkpoint_reader_uses_buffered_backend_and_restores_on_error():
    reader = Mock()
    module = SimpleNamespace(safe_open=reader)
    with patch.dict("sys.modules", {"transformers": SimpleNamespace(modeling_utils=module)}), \
            patch.object(hymt2_worker.os, "name", "nt"):
        with pytest.raises(RuntimeError, match="load failed"):
            with hymt2_worker._checkpoint_reader():
                assert module.safe_open is BufferedCheckpoint
                raise RuntimeError("load failed")
    reader.assert_not_called()
    assert module.safe_open is reader


def test_auto_audio_options_survive_config_round_trip():
    config = VideoConfig(
        background_music_loop=False,
        audio_ducking_enabled=True,
        audio_ducking_reduction_db=-18,
    )
    restored = VideoConfig.model_validate_json(config.model_dump_json())
    assert not restored.background_music_loop
    assert restored.audio_ducking_enabled
    assert restored.audio_ducking_reduction_db == -18


def test_bounded_reader_matches_safetensors_including_bfloat16(tmp_path):
    import torch
    from safetensors.torch import save_file

    tensors = {"bf": torch.arange(12).reshape(3, 4).to(torch.bfloat16),
               "fp": torch.tensor([1.5, 2.5]), "empty": torch.empty(0)}
    path = tmp_path / "weights.safetensors"
    save_file(tensors, path, metadata={"format": "pt"})
    with BufferedCheckpoint(path) as reader:
        assert set(reader.keys()) == set(tensors)
        assert reader.metadata() == {"format": "pt"}
        assert reader.get_slice("bf").get_dtype() == "BF16"
        for name, tensor in tensors.items():
            assert torch.equal(reader.get_tensor(name), tensor)
            assert torch.equal(reader.get_slice(name)[...], tensor)


def test_bounded_reader_rejects_truncated_data(tmp_path):
    import torch
    from safetensors.torch import save_file

    path = tmp_path / "weights.safetensors"
    save_file({"x": torch.ones(4)}, path)
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(ValueError, match="Truncated"):
        BufferedCheckpoint(path)
