"""Offline VieNeu CPU/CUDA synthesis in a cancellable, isolated process.

The GUI imports only stdlib here. No pip, Hub download, Torch or ONNX loading
occurs in Core; the checked resource pack supplies SDK/phonemizer/models.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from pathlib import Path

from haizflow.core.vieneu_assets import CACHE_VERSION, MANIFEST
from haizflow.core.vieneu_voices import native_voice

_PREPARE_LOCK = threading.Lock()


def verify_assets(root: Path, device: str = "") -> Path:
    from haizflow.core.model_integrity import _verify

    selected = {}
    for item in MANIFEST["assets"]:
        path = item["path"]
        if device == "cpu" and (path.startswith(("codec-gpu/", "v3-turbo/update/"))):
            continue
        if device == "gpu" and path.startswith(("codec/", "v3-turbo/onnx_update/")):
            continue
        selected[path] = (item["size"], item["sha256"])
    return _verify(root, kind="VieNeu", revision=CACHE_VERSION, expected=selected,
                   marker_name=f".haizflow-vieneu-{device or 'all'}-integrity.json")


def prepare_runtime(root: Path) -> Path:
    """Extract versioned wheels atomically, without changing other backends."""
    from haizflow.core.model_integrity import _verify

    wheels = {item["path"]: (item["size"], item["sha256"])
              for item in MANIFEST["assets"] if item["path"].startswith("sdk/")}
    _verify(root, kind="VieNeu SDK", revision=CACHE_VERSION, expected=wheels,
            marker_name=".haizflow-vieneu-sdk-v383-integrity.json")
    destination = root / "sdk" / ("runtime-" + MANIFEST["sdk_version"])
    with _PREPARE_LOCK:
        marker = destination / ".ready"
        required = ("vieneu/__init__.py", "vieneu/v3turbo.py", "vieneu/assets/voices_v3_turbo.json",
                    "sea_g2p/__init__.py", "sea_g2p/sea_g2p_rs.pyd", "kaldi_native_fbank/__init__.py",
                    "_kaldi_native_fbank.cp313-win_amd64.pyd", "kaldi-native-fbank-core.dll")
        if (marker.is_file() and marker.read_text(encoding="ascii") == CACHE_VERSION
                and all((destination / name).is_file() for name in required)):
            return destination
        with tempfile.TemporaryDirectory(prefix="vieneu-sdk-", dir=root / "sdk") as work:
            staging = Path(work) / "site-packages"
            staging.mkdir()
            for filename in wheels:
                with zipfile.ZipFile(root / filename) as archive:
                    for member in archive.infolist():
                        relative = Path(member.filename)
                        if relative.is_absolute() or ".." in relative.parts:
                            raise RuntimeError("Gói VieNeu chứa đường dẫn không an toàn.")
                        if not member.is_dir():
                            target = staging / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with archive.open(member) as source, target.open("wb") as output:
                                shutil.copyfileobj(source, output)
            (staging / ".ready").write_text(CACHE_VERSION, encoding="ascii")
            if not all((staging / name).is_file() for name in required):
                raise RuntimeError("Gói SDK VieNeu chưa đầy đủ.")
            if destination.exists():
                # A damaged unpacked runtime is not a valid installed SDK.
                # Keep its recoverable copy inside this specific SDK directory.
                backup = destination.with_name(destination.name + f"-old-{time.time_ns()}")
                os.replace(destination, backup)
            os.replace(staging, destination)
    return destination


def worker_command(request_path: Path, device: str) -> list[str]:
    from haizflow.services.resource_packs import installed_engine_command

    command = installed_engine_command("voice", "vieneu_worker",
                                       {"provider": "vieneu-gpu" if device == "gpu" else "vieneu"})
    if command:
        return [*command, str(request_path)]
    if getattr(sys, "frozen", False):
        # Core intentionally does not include Torch or the phonemizer ABI.
        raise RuntimeError("Cần cập nhật gói Bộ xử lý CPU/GPU để chạy VieNeu.")
    # A source Core checkout may use .venv-core. Reuse the repository's AI
    # development interpreter without importing/installing AI into Core.
    development_python = Path(__file__).resolve().parents[3] / ".venv" / "Scripts" / "python.exe"
    interpreter = str(development_python) if development_python.is_file() else sys.executable
    return [interpreter, "-m", "haizflow.pipeline.vieneu_tts", str(request_path)]


def synthesize_batch_to_mp3(items, video_id, *, device="cpu", language_id="vi",
                            process_registry_id=None, progress_callback=None, **_unused):
    from haizflow.config import MODELS_DIR, TMP_DIR
    from haizflow.core.model_integrity import observe_verification
    from haizflow.pipeline.omnivoice_tts import _encode_mp3, _synthesis_stall_timeout
    from haizflow.pipeline.process_registry import check_cancellation, communicate_process
    from haizflow.services.video_store import log_to_video

    from haizflow.core.vieneu_voices import han_text_notice, unsupported_language_notice

    notice = han_text_notice(items)
    if notice:
        raise ValueError(notice[1])
    notice = unsupported_language_notice("vieneu", language_id)
    if notice:
        raise ValueError(notice[1])
    if device not in {"cpu", "gpu"}:
        raise ValueError(f"Thiết bị VieNeu không hợp lệ: {device}")
    for item in items:
        if item["voice"] == "vieneu:clone":
            reference = Path(str(item.get("reference_path") or ""))
            if not reference.is_file() or reference.stat().st_size <= 0:
                raise ValueError("Nhân bản giọng VieNeu cần mẫu giọng được phép sử dụng, không dùng giọng mặc định.")
        else:
            native_voice(item["voice"])
        if not str(item.get("text") or "").strip():
            raise ValueError("Không thể tạo giọng VieNeu cho câu trống.")
    if not items:
        return
    cancellation_id = process_registry_id or video_id
    check_cancellation(cancellation_id)
    if progress_callback:
        progress_callback(0, len(items), "verifying_runtime")
    with observe_verification(lambda *_: check_cancellation(cancellation_id)):
        root = verify_assets(Path(MODELS_DIR) / "vieneu", device)
        site = prepare_runtime(root)
    Path(TMP_DIR).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vieneu-", dir=TMP_DIR) as work:
        work = Path(work)
        entries = [{**item, "wav": str(work / f"{index}.wav")} for index, item in enumerate(items)]
        from haizflow.utils.ffmpeg import _binary

        references = {}
        for item in entries:
            if item["voice"] != "vieneu:clone":
                continue
            source = str(Path(item["reference_path"]).resolve())
            if source not in references:
                target = work / f"reference-{len(references)}.wav"
                decoder = subprocess.Popen([_binary("ffmpeg"), "-y", "-v", "error", "-i", source,
                    "-t", "8", "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(target)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                _stdout, error = communicate_process(cancellation_id, decoder, label="VieNeu reference decoding",
                                                     timeout_seconds=60)
                if decoder.returncode or not target.is_file() or target.stat().st_size <= 44:
                    raise ValueError("Không đọc được mẫu nhân bản giọng VieNeu: " + str(error or "audio trống")[-400:])
                references[source] = str(target)
            item["reference_path"] = references[source]
        status_path = work / "status.json"
        request = dict(root=str(root), site=str(site), device=device, items=entries, status=str(status_path))
        request_path = work / "request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        environment = os.environ.copy()
        environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONUTF8="1",
                           PYTHONUNBUFFERED="1", TOKENIZERS_PARALLELISM="false")
        source_root = str(Path(__file__).resolve().parents[2])
        environment["PYTHONPATH"] = source_root + os.pathsep + environment.get("PYTHONPATH", "")
        process = subprocess.Popen(worker_command(request_path, device), env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        stop = threading.Event()
        monitor_errors = []
        published = []
        stall_timeout = _synthesis_stall_timeout({"device": "cuda:0" if device == "gpu" else "cpu"})

        def publish_status():
            last = None
            last_activity = time.monotonic()
            while not stop.wait(.3):
                try:
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    status = None
                if not isinstance(status, dict):
                    status = None
                try:
                    check_cancellation(cancellation_id)
                    if status is not None:
                        if status.get("policy") != CACHE_VERSION or status.get("device") != device:
                            raise RuntimeError("Bộ xử lý VieNeu không tương thích với yêu cầu hiện tại.")
                        completed = int(status.get("completed", 0))
                        if not 0 <= completed <= len(entries):
                            raise RuntimeError("VieNeu báo số câu hoàn tất không hợp lệ.")
                        state = (completed, status.get("stage"))
                        if state != last:
                            last_activity = time.monotonic()
                        while len(published) < completed:
                            item = entries[len(published)]
                            _encode_mp3(Path(item["wav"]), Path(item["output_path"]), cancellation_id)
                            published.append(item)
                            last_activity = time.monotonic()
                        if state != last and progress_callback:
                            progress_callback(len(published), len(items), str(state[1] or "synthesizing"))
                        last = state
                    if time.monotonic() - last_activity >= stall_timeout:
                        raise RuntimeError(f"VieNeu không có tiến triển trong {stall_timeout:g} giây "
                                           f"(device={device}, đã tạo {len(published)}/{len(items)} câu).")
                except Exception as exc:
                    monitor_errors.append(exc)
                    try:
                        process.kill()
                    except OSError:
                        pass
                    return

        thread = threading.Thread(target=publish_status, name="vieneu-progress", daemon=True)
        thread.start()
        try:
            _, stderr = communicate_process(cancellation_id, process, label="VieNeu synthesis",
                                             timeout_seconds=None)
        finally:
            stop.set()
            thread.join()
        check_cancellation(cancellation_id)
        if monitor_errors:
            raise monitor_errors[0]
        if process.returncode:
            raise RuntimeError("VieNeu không tạo được giọng: " + str(stderr or "worker exited")[-1800:])
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if (status.get("completed") != len(items) or status.get("stage") != "completed"
                or status.get("policy") != CACHE_VERSION or status.get("device") != device):
            raise RuntimeError("VieNeu chưa hoàn tất toàn bộ câu; không dùng audio thiếu.")
        for item in entries[len(published):]:
            _encode_mp3(Path(item["wav"]), Path(item["output_path"]), cancellation_id)
            published.append(item)
            if progress_callback:
                progress_callback(len(published), len(items), "completed")
        log_to_video(video_id, f"[TTS][VIENEU] device={device} " + json.dumps(status, ensure_ascii=False))


def synthesize_to_mp3(text, voice, output_path, video_id, *, reference_path="", **options):
    return synthesize_batch_to_mp3([dict(text=text, voice=voice, output_path=output_path,
                                       reference_path=reference_path)], video_id, **options)


def _load_model(root: Path, device: str):
    import vieneu

    common = dict(mode="v3turbo", backbone_repo=str(root / "v3-turbo"),
                  max_batch_size=1, max_streams=1, babble_retries=1)
    if device == "cpu":
        from vieneu._v3_turbo_engine import onnx_runtime_lite as onnx
        original = onnx.OnnxV3LiteEngine

        class LocalCodecEngine(original):
            def __init__(self, **options):
                super().__init__(codec_dir=str(root / "codec"), **options)

        onnx.OnnxV3LiteEngine = LocalCodecEngine
        try:
            return vieneu.Vieneu(**common, device="cpu", backend="onnx", precision="fp32",
                                 onnx_dir=str(root / "v3-turbo" / "onnx_update"),
                                 threads=min(6, max(1, (os.cpu_count() or 2) // 2)))
        finally:
            onnx.OnnxV3LiteEngine = original
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("VieNeu GPU cần GPU NVIDIA/CUDA; không tự đổi sang CPU.")
    # BF16 on Ampere+, FP16 on Pascal/Turing. Never allocate FP32 GPU weights.
    dtype = "bfloat16" if torch.cuda.is_bf16_supported() else "float16"
    torch.set_num_threads(min(4, max(1, (os.cpu_count() or 2) // 2)))
    cap = os.environ.get("HAIZFLOW_TEST_VIENEU_VRAM_GIB")
    if cap:
        fraction = float(cap) * 1024**3 / torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(fraction)
    return vieneu.Vieneu(**common, device="cuda", backend="pytorch", dtype=dtype,
                         moss_tokenizer=str(root / "codec-gpu"))


def _worker(request):
    from haizflow.core.vieneu_voices import han_text_notice

    notice = han_text_notice(request["items"])
    if notice:
        raise ValueError(notice[1])
    import numpy as np
    import soundfile as sf

    from haizflow.engine.main import _write_atomic
    from haizflow.pipeline.tts_quality import SpeechQualityError, validate_speech_waveform

    root, device = Path(request["root"]), request["device"]
    verify_assets(root, device)
    # Only use our newly extracted version, not abandoned site-packages from
    # older SDKs. Extraction happens in parent/manager before inference starts.
    site = prepare_runtime(root)
    sys.path.insert(0, str(site))
    _dll_directory = os.add_dll_directory(str(site)) if hasattr(os, "add_dll_directory") else None
    status = dict(completed=0, total=len(request["items"]), stage="loading_model", device=device,
                  policy=CACHE_VERSION, batch_size=1)
    path = Path(request["status"])
    _write_atomic(path, status)
    model = _load_model(root, device)
    for item in request["items"]:
        status["stage"] = "synthesizing"
        _write_atomic(path, status)
        # No inserted reference speech, expression cues or audio watermark.
        # Bounded chunks finish naturally; do not truncate to subtitle duration.
        if item["voice"] == "vieneu:clone":
            reference = Path(str(item.get("reference_path") or ""))
            if not reference.is_file():
                raise ValueError("Mẫu nhân bản giọng VieNeu không còn tồn tại.")
            voice_options = {"ref_audio": str(reference), "denoise": True}
        else:
            voice_options = {"voice": native_voice(item["voice"])}
        for attempt in range(2):
            wav = np.asarray(model.infer(item["text"], **voice_options,
                                       apply_watermark=False, batch_size=1, max_chars=160),
                             dtype=np.float32).reshape(-1)
            try:
                if not len(wav) or not np.isfinite(wav).all():
                    raise SpeechQualityError("VieNeu trả về audio trống/không hợp lệ.")
                validate_speech_waveform(wav, 48000)
                # Native single-syllable speech can be shorter than the old
                # 160 ms text-derived floor. Duration alone cannot establish
                # a missing final phoneme. Keep measured silence/tone/codec
                # validation, without padding, slowing or rewriting the words.
                break
            except SpeechQualityError as exc:
                if attempt == 0:
                    status["stage"] = "retrying_short_utterance"
                    status["quality_retries"] = int(status.get("quality_retries", 0)) + 1
                    _write_atomic(path, status)
                    continue
                detail = str(exc).replace("OmniVoice", "VieNeu")
                raise RuntimeError(f"VieNeu không tạo được audio hợp lệ cho câu "
                                   f"{status['completed'] + 1}/{status['total']} sau 2 lần thử: {detail}") from exc
        peak = float(np.max(np.abs(wav)))
        if peak > .89:
            wav = wav * (.89 / peak)  # Encoding headroom; never amplify quiet speech here.
        sf.write(item["wav"], wav, 48000, subtype="PCM_16")
        status["completed"] += 1
        status["stage"] = "synthesizing"
        _write_atomic(path, status)
    status["stage"] = "completed"
    status["torch_loaded"] = "torch" in sys.modules
    if device == "gpu":
        import torch

        status.update(peak_allocated_gib=torch.cuda.max_memory_allocated() / 1024**3,
                      peak_reserved_gib=torch.cuda.max_memory_reserved() / 1024**3)
    _write_atomic(path, status)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        _worker(json.loads(Path(args[0]).read_text(encoding="utf-8")))
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
