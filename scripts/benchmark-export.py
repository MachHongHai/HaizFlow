"""Measure real export I/O/encoding against an explicitly selected Git revision.

Creates synthetic media in an isolated temporary runtime, never user projects.
Usage: .venv/Scripts/python.exe scripts/benchmark-export.py --baseline-ref <commit>
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path


def previous_module(root, ref, relative):
    source = subprocess.check_output(["git", "show", f"{ref}:{relative}"], cwd=root).decode("utf-8")
    module = types.ModuleType("export_benchmark_baseline_" + Path(relative).stem)
    module.__file__ = str(root / relative)
    sys.modules[module.__name__] = module
    exec(compile(source, relative, "exec"), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--size-mib", type=int, default=256)
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--production", action="store_true", help="Compare two-pass/fused render with OCR patch")
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = root / "build" / "test-runtime"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="export-benchmark-", dir=work) as folder:
        directory = Path(folder)
        os.environ.update(HFLOW_SMOKE_TEST="1", HFLOW_HOME=folder,
                          RUNTIME_DATA_DIR=str(directory / "data"),
                          HFLOW_RESOURCE_ROOT=str(directory / "resources"))
        sys.path.insert(0, str(root / "src"))
        from hflow.pipeline import sequence_compiler
        from hflow.schemas.video import VideoConfig
        from hflow.services import manual_artifacts, project_store, video_export, video_store
        from hflow.utils.ffmpeg import _binary, get_video_duration, preferred_export_encoder, validate_video_integrity

        old_export = previous_module(root, options.baseline_ref, "src/hflow/services/video_export.py")
        old_sequence = previous_module(root, options.baseline_ref, "src/hflow/pipeline/sequence_compiler.py")
        project = project_store.create_project("Export benchmark", str(directory / "projects"), "single")
        video = video_store.create_video("export-benchmark", "synthetic.mp4", VideoConfig(
            project_name="Export benchmark", project_directory=str(directory / "projects"),
            project_key=project["key"], project_id=project["project_id"], project_type="single"))
        Path(video.files["video_input"]).write_bytes(b"synthetic source")
        video = video_store.update_video(video.video_id, status="done", checkpoints={"render": "benchmark"})
        revision = video_export.render_revision(video)
        staging = manual_artifacts.create_staging_directory(video.video_id, "export")
        block = os.urandom(1024**2)
        with (staging / "video.mp4").open("wb") as stream:
            for _ in range(options.size_mib):
                stream.write(block)
        record = manual_artifacts.publish(video.video_id, "export", revision, staging,
            {"video": "video.mp4"}, config_fingerprint=revision)
        video = video_store.update_video(video.video_id, files={**video.files, "final_video": record["resolved_outputs"]["video"]})
        results = {"baseline_ref": options.baseline_ref, "copy_mib": options.size_mib,
                   "copy_validation_cache": "cold each run; OS file cache not flushed", "copy_seconds": {}}
        measured = {"before": [], "after": []}
        event_counts = {}
        for repetition in range(3):
            # Alternate order to reduce page-cache/order bias.
            order = [("before", old_export), ("after", video_export)]
            if repetition % 2:
                order.reverse()
            for name, module in order:
                manual_artifacts._VALIDATED_DIGESTS.clear()
                events = []
                output = directory / f"{name}-{repetition}.mp4"
                start = time.perf_counter()
                module.export_video(video, output, progress=events.append)
                measured[name].append(time.perf_counter() - start)
                event_counts[name] = len(events)
                assert output.stat().st_size == options.size_mib * 1024**2
                output.unlink()
        results["copy_seconds"] = {name: round(statistics.median(values), 3) for name, values in measured.items()}
        results["copy_progress_events"] = event_counts

        media = directory / "synthetic-source.mp4"
        subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
            f"testsrc2=size={options.width}x{options.height}:rate=30:duration={options.duration}", "-f", "lavfi", "-i",
            f"sine=frequency=440:sample_rate=48000:duration={options.duration}",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(media)],
            check=True, capture_output=True)
        results["selected_encoder"] = preferred_export_encoder(18,
            dimensions=(options.width, options.height), duration=options.duration / 2)[0]
        results["speed_source"] = {"width": options.width, "height": options.height, "duration": options.duration}
        results["speed_2x_seconds"] = {}
        audio = {}
        for name, module in [("before", old_sequence), ("after", sequence_compiler)]:
            output = directory / f"speed-{name}.mp4"
            start = time.perf_counter()
            module.finish_export_resolution(str(media), str(output), "source", "benchmark", output_speed=2)
            results["speed_2x_seconds"][name] = round(time.perf_counter() - start, 3)
            validate_video_integrity(str(output))
            assert abs(get_video_duration(str(output)) - options.duration / 2) < .15
            audio[name] = subprocess.check_output([_binary("ffmpeg"), "-v", "error", "-i", str(output),
                "-map", "0:a:0", "-f", "s16le", "-acodec", "pcm_s16le", "-"])
        results["speed_audio_pcm_identical"] = audio["before"] == audio["after"]
        if options.production:
            from hflow.pipeline import render
            from hflow.schemas.video import CropSettings, SubtitleStyle

            old_render = previous_module(root, options.baseline_ref, "src/hflow/pipeline/render.py")
            voice, subtitles = directory / "voice.wav", directory / "subtitles.srt"
            subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                f"sine=frequency=440:sample_rate=48000:duration={options.duration}", "-ac", "2", str(voice)],
                check=True, capture_output=True)
            subtitles.write_text("1\n00:00:01,000 --> 00:00:04,000\nExport benchmark\n", encoding="utf-8")
            region = {"x_percent": 10, "y_percent": 80, "width_percent": 80, "height_percent": 8}
            results["production_1080p_2x_seconds"] = {}
            for name, renderer in [("before", old_render), ("after", render)]:
                base, output = directory / f"production-base-{name}.mp4", directory / f"production-{name}.mp4"
                start = time.perf_counter()
                renderer.render_video(str(media), str(voice), str(subtitles), str(base if name == "before" else output),
                    "keep_ratio", SubtitleStyle(), CropSettings(), video.video_id, region,
                    original_subtitle_removal_mode="patch", encoding_quality=18,
                    **({"export_preset": "1080p-high", "output_speed": 2} if name == "after" else {}))
                if name == "before":
                    old_sequence.finish_export_resolution(str(base), str(output), "1080p-high", video.video_id, output_speed=2)
                results["production_1080p_2x_seconds"][name] = round(time.perf_counter() - start, 3)
                validate_video_integrity(str(output))
                assert abs(get_video_duration(str(output)) - options.duration / 2) < .15
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
