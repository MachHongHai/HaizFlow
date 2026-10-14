"""Pinned offline acoustic preset classifier (not a person's gender identity)."""
from pathlib import Path

from hflow.core.model_integrity import ModelIntegrityError, _sha256

MODEL_FILE = "ecapa_voice_profile_q8.onnx"
MODEL_SIZE = 15_779_619
MODEL_SHA256 = "33a7f84f17d5ceee61aae8b23488e06fc1e3295a44eaf7eb5744f3e01e380784"
MODEL_REVISION = "5debf995242f9851881d4e4848fe6eed2bb5ade7"
MODEL_URL = (
    "https://huggingface.co/Alice-Sabrina-Ivy/voice-gender-classifier-onnx-q8/resolve/"
    + MODEL_REVISION + "/onnx/model_quantized.onnx"
)


def verify_voice_profile(root: Path) -> Path:
    from hflow.update.filesystem import no_links

    path = root / MODEL_FILE
    no_links(path)
    if not path.is_file() or path.stat().st_size != MODEL_SIZE or _sha256(path) != MODEL_SHA256:
        raise ModelIntegrityError("Bundled voice profile model is missing or has an invalid checksum.")
    return path
