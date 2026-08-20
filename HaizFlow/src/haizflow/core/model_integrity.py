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
WHISPER_TURBO_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
WHISPER_TURBO_REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"
WHISPERX_VAD_REVISION = "3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0"
WHISPERX_VAD_FILE = "pytorch_model.bin"
WHISPERX_VAD_URL = (
    f"https://raw.githubusercontent.com/m-bain/whisperX/{WHISPERX_VAD_REVISION}/whisperx/assets/{WHISPERX_VAD_FILE}"
)
WHISPERX_VAD_SIZE = 17_719_103
WHISPERX_VAD_SHA256 = "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
DEMUCS_MODEL_SIGNATURE = "955717e8"
DEMUCS_MODEL_FILE = "955717e8-8726e21a.th"
DEMUCS_MODEL_URL = "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th"
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
# OmniVoice is the multilingual local TTS backend.  The complete checkpoint is
# pinned because model loaders are deliberately offline after first-run setup.
OMNIVOICE_REPO = "k2-fsa/OmniVoice"
OMNIVOICE_REVISION = "c5fdb5ccb189668d56333f77ba2629f4cd7535f4"
OMNIVOICE_SDK_VERSION = "0.2.1"
OMNIVOICE_SDK_FILE = f"omnivoice-{OMNIVOICE_SDK_VERSION}-py3-none-any.whl"
OMNIVOICE_SDK_URL = (
    "https://files.pythonhosted.org/packages/63/68/"
    "862ac66ab83a28e43400c8bf608ac5f1d6d16a0b583540d8bd9d4297b663/" + OMNIVOICE_SDK_FILE
)
OMNIVOICE_SDK_SIZE = 168_460
OMNIVOICE_SDK_SHA256 = "23f113ef51116a16308b55c4c2ac9c08efca7dfb594802f5c8adfb7523313ccc"
OMNIVOICE_TRANSFORMERS_FILE = "transformers-5.3.0-py3-none-any.whl"
OMNIVOICE_TRANSFORMERS_URL = (
    "https://files.pythonhosted.org/packages/b8/88/"
    "ae8320064e32679a5429a2c9ebbc05c2bf32cefb6e076f9b07f6d685a9b4/" + OMNIVOICE_TRANSFORMERS_FILE
)
OMNIVOICE_TRANSFORMERS_SIZE = 10_661_827
OMNIVOICE_TRANSFORMERS_SHA256 = "50ac8c89c3c7033444fb3f9f53138096b997ebb70d4b5e50a2e810bf12d3d29a"
OMNIVOICE_HUB_FILE = "huggingface_hub-1.3.0-py3-none-any.whl"
OMNIVOICE_HUB_URL = (
    "https://files.pythonhosted.org/packages/b1/5b/"
    "c5fde1f56b1f072b3028ec5413f3f5bf472c5891ebb34589cddb1689609f/" + OMNIVOICE_HUB_FILE
)
OMNIVOICE_HUB_SIZE = 533_092
OMNIVOICE_HUB_SHA256 = "763f450169bb05ea3867990e9d3ba9464eb617b874791301dc81be2c6ffb0bf5"
OMNIVOICE_RUNTIME_FILES = {
    OMNIVOICE_SDK_FILE: (OMNIVOICE_SDK_SIZE, OMNIVOICE_SDK_SHA256),
    OMNIVOICE_TRANSFORMERS_FILE: (
        OMNIVOICE_TRANSFORMERS_SIZE,
        OMNIVOICE_TRANSFORMERS_SHA256,
    ),
    OMNIVOICE_HUB_FILE: (OMNIVOICE_HUB_SIZE, OMNIVOICE_HUB_SHA256),
}
OMNIVOICE_FILES = {
    "audio_tokenizer/config.json": (2_531, "eefb20806f7104e77c9a5277c9df0f9bb8826b08eb1d4e8ab2b9829b6ef9fac1"),
    "audio_tokenizer/model.safetensors": (
        805_665_628,
        "fe7c5e8785e0a05833e1bfc3e002ec7f55af21e306b2e7154a448c1f54ccfb0d",
    ),
    "audio_tokenizer/preprocessor_config.json": (
        206,
        "ae61eea88558608ee2fa86d2aec9fce8d99a5ff75d09cb7651ccce21ae1d9084",
    ),
    "chat_template.jinja": (4_168, "a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8"),
    "config.json": (2_238, "5e359117e13b420c5e0c925d4aba650d624767131f1d1746928f8b850d5dc372"),
    "model.safetensors": (2_450_344_112, "730839316de585f4c8298ec0e1712efc10fb19c6fa4e36eb741cb8d51ebcf6aa"),
    "tokenizer.json": (11_423_986, "408f669b7e2b045fdf54201d815bd364e6667dbd845115da81239c40bc6dcfd1"),
    "tokenizer_config.json": (533, "49f78845596a82bf15c83673794bdf9f76f812b11f60ab6a2239d9be65b00676"),
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
WHISPER_TURBO_FILES = {
    "config.json": (2_263, "b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e"),
    "model.bin": (1_617_884_929, "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da"),
    "preprocessor_config.json": (340, "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711"),
    "tokenizer.json": (2_710_337, "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd"),
    "vocabulary.json": (1_068_114, "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1"),
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


def verify_whisper_turbo_model(model_directory: Path) -> Path:
    return _verify(
        model_directory,
        kind="Whisper large-v3-turbo",
        revision=WHISPER_TURBO_REVISION,
        expected=WHISPER_TURBO_FILES,
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


def verify_omnivoice_model(model_directory: Path) -> Path:
    return _verify(
        model_directory,
        kind="OmniVoice multilingual TTS",
        revision=OMNIVOICE_REVISION,
        expected=OMNIVOICE_FILES,
        marker_name=".haizflow-omnivoice-integrity.json",
    )


def verify_omnivoice_sdk(model_directory: Path) -> Path:
    sdk_directory = model_directory / "sdk"
    root = _verify(
        sdk_directory,
        kind="OmniVoice SDK",
        revision=f"{OMNIVOICE_SDK_VERSION}-transformers-5.3.0-hub-1.3.0",
        expected=OMNIVOICE_RUNTIME_FILES,
        marker_name=".haizflow-omnivoice-sdk-integrity.json",
    )
    return root / OMNIVOICE_SDK_FILE


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
        filename: (size, digest) for _language, (_bundle_name, filename, size, digest) in ALIGNMENT_MODELS.items()
    }
    revision = _manifest_id("torchaudio alignment bundle", "1", expected)
    return _verify(
        model_directory,
        kind="torchaudio alignment bundle",
        revision=revision,
        expected=expected,
        marker_name=".haizflow-alignment-integrity.json",
    )
