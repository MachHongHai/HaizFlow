"""Pinned small Core asset. Verification never writes into immutable payloads."""
from pathlib import Path

from haizflow.core.model_integrity import ModelIntegrityError, _sha256

MODEL_FILE = "wespeaker_en_voxceleb_resnet34.onnx"
MODEL_SIZE = 26_534_127
MODEL_SHA256 = "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
MODEL_REVISION = "ff1ac5bca8ef11e90662b879aa923979e0bd277b"
MODEL_URL = (
    "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34/resolve/"
    + MODEL_REVISION + "/voxceleb_resnet34.onnx"
)


def verify_speaker(root: Path) -> Path:
    from haizflow.update.filesystem import no_links

    path = root / MODEL_FILE
    no_links(path)
    if not path.is_file() or path.stat().st_size != MODEL_SIZE or _sha256(path) != MODEL_SHA256:
        raise ModelIntegrityError("Bundled speaker model is missing or has an invalid checksum.")
    return path


def verify_core_models(root: Path, *, required: bool) -> bool:
    """Allow exactly the integrated speaker model; optional AI stays external."""
    from haizflow.update.filesystem import no_links

    no_links(root)
    files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    allowed = {"speaker-identification/" + MODEL_FILE}
    if files - allowed:
        raise ModelIntegrityError("Unexpected model payload in Core: " + ", ".join(sorted(files - allowed)))
    if not files and not required:
        return False
    verify_speaker(root / "speaker-identification")
    return True
