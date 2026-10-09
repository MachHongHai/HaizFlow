"""Transparent libass caption frames, using the export ASS writer verbatim."""
from __future__ import annotations

import hashlib
import bisect
import json
import logging
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import srt
from PIL import Image
from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.pipeline.render import SubtitleRegionLayout, _karaoke_font_directory, _write_positioned_ass
from haizflow.schemas.video import SubtitleStyle
from haizflow.utils.ffmpeg import _binary

logger = logging.getLogger(__name__)


def timestamp(value):
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def sprite_key(header, body, layout):
    return hashlib.sha256((
        "subtitle-sprite-v4\n" + header + body
        + json.dumps(layout, sort_keys=True, ensure_ascii=False)
    ).encode()).hexdigest()


def export_events(segments, layout, fixed, directory):
    """Render one segment clock with the same ASS fitting as final export."""
    events = []
    first_header = ""
    groups: dict[str, tuple[dict, list[dict]]] = {}
    for segment in segments:
        if not str(segment.get("text") or "").strip():
            continue
        resolved = dict(layout)
        style_payload = segment.get("_style")
        if isinstance(style_payload, dict):
            resolved.update(
                fontSize=style_payload.get("font_size", resolved.get("fontSize")),
                outline=style_payload.get("outline_width", resolved.get("outline")),
                positionXPercent=style_payload.get("position_x_percent", resolved.get("positionXPercent")),
                positionYPercent=style_payload.get("position_y_percent", resolved.get("positionYPercent")),
                fontFamily=style_payload.get("font_family", resolved.get("fontFamily")),
                textColor=style_payload.get("text_color", resolved.get("textColor")),
                karaokeColor=style_payload.get("karaoke_color", resolved.get("karaokeColor")),
                outlineColor=style_payload.get("outline_color", resolved.get("outlineColor")),
                bold=int(style_payload.get("font_weight", 400)) >= 600,
                italic=bool(style_payload.get("italic", False)),
                uppercase=bool(style_payload.get("uppercase", False)),
                letterSpacing=style_payload.get("letter_spacing", resolved.get("letterSpacing", 0)),
                alignment=style_payload.get("alignment", resolved.get("alignment", "center")),
                shadow=round(max(
                    abs(float(style_payload.get("shadow_offset_x", 0) or 0)),
                    abs(float(style_payload.get("shadow_offset_y", 0) or 0)),
                )),
                layoutWidth=max(24, round(
                    int(layout["outputWidth"])
                    * float(style_payload.get("max_width_percent", 72) or 72) / 100
                )),
                layoutHeight=max(20, round(
                    int(layout["outputHeight"])
                    * float(style_payload.get("box_height_percent", 12) or 12) / 100
                )),
            )
        key = json.dumps(resolved, sort_keys=True, ensure_ascii=False)
        groups.setdefault(key, (resolved, []))[1].append(segment)

    for group_index, (_key, (resolved, members)) in enumerate(groups.items()):
        style = SubtitleStyle(
            font_size=round(float(resolved["fontSize"])),
            outline=round(float(resolved["outline"])),
            position_x_percent=round(float(resolved["positionXPercent"])),
            position_y_percent=round(float(resolved["positionYPercent"])),
            font_family=str(resolved.get("fontFamily") or "Bangers"),
            text_color=str(resolved.get("textColor") or "#FFFFFF"),
            karaoke_color=str(resolved.get("karaokeColor") or "#FFEF00"),
            outline_color=str(resolved.get("outlineColor") or "#000000"),
            bold=bool(resolved.get("bold", False)),
            italic=bool(resolved.get("italic", False)),
            uppercase=bool(resolved.get("uppercase", False)),
            shadow=round(float(resolved.get("shadow", 2))),
            letter_spacing=float(resolved.get("letterSpacing", resolved.get("letter_spacing", 0)) or 0),
            alignment=str(resolved.get("alignment") or "center"),
        )
        subtitles = [
            srt.Subtitle(
                index=i + 1,
                start=timedelta(seconds=float(segment.get("start", 0) or 0)),
                end=timedelta(seconds=max(
                    float(segment.get("start", 0) or 0) + 0.1,
                    float(segment.get("end", segment.get("start", 0)) or 0),
                )),
                content=" ".join(str(segment.get("text") or "").split()),
            )
            for i, segment in enumerate(members)
        ]
        group = directory / f"style-{group_index}"
        group.mkdir(parents=True, exist_ok=True)
        source = group / "captions.srt"
        source.write_text(srt.compose(subtitles), encoding="utf-8")
        target = group / "captions.ass"
        region = SubtitleRegionLayout(
            0, 0, int(resolved["layoutWidth"]), int(resolved["layoutHeight"])
        )
        _write_positioned_ass(
            str(source), str(target), style,
            int(resolved["outputWidth"]), int(resolved["outputHeight"]),
            region, fixed_font_size=True,
            speech_durations={i + 1: max(0.1, float(segment["_speech_end"]) - float(segment.get("start", 0)))
                              for i, segment in enumerate(members) if segment.get("_speech_end") is not None},
        )
        text = target.read_text(encoding="utf-8")
        header = text.split("Dialogue:", 1)[0]
        if not first_header:
            first_header = header
        for line in text.splitlines():
            if not line.startswith("Dialogue:"):
                continue
            fields = line.split(",", 9)
            events.append({
                "start": timestamp(fields[1]),
                "end": timestamp(fields[2]),
                "body": fields[9],
                "header": header,
                "layout": resolved,
            })
    events.sort(key=lambda item: (item["start"], item["end"]))
    return first_header, events


