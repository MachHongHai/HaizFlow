"""Transparent libass caption frames, using the export ASS writer verbatim."""
from __future__ import annotations

import hashlib
import json
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


def timestamp(value):
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def export_events(segments, layout, fixed, directory):
    """Render one segment clock with the same ASS fitting as final export."""
    style = SubtitleStyle(font_size=int(layout["fontSize"]), outline=int(layout["outline"]),
        position_x_percent=int(layout["positionXPercent"]), position_y_percent=int(layout["positionYPercent"]))
    # Keep the editable segment intact here. _write_positioned_ass partitions
    # it into visual phrases using the current font/layout while retaining one
    # global word clock. Pre-splitting into SRT cues made size changes alter
    # the apparent karaoke timing.
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
        for i, segment in enumerate(segments)
        if str(segment.get("text") or "").strip()
    ]
    if not subtitles:
        return "", []
    source = directory / "captions.srt"
    source.write_text(srt.compose(subtitles), encoding="utf-8")
    target = directory / "captions.ass"
    region = SubtitleRegionLayout(0, 0, int(layout["layoutWidth"]), int(layout["layoutHeight"]))
    _write_positioned_ass(str(source), str(target), style, int(layout["outputWidth"]),
                          int(layout["outputHeight"]), region, fixed_font_size=True)
    text = target.read_text(encoding="utf-8")
    header = text.split("Dialogue:", 1)[0]
    events = []
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        fields = line.split(",", 9)
        events.append({"start": timestamp(fields[1]), "end": timestamp(fields[2]), "body": fields[9]})
    return header, events


def rasterize(header, body, layout, directory):
    key = hashlib.sha256((header + body).encode()).hexdigest()[:24]
    directory = directory / key
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / "complete.json"
    if marker.exists():
        value = json.loads(marker.read_text(encoding="utf-8"))
        if all((directory / name).is_file() for name in ("normal.png", "karaoke.png")):
            return value
    # Both images retain libass's spacing, shadow, outline and alpha coverage.
    clean = re.sub(r"\{\\k[fFoO]?\d+\}", "", body)
    for name, color in (("normal", "FFFFFF"), ("karaoke", "00EFFF")):
        ass = directory / f"{name}.ass"
        ass.write_text(header + f"Dialogue: 0,0:00:00.00,0:00:10.00,Default,,0,0,0,,{{\\1c&H{color}&}}{clean}\n",
                       encoding="utf-8")
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
        bounds = image.getchannel("A").getbbox() or (0, 0, 1, 1)
    value = {"normal": QUrl.fromLocalFile(str(directory / "normal.png")).toString(),
             "karaoke": QUrl.fromLocalFile(str(directory / "karaoke.png")).toString(),
             "x": bounds[0], "y": bounds[1], "width": bounds[2] - bounds[0],
             "height": bounds[3] - bounds[1], "fontSize": int(layout["fontSize"]),
             "outputWidth": width, "outputHeight": height,
             "positionXPercent": layout["positionXPercent"], "positionYPercent": layout["positionYPercent"]}
    marker.write_text(json.dumps(value), encoding="utf-8")
    return value


class SubtitleOverlayRenderer(QObject):
    changed = Signal()
    _ready = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = {}
        self._events = []
        self._header = ""
        self._layout = {}
        self._key = ""
        self._time = 0.0
        self._generation = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="subtitle-libass")
        self._cache = {}
        self._pending = set()
        self._futures = set()
        self._closed = False
        self._ready.connect(self._accept)
        self._root = Path(RUNTIME_DATA_DIR) / "cache" / "subtitle-overlays"

    @Property("QVariantMap", notify=changed)
    def frame(self):
        return dict(self._frame)

    @Slot(str, str, bool)
    def configure(self, payload, layout_json, fixed):
        key = hashlib.sha256((payload + layout_json + str(fixed)).encode()).hexdigest()
        if key == self._key:
            return
        self._key = key
        self._generation += 1
        generation = self._generation
        self._events = []
        self._pending.clear()
        for future in tuple(self._futures):
            future.cancel()
        if self._frame:
            self._frame = {}
            self.changed.emit()
        segments, layout = json.loads(payload), json.loads(layout_json)
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

    @Slot(float)
    def seek(self, seconds):
        self._time = seconds
        event = next((e for e in self._events if e["start"] <= seconds < e["end"]), None)
        if event is None:
            if self._frame:
                self._frame = {}
                self.changed.emit()
            return
        key = (self._generation, event["body"])
        if key in self._cache:
            frame = dict(self._cache[key])
            frame["text"] = re.sub(r"\{[^}]*\}", "", event["body"]).replace(r"\N", "\n")
            frame["progress"] = min(1, max(0, (seconds-event["start"])/max(.01, event["end"]-event["start"])))
            if frame != self._frame:
                self._frame = frame
                self.changed.emit()
        else:
            if self._frame:
                self._frame = {}
                self.changed.emit()
            self._request_frame(event)
        index = self._events.index(event)
        for upcoming in self._events[index + 1:index + 3]:
            self._request_frame(upcoming)

    def _request_frame(self, event):
        key = (self._generation, event["body"])
        if key in self._cache or key in self._pending or self._closed:
            return
        self._pending.add(key)
        header, body, layout = self._header, event["body"], dict(self._layout)
        def render():
            try:
                if key[0] != self._generation:
                    return ("failed_frame", key, "superseded")
                return ("frame", key, rasterize(header, body, layout, self._root))
            except Exception as exc:
                return ("failed_frame", key, str(exc))
        self._submit(render)

    @Slot(object)
    def _accept(self, result):
        if result[0] == "events" and result[1] == self._generation:
            self._header, self._events = result[2:]
            self.seek(self._time)
        elif result[0] == "frame":
            self._pending.discard(result[1])
            self._cache[result[1]] = result[2]
            if len(self._cache) > 128:
                self._cache.pop(next(iter(self._cache)))
            if result[1][0] == self._generation:
                self.seek(self._time)
        elif result[0] == "failed_frame":
            self._pending.discard(result[1])

    @Slot()
    def release(self):
        """Detach editor state while retaining reusable raster cache entries."""
        self._generation += 1
        self._key = ""
        self._events = []
        self._header = ""
        self._layout = {}
        self._pending.clear()
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
