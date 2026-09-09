import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from haizflow.core.dependency_security import (
    _guard_lightning_saving_module,
    validate_checkpoint_weight_maps,
)


class _CheckpointModel:
    CHECKPOINT_HYPER_PARAMS_KEY = "hyper_parameters"


class DependencySecurityTests(unittest.TestCase):
    def _module(self):
        module = types.ModuleType("fake_lightning_saving")

        def load_state(cls, checkpoint, strict=None, **kwargs):
            return cls, checkpoint, strict, kwargs

        module._load_state = load_state
        return module

    def test_lightning_guard_blocks_checkpoint_import_path(self):
        module = self._module()
        self.assertTrue(_guard_lightning_saving_module(module))

        with self.assertRaisesRegex(ValueError, "blocked"):
            module._load_state(
                _CheckpointModel,
                {"hyper_parameters": {"_instantiator": "os.system"}},
            )

    def test_lightning_guard_allows_official_instantiator_and_is_idempotent(self):
        module = self._module()
        self.assertTrue(_guard_lightning_saving_module(module))
        result = module._load_state(
            _CheckpointModel,
            {},
            _instantiator="lightning.pytorch.cli.instantiate_module",
        )

        self.assertEqual(result[3]["_instantiator"], "lightning.pytorch.cli.instantiate_module")
        self.assertFalse(_guard_lightning_saving_module(module))

    def test_upstream_fixed_module_is_not_wrapped(self):
        module = self._module()
        module._ALLOWED_INSTANTIATORS = {"lightning.pytorch.cli.instantiate_module"}
        original = module._load_state

        self.assertFalse(_guard_lightning_saving_module(module))
        self.assertIs(module._load_state, original)

    def test_checkpoint_weight_map_accepts_regular_local_shards(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shard = root / "model-00001-of-00001.safetensors"
            shard.write_bytes(b"verified model payload")
            (root / "model.safetensors.index.json").write_text(
                '{"weight_map":{"layer.weight":"model-00001-of-00001.safetensors"}}',
                encoding="utf-8",
            )

            self.assertEqual(validate_checkpoint_weight_maps(root), (shard,))

    def test_checkpoint_weight_map_rejects_path_traversal(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "model.safetensors.index.json").write_text(
                '{"weight_map":{"layer.weight":"../secret.txt"}}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "escapes"):
                validate_checkpoint_weight_maps(root)


if __name__ == "__main__":
    unittest.main()
