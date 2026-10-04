import hashlib
from unittest.mock import patch

import pytest

from haizflow.core import bundled_models
from haizflow.core.model_integrity import ModelIntegrityError


def test_bundled_model_is_pinned_read_only_and_foreign_files_are_rejected(tmp_path):
    root = tmp_path / "models"
    folder = root / "speaker-identification"
    folder.mkdir(parents=True)
    model = folder / bundled_models.MODEL_FILE
    model.write_bytes(b"pinned speaker")
    original = model.stat().st_mtime_ns
    with patch.object(bundled_models, "MODEL_SIZE", model.stat().st_size), patch.object(
        bundled_models, "MODEL_SHA256", hashlib.sha256(model.read_bytes()).hexdigest()
    ):
        assert bundled_models.verify_core_models(root, required=True)
        assert list(folder.iterdir()) == [model]
        assert model.stat().st_mtime_ns == original
        foreign = folder / "unknown.onnx"
        foreign.write_bytes(b"unexpected")
        with pytest.raises(ModelIntegrityError, match="Unexpected model payload"):
            bundled_models.verify_core_models(root, required=True)
        foreign.unlink()
        model.write_bytes(b"changed speak")
        with pytest.raises(ModelIntegrityError, match="checksum"):
            bundled_models.verify_core_models(root, required=True)


def test_missing_bundled_model_can_only_be_optional(tmp_path):
    assert not bundled_models.verify_core_models(tmp_path / "models", required=False)
    with pytest.raises(ModelIntegrityError):
        bundled_models.verify_core_models(tmp_path / "models", required=True)
