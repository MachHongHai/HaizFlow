import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from haizflow.core import model_integrity


class ModelIntegrityTests(unittest.TestCase):
    def test_production_revisions_are_immutable_commit_hashes(self):
        self.assertRegex(model_integrity.HYMT2_GPU_REVISION, r"^[0-9a-f]{40}$")
        self.assertRegex(model_integrity.HYMT2_CPU_REVISION, r"^[0-9a-f]{40}$")
        self.assertRegex(model_integrity.HYMT2_CPU_SHA256, r"^[0-9a-f]{64}$")
        self.assertRegex(model_integrity.WHISPER_REVISION, r"^[0-9a-f]{40}$")
        self.assertRegex(model_integrity.DEMUCS_MODEL_SIGNATURE, r"^[0-9a-f]{8}$")
        self.assertRegex(model_integrity.DEMUCS_MODEL_SHA256, r"^[0-9a-f]{64}$")
        self.assertIn(model_integrity.DEMUCS_MODEL_SHA256[:8], model_integrity.DEMUCS_MODEL_FILE)
        for _name, (_size, digest) in model_integrity.WHISPER_FILES.items():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(set(model_integrity.ALIGNMENT_MODELS), {"en", "fr", "de", "es", "it"})
        for _bundle, filename, size, digest in model_integrity.ALIGNMENT_MODELS.values():
            self.assertTrue(filename.endswith((".pt", ".pth")))
            self.assertGreater(size, 300_000_000)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_integrity_marker_avoids_rehashing_unchanged_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_file = root / "model.bin"
            model_file.write_bytes(b"pinned model")
            expected_hash = hashlib.sha256(model_file.read_bytes()).hexdigest()
            expected = {"model.bin": (model_file.stat().st_size, expected_hash)}

            model_integrity._verify(root, kind="test", revision="a" * 40, expected=expected)
            marker = json.loads((root / model_integrity.MARKER_NAME).read_text(encoding="utf-8"))
            self.assertEqual(marker["version"], model_integrity.MARKER_VERSION)

            with mock.patch.object(model_integrity, "_sha256", side_effect=AssertionError("unexpected rehash")):
                model_integrity._verify(root, kind="test", revision="a" * 40, expected=expected)

    def test_changed_model_is_rejected_even_when_a_marker_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_file = root / "model.bin"
            model_file.write_bytes(b"original")
            expected = {
                "model.bin": (
                    model_file.stat().st_size,
                    hashlib.sha256(model_file.read_bytes()).hexdigest(),
                )
            }
            model_integrity._verify(root, kind="test", revision="b" * 40, expected=expected)
            model_file.write_bytes(b"tampered")
            with self.assertRaises(model_integrity.ModelIntegrityError):
                model_integrity._verify(root, kind="test", revision="b" * 40, expected=expected)


if __name__ == "__main__":
    unittest.main()
