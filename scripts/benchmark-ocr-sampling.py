"""Opt-in synthetic OCR comparison; never reads or changes user projects."""

import argparse
import json
import hashlib
from dataclasses import replace
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from haizflow.pipeline import subtitle_ocr
from haizflow.pipeline.ocr_runtime import SubtitleOCRRuntime
from haizflow.utils.ffmpeg import _binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--width", type=int, choices=(1280, 1920, 3840), default=1280)
    parser.add_argument("--moving", action="store_true")
    args = parser.parse_args()
    if args.duration < 12:
        parser.error("duration must be at least 12 seconds")
    root = Path(__file__).resolve().parents[1] / "build" / "test-runtime"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ocr-benchmark-", dir=root) as temporary:
        directory = Path(temporary)
        subtitles = []
        for index in range(args.duration // 2):
            start, end = index * 2, min(args.duration, (index + 1) * 2)
            def stamp(seconds):
                return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02},000"
            subtitles.append(f"{index + 1}\n{stamp(start)} --> {stamp(end)}\nThis is subtitle number {index + 1}.\n")
        (directory / "captions.srt").write_text("\n".join(subtitles), encoding="utf-8")
        source = directory / "source.mp4"
        height = args.width * 9 // 16
        background = (f"testsrc2=s={args.width}x{height}:r=10:d={args.duration}" if args.moving
                      else f"color=c=0x202020:s={args.width}x{height}:r=10:d={args.duration}")
        subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
            background, "-vf",
            "subtitles=captions.srt:force_style='FontName=Arial,FontSize=28,Outline=2,MarginV=35'",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2", "-g", "20", str(source)],
            cwd=directory, check=True, capture_output=True, timeout=90)
        results, frames = {}, {}
        with patch.object(subtitle_ocr, "OCR_SEEK_MIN_DURATION", 0), \
                patch.object(subtitle_ocr, "log_to_video"):
            for mode in ("compatibility", "reusable"):
                output = directory / mode
                output.mkdir()
                native = subtitle_ocr._sample_frames_with_av
                sampler = (patch.object(subtitle_ocr, "_sample_frames_with_av", side_effect=
                           subtitle_ocr._SamplingUnavailable("benchmark old path"))
                           if mode == "compatibility" else patch.object(subtitle_ocr, "_sample_frames_with_av", native))
                with sampler:
                    started = time.perf_counter()
                    frames[mode] = subtitle_ocr._sample_frames(str(source), str(output), "ocr-benchmark",
                        duration=args.duration, source_width=args.width, source_height=height,
                        ocr_width=720, ocr_height=404, sample_count=36)
                    results[mode] = {"sampling_seconds": round(time.perf_counter() - started, 3),
                                     "samples": len(frames[mode])}
        if args.model_directory:
            engine = SubtitleOCRRuntime(args.model_directory)
            with patch.object(subtitle_ocr, "_ocr_engine", return_value=engine):
                # Remove one-time session warm-up from the per-method timing.
                subtitle_ocr._ocr_candidates(frames["compatibility"][0], 1, 720, 404)
                for mode, paths in frames.items():
                    started = time.perf_counter()
                    candidates = []
                    reused, cached = 0, {}
                    for index, path in enumerate(paths, 1):
                        fingerprint = hashlib.sha256(path.read_bytes()).digest()
                        if mode == "reusable" and fingerprint in cached:
                            candidates.extend(replace(item, frame=index) for item in cached[fingerprint])
                            reused += 1
                        else:
                            observed = subtitle_ocr._ocr_candidates(path, index, 720, 404)
                            cached[fingerprint] = observed
                            candidates.extend(observed)
                    results[mode]["inference_seconds"] = round(time.perf_counter() - started, 3)
                    results[mode]["text_candidates"] = len(candidates)
                    results[mode]["reused_inference"] = reused
                    results[mode]["region"] = subtitle_ocr.select_subtitle_region(candidates, 36)
            results["runtime"] = engine.detail
        results["sampling_speedup"] = round(
            results["compatibility"]["sampling_seconds"] / results["reusable"]["sampling_seconds"], 2)
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
