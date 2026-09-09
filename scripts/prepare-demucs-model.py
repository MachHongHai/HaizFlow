"""Stage the pinned Demucs vocal-separation checkpoint for offline builds."""

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
    DEMUCS_MODEL_FILE,
    DEMUCS_MODEL_SHA256,
    DEMUCS_MODEL_SIZE,
    DEMUCS_MODEL_URL,
    verify_demucs_model,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_pinned_file(path: Path) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == DEMUCS_MODEL_SIZE
        and _sha256(path) == DEMUCS_MODEL_SHA256
    )


def _stage_from_existing_cache(destination: Path) -> bool:
    cached = Path(TORCH_HOME) / "hub" / "checkpoints" / DEMUCS_MODEL_FILE
    if not _is_pinned_file(cached):
        return False
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{DEMUCS_MODEL_FILE}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(cached, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _download(destination: Path) -> None:
    parsed = urllib.parse.urlparse(DEMUCS_MODEL_URL)
    if parsed.scheme != "https" or parsed.hostname != "dl.fbaipublicfiles.com":
        raise RuntimeError("Demucs model manifest contains an unapproved source.")

    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{DEMUCS_MODEL_FILE}.",
        suffix=".download",
        dir=destination.parent,
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        request = urllib.request.Request(
            DEMUCS_MODEL_URL,
            headers={"User-Agent": "HaizFlow offline-model preparation"},
        )
        digest = hashlib.sha256()
        received = 0
        with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
            final_url = urllib.parse.urlparse(response.geturl())
            if final_url.scheme != "https" or final_url.hostname != "dl.fbaipublicfiles.com":
                raise RuntimeError("Demucs model download redirected to an unapproved source.")
            advertised_size = response.headers.get("Content-Length")
            if advertised_size is not None and int(advertised_size) != DEMUCS_MODEL_SIZE:
                raise RuntimeError("Demucs model download size does not match its pinned manifest.")
            with temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > DEMUCS_MODEL_SIZE:
                        raise RuntimeError("Demucs model download exceeded its pinned size.")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        if received != DEMUCS_MODEL_SIZE or digest.hexdigest() != DEMUCS_MODEL_SHA256:
            raise RuntimeError("Demucs model download failed full SHA-256 verification.")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    destination_directory = Path(MODELS_DIR) / "demucs"
    destination_directory.mkdir(parents=True, exist_ok=True)
    destination = destination_directory / DEMUCS_MODEL_FILE

    try:
        verify_demucs_model(destination_directory)
    except Exception:
        destination.unlink(missing_ok=True)
        if not _stage_from_existing_cache(destination):
            _download(destination)
        verify_demucs_model(destination_directory)

    print(f"Pinned Demucs model ready: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
