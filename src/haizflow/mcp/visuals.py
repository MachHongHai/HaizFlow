"""Bounded visual inspection in the MCP process, never the desktop GUI thread."""
from __future__ import annotations

import hashlib
import io
import json
import math
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

import srt
from PIL import Image

from haizflow.pipeline.render import (
    _crop_filter,
    _karaoke_font_directory,
    _manual_subtitle_layout,
    _write_positioned_ass,
    resolve_subtitle_preview_layout,
)
from haizflow.schemas.video import CropSettings, SubtitleStyle
from haizflow.utils.ffmpeg import _binary


def revision(context):
    data = {key: value for key, value in context.items() if key not in {"revision", "render_path"}}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def geometry(context, patch=None):
    if patch and set(patch) - set(SubtitleStyle.model_fields):
        raise ValueError("Unknown subtitle style fields.")
    style = SubtitleStyle.model_validate({**context["style"], **(patch or {})}, strict=True)
    return resolve_subtitle_preview_layout(
        context.get("cover_region"), context["width"], context["height"], context["output_format"],
        CropSettings(**context["crop"]), style, True, subtitle_language=str(context.get("language") or ""),
    )


def layout_report(context, patch=None, avoid_regions=None):
    layout = geometry(context, patch)
    if not layout:
        raise ValueError("Video dimensions are not ready.")
    w, h = layout["outputWidth"], layout["outputHeight"]
    bw, bh = layout["layoutWidth"], layout["layoutHeight"]
    x = w * layout["positionXPercent"] / 100 - bw / 2
    y = h * layout["positionYPercent"] / 100 - bh / 2
    issues = []
    if x < 0 or y < 0 or x + bw > w or y + bh > h:
        issues.append("Subtitle box extends outside the output frame.")
    if y + bh > h * .9:
        issues.append("Subtitle box enters the lower 10% platform-UI safe margin.")
    if layout["fontSize"] < h * .022:
        issues.append("Font may be too small at mobile viewing size.")
    from PIL import ImageFont

    from haizflow.pipeline.render import _ass_font_em_scale, _font_path_details, subtitle_preview_frame_for_layout
    font_path = _font_path_details(layout["fontFamily"], False, False)[0]
    font = ImageFont.truetype(str(font_path), layout["fontSize"])
    em_scale = _ass_font_em_scale(str(font_path))
    sampled = context["cues"][:2000]
    for cue in sampled:
        start, end = float(cue["start"]), float(cue["end"])
        # Measure the actual renderer's displayed phrase rather than treating
        # an entire long, progressively displayed sentence as one line.
        phrase = subtitle_preview_frame_for_layout(cue["text"], start, end, (start + end) / 2,
                                                   layout["fontSize"], bw, layout["outline"])["text"]
        lines = str(phrase).splitlines()
        if any(font.getlength(line) * em_scale + layout["outline"] * 4 > bw for line in lines):
            issues.append("At least one sampled displayed phrase may exceed the subtitle box width.")
            break
    overlaps = 0.0
    for region in avoid_regions or []:
        if set(region) != {"x", "y", "width", "height"}:
            raise ValueError("Avoid regions require x/y/width/height percentages in output coordinates.")
        if any(type(v) not in {int, float} or not math.isfinite(v) or not 0 <= v <= 100 for v in region.values()):
            raise ValueError("Avoid region values must be finite percentages.")
        if region["x"] + region["width"] > 100 or region["y"] + region["height"] > 100:
            raise ValueError("Avoid region extends outside the output frame.")
        rx, ry, rw, rh = (region[k] / 100 for k in ("x", "y", "width", "height"))
        area = max(0, min((x + bw) / w, rx + rw) - max(x / w, rx))
        area *= max(0, min((y + bh) / h, ry + rh) - max(y / h, ry))
        overlaps += area
    if overlaps:
        issues.append("Subtitle box overlaps a user/agent-specified avoid region.")
    return {"revision": context["revision"], "geometry": layout, "issues": issues,
            "overlap_area": overlaps, "visual_review_required": True,
            "limitations": "No automatic face detection. Safe margins are heuristics, not platform guarantees."}


