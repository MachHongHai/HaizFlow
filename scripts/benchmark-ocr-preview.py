"""Compare committed preview code with local CPU candidates in private storage."""

import argparse
import copy
import hashlib
import json
import re
import runpy
import statistics
import subprocess
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


def baseline_module(name, relative):
    source = subprocess.check_output(["git", "show", f"HEAD:{relative}"], encoding="utf-8")
    module = types.ModuleType(name)
    module.__file__ = str(Path(relative).resolve())
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--modes", nargs="+", choices=["baseline", "cpu", "coarse-cpu", "whole-cpu"],
                        default=["baseline", "cpu", "cpu", "baseline"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    runpy.run_path(str(root / "tests/conftest.py"))
    from haizflow.desktop import editor_preview_controller as preview
    from haizflow.pipeline import render
    from haizflow.schemas.editor import EditorDocument
    from haizflow.schemas.video import VideoInfo
    from haizflow.services import editor_documents, ocr_layers, video_store
    from haizflow.utils.ffmpeg import _binary

    old_render = baseline_module("preview_baseline_render", "src/haizflow/pipeline/render.py")
    old_preview = baseline_module("preview_baseline_controller", "src/haizflow/desktop/editor_preview_controller.py")
    old_preview.render_video = old_render.render_video
    video = VideoInfo.model_validate_json((args.workspace / "video.json").read_text("utf-8"))
    document = EditorDocument.model_validate_json((args.workspace / "editor/document.json").read_text("utf-8"))
    source = Path(video.files["video_input"])
    source_hash = hashlib.file_digest(source.open("rb"), "sha256").hexdigest()
    with patch.object(video_store, "get_video_dir", return_value=str(args.workspace)), \
            patch.object(editor_documents, "load", return_value=document):
        region = ocr_layers.render_region(video, preview.EditorPreviewController._ocr_region(
            args.workspace, video.files.get("ocr_region", "")))
    settings = dict(video_id=video.video_id, source_path=str(source),
        source_identity=preview.EditorPreviewController._file_identity(source), editor_sequence={},
        segments=[], subtitle_style=video.subtitle_style.model_dump(), crop=video.crop.model_dump(),
        output_format="keep_ratio", subtitle_layout_override=False, remove_original_subtitles=True,
        removal_mode=video.original_subtitle_removal_mode, watermark_text="", watermark_scale_percent=100,
        ocr_region=region, original_subtitle_intervals=[],
        preview_encoding="manual-base-pcm-libass-watermark-overlay-v3", independent_manual_preview=True,
        original_video_volume=100, background_music_volume=30, tts_volume=100,
        audio_inputs={}, voice_state={}, request_fingerprint="comparison")
    directory = root / "build" / f"ocr-preview-compare-{time.time_ns()}"
    directory.mkdir(parents=True)
    results = []
    for trial, mode in enumerate(args.modes, 1):
        cls = old_preview.EditorPreviewController if mode == "baseline" else preview.EditorPreviewController
        if mode in {"coarse-cpu", "whole-cpu"}:
            cls = type("GroupedPreview", (cls,), {"_VISUAL_CHUNK_SECONDS": 24 if mode == "coarse-cpu" else 86400})
        renderer = old_render if mode == "baseline" else render
        controller = cls(SimpleNamespace(editorPreviewChanged=Mock()))
        controller._generation = 1
        controller._active_process_id = f"comparison-{trial}"
        trial_settings = copy.deepcopy(settings)
        destination = directory / f"{trial}-{mode}"
        destination.mkdir()
        with patch.object(renderer, "log_to_video"), \
                patch.object(editor_documents, "load", return_value=document), \
                patch.object(controller, "_finish_success") as success, \
                patch.object(controller, "_finish_error") as failure, \
                patch.object(subprocess, "Popen", wraps=subprocess.Popen) as launches:
            started = time.perf_counter()
            controller._render_current(1, controller._active_process_id, video, trial_settings, destination)
            elapsed = time.perf_counter() - started
            assert not failure.called, failure.call_args
            assert success.called
            output = Path(success.call_args.args[1])
            commands = [call.args[0] for call in launches.call_args_list]
            row = dict(mode=mode, seconds=round(elapsed, 4), output=str(output),
                ffmpeg=sum("ffmpeg" in str(command[0]).lower() for command in commands),
                ffprobe=sum("ffprobe" in str(command[0]).lower() for command in commands),
                nvenc_jobs=sum("h264_nvenc" in command for command in commands),
                sha256=hashlib.file_digest(output.open("rb"), "sha256").hexdigest())
            results.append(row)
            print(json.dumps(row), flush=True)
    reference = results[0]["output"]
    for mode in sorted(set(args.modes) - {"baseline"}):
        candidate = next(row["output"] for row in results if row["mode"] == mode)
        result = subprocess.run([_binary("ffmpeg"), "-v", "info", "-i", reference, "-i", candidate,
            "-filter_complex", "[0:v][1:v]ssim", "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=90, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stderr[-1000:]
        score = re.findall(r"All:([0-9.]+)", result.stderr)
        assert score, result.stderr[-1000:]
        for row in results:
            if row["mode"] == mode:
                row["ssim_against_baseline"] = float(score[-1])
    assert hashlib.file_digest(source.open("rb"), "sha256").hexdigest() == source_hash
    summary = dict(baseline_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        source_sha256=source_hash, results=results,
        median_seconds={mode: statistics.median(row["seconds"] for row in results if row["mode"] == mode)
                        for mode in sorted(set(args.modes))})
    (directory / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
