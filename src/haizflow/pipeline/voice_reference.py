"""Transcribe authorised clone samples locally before the speech model loads."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS, MODELS_DIR, TMP_DIR
from haizflow.core.model_integrity import verify_whisper_model, verify_whisper_turbo_model
from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.services.video_store import log_to_video


def transcribe_reference(path: str, video_id: str, *, process_registry_id: str | None = None,
                         device: str | None = None) -> str:
    cancellation_id = process_registry_id or video_id
    reference = Path(path).resolve()
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    cache = Path(TMP_DIR) / "voice-reference-transcripts" / f"{digest}.json"
    try:
        text = str(json.loads(cache.read_text(encoding="utf-8"))["text"]).strip()
        if text:
            return text
    except (OSError, ValueError, KeyError):
        pass
    from haizflow.services.resource_packs import installed_engine_command

    model_root = None
    model_name = "small"
    for name, verifier in (("small", verify_whisper_model), ("large-v3-turbo", verify_whisper_turbo_model)):
        try:
            model_root = verifier(Path(MODELS_DIR) / "whisper" / name)
            model_name = name
            break
        except (RuntimeError, OSError):
            continue
    if model_root is None:
        raise RuntimeError("Cần cài Whisper Small hoặc Whisper Turbo để nhận dạng nội dung mẫu giọng.")
    recognition_device = "gpu" if device in {"gpu", "cuda", "cuda:0"} else "cpu"
    log_to_video(video_id, f"[CLONE-ASR][START] model={model_name} device={recognition_device} "
                 "detail=Nhận dạng nội dung mẫu giọng; đây không phải bước tạo giọng OmniVoice.")
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clone-asr-", dir=TMP_DIR) as directory:
        root = Path(directory)
        response = root / "response.json"
        request = root / "request.json"
        request.write_text(
            json.dumps(
                {
                    "protocol_version": 1,
                    "operation": "reference_transcribe",
                    "payload": {"audio_path": str(reference), "model_root": str(model_root),
                                "device": recognition_device},
                    "response_path": str(response),
                    "status_path": str(root / "status.json"),
                }
            ),
            encoding="utf-8",
        )
        command = installed_engine_command(
            "recognition", "transcribe", {"device": recognition_device, "model": model_name}
        )
        if not command and recognition_device == "cpu":
            command = installed_engine_command("recognition", "transcribe", {"device": "gpu", "model": model_name})
        if not command:
            if getattr(sys, "frozen", False):
                raise RuntimeError("Cần cài môi trường Whisper trong Gói tài nguyên để nhận dạng mẫu giọng.")
            command = [
                sys.executable,
                "-m",
                "haizflow.engine.main",
            ]
        environment = os.environ.copy()
        environment.update(PYTHONUTF8="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        if not getattr(sys, "frozen", False):
            environment["PYTHONPATH"] = (
                str(Path(__file__).resolve().parents[2]) + os.pathsep + environment.get("PYTHONPATH", "")
            )
        check_cancellation(cancellation_id)
        process = subprocess.Popen(
            [*command, "--request", str(request)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _stdout, stderr = communicate_process(
            cancellation_id, process, label="Clone sample recognition", timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS
        )
        if process.returncode or not response.is_file():
            raise RuntimeError(f"Không nhận dạng được mẫu giọng: {stderr[-500:]}")
        result = json.loads(response.read_text(encoding="utf-8"))
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or "Không nhận dạng được mẫu giọng."))
        text = str(result.get("result", {}).get("text") or "").strip()
        if not text:
            raise RuntimeError("Mẫu giọng chưa có lời nói rõ. Hãy thu lại 5–15 giây trong môi trường yên tĩnh.")
        cache.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
        for line in stderr.splitlines():
            if line.startswith("[CLONE-ASR]"):
                log_to_video(video_id, line)
        log_to_video(video_id, "[CLONE-ASR][DONE] Nội dung mẫu đã sẵn sàng; tiếp tục tạo giọng OmniVoice.")
        return text


def recognize_reference(audio_path: str, model_root: str, *, device: str = "cpu") -> str:
    from faster_whisper import WhisperModel

    def recognize(target):
        model = WhisperModel(
            model_root, device=target, compute_type="float16" if target == "cuda" else "int8",
            local_files_only=True, cpu_threads=max(1, min(4, (os.cpu_count() or 4) - 1)),
        )
        print(f"[CLONE-ASR][DEVICE] device={target} compute_type={'float16' if target == 'cuda' else 'int8'}",
              file=sys.stderr, flush=True)
        segments, _info = model.transcribe(audio_path, beam_size=3, vad_filter=True, condition_on_previous_text=False)
        return " ".join(segment.text.strip() for segment in segments).strip()

    target = "cuda" if device == "gpu" else "cpu"
    try:
        return recognize(target)
    except RuntimeError as exc:
        # The small auxiliary ASR may share VRAM with a resident TTS worker.
        # Only resource/CUDA availability failures permit a visible CPU retry.
        if target != "cuda" or not any(token in str(exc).lower() for token in (
            "out of memory", "cuda failed", "cublas", "cudnn", "cuda driver", "no cuda",
        )):
            raise
        print("[CLONE-ASR][WARN] GPU không đủ tài nguyên hoặc chưa khả dụng; nhận dạng mẫu trên CPU. "
              "Thiết bị tạo giọng OmniVoice không thay đổi.", file=sys.stderr, flush=True)
        return recognize("cpu")
