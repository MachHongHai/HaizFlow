"""Measure the installed, pinned SDK without touching projects or their cache."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument("--batches", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--rounds", type=int, default=2, help="Repeat matched workloads after a single warm-up.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--pipeline", action="store_true", help="Also verify production batching and model-release/reload timings.")
    args = parser.parse_args()
    from haizflow.config import MODELS_DIR
    from haizflow.pipeline.omnivoice_tts import _encode_voice_reference, _prepare_isolated_runtime, _preset_reference, _worker_environment

    os.environ.update(_worker_environment())
    sdk = _prepare_isolated_runtime()
    sys.path.insert(0, str(sdk))
    started = time.perf_counter()
    import numpy as np
    import psutil
    import soundfile as sf
    import torch
    from omnivoice import OmniVoice

    report = {"device": args.device, "imports_seconds": round(time.perf_counter() - started, 3), "results": []}
    args.report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    required = (2 if args.device == "gpu" else 6) * 1024**3
    if psutil.virtual_memory().available < required:
        report["skipped"] = "Not enough free RAM to load the model with safety headroom."
        save()
        print(json.dumps(report), flush=True)
        return 0
    device = "cuda:0" if args.device == "gpu" else "cpu"
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if args.device == "gpu":
        torch.backends.cuda.matmul.allow_tf32 = True
    started = time.perf_counter()
    model = OmniVoice.from_pretrained(str(Path(MODELS_DIR) / "omnivoice"), device_map=device,
                                     dtype=torch.float16 if args.device == "gpu" else torch.float32,
                                     low_cpu_mem_usage=True)
    report["model_load_seconds"] = round(time.perf_counter() - started, 3)
    if args.device == "cpu":
        torch.set_num_threads(min(8, max(1, (os.cpu_count() or 4) - 1)))
    reference, transcript = _preset_reference("omnivoice:male", "vi")
    prompt = _encode_voice_reference(model, torch, reference, transcript)
    if args.device == "gpu":
        torch.cuda.empty_cache()
        report["baseline_vram_mib"] = round(torch.cuda.memory_allocated() / 1024**2, 1)
    texts = ["Xin chào bạn, hôm nay chúng ta sẽ bắt đầu một hành trình mới.",
             "Mọi người đã sẵn sàng chưa? Hãy cùng nhau tìm hiểu nhé.",
             "Đây là một câu thoại dùng để kiểm tra tốc độ tạo giọng đọc.",
             "Cảm ơn bạn đã lắng nghe, hẹn gặp lại trong video tiếp theo."]
    if args.rounds < 1 or args.rounds > 10:
        parser.error("Rounds must be between 1 and 10.")
    with torch.inference_mode():
        model.generate(text=texts[0], language="vi", voice_clone_prompt=prompt,
                       num_step=32 if args.device == "gpu" else 16, normalize_text=False,
                       audio_chunk_duration=10.0, audio_chunk_threshold=8.0)
    if args.device == "gpu":
        torch.cuda.empty_cache()
    for size in args.batches:
        if size < 1 or size > 8:
            parser.error("Batch size must be between 1 and 8.")
        if args.device == "gpu":
            free, _total = torch.cuda.mem_get_info()
            if free < (1.0 + size * 0.15) * 1024**3:
                report["results"].append({"batch": size, "free_vram_mib": round(free / 1024**2, 1), "skipped": "Insufficient VRAM headroom."})
                save()
                continue
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
        started = time.perf_counter()
        outputs = None
        try:
            valid = True
            for _round in range(args.rounds):
                for offset in range(0, len(texts), size):
                    candidate = texts[offset:offset + size]
                    torch.manual_seed(42)
                    with torch.inference_mode():
                        outputs = model.generate(text=candidate, language="vi", voice_clone_prompt=prompt,
                                                 num_step=32 if args.device == "gpu" else 16, normalize_text=False,
                                                 audio_chunk_duration=10.0, audio_chunk_threshold=8.0)
                    valid = valid and len(outputs) == len(candidate) and all(np.isfinite(audio).all() and len(audio) >= 240 for audio in outputs)
                    del outputs
                    outputs = None
            if args.device == "gpu":
                torch.cuda.synchronize()
            seconds = time.perf_counter() - started
            count = len(texts) * args.rounds
            item = {"batch": size, "segments": count, "seconds": round(seconds, 3),
                    "seconds_per_segment": round(seconds / count, 3), "valid": valid}
            if args.device == "gpu":
                item["peak_vram_mib"] = round(torch.cuda.max_memory_allocated() / 1024**2, 1)
            report["results"].append(item)
        except torch.OutOfMemoryError:
            report["results"].append({"batch": size, "failed": "out_of_memory"})
            break
        finally:
            del outputs
            if args.device == "gpu":
                torch.cuda.empty_cache()
            save()
        print(json.dumps(report["results"][-1]), flush=True)
    if args.pipeline:
        from haizflow.pipeline.omnivoice_tts import _worker_main

        output_root = args.report.with_suffix("")
        output_root.mkdir(parents=True, exist_ok=True)
        request = {"model_root": str(Path(MODELS_DIR) / "omnivoice"), "site_packages": str(sdk),
                   "device": device, "language": "vi", "speaker_mode": "single", "voice_seed": 42,
                   "inference_steps": 32 if args.device == "gpu" else 16,
                   "preset_reference_path": reference, "preset_reference_text": transcript,
                   "items": [{"text": text, "voice": "omnivoice:male", "wav_path": str(output_root / f"voice_{index:04d}.wav")}
                             for index, text in enumerate(texts * args.rounds, 1)],
                   "status_path": str(output_root / "status.json")}
        request_path = output_root / "request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        runtime = {"modules": (np, sf, torch, OmniVoice), "model": model,
                   "model_key": (request["model_root"], device)}
        # Do not leave caller references retaining weights during release.
        del model, prompt
        if args.device == "gpu":
            torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        _worker_main(str(request_path), runtime)
        report["pipeline_seconds"] = round(time.perf_counter() - started, 3)
        report["pipeline_status"] = json.loads(Path(request["status_path"]).read_text(encoding="utf-8"))
        report["batch_profiles"] = {str(key): value for key, value in runtime.get("batch_profiles", {}).items()}
        if args.device == "gpu":
            report["pipeline_peak_vram_mib"] = round(torch.cuda.max_memory_allocated() / 1024**2, 1)
        Path(output_root / "transcript.json").write_text(json.dumps([{"text": text} for text in texts * args.rounds], ensure_ascii=False), encoding="utf-8")
        release_path = output_root / "release.json"
        release_path.write_text(json.dumps({"operation": "release_model"}), encoding="utf-8")
        _worker_main(str(release_path), runtime)
        report["modules_retained"] = "modules" in runtime and "model" not in runtime
        if args.device == "gpu":
            report["released_vram_mib"] = round(torch.cuda.memory_allocated() / 1024**2, 1)
        request["items"] = []
        request_path.write_text(json.dumps(request), encoding="utf-8")
        _worker_main(str(request_path), runtime)
        report["reload_status"] = json.loads(Path(request["status_path"]).read_text(encoding="utf-8"))
        _worker_main(str(release_path), runtime)
        save()
    print(json.dumps(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
