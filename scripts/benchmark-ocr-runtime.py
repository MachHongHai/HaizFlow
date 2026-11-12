"""Compare CPU OCR session policies on identical sampled frames, read-only source."""

import argparse
import gc
import hashlib
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from haizflow.pipeline import ocr_runtime, subtitle_ocr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--model-directory", required=True, type=Path)
    parser.add_argument("--paired", action="store_true", help="Alternate old/fixed inference on each identical frame")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "build" / "test-runtime"
    root.mkdir(parents=True, exist_ok=True)
    duration = subtitle_ocr.get_video_duration(str(args.source))
    width, height = subtitle_ocr.get_video_dimensions(str(args.source))
    ocr_width = min(width, subtitle_ocr.OCR_FRAME_MAX_WIDTH)
    ocr_height = round(height * ocr_width / width) // 2 * 2
    with tempfile.TemporaryDirectory(prefix="ocr-runtime-", dir=root) as staging:
        start = time.perf_counter()
        with patch.object(subtitle_ocr, "log_to_video"):
            frames = subtitle_ocr._sample_frames(str(args.source), staging, "ocr-runtime-test",
                duration=duration, source_width=width, source_height=height,
                ocr_width=ocr_width, ocr_height=ocr_height, sample_count=36)
        print(json.dumps({"sampling_seconds": time.perf_counter() - start, "frames": len(frames)}), flush=True)
        if args.paired:
            paired(args.model_directory, frames, ocr_width, ocr_height)
            return
        from rapidocr import RapidOCR
        options = ocr_runtime._session_options
        for policy in ("release", "old-dev", "fixed", "fixed", "old-dev", "release"):
            def old_options(ort, provider=ocr_runtime.CPU):
                result = options(ort, provider)
                result.intra_op_num_threads = min(4, result.intra_op_num_threads)
                result.enable_mem_pattern = False
                return result

            start = time.perf_counter()
            if policy == "release":
                engine = RapidOCR(params={"Global.model_root_dir": str(args.model_directory),
                    "Global.use_cls": False, "Global.log_level": "error",
                    **{f"{name}.model_path": str(args.model_directory / f"subtitle-{short}.onnx")
                       for name, short in (("Det", "det"), ("Cls", "cls"), ("Rec", "rec"))}})
            else:
                with patch.object(ocr_runtime, "_session_options", old_options if policy == "old-dev" else options):
                    engine = ocr_runtime._create_engine(args.model_directory, ocr_runtime.CPU)
            setup = time.perf_counter() - start
            start = time.perf_counter()
            with patch.object(subtitle_ocr, "_ocr_engine", return_value=engine):
                candidates = [candidate for i, frame in enumerate(frames, 1)
                              for candidate in subtitle_ocr._ocr_candidates(frame, i, ocr_width, ocr_height)]
            elapsed = time.perf_counter() - start
            text = [(item.frame, item.text) for item in candidates]
            print(json.dumps({"policy": policy, "setup_seconds": round(setup, 4),
                "inference_seconds": round(elapsed, 4), "candidates": len(candidates),
                "text_sha256": hashlib.sha256(json.dumps(text, ensure_ascii=False).encode()).hexdigest(),
                "region": subtitle_ocr.select_subtitle_region(candidates, 36)}, ensure_ascii=False), flush=True)
            del engine, candidates
            gc.collect()


def paired(model_directory, frames, width, height):
    options = ocr_runtime._session_options

    def old_options(ort, provider=ocr_runtime.CPU):
        result = options(ort, provider)
        result.intra_op_num_threads = min(4, result.intra_op_num_threads)
        result.enable_mem_pattern = False
        return result

    with patch.object(ocr_runtime, "_session_options", old_options):
        old = ocr_runtime._create_engine(model_directory, ocr_runtime.CPU)
    fixed = ocr_runtime._create_engine(model_directory, ocr_runtime.CPU)
    for engine in (old, fixed):
        engine(str(frames[0]))
    for trial in range(2):
        results = {name: {"seconds": 0, "candidates": []} for name in ("old-dev", "fixed")}
        for index, frame in enumerate(frames, 1):
            order = [("old-dev", old), ("fixed", fixed)]
            if (index + trial) % 2:
                order.reverse()
            for name, engine in order:
                started = time.perf_counter()
                with patch.object(subtitle_ocr, "_ocr_engine", return_value=engine):
                    candidates = subtitle_ocr._ocr_candidates(frame, index, width, height)
                results[name]["seconds"] += time.perf_counter() - started
                results[name]["candidates"].extend(candidates)
        for name, result in results.items():
            candidates = result["candidates"]
            text = [(item.frame, item.text) for item in candidates]
            print(json.dumps({"trial": trial + 1, "policy": name, "inference_seconds": round(result["seconds"], 4),
                "candidates": len(candidates),
                "text_sha256": hashlib.sha256(json.dumps(text, ensure_ascii=False).encode()).hexdigest(),
                "region": subtitle_ocr.select_subtitle_region(candidates, 36)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
