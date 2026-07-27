"""Stage every pinned torchaudio alignment model for the offline installer."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.config import MODELS_DIR, TORCH_HOME  # noqa: E402
from haizflow.core.model_integrity import (  # noqa: E402
    ALIGNMENT_MODEL_BASE_URL,
    ALIGNMENT_MODELS,
    ModelIntegrityError,
    verify_alignment_model,
    verify_alignment_models,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_pinned_file(path: Path, expected_size: int, expected_sha256: str) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == expected_size
        and _sha256(path) == expected_sha256
    )


def _copy_atomic(source: Path, destination: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _download(filename: str, expected_size: int, expected_sha256: str, destination: Path) -> None:
    source = ALIGNMENT_MODEL_BASE_URL + filename
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme != "https" or parsed.hostname != "download.pytorch.org":
        raise RuntimeError("Alignment model manifest contains an unapproved source.")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{filename}.",
        suffix=".download",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        request = urllib.request.Request(
            source,
            headers={"User-Agent": "HaizFlow offline-model preparation"},
        )
        digest = hashlib.sha256()
        received = 0
        with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
            final_url = urllib.parse.urlparse(response.geturl())
            if final_url.scheme != "https" or final_url.hostname != "download.pytorch.org":
                raise RuntimeError("Alignment model download redirected to an unapproved source.")
            advertised_size = response.headers.get("Content-Length")
            if advertised_size is not None and int(advertised_size) != expected_size:
                raise RuntimeError("Alignment model download size does not match its pinned manifest.")
            with temporary.open("wb") as output:
                while chunk := response.read(8 * 1024 * 1024):
                    received += len(chunk)
                    if received > expected_size:
                        raise RuntimeError("Alignment model download exceeded its pinned size.")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        if received != expected_size or digest.hexdigest() != expected_sha256:
            raise RuntimeError("Alignment model download failed full SHA-256 verification.")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    destination_directory = Path(MODELS_DIR) / "alignment"
    destination_directory.mkdir(parents=True, exist_ok=True)
    torch_cache = Path(TORCH_HOME) / "hub" / "checkpoints"

    remaining_bytes = 0
    for language, (_bundle_name, _filename, size, _digest) in ALIGNMENT_MODELS.items():
        try:
            verify_alignment_model(destination_directory, language)
        except ModelIntegrityError:
            remaining_bytes += size
    if shutil.disk_usage(destination_directory).free < remaining_bytes + 512 * 1024 * 1024:
        raise RuntimeError(
            f"At least {(remaining_bytes + 512 * 1024 * 1024) / (1024**3):.1f} GB free "
            "is required to stage the offline alignment models."
        )

    for language, (_bundle_name, filename, size, digest) in ALIGNMENT_MODELS.items():
        destination = destination_directory / filename
        try:
            verify_alignment_model(destination_directory, language)
            print(f"Alignment model already verified: {language} ({filename})")
            continue
        except ModelIntegrityError:
            destination.unlink(missing_ok=True)

        cached = torch_cache / filename
        if _is_pinned_file(cached, size, digest):
            print(f"Staging verified alignment model from the portable cache: {language}")
            _copy_atomic(cached, destination)
        else:
            print(f"Downloading pinned alignment model: {language} ({size / (1024**2):.1f} MiB)")
            _download(filename, size, digest, destination)
        verify_alignment_model(destination_directory, language)

    verify_alignment_models(destination_directory)
    print(f"Pinned alignment models ready: {destination_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
