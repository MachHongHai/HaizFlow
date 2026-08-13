"""Pinned model revisions and local integrity verification."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


HYMT2_GPU_REPO = "tencent/Hy-MT2-1.8B"
HYMT2_GPU_REVISION = "9a341cd1b679d3efd23b46e847b01745a71ed792"
HYMT2_CPU_REPO = "tencent/Hy-MT2-1.8B-GGUF"
HYMT2_CPU_REVISION = "1cd5208700acedef4ef93019b6cfc148b8522d45"
HYMT2_CPU_FILE = "Hy-MT2-1.8B-Q4_K_M.gguf"
HYMT2_CPU_SHA256 = "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699"
WHISPER_REPO = "Systran/faster-whisper-small"
WHISPER_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
WHISPERX_VAD_REVISION = "3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0"
WHISPERX_VAD_FILE = "pytorch_model.bin"
WHISPERX_VAD_URL = (
    "https://raw.githubusercontent.com/m-bain/whisperX/"
    f"{WHISPERX_VAD_REVISION}/whisperx/assets/{WHISPERX_VAD_FILE}"
)
WHISPERX_VAD_SIZE = 17_719_103
WHISPERX_VAD_SHA256 = "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
DEMUCS_MODEL_SIGNATURE = "955717e8"
DEMUCS_MODEL_FILE = "955717e8-8726e21a.th"
DEMUCS_MODEL_URL = (
    "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/"
    "955717e8-8726e21a.th"
)
DEMUCS_MODEL_SIZE = 84_141_911
DEMUCS_MODEL_SHA256 = "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
# PP-OCRv5 Mobile is intentionally external to the frozen application.  The
# small ONNX bundle is checksum-pinned and fetched once by model_bootstrap.
SUBTITLE_OCR_REVISION = "rapidocr-v3.8.0-pp-ocrv5-chinese-mobile"
SUBTITLE_OCR_BASE_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/onnx/PP-OCRv5/"
SUBTITLE_OCR_FILES = {
    "subtitle-det.onnx": (4_819_576, "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae"),
    # Use the Chinese/English recognizer rather than the Latin-only model.
    # Subtitle removal needs reliable text identity (not just polygons) to
    # distinguish changing CJK captions from a moving creator watermark.
    "subtitle-rec.onnx": (16_631_306, "5825fc7ebf84ae7a412be049820b4d86d77620f204a041697b0494669b1742c5"),
    "subtitle-cls.onnx": (1_018_508, "54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7"),
}
# VieNeu v3 Turbo is the recommended local Vietnamese TTS backend. Only the
# preset-voice ONNX INT8 payload is installed; voice-cloning weights are not
# needed by HaizFlow and would add avoidable disk and startup cost.
VIENEU_MODEL_REPO = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
VIENEU_MODEL_REVISION = "75ff82a72f54d55ed389e1eeb12041d3c4bac7d4"
VIENEU_SDK_VERSION = "3.2.5"
VIENEU_SDK_FILE = "vieneu-3.2.5-py3-none-any.whl"
VIENEU_SDK_URL = (
    "https://files.pythonhosted.org/packages/ff/02/"
    "41b67c880d1fbe54dec79c06450c1cfd37369c4465f74d023c4095af8e49/"
    + VIENEU_SDK_FILE
)
VIENEU_SDK_SIZE = 1_162_151
VIENEU_SDK_SHA256 = "a37474eaeb3e1da523f2ff5eaf76da8b339840afe6cb775205dfc2fae0397b68"
VIENEU_MODEL_FILES = {
    "config.json": (2_152, "a9f8d9c4b4736448ab355d1a98cfe48f5e39aecf2916c37b0806c228612e9a2d"),
    "tokenizer.json": (22_320, "6cc6bcbe380b8c37bd9f2514e37c5dfa3e00e122c6e3125dae5c4afe48e39158"),
    "vieneu_acoustic_cached.onnx": (7_207_223, "0be6575ffe1c4c2009edb9c9b218c235f09665f630d1840e63c74bef30d462c1"),
    "vieneu_backbone_shared.data": (103_891_968, "68c0bd5e75f9cf2d557040201f5465dc03a61206813845f2de1ebe6542652b92"),
    "vieneu_decode_step.onnx": (1_062_040, "7907f8e067de22ee88f0912ffc8ccaf7cf90025e1d41351d2a5bb7cec44fc859"),
    "vieneu_prefill.onnx": (1_090_823, "9d04bd8023c5a003dd60939848bba7e85c5d8448480e607a9ae7aa3ecd6d7494"),
    "vieneu_v3_heads.npz": (52_219_622, "c2eadeb5b0b85c3009270352adea8c05a72f31c5a9f189ead9184333fb1becb8"),
}
VIENEU_CODEC_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"
VIENEU_CODEC_REVISION = "ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae"
VIENEU_CODEC_FILES = {
    "codec_browser_onnx_meta.json": (17_036, "3e291c883bb7d11ff2fe8e964e3e495519760358859f35c951254c7741592731"),
    "moss_audio_tokenizer_decode_full.onnx": (681_902, "0fbbafe3fd4afa2a019af5c5ced204af6e2d1db044fa40f021525d2aee95b4ac"),
    "moss_audio_tokenizer_decode_shared.data": (44_198_912, "e69d52e0f4e84ca27850557ee54face46632d3a5a16c89bd246c7c408466dcad"),
    "moss_audio_tokenizer_decode_step.onnx": (351_400, "9527c86a29e1837edec1f74db57d5eeaadb3a715af3382703566460afed25855"),
    "moss_audio_tokenizer_encode.data": (44_507_136, "aa751265b2bab2887eac224484546b194875aa7494b607115439b3dc6b228a2c"),
    "moss_audio_tokenizer_encode.onnx": (815_775, "eadea4a645abdcf98714c7aead122ee2ce7da6e080f9f80b977cd1ca8e19473a"),
}
ALIGNMENT_MODEL_BASE_URL = "https://download.pytorch.org/torchaudio/models/"
ALIGNMENT_MODELS = {
    "en": (
        "WAV2VEC2_ASR_BASE_960H",
        "wav2vec2_fairseq_base_ls960_asr_ls960.pth",
        377_664_473,
        "488fd4f16de84438ffc945334278c1b9fb9b7159a806c1080b16111a958c945d",
    ),
    "fr": (
        "VOXPOPULI_ASR_BASE_10K_FR",
        "wav2vec2_voxpopuli_base_10k_asr_fr.pt",
        377_708_313,
        "30eeb5e5000e011838a39328c21eadf5ddaedbef0ea3f7cf5a790fd8695b92b5",
    ),
    "de": (
        "VOXPOPULI_ASR_BASE_10K_DE",
        "wav2vec2_voxpopuli_base_10k_asr_de.pt",
        377_677_593,
        "5fcd937817d4cc358aa9730ccaa92cdae37af4b62959b67ba77ef1f5da7938cf",
    ),
    "es": (
        "VOXPOPULI_ASR_BASE_10K_ES",
        "wav2vec2_voxpopuli_base_10k_asr_es.pt",
        377_686_809,
        "272a92b156b78e697e6c7cf7c64f274250a36d0047440e27a895a377d3af818f",
    ),
    "it": (
        "VOXPOPULI_ASR_BASE_10K_IT",
        "wav2vec2_voxpopuli_base_10k_asr_it.pt",
        377_689_881,
        "620bad579ee46ba1f67df2e7c858c111d14a09b349a62b1c672f0275a68484eb",
    ),
}

WHISPER_FILES = {
    "config.json": (2370, "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828"),
    "model.bin": (483546902, "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
    "tokenizer.json": (2203239, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
    "vocabulary.txt": (459861, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913"),
}

HYMT2_GPU_FILES = {
    "chat_template.jinja": (654, "b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee"),
    "config.json": (1348, "da40c514cc74a5748a2e591b1b95fca4b7e94de05349abe4ea4164a82641de1a"),
    "generation_config.json": (221, "0e28667f1cb4c7b880b9223b2d87978f88e79ed7ae037de1021f826c18d4ed6f"),
    "model.safetensors": (4077072784, "29e9117a44c79f81857613601968ff482d8a23c2d6736a1710bba9e5ca4762e5"),
    "special_tokens_map.json": (488, "bb9f59990034dae326581b9c62471523975417869f78a244b7ae2ce8cbb085eb"),
    "tokenizer.json": (9527287, "b475bbef1b0b2fd57dcb865332b546475bd1ede2deb3bb91bafd0c047a8a530a"),
    "tokenizer_config.json": (165815, "53bd8581b601a8ee9caefeb988207de50b3fc0b733295bdf5ad68dec4cc0b07c"),
}

MARKER_NAME = ".haizflow-model-integrity.json"
MARKER_VERSION = 3
QUICK_SAMPLE_BYTES = 64 * 1024


class ModelIntegrityError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_id(kind: str, revision: str, files: dict[str, tuple[int, str]]) -> str:
    payload = json.dumps(
        {"kind": kind, "revision": revision, "files": files},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _quick_fingerprint(path: Path) -> str:
    """Detect same-size rewrites without hashing multi-gigabyte weights again."""
    size = path.stat().st_size
    offsets = {0, max(0, size // 2 - QUICK_SAMPLE_BYTES // 2), max(0, size - QUICK_SAMPLE_BYTES)}
    digest = hashlib.blake2b(digest_size=16)
    with path.open("rb") as file:
        for offset in sorted(offsets):
            file.seek(offset)
            digest.update(offset.to_bytes(8, "little"))
            digest.update(file.read(QUICK_SAMPLE_BYTES))
    return digest.hexdigest()


def _state(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "sample": _quick_fingerprint(path),
    }


def _marker_is_current(marker_path: Path, manifest_id: str, files: dict[str, Path]) -> bool:
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("version") != MARKER_VERSION or marker.get("manifest_id") != manifest_id:
            return False
        recorded = marker.get("files") or {}
        return all(recorded.get(name) == _state(path) for name, path in files.items())
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _write_marker(marker_path: Path, manifest_id: str, files: dict[str, Path]) -> None:
    payload = {
        "version": MARKER_VERSION,
        "manifest_id": manifest_id,
        "files": {name: _state(path) for name, path in files.items()},
    }
    temporary = marker_path.with_name(f"{marker_path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, marker_path)
    except OSError:
        temporary.unlink(missing_ok=True)


def _verify(
    root: Path,
    *,
    kind: str,
    revision: str,
    expected: dict[str, tuple[int, str]],
    marker_name: str = MARKER_NAME,
) -> Path:
    root = root.expanduser().resolve()
    files = {name: root / name for name in expected}
    for name, path in files.items():
        expected_size, _expected_hash = expected[name]
        if not path.is_file() or path.stat().st_size != expected_size:
            raise ModelIntegrityError(f"{kind} file is missing or has the wrong size: {path}")

    manifest_id = _manifest_id(kind, revision, expected)
    marker_path = root / marker_name
    if _marker_is_current(marker_path, manifest_id, files):
        return root

    for name, path in files.items():
        _expected_size, expected_hash = expected[name]
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise ModelIntegrityError(
                f"{kind} checksum mismatch for {name}: expected {expected_hash}, got {actual_hash}"
            )
    _write_marker(marker_path, manifest_id, files)
    return root


def verify_cpu_model(model_path: Path) -> Path:
    model_path = model_path.expanduser().resolve()
    _verify(
        model_path.parent,
        kind="cpu",
        revision=HYMT2_CPU_REVISION,
        expected={HYMT2_CPU_FILE: (1133080448, HYMT2_CPU_SHA256)},
    )
    return model_path


def verify_gpu_model(model_directory: Path) -> Path:
    return _verify(
        model_directory,
        kind="gpu",
        revision=HYMT2_GPU_REVISION,
        expected=HYMT2_GPU_FILES,
    )


def verify_whisper_model(model_directory: Path) -> Path:
    return _verify(
        model_directory,
        kind="Whisper small",
        revision=WHISPER_REVISION,
        expected=WHISPER_FILES,
    )


def verify_whisperx_vad_model(model_directory: Path) -> Path:
    root = _verify(
        model_directory,
        kind="WhisperX VAD",
        revision=WHISPERX_VAD_REVISION,
        expected={WHISPERX_VAD_FILE: (WHISPERX_VAD_SIZE, WHISPERX_VAD_SHA256)},
    )
    return root / WHISPERX_VAD_FILE


def verify_demucs_model(model_directory: Path) -> Path:
    return _verify(
        model_directory,
        kind="Demucs htdemucs",
        revision=DEMUCS_MODEL_SHA256,
        expected={DEMUCS_MODEL_FILE: (DEMUCS_MODEL_SIZE, DEMUCS_MODEL_SHA256)},
    )


def verify_subtitle_ocr_models(model_directory: Path) -> Path:
    """Verify the lightweight, local-only OCR bundle used for subtitle detection."""
    return _verify(
        model_directory,
        kind="subtitle OCR",
        revision=SUBTITLE_OCR_REVISION,
        expected=SUBTITLE_OCR_FILES,
        marker_name=".haizflow-subtitle-ocr-integrity.json",
    )


def verify_vieneu_models(model_directory: Path) -> tuple[Path, Path]:
    model_root = _verify(
        model_directory / "v3-turbo" / "onnx_int8",
        kind="VieNeu v3 Turbo ONNX INT8",
        revision=VIENEU_MODEL_REVISION,
        expected=VIENEU_MODEL_FILES,
        marker_name=".haizflow-vieneu-model-integrity.json",
    )
    codec_root = _verify(
        model_directory / "codec",
        kind="VieNeu MOSS audio codec",
        revision=VIENEU_CODEC_REVISION,
        expected=VIENEU_CODEC_FILES,
        marker_name=".haizflow-vieneu-codec-integrity.json",
    )
    return model_root, codec_root


def verify_vieneu_sdk(model_directory: Path) -> Path:
    root = _verify(
        model_directory / "sdk",
        kind=f"VieNeu SDK {VIENEU_SDK_VERSION}",
        revision=VIENEU_SDK_SHA256,
        expected={VIENEU_SDK_FILE: (VIENEU_SDK_SIZE, VIENEU_SDK_SHA256)},
        marker_name=".haizflow-vieneu-sdk-integrity.json",
    )
    return root / VIENEU_SDK_FILE


def verify_alignment_model(model_directory: Path, language: str) -> Path:
    try:
        _bundle_name, filename, size, digest = ALIGNMENT_MODELS[language]
    except KeyError as exc:
        raise ModelIntegrityError(f"Unsupported alignment-model language: {language}") from exc
    root = _verify(
        model_directory,
        kind=f"torchaudio alignment {language}",
        revision=digest,
        expected={filename: (size, digest)},
        marker_name=f".haizflow-alignment-{language}-integrity.json",
    )
    return root / filename


def verify_alignment_models(model_directory: Path) -> Path:
    expected = {
        filename: (size, digest)
        for _language, (_bundle_name, filename, size, digest) in ALIGNMENT_MODELS.items()
    }
    revision = _manifest_id("torchaudio alignment bundle", "1", expected)
    return _verify(
        model_directory,
        kind="torchaudio alignment bundle",
        revision=revision,
        expected=expected,
        marker_name=".haizflow-alignment-integrity.json",
    )
