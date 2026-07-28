"""Conservative detection of burned-in source subtitles.

This is deliberately not a general text detector.  It samples a small lower
band of the video, accepts text only when it occurs in several frames, and
rejects static lower-thirds/watermarks.  A missed subtitle is preferable to
blurring unrelated on-screen content.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from haizflow.config import MODELS_DIR
from haizflow.core.model_integrity import verify_subtitle_ocr_models
from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.services.video_store import log_to_video
from haizflow.utils.ffmpeg import get_video_dimensions, get_video_duration


SAMPLE_COUNT = 24
ROI_TOP = 0.55
ROI_BOTTOM = 0.93
MIN_CONFIDENCE = 0.68
DETECTOR_CACHE_VERSION = 7


@dataclass(frozen=True)
class TextCandidate:
    frame: int
    x: float
    y: float
    width: float
    height: float
    text: str
    confidence: float


def _normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _is_meaningful(text: str) -> bool:
    return sum(character.isalnum() for character in text) >= 2


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("A percentile needs at least one value.")
    index = round((len(ordered) - 1) * fraction)
    return ordered[max(0, min(len(ordered) - 1, index))]


def _merge_frame_lines(candidates: list[TextCandidate]) -> list[TextCandidate]:
    """Join OCR word boxes that belong to the same subtitle line."""
    by_frame: dict[int, list[TextCandidate]] = {}
    for item in candidates:
        if item.confidence >= MIN_CONFIDENCE and _is_meaningful(item.text):
            by_frame.setdefault(item.frame, []).append(item)

    merged: list[TextCandidate] = []
    for frame, frame_items in by_frame.items():
        lines: list[list[TextCandidate]] = []
        for item in sorted(frame_items, key=lambda value: value.x):
            item_centre_y = item.y + item.height / 2
            for line in lines:
                line_centre_y = sum(value.y + value.height / 2 for value in line) / len(line)
                line_right = max(value.x + value.width for value in line)
                if abs(item_centre_y - line_centre_y) <= 2.5 and item.x - line_right <= 8:
                    line.append(item)
                    break
            else:
                lines.append([item])

        for line in lines:
            left = min(item.x for item in line)
            top = min(item.y for item in line)
            right = max(item.x + item.width for item in line)
            bottom = max(item.y + item.height for item in line)
            ordered = sorted(line, key=lambda value: value.x)
            merged.append(TextCandidate(
                frame=frame,
                x=left,
                y=top,
                width=right - left,
                height=bottom - top,
                text=" ".join(item.text for item in ordered),
                confidence=sum(item.confidence for item in line) / len(line),
            ))
    return merged


def select_subtitle_region(candidates: list[TextCandidate], sample_count: int = SAMPLE_COUNT) -> dict | None:
    """Return a high-confidence normalised subtitle region, or ``None``.

    Coordinates are percentages of the *source frame*.  Candidates must
    already have been restricted to the lower OCR band.
    """
    filtered = [
        item for item in _merge_frame_lines(candidates)
        if (
            item.confidence >= MIN_CONFIDENCE
            and _is_meaningful(item.text)
            # Burned-in captions are normally centred in the lower safe area.
            # Keeping this deliberately narrow avoids scoreboards, chat panes,
            # watermarks and text embedded in the video action.
            and 12 <= item.width <= 82
            and 1 <= item.height <= 14
            and 25 <= item.x + item.width / 2 <= 75
            and 68 <= item.y + item.height / 2 <= 93
        )
    ]
    if not filtered:
        return None

    clusters: list[list[TextCandidate]] = []
    for item in sorted(filtered, key=lambda value: (value.y, value.x, value.frame)):
        centre_x, centre_y = item.x + item.width / 2, item.y + item.height / 2
        for cluster in clusters:
            reference = cluster[0]
            ref_x, ref_y = reference.x + reference.width / 2, reference.y + reference.height / 2
            if abs(centre_x - ref_x) <= 10 and abs(centre_y - ref_y) <= 6:
                cluster.append(item)
                break
        else:
            clusters.append([item])

    minimum_frames = max(3, math.ceil(sample_count * 0.25))
    viable: list[tuple[tuple[int, float], list[TextCandidate]]] = []
    for cluster in clusters:
        by_frame: dict[int, TextCandidate] = {}
        for item in cluster:
            previous = by_frame.get(item.frame)
            if previous is None or item.confidence > previous.confidence:
                by_frame[item.frame] = item
        values = list(by_frame.values())
        if len(values) < minimum_frames:
            continue
        labels = [_normalise_text(item.text) for item in values]
        # A logo/lower-third tends to be identical in nearly every sample;
        # subtitles naturally change over time.  The precision bias here is
        # intentional: no uncertain region is blurred.
        if len(set(labels)) < 2 or max(labels.count(label) for label in set(labels)) / len(labels) > 0.80:
            continue
        viable.append(((len(values), sum(item.confidence for item in values) / len(values)), values))
    if not viable:
        return None

    _rank, selected = max(viable, key=lambda item: item[0])
    # A caption's horizontal length varies substantially between cues, so use
    # its full observed horizontal envelope plus a small outline margin.  The
    # vertical size is stable enough for the 90th percentile, avoiding a tall
    # rectangle caused by one anomalous OCR box.
    centre_y = _percentile([item.y + item.height / 2 for item in selected], 0.50)
    height = _percentile([item.height for item in selected], 0.90)
    # OCR boxes already include the glyph outline.  Keep only a small safety
    # margin so the blur follows the original subtitle instead of reading as a
    # large opaque band on narrow mobile video.
    horizontal_padding, vertical_padding = 1.5, 0.20
    left = max(0.0, min(item.x for item in selected) - horizontal_padding)
    top = max(0.0, centre_y - height / 2 - vertical_padding)
    right = min(100.0, max(item.x + item.width for item in selected) + horizontal_padding)
    bottom = min(100.0, centre_y + height / 2 + vertical_padding)
    return {
        "x_percent": round(left, 2),
        "y_percent": round(top, 2),
        "width_percent": round(max(1.0, right - left), 2),
        "height_percent": round(max(1.0, bottom - top), 2),
        "confidence": round(sum(item.confidence for item in selected) / len(selected), 3),
        "samples": len(selected),
    }


@lru_cache(maxsize=1)
def _ocr_engine():
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:  # pragma: no cover - caught before a release build
        raise RuntimeError("Original subtitle detection is unavailable because RapidOCR is missing.") from exc
    model_dir = verify_subtitle_ocr_models(Path(MODELS_DIR) / "subtitle-ocr")
    return RapidOCR(params={
        "Global.model_root_dir": str(model_dir),
        "Global.use_cls": False,
        "Global.log_level": "error",
        "Det.model_path": str(model_dir / "subtitle-det.onnx"),
        "Rec.model_path": str(model_dir / "subtitle-rec.onnx"),
        "Cls.model_path": str(model_dir / "subtitle-cls.onnx"),
    })


def _ocr_candidates(frame_path: Path, frame: int, source_width: int, source_height: int) -> list[TextCandidate]:
    output = _ocr_engine()(str(frame_path))
    boxes = getattr(output, "boxes", None)
    texts = getattr(output, "txts", None)
    scores = getattr(output, "scores", None)
    boxes = [] if boxes is None else boxes
    texts = [] if texts is None else texts
    scores = [] if scores is None else scores
    candidates: list[TextCandidate] = []
    for box, text, score in zip(boxes, texts, scores):
        try:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            x, y = min(xs), min(ys)
            width, height = max(xs) - x, max(ys) - y
            candidates.append(TextCandidate(
                frame=frame,
                x=100 * x / source_width,
                y=100 * (ROI_TOP * source_height + y) / source_height,
                width=100 * width / source_width,
                height=100 * height / source_height,
                text=str(text),
                confidence=float(score),
            ))
        except (TypeError, ValueError, IndexError):
            continue
    return candidates


def _source_state(video_path: str) -> dict[str, int | str]:
    state = os.stat(video_path)
    return {"path": os.path.abspath(video_path), "size": state.st_size, "mtime_ns": state.st_mtime_ns}


def detect_original_subtitle_region(video_path: str, temp_dir: str, video_id: str) -> dict | None:
    """Sample the lower band and return a region suitable for final rendering.

    Detection is cached per source file inside the project workspace.  This
    function runs in the pipeline worker, never on Qt's GUI thread.
    """
    cache_path = Path(temp_dir) / "original_subtitle_region.json"
    source_state = _source_state(video_path)
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("version") == DETECTOR_CACHE_VERSION and cached.get("source") == source_state:
            return cached.get("region")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass

    duration = get_video_duration(video_path)
    source_width, source_height = get_video_dimensions(video_path)
    if duration <= 0 or source_width <= 0 or source_height <= 0:
        raise RuntimeError("Unable to inspect the source video for original subtitles.")
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="subtitle-ocr-", dir=temp_dir) as frame_dir:
        output_pattern = str(Path(frame_dir) / "frame-%03d.jpg")
        frame_rate = SAMPLE_COUNT / duration
        crop_height = max(2, int(source_height * (ROI_BOTTOM - ROI_TOP)) // 2 * 2)
        crop_top = max(0, int(source_height * ROI_TOP) // 2 * 2)
        command = [
            "ffmpeg", "-y", "-i", video_path, "-an", "-vf",
            f"fps={frame_rate:.8f},crop={source_width}:{crop_height}:0:{crop_top}",
            "-frames:v", str(SAMPLE_COUNT), output_pattern,
        ]
        check_cancellation(video_id)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _stdout, stderr = communicate_process(video_id, process, label="Original subtitle scan", timeout_seconds=600)
        check_cancellation(video_id)
        if process.returncode != 0:
            raise RuntimeError(f"Unable to sample frames for original subtitle detection: {stderr[-500:]}")
        candidates: list[TextCandidate] = []
        for index, frame_path in enumerate(sorted(Path(frame_dir).glob("frame-*.jpg")), 1):
            check_cancellation(video_id)
            candidates.extend(_ocr_candidates(frame_path, index, source_width, source_height))
    region = select_subtitle_region(candidates, SAMPLE_COUNT)
    payload = {"version": DETECTOR_CACHE_VERSION, "source": source_state, "region": region}
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, cache_path)
    if region:
        log_to_video(video_id, "Detected a high-confidence burned-in subtitle region for removal.")
    else:
        log_to_video(video_id, "No reliable burned-in subtitle region was found; source subtitles were left unchanged.")
    return region