def _karaoke_line_regions(body, alpha):
    """Pair disjoint ink bands with the continuous clock in export's ASS tags."""
    lines = body.split(r"\N")
    bounds = alpha.getbbox() or (0, 0, 1, 1)
    top, bottom = bounds[1], bounds[3]
    rows = alpha.getprojection()[1]
    gaps = []
    gap_start = None
    for y in range(top, bottom):
        if not rows[y] and gap_start is None:
            gap_start = y
        elif rows[y] and gap_start is not None:
            gaps.append((y - gap_start, (y + gap_start) // 2))
            gap_start = None
    # Accent gaps are smaller than inter-line gaps. Never let one line's mask
    # overlap another; even touching heavy outlines get disjoint fallback bands.
    if len(gaps) >= len(lines) - 1:
        cuts = sorted(midpoint for _, midpoint in sorted(gaps, reverse=True)[:len(lines) - 1])
    else:
        cuts = [round(top + (bottom - top) * i / len(lines)) for i in range(1, len(lines))]
    edges = [top, *cuts, bottom]
    result = []
    clock = 0
    for index, line in enumerate(lines):
        y0, y1 = edges[index:index + 2]
        ink = alpha.crop((0, y0, alpha.width, y1)).getbbox()
        x0, ink_y0, x1, ink_y1 = ink or (0, 0, 0, y1 - y0)
        duration = sum(int(value) for value in re.findall(r"\\k[fFoO]?(\d+)", line))
        result.append(dict(x=x0, y=y0 + ink_y0, width=x1 - x0, height=ink_y1 - ink_y0,
                           startCs=clock, durationCs=duration))
        clock += duration
    return result


def rasterize(header, body, layout, directory):
    # Bump this prefix whenever sprite composition changes. Otherwise a frame
    # produced by an older renderer can silently survive an application update.
    key = sprite_key(header, body, layout)[:24]
    directory = directory / key
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / "complete.json"
    if marker.exists():
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
            if (isinstance(value, dict) and "normal" in value and "karaoke" in value
                    and all((directory / name).is_file()
                            and (directory / name).stat().st_size > 0
                            for name in ("normal.png", "karaoke.png"))):
                for name in ("normal.png", "karaoke.png"):
                    with Image.open(directory / name) as image:
                        if image.size != (int(layout["outputWidth"]), int(layout["outputHeight"])):
                            raise ValueError("Unexpected caption raster dimensions")
                return value
        except (OSError, ValueError):
            pass  # Interrupted cache publication is rebuilt, not a lost cue.
    # Both images retain libass's spacing, shadow, outline and alpha coverage.
    clean = re.sub(r"\\k[fFoO]?\d+", "", body)
    # Per-cue style overrides may already set primary/secondary colours. Remove
    # those two tags before producing the two otherwise-identical sprites so the
    # requested normal/karaoke colour cannot be overridden later in the line.
    clean = re.sub(r"\\[12]c&H[0-9A-Fa-f]{6,8}&?", "", clean)
    def ass_bgr(value, fallback):
        color = str(value or fallback).lstrip("#")
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", color):
            color = fallback.lstrip("#")
        return f"{color[4:6]}{color[2:4]}{color[0:2]}".upper()

    for name, color in (
        ("normal", ass_bgr(layout.get("textColor"), "#FFFFFF")),
        ("karaoke", ass_bgr(layout.get("karaokeColor"), "#FFEF00")),
    ):
        ass = directory / f"{name}.ass"
        ass.write_text(
            header + f"Dialogue: 0,0:00:00.00,0:00:10.00,Default,,0,0,0,,"
            f"{{\\1c&H{color}&\\2c&H{color}&}}{clean}\n", encoding="utf-8")
    fonts = str(_karaoke_font_directory()).replace("\\", "/").replace(":", "\\:")
    width, height = int(layout["outputWidth"]), int(layout["outputHeight"])
    command = [_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
        f"color=c=black@0:s={width}x{height}:r=1,format=rgba", "-filter_complex",
        f"[0:v]split[a][b];[a]ass=normal.ass:fontsdir='{fonts}':alpha=1[n];"
        f"[b]ass=karaoke.ass:fontsdir='{fonts}':alpha=1[k]",
        "-map", "[n]", "-frames:v", "1", "-threads", "1", "normal.png",
        "-map", "[k]", "-frames:v", "1", "-threads", "1", "karaoke.png"]
    subprocess.run(command, cwd=directory, check=True, capture_output=True, timeout=20,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with Image.open(directory / "normal.png") as image:
        alpha = image.getchannel("A")
        bounds = alpha.getbbox() or (0, 0, 1, 1)
        karaoke_lines = _karaoke_line_regions(body, alpha)
    value = {"normal": QUrl.fromLocalFile(str(directory / "normal.png")).toString(),
             "karaoke": QUrl.fromLocalFile(str(directory / "karaoke.png")).toString(),
             "x": bounds[0], "y": bounds[1], "width": bounds[2] - bounds[0],
             "height": bounds[3] - bounds[1], "fontSize": int(layout["fontSize"]),
             "outputWidth": width, "outputHeight": height,
             "positionXPercent": layout["positionXPercent"], "positionYPercent": layout["positionYPercent"],
             "karaokeLines": karaoke_lines, "lineCount": len(karaoke_lines)}
    marker.write_text(json.dumps(value), encoding="utf-8")
    return value


class SubtitleOverlayRenderer(QObject):
    changed = Signal()
    _ready = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = {}
        self._events = []
        self._indexed_events = None
        self._event_starts = []
        self._event_max_ends = []
        self._event_keys = []
        self._header = ""
        self._layout = {}
        self._key = ""
        self._time = 0.0
        self._generation = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="subtitle-libass")
        self._cache = {}
        self._pending = set()
        self._frame_futures = {}
        self._futures = set()
        self._closed = False
        self._reconfiguring = False
        self._retain_frame = False
        self._frame_window = None
        self._ready.connect(self._accept)
        self._root = Path(RUNTIME_DATA_DIR) / "cache" / "subtitle-overlays"

    @Property("QVariantMap", notify=changed)
    def frame(self):
        return dict(self._frame)

    @Slot(str, str, bool)
    @Slot(str, str, bool, bool)
    def configure(self, payload, layout_json, fixed, preserve_frame=False):
        segments, layout = json.loads(payload), json.loads(layout_json)
        caption_inputs = [{name: segment.get(name) for name in ("start", "end", "text", "_style", "_speech_end")}
                          for segment in segments]
        # Publication revisions, speaker metadata and OCR state do not change
        # the ASS output. Keep the visible cue attached on those refreshes.
        key = hashlib.sha256(json.dumps(
            [caption_inputs, layout, fixed], sort_keys=True, ensure_ascii=False,
        ).encode()).hexdigest()
        if key == self._key:
            self._retain_frame = preserve_frame
            return
        self._key = key
        self._generation += 1
        generation = self._generation
        self._reconfiguring = True
        self._retain_frame = preserve_frame
        self._events = []
        self._pending.clear()
        self._frame_futures.clear()
        for future in tuple(self._futures):
            future.cancel()
        if self._frame and not preserve_frame:
            self._frame = {}
            self.changed.emit()
        self._layout = layout
        def build():
            try:
                self._root.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(dir=self._root) as work:
                    header, events = export_events(segments, layout, fixed, Path(work))
                return ("events", generation, header, events)
            except Exception as exc:
                return ("error", generation, str(exc))
        self._submit(build)

    def _submit(self, operation):
        future = self._executor.submit(operation)
        self._futures.add(future)

        def deliver(completed):
            self._futures.discard(completed)
            self._deliver(completed)

        future.add_done_callback(deliver)
        return future

    def _deliver(self, future):
        if not self._closed and not future.cancelled():
            self._ready.emit(future.result())

    @Slot()
    def clear(self):
        """Release a closed sample dialog without tearing down its worker pool."""
        self.release()
        self._cache.clear()

    @Slot(float)
    def seek(self, seconds):
        self._time = seconds
        can_retain = self._retain_frame and self._frame_window is not None \
            and self._frame_window[0] <= seconds < self._frame_window[1]
        if self._reconfiguring and can_retain:
            return
        if self._reconfiguring:
            if self._frame:
                self._frame = {}
                self.changed.emit()
            return
        self._ensure_event_index()
        latest_start = bisect.bisect_right(self._event_starts, seconds) - 1
        index = bisect.bisect_right(self._event_max_ends, seconds)
        event = self._events[index] if 0 <= index <= latest_start else None
        if event is None:
            if self._frame:
                self._frame = {}
                self.changed.emit()
            return
        key = self._event_keys[index]
        legacy_key = (self._generation, event["body"])
        if key not in self._cache and legacy_key in self._cache:
            key = legacy_key
        if key in self._cache:
            self._frame_window = (event["start"], event["end"])
            frame = dict(self._cache[key])
            frame["text"] = re.sub(r"\{[^}]*\}", "", event["body"]).replace(r"\N", "\n")
            frame["progress"] = min(1, max(0, (seconds-event["start"])/max(.01, event["end"]-event["start"])))
            elapsed_cs = (seconds - event["start"]) * 100
            frame["karaokeLines"] = [
                dict(line, progress=min(1, max(0,
                    (elapsed_cs - line["startCs"]) / line["durationCs"]
                    if line["durationCs"] else float(elapsed_cs >= line["startCs"]))))
                for line in frame.get("karaokeLines", [])
            ]
            if frame != self._frame:
                self._frame = frame
                self.changed.emit()
        else:
            if self._frame and not can_retain:
                self._frame = {}
                self.changed.emit()
            pending_key = (self._generation, key)
            if pending_key not in self._pending:
                # A seek must not wait behind a queue of obsolete lookahead
                # frames. Running FFmpeg is bounded to one job; queued jobs can
                # be cancelled before the requested cue is submitted first.
                for queued_key, future in tuple(self._frame_futures.items()):
                    if future.cancel():
                        self._frame_futures.pop(queued_key, None)
                        self._pending.discard(queued_key)
            self._request_frame(event)
        for upcoming_index in range(index + 1, min(len(self._events), index + 13)):
            upcoming = self._events[upcoming_index]
            if upcoming["start"] > seconds + 8:
                break
            self._request_frame(upcoming, self._event_keys[upcoming_index])

    def _ensure_event_index(self):
        if self._indexed_events is self._events and len(self._event_keys) == len(self._events):
            return
        self._indexed_events = self._events
        self._event_starts = [event["start"] for event in self._events]
        maximum = float("-inf")
        self._event_max_ends = []
        for event in self._events:
            maximum = max(maximum, event["end"])
            self._event_max_ends.append(maximum)
        self._event_keys = [self._event_key(event) for event in self._events]

    def _event_key(self, event):
        return sprite_key(str(event.get("header") or self._header), event["body"],
                          event.get("layout") or self._layout)

    def _request_frame(self, event, cache_key=None):
        cache_key = cache_key or self._event_key(event)
        key = (self._generation, cache_key)
        if cache_key in self._cache or key in self._pending or self._closed:
            return
        self._pending.add(key)
        header = str(event.get("header") or self._header)
        body = event["body"]
        layout = dict(event.get("layout") or self._layout)
        def render():
            try:
                if key[0] != self._generation:
                    return ("failed_frame", key, "superseded")
                return ("frame", key, rasterize(header, body, layout, self._root))
            except Exception as exc:
                return ("failed_frame", key, str(exc))
        self._frame_futures[key] = self._submit(render)

    @Slot(object)
    def _accept(self, result):
        if result[0] == "events" and result[1] == self._generation:
            self._reconfiguring = False
            self._header, self._events = result[2:]
            self.seek(self._time)
        elif result[0] == "error" and result[1] == self._generation:
            self._reconfiguring = False
            self._key = ""
            logger.warning("Caption preview configuration failed: %s", result[2])
            self.seek(self._time)
        elif result[0] == "frame":
            self._pending.discard(result[1])
            self._frame_futures.pop(result[1], None)
            # Revisions are delivery guards, not raster identities. OCR/audio
            # refreshes must reuse unchanged captions without another FFmpeg
            # job or a blank frame at each subtitle boundary.
            self._cache[result[1][1]] = result[2]
            if len(self._cache) > 128:
                self._cache.pop(next(iter(self._cache)))
            if result[1][0] == self._generation:
                self.seek(self._time)
        elif result[0] == "failed_frame":
            self._pending.discard(result[1])
            self._frame_futures.pop(result[1], None)
            if result[1][0] == self._generation:
                logger.warning("Caption preview raster failed: %s", result[2])

    @Slot()
    def release(self):
        """Detach editor state while retaining reusable raster cache entries."""
        self._generation += 1
        self._reconfiguring = False
        self._retain_frame = False
        self._frame_window = None
        self._key = ""
        self._events = []
        self._header = ""
        self._indexed_events = None
        self._event_starts = []
        self._event_max_ends = []
        self._event_keys = []
        self._layout = {}
        self._pending.clear()
        self._frame_futures.clear()
        for future in tuple(self._futures):
            future.cancel()
        if self._frame:
            self._frame = {}
            self.changed.emit()

    def close(self):
        self._closed = True
        self.release()
        for future in tuple(self._futures):
            future.cancel()
        self._futures.clear()
        self._pending.clear()
        self._executor.shutdown(wait=False, cancel_futures=True)
