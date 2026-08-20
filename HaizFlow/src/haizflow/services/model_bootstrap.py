"""Install checksum-pinned model payloads into HaizFlow's portable runtime.

This module is the only production code allowed to download inference models.
Pipeline loaders deliberately remain local-only so a long network transfer can
never begin unexpectedly after the user starts processing a video.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from haizflow.core.model_integrity import (
    ALIGNMENT_MODEL_BASE_URL,
    ALIGNMENT_MODELS,
    DEMUCS_MODEL_FILE,
    DEMUCS_MODEL_SHA256,
    DEMUCS_MODEL_SIZE,
    DEMUCS_MODEL_URL,
    HYMT2_CPU_FILE,
    HYMT2_CPU_REPO,
    HYMT2_CPU_REVISION,
    HYMT2_CPU_SHA256,
    HYMT2_GPU_FILES,
    HYMT2_GPU_REPO,
    HYMT2_GPU_REVISION,
    SUBTITLE_OCR_BASE_URL,
    SUBTITLE_OCR_FILES,
    OMNIVOICE_FILES,
    OMNIVOICE_HUB_FILE,
    OMNIVOICE_HUB_SHA256,
    OMNIVOICE_HUB_SIZE,
    OMNIVOICE_HUB_URL,
    OMNIVOICE_REPO,
    OMNIVOICE_REVISION,
    OMNIVOICE_SDK_FILE,
    OMNIVOICE_SDK_SHA256,
    OMNIVOICE_SDK_SIZE,
    OMNIVOICE_SDK_URL,
    OMNIVOICE_TRANSFORMERS_FILE,
    OMNIVOICE_TRANSFORMERS_SHA256,
    OMNIVOICE_TRANSFORMERS_SIZE,
    OMNIVOICE_TRANSFORMERS_URL,
    WHISPER_FILES,
    WHISPER_REPO,
    WHISPER_REVISION,
    WHISPER_TURBO_FILES,
    WHISPER_TURBO_REPO,
    WHISPER_TURBO_REVISION,
    WHISPERX_VAD_FILE,
    WHISPERX_VAD_SHA256,
    WHISPERX_VAD_SIZE,
    WHISPERX_VAD_URL,
    verify_alignment_models,
    verify_cpu_model,
    verify_demucs_model,
    verify_gpu_model,
    verify_subtitle_ocr_models,
    verify_omnivoice_model,
    verify_omnivoice_sdk,
    verify_whisper_model,
    verify_whisper_turbo_model,
    verify_whisperx_vad_model,
)


DOWNLOAD_HEADROOM_BYTES = 1024**3
DOWNLOAD_CHUNK_BYTES = 4 * 1024 * 1024
DOWNLOAD_RETRIES = 3
DOWNLOAD_TIMEOUT_SECONDS = 60
USER_AGENT = "HaizFlow model bootstrap/1"


class ModelBootstrapError(RuntimeError):
    """The required local model set could not be installed safely."""


class ModelBootstrapCancelled(ModelBootstrapError):
    """The user or application shutdown cancelled model installation."""


@dataclass(frozen=True)
class ModelAsset:
    component: str
    label: str
    url: str
    relative_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelProgress:
    state: str
    component: str
    detail: str
    completed_bytes: int
    total_bytes: int


ProgressCallback = Callable[[ModelProgress], None]


def _hub_url(repo: str, revision: str, filename: str) -> str:
    quoted_filename = urllib.parse.quote(filename, safe="/")
    return f"https://huggingface.co/{repo}/resolve/{revision}/{quoted_filename}?download=true"


def required_assets(device: str) -> tuple[ModelAsset, ...]:
    """Return the first-run payload for the selected processing backend.

    Common speech, separation, and subtitle-alignment models are always
    installed. Only the active HY-MT2 backend is downloaded; switching device
    later invokes this same bootstrap and adds the other backend on demand.
    """
    normalized_device = "gpu" if device == "gpu" else "cpu"
    assets: list[ModelAsset] = [
        ModelAsset(
            "whisper",
            "Whisper speech recognition",
            _hub_url(WHISPER_REPO, WHISPER_REVISION, filename),
            f"whisper/small/{filename}",
            size,
            digest,
        )
        for filename, (size, digest) in WHISPER_FILES.items()
    ]
    assets.append(
        ModelAsset(
            "whisperx-vad",
            "WhisperX voice activity detection",
            WHISPERX_VAD_URL,
            f"whisperx-vad/{WHISPERX_VAD_FILE}",
            WHISPERX_VAD_SIZE,
            WHISPERX_VAD_SHA256,
        )
    )
    if normalized_device == "gpu":
        assets.extend(
            ModelAsset(
                "whisper-turbo",
                "Whisper large-v3-turbo speech recognition",
                _hub_url(WHISPER_TURBO_REPO, WHISPER_TURBO_REVISION, filename),
                f"whisper/large-v3-turbo/{filename}",
                size,
                digest,
            )
            for filename, (size, digest) in WHISPER_TURBO_FILES.items()
        )
        assets.extend(
            ModelAsset(
                "hymt2-gpu",
                "HY-MT2 GPU translation",
                _hub_url(HYMT2_GPU_REPO, HYMT2_GPU_REVISION, filename),
                f"hymt2-transformers/{filename}",
                size,
                digest,
            )
            for filename, (size, digest) in HYMT2_GPU_FILES.items()
        )
    else:
        assets.append(
            ModelAsset(
                "hymt2-cpu",
                "HY-MT2 CPU translation",
                _hub_url(HYMT2_CPU_REPO, HYMT2_CPU_REVISION, HYMT2_CPU_FILE),
                f"hymt2-gguf/{HYMT2_CPU_FILE}",
                1_133_080_448,
                HYMT2_CPU_SHA256,
            )
        )
    assets.append(
        ModelAsset(
            "demucs",
            "Demucs audio separation",
            DEMUCS_MODEL_URL,
            f"demucs/{DEMUCS_MODEL_FILE}",
            DEMUCS_MODEL_SIZE,
            DEMUCS_MODEL_SHA256,
        )
    )
    assets.extend(
        ModelAsset(
            "alignment",
            "Subtitle alignment",
            ALIGNMENT_MODEL_BASE_URL + filename,
            f"alignment/{filename}",
            size,
            digest,
        )
        for _language, (_bundle, filename, size, digest) in ALIGNMENT_MODELS.items()
    )
    ocr_paths = {
        "subtitle-det.onnx": "det/ch_PP-OCRv5_det_mobile.onnx",
        "subtitle-rec.onnx": "rec/ch_PP-OCRv5_rec_mobile.onnx",
        "subtitle-cls.onnx": "cls/ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
    }
    assets.extend(
        ModelAsset(
            "subtitle-ocr",
            "Original subtitle detection",
            SUBTITLE_OCR_BASE_URL + ocr_paths[filename],
            f"subtitle-ocr/{filename}",
            size,
            digest,
        )
        for filename, (size, digest) in SUBTITLE_OCR_FILES.items()
    )
    assets.extend(
        ModelAsset(
            "omnivoice",
            "OmniVoice multilingual local speech",
            _hub_url(OMNIVOICE_REPO, OMNIVOICE_REVISION, filename),
            f"omnivoice/{filename}",
            size,
            digest,
        )
        for filename, (size, digest) in OMNIVOICE_FILES.items()
    )
    assets.append(
        ModelAsset(
            "omnivoice-sdk",
            "OmniVoice local inference runtime",
            OMNIVOICE_SDK_URL,
            f"omnivoice/sdk/{OMNIVOICE_SDK_FILE}",
            OMNIVOICE_SDK_SIZE,
            OMNIVOICE_SDK_SHA256,
        )
    )
    assets.extend(
        (
            ModelAsset(
                "omnivoice-runtime",
                "OmniVoice isolated Transformers runtime",
                OMNIVOICE_TRANSFORMERS_URL,
                f"omnivoice/sdk/{OMNIVOICE_TRANSFORMERS_FILE}",
                OMNIVOICE_TRANSFORMERS_SIZE,
                OMNIVOICE_TRANSFORMERS_SHA256,
            ),
            ModelAsset(
                "omnivoice-runtime",
                "OmniVoice isolated model hub runtime",
                OMNIVOICE_HUB_URL,
                f"omnivoice/sdk/{OMNIVOICE_HUB_FILE}",
                OMNIVOICE_HUB_SIZE,
                OMNIVOICE_HUB_SHA256,
            ),
        )
    )
    return tuple(assets)


def required_download_bytes(device: str) -> int:
    return sum(asset.size for asset in required_assets(device))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_is_valid(path: Path, asset: ModelAsset) -> bool:
    try:
        return path.is_file() and path.stat().st_size == asset.size and _sha256(path) == asset.sha256
    except OSError:
        return False


def _prepare_partial(destination: Path, asset: ModelAsset) -> int:
    """Return a safe resumable offset, promoting a complete verified part."""
    partial = destination.with_name(destination.name + ".part")
    try:
        partial_size = partial.stat().st_size
    except FileNotFoundError:
        return 0
    except OSError:
        partial.unlink(missing_ok=True)
        return 0

    if partial_size > asset.size:
        partial.unlink(missing_ok=True)
        return 0
    if partial_size == asset.size:
        if _sha256(partial) == asset.sha256:
            os.replace(partial, destination)
            return asset.size
        partial.unlink(missing_ok=True)
        return 0
    return partial_size


def _approved_download_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme.lower() == "https" and (
        host == "huggingface.co"
        or host.endswith(".huggingface.co")
        or host.endswith(".hf.co")
        or host == "raw.githubusercontent.com"
        or host == "download.pytorch.org"
        or host == "dl.fbaipublicfiles.com"
        or host == "modelscope.cn"
        or host.endswith(".modelscope.cn")
        or host == "files.pythonhosted.org"
    )


def _check_cancelled(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ModelBootstrapCancelled("Model download was cancelled.")


def _open_download(asset: ModelAsset, offset: int):
    headers = {"User-Agent": USER_AGENT}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(asset.url, headers=headers)
    response = urllib.request.urlopen(  # nosec B310 - URL and redirect are validated below.
        request,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
    )
    if not _approved_download_url(response.geturl()):
        response.close()
        raise ModelBootstrapError("Model download redirected to an unapproved host.")
    return response


def _download_asset(
    root: Path,
    asset: ModelAsset,
    *,
    base_completed: int,
    total_bytes: int,
    progress: ProgressCallback,
    cancel_event,
) -> None:
    destination = root / Path(asset.relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _asset_is_valid(destination, asset):
        progress(
            ModelProgress(
                "downloading",
                asset.label,
                f"{asset.label} is already available",
                base_completed + asset.size,
                total_bytes,
            )
        )
        return
    if destination.exists():
        destination.unlink(missing_ok=True)

    partial = destination.with_name(destination.name + ".part")
    if _prepare_partial(destination, asset) == asset.size:
        progress(
            ModelProgress(
                "downloading",
                asset.label,
                f"{asset.label} is already available",
                base_completed + asset.size,
                total_bytes,
            )
        )
        return

    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        _check_cancelled(cancel_event)
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            with _open_download(asset, offset) as response:
                status = getattr(response, "status", response.getcode())
                resume = offset > 0 and status == 206
                if offset and not resume:
                    offset = 0
                mode = "ab" if resume else "wb"
                advertised = response.headers.get("Content-Length")
                expected_response_size = asset.size - offset
                if advertised is not None and int(advertised) != expected_response_size:
                    raise ModelBootstrapError(f"{asset.label} returned an unexpected download size.")
                written = offset
                with partial.open(mode) as output:
                    while True:
                        _check_cancelled(cancel_event)
                        chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > asset.size:
                            raise ModelBootstrapError(f"{asset.label} exceeded its pinned size.")
                        output.write(chunk)
                        progress(
                            ModelProgress(
                                "downloading",
                                asset.label,
                                f"Downloading {asset.label}",
                                base_completed + written,
                                total_bytes,
                            )
                        )
                    output.flush()
                    os.fsync(output.fileno())
            if partial.stat().st_size != asset.size:
                raise ModelBootstrapError(f"{asset.label} download ended before the expected size.")
            progress(
                ModelProgress(
                    "verifying",
                    asset.label,
                    f"Verifying {asset.label}",
                    base_completed + asset.size,
                    total_bytes,
                )
            )
            if _sha256(partial) != asset.sha256:
                partial.unlink(missing_ok=True)
                raise ModelBootstrapError(f"{asset.label} failed SHA-256 verification.")
            os.replace(partial, destination)
            return
        except ModelBootstrapCancelled:
            # Pausing is intentionally resumable. The final destination is
            # still untouched until the complete payload passes SHA-256.
            raise
        except (OSError, ValueError, urllib.error.URLError, ModelBootstrapError) as exc:
            last_error = exc
            if attempt == DOWNLOAD_RETRIES:
                break
            _check_cancelled(cancel_event)
            time.sleep(min(2**attempt, 5))
    raise ModelBootstrapError(
        f"Could not download {asset.label} after {DOWNLOAD_RETRIES} attempts: {last_error}"
    ) from last_error


def _verify_installed_components(root: Path, device: str) -> None:
    verify_whisper_model(root / "whisper" / "small")
    if device == "gpu":
        verify_whisper_turbo_model(root / "whisper" / "large-v3-turbo")
    verify_whisperx_vad_model(root / "whisperx-vad")
    if device == "gpu":
        verify_gpu_model(root / "hymt2-transformers")
    else:
        verify_cpu_model(root / "hymt2-gguf" / HYMT2_CPU_FILE)
    verify_demucs_model(root / "demucs")
    verify_alignment_models(root / "alignment")
    verify_subtitle_ocr_models(root / "subtitle-ocr")
    verify_omnivoice_model(root / "omnivoice")
    verify_omnivoice_sdk(root / "omnivoice")


def models_ready(root: Path, device: str) -> bool:
    try:
        _verify_installed_components(root.expanduser().resolve(), "gpu" if device == "gpu" else "cpu")
        return True
    except (OSError, RuntimeError):
        return False


def install_required_models(
    root: Path,
    device: str,
    *,
    progress: ProgressCallback,
    cancel_event=None,
) -> Path:
    """Install and verify the selected first-run model set."""
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    normalized_device = "gpu" if device == "gpu" else "cpu"
    assets = required_assets(normalized_device)
    total_bytes = sum(asset.size for asset in assets)
    progress(ModelProgress("checking", "", "Checking installed models", 0, total_bytes))

    valid: set[str] = set()
    completed = 0
    for asset in assets:
        _check_cancelled(cancel_event)
        if _asset_is_valid(root / Path(asset.relative_path), asset):
            valid.add(asset.relative_path)
            completed += asset.size
        progress(
            ModelProgress(
                "checking",
                asset.label,
                f"Checking {asset.label}",
                completed,
                total_bytes,
            )
        )

    missing_bytes = 0
    for asset in assets:
        if asset.relative_path in valid:
            continue
        destination = root / Path(asset.relative_path)
        resumable_bytes = _prepare_partial(destination, asset)
        if resumable_bytes == asset.size and _asset_is_valid(destination, asset):
            valid.add(asset.relative_path)
            completed += asset.size
            continue
        missing_bytes += asset.size - resumable_bytes
    required_free = missing_bytes + DOWNLOAD_HEADROOM_BYTES
    if missing_bytes and shutil.disk_usage(root).free < required_free:
        required_gib = required_free / 1024**3
        available_gib = shutil.disk_usage(root).free / 1024**3
        raise ModelBootstrapError(
            f"Not enough free space for models. Required {required_gib:.1f} GiB; "
            f"available {available_gib:.1f} GiB in {root}."
        )

    for asset in assets:
        _check_cancelled(cancel_event)
        if asset.relative_path in valid:
            continue
        _download_asset(
            root,
            asset,
            base_completed=completed,
            total_bytes=total_bytes,
            progress=progress,
            cancel_event=cancel_event,
        )
        completed += asset.size

    _check_cancelled(cancel_event)
    progress(
        ModelProgress(
            "verifying",
            "",
            "Verifying the complete model set",
            total_bytes,
            total_bytes,
        )
    )
    _verify_installed_components(root, normalized_device)
    progress(ModelProgress("ready", "", "Models are ready", total_bytes, total_bytes))
    return root


def model_payload_paths(root: Path, device: str) -> Iterable[Path]:
    """Expose the pinned expected paths for diagnostics and tests."""
    return tuple(root / Path(asset.relative_path) for asset in required_assets(device))
