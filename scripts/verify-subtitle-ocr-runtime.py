"""Opt-in CPU/GPU OCR comparison, writing evidence outside the source project."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    # Imported sources conventionally live in input/ under their workspace.
    workspace = source.parent.parent if source.parent.name == "input" else source.parent
    if output.is_relative_to(workspace) or workspace.is_relative_to(output):
        parser.error("Evidence must be outside, and not contain, the source workspace.")
    output.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        HAIZFLOW_SMOKE_TEST="1",
        RUNTIME_DATA_DIR=str(output / "runtime"),
        CACHE_DIR=str(output / "cache"),
        TMP_DIR=str(output / "tmp"),
        MODELS_DIR=str(args.models.resolve().parent),
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

    import onnxruntime as ort

    from haizflow.core.model_integrity import verify_subtitle_ocr_models
    from haizflow.pipeline import ocr_runtime
    from haizflow.pipeline.ocr_runtime import CPU, _create_engine, preferred_provider
    from haizflow.pipeline.subtitle_ocr import _ocr_candidates, select_subtitle_region
    from haizflow.utils.ffmpeg import _binary, get_video_dimensions, get_video_duration

    models = verify_subtitle_ocr_models(args.models.resolve())
    width, height = get_video_dimensions(str(source))
    target_width = min(width, 720)
    target_height = max(2, round(height * target_width / width)) // 2 * 2
    duration = get_video_duration(str(source))
    frames = output / "frames"
    frames.mkdir(exist_ok=True)
    subprocess.run(
        [
            _binary("ffmpeg"),
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-an",
            "-vf",
            f"fps={36 / duration:.8f},scale={target_width}:{target_height}",
            "-frames:v",
            "36",
            str(frames / "frame-%03d.png"),
        ],
        check=True,
        timeout=300,
    )
    paths = sorted(frames.glob("frame-*.png"))
    report = {
        "source": str(source),
        "providers": ort.get_available_providers(),
        "runtime": ort.__version__,
        "sample_count": len(paths),
        "results": {},
    }
    selected = preferred_provider(ort.get_available_providers())
    if selected == CPU:
        raise RuntimeError("No installed GPU provider; run this comparison in the isolated vision environment.")
    from unittest.mock import patch

    for provider in (CPU, selected):
        started = time.perf_counter()
        session_index = 0
        session_options = ocr_runtime._session_options

        def profiling_options(ort_module):
            nonlocal session_index
            options = session_options(ort_module)
            session_index += 1
            options.enable_profiling = True
            options.profile_file_prefix = str(output / f"{provider}-{session_index}")
            return options

        with patch.object(ocr_runtime, "_session_options", side_effect=profiling_options):
            engine = _create_engine(models, provider)
        init_seconds = time.perf_counter() - started
        engine(str(paths[0]))  # Warm-up excluded from the timed sample loop.
        started = time.perf_counter()
        candidates = []
        with patch("haizflow.pipeline.subtitle_ocr._ocr_engine", return_value=engine):
            for index, path in enumerate(paths, 1):
                candidates.extend(_ocr_candidates(path, index, target_width, target_height))
        elapsed = time.perf_counter() - started
        node_providers = Counter()
        for component in (engine.text_det, engine.text_rec):
            profile_path = Path(component.session.session.end_profiling())
            events = json.loads(profile_path.read_text("utf-8"))
            node_providers.update(
                event.get("args", {}).get("provider")
                for event in events
                if event.get("cat") == "Node" and event.get("args", {}).get("provider")
            )
        engine.text_cls.session.session.end_profiling()
        if provider != CPU and not node_providers[provider]:
            raise RuntimeError(f"{provider} registered but no OCR nodes executed on it.")
        report["results"][provider] = {
            "init_seconds": init_seconds,
            "inference_seconds": elapsed,
            "candidates": len(candidates),
            "region": select_subtitle_region(candidates, len(paths)),
            "effective_det": engine.text_det.session.session.get_providers(),
            "effective_rec": engine.text_rec.session.session.get_providers(),
            "profiled_node_providers": dict(node_providers),
            "observations": [vars(item) for item in candidates],
        }
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(
            json.dumps(
                {"provider": provider, "seconds": elapsed, "region": report["results"][provider]["region"]},
                ensure_ascii=False,
            ),
            flush=True,
        )
        del engine
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