def suggest(context, avoid_regions=None):
    base = geometry(context)
    if not base:
        raise ValueError("Video dimensions are not ready.")
    height, width = base["outputHeight"], base["outputWidth"]
    font = max(20, min(100, round(min(width * .065, height * .045))))
    candidates = []
    for y in (76, 66, 24, 36):
        patch = {"position_x_percent": 50, "position_y_percent": y, "font_size": font,
                 "box_width_percent": 82, "box_height_percent": 14, "max_chars_per_line": 32}
        report = layout_report(context, patch, avoid_regions)
        candidates.append({"style_patch": patch, "report": report})
    candidates.sort(key=lambda item: (item["report"]["overlap_area"], len(item["report"]["issues"])))
    return {"revision": context["revision"], "candidates": candidates,
            "next_step": "Inspect source frames, preview a candidate, then apply with the matching revision. "
                         "Inspect rendered frames after export before publishing."}


def _run(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, check=True, timeout=30,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout


def frames(context, times, view="source", patch=None):
    if view not in {"source", "result", "layout"}:
        raise ValueError("Unknown preview view.")
    if patch and view != "layout":
        raise ValueError("A style patch is only used in a layout draft.")
    path = Path(context["render_path"] if view == "result" else context["source_path"])
    if not path.is_file():
        raise ValueError("A current render is required for result inspection; export first.")
    identity = (path.stat().st_size, path.stat().st_mtime_ns)
    probe = json.loads(_run([_binary("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                             "-of", "json", str(path)]))
    duration = float(probe["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Media duration is unavailable.")
    if not times:
        cues = context["cues"]
        times = [(float(cues[i]["start"]) + float(cues[i]["end"])) / 2
                 for i in sorted({0, len(cues) // 2, len(cues) - 1})] if cues else [duration * f for f in (.1, .5, .9)]
        if view == "result":
            times = [t / context["output_speed"] for t in times]
        times = [min(max(0, t), max(0, duration - .01)) for t in times]
    if not 1 <= len(times) <= 4 or any(not math.isfinite(t) or not 0 <= t < duration for t in times):
        raise ValueError("Choose 1–4 finite timestamps inside the selected media duration.")
    result = []
    with tempfile.TemporaryDirectory(prefix="haizflow-mcp-preview-") as directory:
        filters = []
        if view == "layout":
            style = SubtitleStyle.model_validate({**context["style"], **(patch or {})}, strict=True)
            layout = geometry(context, patch)
            crop = _crop_filter(CropSettings(**context["crop"]))
            if crop:
                filters.append(crop)
            ow, oh = layout["outputWidth"], layout["outputHeight"]
            if ow * oh > 17000000:
                raise ValueError("Layout draft exceeds the 4K preview budget. Use source/result inspection instead.")
            # This is a positioning draft, not a pretend final render. Ratio
            # conversion uses a neutral letterbox; patch/blur/watermark/audio
            # and per-cue style overrides are inspected in result mode instead.
            filters += [f"scale={ow}:{oh}:force_original_aspect_ratio=decrease",
                        f"pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2"]
            cues = [srt.Subtitle(index=i + 1, start=timedelta(seconds=float(c["start"])),
                                end=timedelta(seconds=float(c["end"])), content=c["text"])
                    for i, c in enumerate(context["cues"])]
            if not cues:
                raise ValueError("Create or import subtitles before previewing a layout draft.")
            subtitle_path = Path(directory) / "captions.srt"
            subtitle_path.write_text(srt.compose(cues), encoding="utf-8")
            # Controlled temporary filenames only; no agent-supplied FFmpeg filters.
            _write_positioned_ass(str(subtitle_path), str(Path(directory) / "captions.ass"), style, ow, oh,
                                  region_layout=_manual_subtitle_layout(style, ow, oh), fixed_font_size=True,
                                  subtitle_language=str(context.get("language") or ""))
            fontdir = str(_karaoke_font_directory()).replace("\\", "/").replace(":", "\\:")
            filters.append(f"ass=filename=captions.ass:fontsdir='{fontdir}'")
        filters.append("scale=640:640:force_original_aspect_ratio=decrease")
        for time in times:
            timeline_filters = ([f"setpts=PTS+{time}/TB"] if view == "layout" else []) + filters
            data = _run([_binary("ffmpeg"), "-hide_banner", "-v", "error", "-threads", "2",
                         "-ss", str(time), "-i", str(path), "-vf", ",".join(timeline_filters), "-frames:v", "1",
                         "-an", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "pipe:1"], directory)
            image = Image.open(io.BytesIO(data))
            image.load()
            if len(data) > 700000 or max(image.size) > 640:
                raise ValueError("Preview exceeded its bounded image budget.")
            result.append((time, data))
    if (path.stat().st_size, path.stat().st_mtime_ns) != identity:
        raise ValueError("Media changed during preview. Inspect again.")
    return result
