"""Entrypoint shared by CPU, CUDA, and vision resource-pack executables."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import sys
import tempfile
from pathlib import Path

PROTOCOL_VERSION = 1

SMOKE_MODULES = {
    "cpu": (
        "torch",
        "torchaudio",
        "torchvision",
        "ctranslate2",
        "faster_whisper",
        "transformers",
        "whisperx",
        "demucs",
        "llama_cpp",
    ),
    "cuda128": (
        "torch",
        "torchaudio",
        "torchvision",
        "ctranslate2",
        "faster_whisper",
        "transformers",
        "whisperx",
        "demucs",
    ),
    "vision": ("onnxruntime", "rapidocr"),
}


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _status(path: Path, **values) -> None:
    _write_atomic(path, values)


def _warm(capability: str, context: dict) -> None:
    if capability == "recognition":
        from haizflow.pipeline.transcribe import warm_whisperx_model

        warm_whisperx_model(str(context.get("model") or "small"))
    elif capability == "translation":
        from haizflow.services.translation import warm_hymt2_worker

        warm_hymt2_worker()
    elif capability == "voice":
        from haizflow.pipeline.omnivoice_tts import warm_runtime

        warm_runtime(str(context.get("language") or "vi"))
    elif capability == "separation":
        import torch
        from demucs.separate import main as _demucs_main  # noqa: F401, PLC0415

        device = str(context.get("device") or "cpu")
        if device in {"gpu", "cuda"} and torch.cuda.is_available():
            torch.cuda.init()
    elif capability == "ocr":
        import haizflow.pipeline.subtitle_ocr  # noqa: F401, PLC0415
    else:
        raise ValueError(f"Unsupported warm capability: {capability}")


def _release(capability: str) -> None:
    if capability == "recognition":
        from haizflow.pipeline.transcribe import release_warm_whisperx_model

        release_warm_whisperx_model()
    elif capability == "translation":
        from haizflow.services.translation import shutdown_hymt2_worker

        shutdown_hymt2_worker()
    elif capability == "voice":
        from haizflow.pipeline.omnivoice_tts import clear_runtime

        clear_runtime()


def smoke_test(profile: str) -> dict:
    """Import the runtime surface that a frozen profile promises to provide."""

    modules = SMOKE_MODULES.get(profile)
    if modules is None:
        raise ValueError(f"Unsupported engine profile: {profile}")
    versions: dict[str, str] = {}
    # These imports exercise the shared HaizFlow runtime boundary as well as
    # third-party inference modules. A profile is not usable if it can import
    # Torch/ONNX but fails while loading project configuration or schemas.
    importlib.import_module("haizflow.config")
    importlib.import_module("haizflow.services.video_store")
    for module_name in modules:
        importlib.import_module(module_name)
        distribution_name = module_name.replace("_", "-")
        try:
            versions[module_name] = importlib.metadata.version(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            versions[module_name] = "imported"

    if profile in {"cpu", "cuda128"}:
        import torch

        cuda_version = str(torch.version.cuda or "")
        if profile == "cpu" and cuda_version:
            raise RuntimeError(f"CPU engine contains a CUDA Torch build ({cuda_version}).")
        if profile == "cuda128" and not cuda_version.startswith("12.8"):
            raise RuntimeError(f"CUDA 12.8 engine contains an incompatible Torch build ({cuda_version or 'CPU'}).")
    return {"profile": profile, "modules": versions}


def rpc_server() -> int:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            request_id = str(request.get("request_id") or "")
            if request.get("protocol_version") != PROTOCOL_VERSION or not request_id:
                raise ValueError("Unsupported engine protocol request.")
            operation = str(request.get("operation") or "")
            payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
            if operation == "shutdown":
                response = {"shutdown": True}
            elif operation == "warm":
                capability = str(payload.get("capability") or "")
                _warm(capability, dict(payload.get("context") or {}))
                response = {"capability": capability, "resident": True}
            elif operation == "release":
                capability = str(payload.get("capability") or "")
                _release(capability)
                response = {"capability": capability, "resident": False}
            elif operation == "file_task":
                request_path = Path(str(payload.get("request_path") or ""))
                if not request_path.is_file():
                    raise ValueError("Engine file task request is missing.")
                return_code = run_file_request(request_path)
                if return_code:
                    try:
                        task_request = json.loads(request_path.read_text(encoding="utf-8"))
                        task_response = json.loads(Path(task_request["response_path"]).read_text(encoding="utf-8"))
                        detail = str(task_response.get("error") or "Engine file task failed.")
                    except (OSError, KeyError, json.JSONDecodeError):
                        detail = "Engine file task failed."
                    raise RuntimeError(detail)
                response = {"completed": True}
            else:
                raise ValueError(f"Unsupported engine operation: {operation}")
            print(
                json.dumps(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "request_id": request_id,
                        "event": "response",
                        "ok": True,
                        "result": response,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if operation == "shutdown":
                return 0
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "request_id": str(locals().get("request_id") or ""),
                        "event": "response",
                        "ok": False,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    return 0


def run_file_request(request_path: Path) -> int:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    response_path = Path(str(request["response_path"]))
    status_path = Path(str(request["status_path"]))
    operation = str(request.get("operation") or "")
    payload = dict(request.get("payload") or {})
    try:
        if request.get("protocol_version") != PROTOCOL_VERSION:
            raise ValueError("Unsupported engine protocol request.")
        if operation == "transcribe":
            from haizflow.pipeline.transcribe import transcribe

            def progress(stage, detail):
                _status(status_path, stage=str(stage), detail=str(detail), current=0, total=0)

            segments, language = transcribe(
                str(payload["audio_path"]),
                str(payload["output_json_path"]),
                str(payload.get("source_language") or "auto"),
                str(payload["video_id"]),
                progress_callback=progress,
                model_name=str(payload.get("model_name") or "small"),
            )
            result = {"segments": segments, "detected_language": language}
        elif operation == "subtitle_ocr":
            from haizflow.pipeline.subtitle_ocr import detect_original_subtitle_region

            def progress(current, total):
                _status(status_path, stage="ocr", detail="", current=int(current), total=int(total))

            region = detect_original_subtitle_region(
                str(payload["video_path"]),
                str(payload["temp_dir"]),
                str(payload["video_id"]),
                progress_callback=progress,
            )
            result = {"region": region}
        elif operation == "demucs_task":
            from demucs.separate import main as separate

            arguments = payload.get("arguments")
            if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
                raise ValueError("Demucs task arguments are invalid.")
            previous = os.environ.get("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD")
            os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
            try:
                outcome = separate(arguments)
                if isinstance(outcome, int) and outcome:
                    raise RuntimeError(f"Demucs separation failed with exit code {outcome}.")
            except SystemExit as exc:
                if int(exc.code or 0):
                    raise RuntimeError(f"Demucs separation failed with exit code {exc.code}.") from exc
            finally:
                if previous is None:
                    os.environ.pop("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", None)
                else:
                    os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = previous
            result = {}
        else:
            raise ValueError(f"Unsupported file task: {operation}")
        response = {"protocol_version": PROTOCOL_VERSION, "ok": True, "result": result}
        return_code = 0
    except Exception as exc:
        response = {"protocol_version": PROTOCOL_VERSION, "ok": False, "error": str(exc)}
        return_code = 1
    _write_atomic(response_path, response)
    return return_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--profile", choices=sorted(SMOKE_MODULES))
    parser.add_argument("--request", type=Path)
    args, remaining = parser.parse_known_args(argv)
    if args.smoke:
        if not args.profile:
            parser.error("--smoke requires --profile.")
        result = smoke_test(args.profile)
        print(json.dumps({"protocol_version": PROTOCOL_VERSION, "ok": True, **result}), flush=True)
        return 0
    if args.rpc:
        return rpc_server()
    if args.request:
        return run_file_request(args.request)
    if "--runtime-probe" in remaining:
        from dataclasses import asdict

        from haizflow.core.runtime_probe import run_runtime_probe

        index = remaining.index("--runtime-probe")
        if len(remaining) <= index + 1 or remaining[index + 1] not in {"cpu", "gpu"}:
            raise SystemExit("Runtime probe requires cpu or gpu.")
        result = run_runtime_probe(remaining[index + 1])
        print(json.dumps({"event": "runtime_probe", **asdict(result)}, ensure_ascii=True), flush=True)
        return 0 if result.ok else 1
    if "--hymt2-worker" in remaining:
        from haizflow.services.hymt2_worker import main as worker

        index = remaining.index("--hymt2-worker")
        return worker(remaining[index + 1 :])
    if "--omnivoice-worker" in remaining or "--omnivoice-server" in remaining:
        from haizflow.pipeline.omnivoice_tts import main as worker

        if "--omnivoice-server" in remaining:
            return worker(["--server"])
        index = remaining.index("--omnivoice-worker")
        if len(remaining) <= index + 1:
            raise SystemExit("OmniVoice worker requires a request file.")
        return worker(["--worker", remaining[index + 1]])
    if "--demucs-separate" in remaining:
        from demucs.separate import main as separate

        index = remaining.index("--demucs-separate")
        return int(separate(remaining[index + 1 :]) or 0)
    parser.error("No engine operation was selected.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
