"""Asynchronous, output-faithful preview clips for the subtitle editor."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

import srt
from PySide6.QtCore import QUrl

from haizflow.pipeline.audio_timeline import build_audio_timeline
from haizflow.pipeline.process_registry import (
    cancel_video,
    clean_video,
    communicate_process,
    start_video,
)
from haizflow.pipeline.render import map_subtitle_region_to_output_percent, render_video
from haizflow.schemas.video import CropSettings
from haizflow.services import manual_artifacts, video_store
from haizflow.utils.ffmpeg import _binary, get_video_dimensions, get_video_duration


class EditorPreviewController:
    """Render a cached, full-timeline proxy through the production pipeline.

    Requests are generation based. A newer edit cancels the previous FFmpeg
    process and only the latest result may update QML. Files stay inside the
    selected video's workspace, never in the operating-system temp directory.

    QML receives one continuous audio/video proxy, so Windows Media Foundation
    owns a single playback clock. Internally, visual and audio artifacts remain
    independently cached; a fast stream-copy mux publishes their synchronized
    playback file without encoding video frames again. The visual proxy is
    assembled from fixed cached chunks. An
    edit invalidates only overlapping subtitle chunks; unchanged frames are
    stream-copied into the next published proxy instead of being encoded
    again.
    """

    _VISUAL_CHUNK_SECONDS = 12.0

    @staticmethod
    def _manual_voice_artifact(video) -> dict | None:
        """Return only the TTS manifest matching the current Manual document.

        Legacy stage flags are intentionally ignored.  A flag can remain set
        after text or voice settings change, while the immutable artifact
        signature cannot.  This keeps subtitle and audio preview publication
        synchronized.
        """
        if getattr(video, "project_type", "single") != "manual":
            return None
        # ``manual_tools`` is intentionally light to import: model runtimes
        # are loaded only by explicit background tool runners.
        from haizflow.pipeline.manual_tools import active_voice_record

        return active_voice_record(video, validate=False)

    def __init__(self, host):
        self._host = host
        self._lock = threading.RLock()
        self._worker_lock = threading.Lock()
        self._generation = 0
        self._active_process_id = ""
        self._source = ""
        self._base_source = ""
        self._audio_source = ""
        self._busy = False
        self._progress = 0.0
        self._stage = ""
        self._error = ""
        self._start_seconds = 0.0
        self._duration_seconds = 0.0
        self._video_id = ""
        self._request_fingerprint = ""
        self._completed_requests: dict[str, tuple[str, str, float, float, dict, str]] = {}
        self._completed_base_sources: dict[str, tuple[str, dict]] = {}
        self._duration_cache: dict[tuple[str, int, int], float] = {}
        self._published_output_identity: dict = {}
        self._last_progress_emit = 0.0
        self._pin_owner = f"editor-preview:{id(self)}"
        self._pinned_video_id = ""

    @property
    def source(self) -> str:
        with self._lock:
            return self._source

    @property
    def base_source(self) -> str:
        """Subtitle-free visual proxy used for direct on-canvas editing."""
        with self._lock:
            return self._base_source

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    @property
    def audio_source(self) -> str:
        with self._lock:
            return self._audio_source

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    @property
    def progress(self) -> float:
        with self._lock:
            return self._progress

    @property
    def stage(self) -> str:
        with self._lock:
            return self._stage

    @property
    def start_seconds(self) -> float:
        with self._lock:
            return self._start_seconds

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            return self._duration_seconds

    @staticmethod
    def _model_dict(value) -> dict:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        dump = getattr(value, "model_dump", None)
        if callable(dump):
            result = dump()
            return dict(result) if isinstance(result, dict) else {}
        return {}

    @staticmethod
    def _file_identity(path_value: object) -> dict:
        """Return a small cache fingerprint without reading large media files."""
        raw_path = str(path_value or "").strip()
        if not raw_path:
            return {}
        path = os.path.abspath(raw_path)
        try:
            stat = os.stat(path)
        except OSError:
            return {"path": path, "missing": True}
        return {
            "path": path,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }

    @staticmethod
    def _write_silent_wav(path: Path, duration_seconds: float) -> None:
        sample_rate = 48_000
        frames = max(1, round(duration_seconds * sample_rate))
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            silence = b"\x00\x00" * min(frames, sample_rate)
            remaining = frames
            while remaining > 0:
                count = min(remaining, sample_rate)
                output.writeframesraw(silence[: count * 2])
                remaining -= count

    @staticmethod
    def _write_window_srt(path: Path, segments: list[dict], start: float, duration: float) -> None:
        end = start + duration
        subtitles: list[srt.Subtitle] = []
        for segment in segments:
            segment_start = max(start, float(segment.get("start", 0) or 0))
            segment_end = min(end, float(segment.get("end", 0) or 0))
            content = " ".join(str(segment.get("text", "") or "").split())
            if not content or segment_end <= segment_start + 0.01:
                continue
            subtitles.append(
                srt.Subtitle(
                    index=len(subtitles) + 1,
                    start=datetime.timedelta(seconds=segment_start - start),
                    end=datetime.timedelta(seconds=segment_end - start),
                    content=content,
                )
            )
        if not subtitles:
            subtitles.append(
                srt.Subtitle(
                    index=1,
                    start=datetime.timedelta(0),
                    end=datetime.timedelta(seconds=min(0.08, duration)),
                    content="\u200b",
                )
            )
        path.write_text(srt.compose(subtitles), encoding="utf-8")

    @staticmethod
    def _ocr_region(video_dir: Path, configured_path: str = "") -> dict:
        for path in (
            Path(configured_path) if configured_path else None,
            video_dir / "temp" / "original_subtitle_region.json",
        ):
            if path is None:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                region = payload.get("region", payload) if isinstance(payload, dict) else {}
                if isinstance(region, dict) and region:
                    return dict(region)
            except (OSError, TypeError, json.JSONDecodeError):
                continue
        return {}

    @staticmethod
    def _source_subtitle_intervals(video_dir: Path, configured_path: str = "") -> list[tuple[float, float]]:
        """Read source-caption visibility windows without changing OCR bounds."""
        segments = EditorPreviewController._load_segments(
            configured_path or str(video_dir / "temp" / "source_segments.json")
        )
        intervals: list[tuple[float, float]] = []
        for segment in segments:
            try:
                start = max(0.0, float(segment.get("start", 0) or 0))
                end = max(start, float(segment.get("end", start) or start))
            except (TypeError, ValueError):
                continue
            if end > start + 0.01:
                intervals.append((round(start, 3), round(end, 3)))
        return intervals

    @staticmethod
    def _visual_cache_payload(settings: dict) -> dict:
        """Keep audio-only changes from invalidating the visual proxy."""
        removes_source_text = bool(settings["remove_original_subtitles"])
        return {
            "video_id": settings["video_id"],
            "source_identity": settings["source_identity"],
            "segments": [
                {
                    "start": item.get("start", 0),
                    "end": item.get("end", 0),
                    "text": item.get("text", ""),
                }
                for item in settings["segments"]
            ],
            "subtitle_style": settings["subtitle_style"],
            "crop": settings["crop"],
            "output_format": settings["output_format"],
            "subtitle_layout_override": settings["subtitle_layout_override"],
            "remove_original_subtitles": removes_source_text,
            # Blur/patch/OCR are irrelevant while the source is unchanged.
            # Normalizing them gives "Giữ nguyên" one stable cache identity.
            "removal_mode": settings["removal_mode"] if removes_source_text else "keep",
            "watermark_text": settings["watermark_text"],
            "ocr_region": settings["ocr_region"] if removes_source_text else {},
            "original_subtitle_intervals": settings["original_subtitle_intervals"] if removes_source_text else [],
            "preview_encoding": settings["preview_encoding"],
        }

    @staticmethod
    def _base_visual_cache_payload(settings: dict) -> dict:
        """Fingerprint source effects that do not depend on translated text."""
        removes_source_text = bool(settings["remove_original_subtitles"])
        return {
            "video_id": settings["video_id"],
            "source_identity": settings["source_identity"],
            "crop": settings["crop"],
            "output_format": settings["output_format"],
            "remove_original_subtitles": removes_source_text,
            "removal_mode": settings["removal_mode"] if removes_source_text else "keep",
            "watermark_text": settings["watermark_text"],
            "ocr_region": settings["ocr_region"] if removes_source_text else {},
            "original_subtitle_intervals": settings["original_subtitle_intervals"] if removes_source_text else [],
            "preview_encoding": settings["preview_encoding"],
        }

    @staticmethod
    def _audio_cache_payload(settings: dict) -> dict:
        """Fingerprint only data that can change the audible preview mix."""
        voice_ready = bool((settings.get("voice_state") or {}).get("ready"))
        audio_inputs = dict(settings["audio_inputs"])
        if not voice_ready:
            # Text, voice choice and clone reference are inaudible until an
            # exact Manual TTS manifest exists. Keep the original/music mix
            # hot while translation and subtitle layers are edited.
            audio_inputs.pop("transcript_json", None)
            audio_inputs.pop("voice_reference", None)
            audio_inputs.pop("voice_output", None)
        return {
            "video_id": settings["video_id"],
            "source_identity": settings["source_identity"],
            "segments": [
                {
                    "start": item.get("start", 0),
                    "end": item.get("end", 0),
                    "text": item.get("text", ""),
                    "speaker": item.get("speaker", ""),
                }
                for item in (settings["segments"] if voice_ready else [])
            ],
            "tts_provider": settings["tts_provider"] if voice_ready else "",
            "tts_voice": settings["tts_voice"] if voice_ready else "",
            "target_language": settings["target_language"] if voice_ready else "",
            "speaker_mode": settings["speaker_mode"] if voice_ready else "",
            "original_video_volume": settings["original_video_volume"],
            "background_music_volume": settings["background_music_volume"],
            "tts_volume": settings["tts_volume"],
            "audio_inputs": audio_inputs,
            "voice_state": settings.get("voice_state", {}),
            "duration": settings["duration"],
            "audio_cache_version": "editor-audio-v4-optional-voice-layer",
        }

    @classmethod
    def _visual_chunk_cache_payload(
        cls,
        settings: dict,
        base_signature: str,
        start: float,
        duration: float,
    ) -> dict:
        """Fingerprint only captions that overlap one preview chunk."""
        end = start + duration
        return {
            "base_signature": base_signature,
            "start": round(start, 3),
            "duration": round(duration, 3),
            "segments": [
                {
                    "start": item.get("start", 0),
                    "end": item.get("end", 0),
                    "text": item.get("text", ""),
                }
                for item in settings["segments"]
                if float(item.get("end", 0) or 0) > start
                and float(item.get("start", 0) or 0) < end
            ],
            "subtitle_style": settings["subtitle_style"],
            "subtitle_layout_override": settings["subtitle_layout_override"],
            "preview_encoding": settings["preview_encoding"],
        }

    @classmethod
    def _visual_chunk_windows(cls, duration: float) -> list[tuple[float, float]]:
        windows: list[tuple[float, float]] = []
        start = 0.0
        while start < duration - 0.001:
            chunk_duration = min(cls._VISUAL_CHUNK_SECONDS, duration - start)
            windows.append((round(start, 3), round(chunk_duration, 3)))
            start += cls._VISUAL_CHUNK_SECONDS
        return windows

    def request(self, payload: str, playhead_seconds: float) -> bool:
        # Kept in the public slot for QML/API compatibility. A full-timeline
        # proxy is independent of the current playhead and can be reused for
        # every seek operation.
        _ = playhead_seconds
        video = self._host._selected_video()
        if not video:
            return False
        try:
            segments = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return False
        if not isinstance(segments, list):
            return False

        source_path = self._host._resolve_video_file(
            video,
            ("video_input", "input_video"),
            ("input", "video.mp4"),
        )
        if not source_path or not os.path.isfile(source_path):
            return False

        video_dir = Path(video_store.get_video_dir(video.video_id))
        files = dict(getattr(video, "files", {}) or {})
        ocr_region = self._ocr_region(video_dir, str(files.get("ocr_region") or ""))
        original_subtitle_intervals = self._source_subtitle_intervals(
            video_dir,
            str(files.get("source_segments") or ""),
        )
        settings = {
            "video_id": video.video_id,
            "source_path": os.path.abspath(source_path),
            "source_identity": self._file_identity(source_path),
            "segments": segments,
            "subtitle_style": self._model_dict(getattr(video, "subtitle_style", None)),
            "crop": self._model_dict(getattr(video, "crop", None)),
            "output_format": str(getattr(video, "output_format", "keep_ratio") or "keep_ratio"),
            "subtitle_layout_override": bool(getattr(video, "subtitle_layout_override", False)),
            "remove_original_subtitles": bool(getattr(video, "remove_original_subtitles", True)),
            "removal_mode": str(getattr(video, "original_subtitle_removal_mode", "patch") or "patch"),
            "watermark_text": str(getattr(video, "watermark_text", "") or ""),
            "tts_provider": str(getattr(video, "tts_provider", "edge") or "edge"),
            "tts_voice": str(getattr(video, "tts_voice", "") or ""),
            "target_language": str(getattr(video, "target_language", "vi") or "vi"),
            "speaker_mode": str(getattr(video, "speaker_mode", "single") or "single"),
            "original_video_volume": int(getattr(video, "original_video_volume", 60) or 0),
            "background_music_volume": int(getattr(video, "background_music_volume", 30) or 0),
            "tts_volume": int(getattr(video, "tts_volume", 100) or 0),
            # Audio-layer and clone-reference changes must invalidate a cached
            # mix even when subtitle text and the visual filter graph did not
            # change. Only metadata is hashed; large media is never read here.
            "audio_inputs": {
                key: self._file_identity(files.get(key))
                for key in (
                    "background_audio",
                    "background_music",
                    "voice_reference",
                    "voice_output",
                    "transcript_json",
                )
            },
            # Voice parts are stored as a directory, so their durable
            # checkpoint—not a file identity—is the correct invalidation
            # source. Without it, completing Manual TTS looked identical to
            # the earlier visual-only request and QML kept silent audio until
            # the user opened the Audio tool.
            "voice_state": (
                {
                    "artifact": str(manual_voice.get("artifact_id") or ""),
                    "signature": str(manual_voice.get("signature") or ""),
                    "ready": True,
                }
                if (manual_voice := self._manual_voice_artifact(video))
                else {
                    "checkpoint": str((getattr(video, "checkpoints", {}) or {}).get("voice") or ""),
                    "ready": (
                        getattr(video, "project_type", "single") != "manual"
                        and "voice" in set(getattr(video, "manual_completed_stages", []) or [])
                    ),
                }
            ),
            "ocr_region": ocr_region,
            "original_subtitle_intervals": original_subtitle_intervals,
            # Version the proxy cache when its encoding contract changes.
            "preview_encoding": "layered-full-timeline-sdr-yuv420p-v5",
        }
        preview_dir = video_dir / "temp" / "editor-preview"
        fingerprint_settings = dict(settings)
        if not settings["remove_original_subtitles"]:
            fingerprint_settings.update(
                removal_mode="keep",
                ocr_region={},
                original_subtitle_intervals=[],
            )
        request_fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_settings,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        settings["request_fingerprint"] = request_fingerprint

        cache_hit = False
        with self._lock:
            # Text editing, focus changes and draft auto-save can coalesce into
            # the same QML request. Never cancel a useful FFmpeg/TTS worker just
            # to start the exact same work again.
            if request_fingerprint == self._request_fingerprint:
                if self._busy:
                    return True
                if self._stage == "ready" and self._source and self._published_source_is_intact():
                    return True
            completed = self._completed_requests.get(request_fingerprint)
            if completed:
                (
                    cached_video,
                    cached_audio,
                    cached_start,
                    cached_duration,
                    cached_identity,
                    cached_visual_signature,
                ) = completed
                video_intact = (
                    Path(cached_video).is_file()
                    and self._file_identity(cached_video) == cached_identity
                )
                audio_intact = not cached_audio or Path(cached_audio).is_file()
                if video_intact and audio_intact:
                    self._generation += 1
                    generation = self._generation
                    previous_process_id = self._active_process_id
                    self._active_process_id = ""
                    self._source = QUrl.fromLocalFile(str(Path(cached_video).resolve())).toString()
                    cached_base = self._completed_base_sources.get(request_fingerprint)
                    if cached_base and Path(cached_base[0]).is_file() and self._file_identity(
                        cached_base[0]
                    ) == cached_base[1]:
                        self._base_source = QUrl.fromLocalFile(
                            str(Path(cached_base[0]).resolve())
                        ).toString()
                    else:
                        self._base_source = ""
                    self._audio_source = (
                        QUrl.fromLocalFile(str(Path(cached_audio).resolve())).toString() if cached_audio else ""
                    )
                    self._busy = False
                    self._progress = 1.0
                    self._stage = "ready"
                    self._error = ""
                    self._video_id = video.video_id
                    self._request_fingerprint = request_fingerprint
                    self._start_seconds = cached_start
                    self._duration_seconds = cached_duration
                    self._published_output_identity = self._file_identity(cached_video)
                    self._last_progress_emit = 0.0
                    if getattr(video, "project_type", "single") == "manual":
                        if self._pinned_video_id and self._pinned_video_id != video.video_id:
                            manual_artifacts.unpin(self._pinned_video_id, self._pin_owner)
                        manual_artifacts.pin(
                            video.video_id,
                            "visual_proxy",
                            cached_visual_signature,
                            self._pin_owner,
                        )
                        self._pinned_video_id = video.video_id
                    cache_hit = True
            if cache_hit:
                process_id = ""
            else:
                self._generation += 1
                generation = self._generation
                previous_process_id = self._active_process_id
                process_id = f"editor-preview-{video.video_id}-{generation}"
                self._active_process_id = process_id
                self._busy = True
                self._progress = 0.0
                self._stage = "preparing"
                self._error = ""
                # Keep the last complete base visible while a replacement is
                # being prepared. It is cleared only when changing project.
                self._video_id = video.video_id
                self._request_fingerprint = request_fingerprint
                self._last_progress_emit = 0.0
        if previous_process_id:
            cancel_video(previous_process_id)
        self._host.editorPreviewChanged.emit()
        if cache_hit:
            return True

        worker = threading.Thread(
            target=self._render,
            args=(generation, process_id, video, settings, preview_dir),
            name=f"editor-preview-{video.video_id[:8]}",
            daemon=True,
        )
        worker.start()
        return True

    def _request_is_current(self, generation: int, process_id: str) -> bool:
        with self._lock:
            return (
                generation == self._generation
                and process_id == self._active_process_id
                and bool(process_id)
            )

    def _render(self, generation, process_id, video, settings, preview_dir: Path) -> None:
        # Only one preview worker may touch decoder/cache state at a time.
        # A newer request cancels the process used by the current worker and
        # waits here; an obsolete worker can never re-register its process id.
        with self._worker_lock:
            if not self._request_is_current(generation, process_id):
                return
            self._render_current(generation, process_id, video, settings, preview_dir)

    def _render_current(self, generation, process_id, video, settings, preview_dir: Path) -> None:
        try:
            # FFprobe can block on a damaged file.  It must never run on the
            # GUI thread; every request enters this worker before probing.
            total_duration = self._source_duration(settings["source_path"])
            if not self._request_is_current(generation, process_id):
                return
            if total_duration <= 0:
                raise RuntimeError("The source video duration could not be read")
            # The playhead is deliberately absent from the signature. Seeking
            # must reuse the same proxy instead of creating a new FFmpeg job.
            settings["start"] = 0.0
            settings["duration"] = round(total_duration, 3)
            base_signature = hashlib.sha256(
                json.dumps(
                    self._base_visual_cache_payload(settings),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:20]
            visual_signature = hashlib.sha256(
                json.dumps(
                    self._visual_cache_payload(settings),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:20]
            audio_signature = hashlib.sha256(
                json.dumps(
                    self._audio_cache_payload(settings),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:20]
            # Keep expensive source effects in a stable base proxy. Subtitle
            # edits then re-render only a lightweight second layer, matching
            # the render-cache model used by desktop NLEs.
            base_dir = preview_dir / f"base-{base_signature}"
            render_dir = preview_dir / f"visual-{visual_signature}"
            audio_dir = preview_dir / f"audio-{audio_signature}"
            base_output_path = base_dir / "preview.mp4"
            base_completion_path = base_dir / "preview.complete.json"
            output_path = render_dir / "preview.mp4"
            completion_path = render_dir / "preview.complete.json"
            self._remove_stale_files(output_path)
            self._remove_stale_audio_dirs(preview_dir, audio_dir / "preview-audio.wav")
            if not self._request_is_current(generation, process_id):
                return
            base_dir.mkdir(parents=True, exist_ok=True)
            render_dir.mkdir(parents=True, exist_ok=True)
            cache_is_complete = self._preview_cache_is_complete(
                output_path,
                completion_path,
                settings["duration"],
            )
            if not cache_is_complete:
                proxy_subtitle_region = {}
                if settings["ocr_region"]:
                    source_width, source_height = get_video_dimensions(settings["source_path"])
                    proxy_subtitle_region = map_subtitle_region_to_output_percent(
                        settings["ocr_region"],
                        source_width,
                        source_height,
                        settings["output_format"],
                        video.crop,
                    )
                base_is_complete = self._preview_cache_is_complete(
                    base_output_path,
                    base_completion_path,
                    settings["duration"],
                )
                chunk_specs: list[tuple[float, float, Path, Path]] = []
                for chunk_start, chunk_duration in self._visual_chunk_windows(settings["duration"]):
                    chunk_signature = hashlib.sha256(
                        json.dumps(
                            self._visual_chunk_cache_payload(
                                settings,
                                base_signature,
                                chunk_start,
                                chunk_duration,
                            ),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()[:20]
                    chunk_dir = preview_dir / f"chunk-{chunk_signature}"
                    chunk_dir.mkdir(parents=True, exist_ok=True)
                    chunk_specs.append(
                        (
                            chunk_start,
                            chunk_duration,
                            chunk_dir / "preview.mp4",
                            chunk_dir / "preview.complete.json",
                        )
                    )
                missing_chunks = [
                    spec
                    for spec in chunk_specs
                    if not self._preview_cache_is_complete(spec[2], spec[3], spec[1])
                ]
                if not self._request_is_current(generation, process_id):
                    return
                start_video(process_id)
                try:
                    if not base_is_complete:
                        if not self._render_proxy_layer(
                            generation,
                            process_id,
                            video,
                            settings["source_path"],
                            base_output_path,
                            base_completion_path,
                            [],
                            settings["duration"],
                            settings["output_format"],
                            video.crop,
                            settings["ocr_region"] if settings["remove_original_subtitles"] else None,
                            settings["watermark_text"],
                            False,
                            settings["removal_mode"],
                            0.03,
                            0.39,
                            subtitle_region_override=None,
                            original_subtitle_intervals=settings["original_subtitle_intervals"],
                        ):
                            return
                    chunk_progress_start = 0.44 if not base_is_complete else 0.03
                    chunk_progress_span = 0.18 if not base_is_complete else 0.57
                    per_chunk_span = chunk_progress_span / max(1, len(missing_chunks))
                    for index, (chunk_start, chunk_duration, chunk_path, chunk_marker) in enumerate(
                        missing_chunks
                    ):
                        if not self._render_proxy_layer(
                            generation,
                            process_id,
                            video,
                            str(base_output_path),
                            chunk_path,
                            chunk_marker,
                            settings["segments"],
                            chunk_duration,
                            "keep_ratio",
                            CropSettings(),
                            None,
                            "",
                            settings["subtitle_layout_override"],
                            settings["removal_mode"],
                            chunk_progress_start + index * per_chunk_span,
                            per_chunk_span,
                            source_start_seconds=chunk_start,
                            subtitle_region_override=proxy_subtitle_region,
                        ):
                            return
                    self._set_progress(generation, 0.63, "assembling")
                    if not self._assemble_preview_chunks(
                        generation,
                        process_id,
                        [spec[2] for spec in chunk_specs],
                        output_path,
                        completion_path,
                        settings["duration"],
                    ):
                        return
                finally:
                    clean_video(process_id)
            if not self._request_is_current(generation, process_id):
                return
            start_video(process_id)
            try:
                audio_path = self._prepare_preview_audio(
                    generation,
                    process_id,
                    video,
                    settings,
                    audio_dir,
                )
                base_playback_path = self._mux_preview_media(
                    generation,
                    process_id,
                    base_output_path,
                    audio_path,
                    preview_dir,
                    settings["duration"],
                    publish_progress=False,
                )
                if base_playback_path is None:
                    return
                playback_path = self._mux_preview_media(
                    generation,
                    process_id,
                    output_path,
                    audio_path,
                    preview_dir,
                    settings["duration"],
                )
                if playback_path is None:
                    return
            finally:
                clean_video(process_id)
            self._set_progress(generation, 0.99, "loading")
            self._finish_success(
                generation,
                playback_path,
                settings["start"],
                settings["duration"],
                video_id=video.video_id,
                request_fingerprint=str(settings.get("request_fingerprint") or ""),
                visual_signature=visual_signature,
                visual_cache_path=output_path,
                base_playback_path=base_playback_path,
            )
        except Exception as exc:
            self._finish_error(generation, str(exc))

    def _render_proxy_layer(
        self,
        generation: int,
        process_id: str,
        video,
        source_path: str,
        output_path: Path,
        completion_path: Path,
        segments: list[dict],
        duration: float,
        output_format: str,
        crop: CropSettings,
        ocr_region: dict | None,
        watermark_text: str,
        subtitle_layout_override: bool,
        removal_mode: str,
        progress_start: float,
        progress_span: float,
        *,
        source_start_seconds: float = 0.0,
        subtitle_region_override: dict | None = None,
        original_subtitle_intervals: list[tuple[float, float]] | None = None,
    ) -> bool:
        """Render and atomically publish one reusable visual cache layer."""
        output_path.unlink(missing_ok=True)
        completion_path.unlink(missing_ok=True)
        render_dir = output_path.parent
        subtitle_path = render_dir / f"subtitles-{generation}.srt"
        silent_path = render_dir / f"silence-{generation}.wav"
        staged_output = render_dir / f"preview-{generation}.rendering.mp4"
        self._write_window_srt(subtitle_path, segments, source_start_seconds, duration)
        self._write_silent_wav(silent_path, duration)
        try:
            self._set_progress(generation, progress_start, "rendering")
            render_video(
                source_path,
                str(silent_path),
                str(subtitle_path),
                str(staged_output),
                output_format,
                video.subtitle_style,
                crop,
                video.video_id,
                ocr_region,
                watermark_text,
                subtitle_layout_override,
                original_subtitle_removal_mode=removal_mode,
                source_start_seconds=source_start_seconds,
                source_duration_seconds=duration,
                process_registry_id=process_id,
                compatibility_preview=True,
                subtitle_region_override=subtitle_region_override,
                original_subtitle_intervals=original_subtitle_intervals,
                progress_callback=lambda fraction: self._set_progress(
                    generation,
                    progress_start + max(0.0, min(1.0, float(fraction))) * progress_span,
                    "rendering",
                ),
            )
            rendered_duration = get_video_duration(str(staged_output))
            if rendered_duration < duration - 0.25:
                raise RuntimeError("Editor preview render ended before the source timeline.")
            with self._lock:
                if generation != self._generation:
                    return False
            os.replace(staged_output, output_path)
            self._write_completion_marker(completion_path, output_path, rendered_duration)
            return True
        finally:
            subtitle_path.unlink(missing_ok=True)
            silent_path.unlink(missing_ok=True)
            staged_output.unlink(missing_ok=True)

    def _assemble_preview_chunks(
        self,
        generation: int,
        process_id: str,
        chunk_paths: list[Path],
        output_path: Path,
        completion_path: Path,
        expected_duration: float,
    ) -> bool:
        """Join cached chunks without re-encoding their video frames."""
        if not chunk_paths:
            raise RuntimeError("Editor preview did not produce any visual chunks.")
        output_path.unlink(missing_ok=True)
        completion_path.unlink(missing_ok=True)
        render_dir = output_path.parent
        staged_output = render_dir / f"preview-{generation}.assembling.mp4"
        concat_path = render_dir / f"preview-{generation}.concat.txt"
        try:
            with self._lock:
                if generation != self._generation:
                    return False
            if len(chunk_paths) == 1:
                shutil.copy2(chunk_paths[0], staged_output)
            else:
                concat_lines = []
                for path in chunk_paths:
                    escaped = str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
                    concat_lines.append(f"file '{escaped}'")
                concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
                process = subprocess.Popen(
                    [
                        "ffmpeg",
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(concat_path),
                        "-c",
                        "copy",
                        "-movflags",
                        "+faststart",
                        str(staged_output),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                _stdout, stderr = communicate_process(
                    process_id,
                    process,
                    label="Editor preview cache assembly",
                )
                if process.returncode != 0:
                    detail = " ".join((stderr or "").split())[-900:]
                    raise RuntimeError(
                        "Editor preview chunks could not be assembled."
                        + (f" FFmpeg: {detail}" if detail else "")
                    )
            rendered_duration = get_video_duration(str(staged_output))
            if rendered_duration < expected_duration - 0.25:
                raise RuntimeError("Editor preview assembly ended before the source timeline.")
            with self._lock:
                if generation != self._generation:
                    return False
            os.replace(staged_output, output_path)
            self._write_completion_marker(
                completion_path,
                output_path,
                rendered_duration,
                chunk_directories=[path.parent.name for path in chunk_paths],
            )
            self._set_progress(generation, 0.65, "assembling")
            return True
        finally:
            staged_output.unlink(missing_ok=True)
            concat_path.unlink(missing_ok=True)

    def _mux_preview_media(
        self,
        generation: int,
        process_id: str,
        visual_path: Path,
        audio_path: Path | None,
        preview_dir: Path,
        expected_duration: float,
        *,
        publish_progress: bool = True,
    ) -> Path | None:
        """Publish one playback file with one clock for QMediaPlayer.

        The visual stream is copied bit-for-bit. Only the already-cached WAV
        mix is encoded to AAC, which is far cheaper than rendering a frame and
        avoids the unreliable pair of independently clocked MediaPlayers used
        by the old Manual editor.
        """
        if audio_path is None or not audio_path.is_file() or audio_path.stat().st_size <= 44:
            return visual_path
        media_signature = hashlib.sha256(
            json.dumps(
                {
                    "visual": self._file_identity(visual_path),
                    "audio": self._file_identity(audio_path),
                    "duration": round(float(expected_duration), 3),
                    "format": "editor-playback-mp4-aac-v1",
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:20]
        media_dir = preview_dir / f"media-{media_signature}"
        media_dir.mkdir(parents=True, exist_ok=True)
        output_path = media_dir / "preview.mp4"
        completion_path = media_dir / "preview.complete.json"
        if self._preview_cache_is_complete(output_path, completion_path, expected_duration):
            self._remove_stale_media_dirs(preview_dir, output_path)
            if publish_progress:
                self._set_progress(generation, 0.97, "loading")
            return output_path

        staged_output = media_dir / f"preview-{generation}.muxing.mp4"
        staged_output.unlink(missing_ok=True)
        if publish_progress:
            self._set_progress(generation, 0.94, "mixing")
        process = subprocess.Popen(
            [
                _binary("ffmpeg"),
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(visual_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-b:a",
                "160k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(staged_output),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            _stdout, stderr = communicate_process(
                process_id,
                process,
                label="Editor preview audio/video mux",
            )
            if not self._request_is_current(generation, process_id):
                return None
            if process.returncode != 0:
                detail = " ".join((stderr or "").split())[-900:]
                raise RuntimeError(
                    "Không thể ghép âm thanh vào bản xem trước."
                    + (f" FFmpeg: {detail}" if detail else "")
                )
            rendered_duration = get_video_duration(str(staged_output))
            if rendered_duration < expected_duration - 0.25:
                raise RuntimeError("Bản xem trước có âm thanh kết thúc sớm hơn video nguồn.")
            if not self._request_is_current(generation, process_id):
                return None
            os.replace(staged_output, output_path)
            self._write_completion_marker(completion_path, output_path, rendered_duration)
            self._remove_stale_media_dirs(preview_dir, output_path)
            if publish_progress:
                self._set_progress(generation, 0.97, "loading")
            return output_path
        finally:
            staged_output.unlink(missing_ok=True)

    def _source_duration(self, source_path: str) -> float:
        """Cache FFprobe by immutable file identity across editor revisions."""
        identity = self._file_identity(source_path)
        key = (
            str(identity.get("path", "")),
            int(identity.get("size", 0) or 0),
            int(identity.get("mtime_ns", 0) or 0),
        )
        with self._lock:
            cached = self._duration_cache.get(key)
        if cached is not None:
            return cached
        duration = get_video_duration(source_path)
        if duration > 0:
            with self._lock:
                # One editor session has one source; bound stale identities.
                self._duration_cache = {key: duration}
        return duration

    def _published_source_is_intact(self) -> bool:
        """Allow a caller to recover if a cached proxy was externally truncated."""
        previous = dict(self._published_output_identity)
        path = str(previous.get("path", ""))
        if not path:
            return False
        current = self._file_identity(path)
        return (
            current.get("path") == previous.get("path")
            and current.get("size") == previous.get("size")
            and current.get("mtime_ns") == previous.get("mtime_ns")
        )

    @staticmethod
    def _write_completion_marker(
        marker_path: Path,
        output_path: Path,
        duration: float,
        *,
        chunk_directories: list[str] | None = None,
    ) -> None:
        payload = {
            "version": 1,
            "duration": round(float(duration), 3),
            "size": output_path.stat().st_size,
        }
        if chunk_directories:
            payload["chunk_directories"] = list(dict.fromkeys(chunk_directories))
        staged = marker_path.with_suffix(".writing.json")
        staged.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.replace(staged, marker_path)

    @classmethod
    def _preview_cache_is_complete(
        cls,
        output_path: Path,
        marker_path: Path,
        expected_duration: float,
    ) -> bool:
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            return False
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if (
                int(marker.get("version", 0)) == 1
                and int(marker.get("size", -1)) == output_path.stat().st_size
                and float(marker.get("duration", 0) or 0) >= expected_duration - 0.25
            ):
                return True
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
        # Backward-compatible one-time validation for proxies created before
        # completion markers existed. Future hits avoid FFprobe entirely.
        duration = get_video_duration(str(output_path))
        if duration < expected_duration - 0.25:
            return False
        try:
            cls._write_completion_marker(marker_path, output_path, duration)
        except OSError:
            pass
        return True

    @staticmethod
    def _load_segments(path: str) -> list[dict]:
        try:
            with open(path, encoding="utf-8") as file:
                value = json.load(file)
            return value if isinstance(value, list) else []
        except (OSError, TypeError, json.JSONDecodeError):
            return []

    @staticmethod
    def _same_spoken_line(current: dict, baseline: dict) -> bool:
        return " ".join(str(current.get("text", "") or "").split()) == " ".join(
            str(baseline.get("text", "") or "").split()
        )

    @staticmethod
    def _link_or_copy(source: Path, target: Path) -> None:
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)

    @staticmethod
    def _voice_cache_key(segment: dict, settings: dict) -> str:
        """Key a voice clip by audible inputs, independent of timeline index."""
        payload = {
            "text": " ".join(str(segment.get("text", "") or "").split()),
            "provider": settings["tts_provider"],
            "voice": settings["tts_voice"],
            "language": settings["target_language"],
            "speaker_mode": settings["speaker_mode"],
            "voice_reference": settings.get("audio_inputs", {}).get("voice_reference", {}),
        }
        if settings["speaker_mode"] == "multiple":
            # Multi-speaker cloning derives identity from the source interval,
            # so identical translated text at another timestamp is not the
            # same audible clip.
            payload["source_start"] = round(float(segment.get("start", 0) or 0), 3)
            payload["source_end"] = round(float(segment.get("end", 0) or 0), 3)
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _prepare_preview_audio(
        self,
        generation: int,
        process_id: str,
        video,
        settings: dict,
        render_dir: Path,
    ) -> Path | None:
        """Rebuild a preview mix exclusively from already generated clips.

        Preview is a cache/mix operation, never a hidden TTS entry point.
        Timing and level edits reuse existing voice parts.  If text changes
        and no exact cached clip exists, the currently published synchronized
        preview remains visible until the user explicitly runs the Voice tool.
        """
        is_manual = getattr(video, "project_type", "single") == "manual"
        status = str(getattr(video, "status", "") or "")
        # A Manual tool is not a linear pipeline stage. Existing source,
        # separation and TTS artifacts remain valid while another tool is
        # queued or running, so the editor must keep its audible mix alive.
        # Auto/Batch retain their stricter completed-output gate.
        if not is_manual and status not in {"done", "manual_ready"}:
            return None
        manual_voice = self._manual_voice_artifact(video)
        files = dict(getattr(video, "files", {}) or {})
        transcript_path = str(files.get("transcript_json") or "")
        baseline = self._load_segments(transcript_path)
        segments = settings["segments"]

        render_dir.mkdir(parents=True, exist_ok=True)
        preview_mix = render_dir / "preview-audio.wav"
        if preview_mix.is_file() and preview_mix.stat().st_size > 44:
            return preview_mix

        self._set_progress(generation, 0.68, "mixing")
        preview_segments = render_dir / "preview-segments.json"
        audio_segments = list(segments)
        preview_parts = render_dir / "voice-parts"
        preview_parts.mkdir(parents=True, exist_ok=True)
        voice_cache = render_dir.parent / "voice-cache"
        voice_cache.mkdir(parents=True, exist_ok=True)
        configured_parts = str(files.get("voice_parts_dir") or "")
        if manual_voice:
            manifest_path = str((manual_voice.get("resolved_outputs") or {}).get("manifest") or "")
            configured_parts = str(Path(manifest_path).parent / "parts") if manifest_path else configured_parts
        original_parts = (
            Path(configured_parts)
            if configured_parts
            else Path(video_store.get_video_dir(video.video_id)) / "temp" / "voice_parts"
        )
        for index, segment in enumerate(audio_segments if (manual_voice or not is_manual) else []):
            target_part = preview_parts / f"voice_{index + 1:04d}.mp3"
            if target_part.is_file() and target_part.stat().st_size > 0:
                continue
            cached_part = voice_cache / f"{self._voice_cache_key(segment, settings)}.mp3"
            if cached_part.is_file() and cached_part.stat().st_size > 0:
                self._link_or_copy(cached_part, target_part)
                continue
            if index < len(baseline) and self._same_spoken_line(segment, baseline[index]):
                source_part = original_parts / target_part.name
                if source_part.is_file() and source_part.stat().st_size > 0:
                    self._link_or_copy(source_part, target_part)

        missing_parts = [
            index + 1
            for index in range(len(audio_segments))
            if not (preview_parts / f"voice_{index + 1:04d}.mp3").is_file()
            or (preview_parts / f"voice_{index + 1:04d}.mp3").stat().st_size <= 0
        ]
        if missing_parts:
            if is_manual:
                # Never keep stale speech under newly edited text. Manual
                # preview drops only the unavailable TTS layer and keeps the
                # source/music layers live until Voice is explicitly run.
                audio_segments = []
            else:
                raise RuntimeError(
                    "Bản xem trước chưa đổi vì phụ đề đã sửa chưa có giọng tương ứng. "
                    "Hãy chọn Giọng đọc và tạo lại giọng."
                )
        if is_manual and not manual_voice:
            audio_segments = []
        preview_segments.write_text(
            json.dumps(audio_segments, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for index, segment in enumerate(audio_segments):
            source_part = preview_parts / f"voice_{index + 1:04d}.mp3"
            cached_part = voice_cache / f"{self._voice_cache_key(segment, settings)}.mp3"
            if not source_part.is_file() or source_part.stat().st_size <= 0:
                continue
            try:
                if cached_part.exists() and os.path.samefile(source_part, cached_part):
                    continue
            except OSError:
                pass
            staged_cache = cached_part.with_suffix(f".{os.getpid()}.part")
            try:
                self._link_or_copy(source_part, staged_cache)
                os.replace(staged_cache, cached_part)
            finally:
                staged_cache.unlink(missing_ok=True)
        self._set_progress(generation, 0.76, "mixing")
        source_path = settings["source_path"]
        separated_background = Path(str(files.get("background_audio") or ""))
        background_path = (
            str(separated_background)
            if bool(getattr(video, "enable_audio_separation", False))
            and separated_background.is_file()
            and separated_background.stat().st_size > 44
            else source_path
        )
        music_path = str(files.get("background_music") or "")
        base_audio_payload = {
            "background": self._file_identity(background_path),
            "music": self._file_identity(music_path),
            "source_volume": settings["original_video_volume"],
            "music_volume": settings["background_music_volume"],
            "duration": settings["duration"],
            "format": "mono-16k-v1",
        }
        base_audio_signature = hashlib.sha256(
            json.dumps(base_audio_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        base_audio_path = render_dir.parent / f"audio-base-{base_audio_signature}" / "base.wav"
        build_audio_timeline(
            str(preview_segments),
            str(preview_parts),
            source_path,
            str(preview_mix),
            video.video_id,
            background_audio_path=background_path,
            original_video_volume=settings["original_video_volume"],
            background_music_path=music_path if os.path.isfile(music_path) else None,
            background_music_volume=settings["background_music_volume"],
            tts_volume=settings["tts_volume"],
            prepared_base_audio_path=str(base_audio_path),
            process_registry_id=process_id,
            require_voice_parts=bool(audio_segments),
            require_background_audio=not is_manual,
        )
        return preview_mix

    def _finish_success(
        self,
        generation: int,
        output_path: Path,
        start: float,
        duration: float,
        audio_path: Path | None = None,
        *,
        video_id: str = "",
        request_fingerprint: str = "",
        visual_signature: str = "",
        visual_cache_path: Path | None = None,
        base_playback_path: Path | None = None,
    ) -> None:
        # Finish cache bookkeeping before publishing the idle state. On
        # Windows, route teardown can delete the video workspace immediately
        # after QML observes ``busy == false``; publishing first raced that
        # deletion against completion-marker reads in this worker.
        with self._lock:
            if generation != self._generation:
                return
        with self._lock:
            if generation != self._generation:
                return
            resolved_video_id = video_id or self._video_id
            resolved_fingerprint = request_fingerprint or self._request_fingerprint
            resolved_visual_signature = visual_signature or resolved_fingerprint
        published_output = output_path
        cache_visual = visual_cache_path or output_path
        video = video_store.get_video(resolved_video_id)
        if video and getattr(video, "project_type", "single") == "manual" and resolved_fingerprint:
            try:
                manual_artifacts.register_existing(
                    video.video_id,
                    "visual_proxy",
                    resolved_visual_signature,
                    {"video": str(cache_visual)},
                    inputs=[
                        artifact_id
                        for kind, artifact_signature in (getattr(video, "active_artifacts", {}) or {}).items()
                        if kind in {"subtitle_document", "ocr_region"} and artifact_signature
                        for artifact_id in [manual_artifacts.artifact_id(kind, artifact_signature)]
                    ],
                    config_fingerprint="editor-visual-proxy-v1",
                    activate_artifact=False,
                )
            except (OSError, RuntimeError, ValueError):
                # Preview publication must stay usable even if an optional
                # cache maintenance pass fails. The rendered file remains in
                # the editor workspace as a safe fallback.
                published_output = output_path
        with self._lock:
            if (
                generation != self._generation
                or resolved_video_id != self._video_id
                or resolved_fingerprint != self._request_fingerprint
            ):
                return
            source_url = QUrl.fromLocalFile(str(published_output.resolve())).toString()
            self._source = source_url
            if base_playback_path is not None and base_playback_path.is_file():
                resolved_base = str(base_playback_path.resolve())
                self._base_source = QUrl.fromLocalFile(resolved_base).toString()
                self._completed_base_sources[resolved_fingerprint] = (
                    resolved_base,
                    self._file_identity(resolved_base),
                )
            self._start_seconds = start
            self._duration_seconds = duration
            # ``output_path`` is the atomically published A/V mux. Never
            # expose the WAV beside it: a second QMediaPlayer introduces a
            # second clock and was the source of intermittent silent/desynced
            # Manual playback. Keep the property for old QML compatibility,
            # but new previews intentionally publish it empty.
            self._audio_source = ""
            self._busy = False
            self._progress = 1.0
            self._stage = "ready"
            self._error = ""
            self._active_process_id = ""
            self._published_output_identity = self._file_identity(published_output)
            self._completed_requests[resolved_fingerprint] = (
                str(published_output.resolve()),
                "",
                start,
                duration,
                self._file_identity(published_output),
                resolved_visual_signature,
            )
            while len(self._completed_requests) > 12:
                evicted = next(iter(self._completed_requests))
                self._completed_requests.pop(evicted)
                self._completed_base_sources.pop(evicted, None)
            if video and getattr(video, "project_type", "single") == "manual":
                if self._pinned_video_id and self._pinned_video_id != video.video_id:
                    manual_artifacts.unpin(self._pinned_video_id, self._pin_owner)
                manual_artifacts.pin(
                    video.video_id,
                    "visual_proxy",
                    resolved_visual_signature,
                    self._pin_owner,
                )
                self._pinned_video_id = video.video_id
        self._host.editorPreviewChanged.emit()

    def _finish_error(self, generation: int, error: str) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._busy = False
            self._progress = 0.0
            self._stage = "error"
            self._error = error
            self._active_process_id = ""
        self._host.editorPreviewChanged.emit()

    def _set_progress(self, generation: int, progress: float, stage: str) -> None:
        """Publish throttled render progress without touching QML off-thread."""
        should_emit = False
        now = time.monotonic()
        with self._lock:
            if generation != self._generation:
                return
            normalized = max(0.0, min(1.0, float(progress)))
            stage_changed = stage != self._stage
            meaningful_step = normalized >= self._progress + 0.025
            ready_to_emit = now - self._last_progress_emit >= 0.08
            if stage_changed or normalized >= 0.99 or (meaningful_step and ready_to_emit):
                self._progress = normalized
                self._stage = stage
                self._last_progress_emit = now
                should_emit = True
        if should_emit:
            self._host.editorPreviewChanged.emit()

    @staticmethod
    def _remove_stale_files(current_path: Path) -> None:
        preview_dir = current_path.parent.parent
        try:
            visual_candidates = sorted(
                preview_dir.glob("visual-*/preview.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            base_candidates = sorted(
                preview_dir.glob("base-*/preview.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            chunk_candidates = sorted(
                preview_dir.glob("chunk-*/preview.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        retained_visuals = [current_path] if current_path in visual_candidates else []
        retained_visuals.extend(path for path in visual_candidates if path != current_path)
        retained_visuals = retained_visuals[:4]
        referenced_chunk_dirs: set[str] = set()
        has_chunk_manifest = False
        for visual_path in retained_visuals:
            marker_path = visual_path.parent / "preview.complete.json"
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                names = marker.get("chunk_directories", [])
                if isinstance(names, list):
                    has_chunk_manifest = has_chunk_manifest or bool(names)
                    referenced_chunk_dirs.update(
                        str(name) for name in names if str(name).startswith("chunk-")
                    )
            except (OSError, TypeError, json.JSONDecodeError):
                continue
        # Keep the active proxy plus recent Undo/Redo states. New completion
        # markers reference their exact chunks; the small legacy fallback is
        # only for caches created before manifests existed.
        stale_chunks = (
            [path for path in chunk_candidates if path.parent.name not in referenced_chunk_dirs]
            if has_chunk_manifest
            else chunk_candidates[32:]
        )
        stale_visuals = [path for path in visual_candidates if path not in retained_visuals]
        for path in [*stale_visuals, *base_candidates[2:], *stale_chunks]:
            try:
                shutil.rmtree(path.parent)
            except OSError:
                pass

    @staticmethod
    def _remove_stale_media_dirs(preview_dir: Path, current_media_path: Path) -> None:
        try:
            candidates = sorted(
                (path for path in preview_dir.glob("media-*/preview.mp4") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        retained = [current_media_path] if current_media_path in candidates else []
        retained.extend(path for path in candidates if path != current_media_path)
        for path in candidates:
            if path in retained[:6]:
                continue
            try:
                shutil.rmtree(path.parent)
            except OSError:
                pass

    @staticmethod
    def _remove_stale_audio_dirs(preview_dir: Path, current_audio_path: Path | None) -> None:
        try:
            candidates = sorted(
                (
                    path
                    for path in preview_dir.glob("audio-*")
                    if path.is_dir() and not path.name.startswith("audio-base-")
                ),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        current_dir = current_audio_path.parent if current_audio_path is not None else None
        retained = 0
        for path in candidates:
            if current_dir is not None and path == current_dir:
                retained += 1
                continue
            retained += 1
            if retained <= 4:
                continue
            try:
                shutil.rmtree(path)
            except OSError:
                pass
        try:
            base_candidates = sorted(
                (
                    path
                    for path in preview_dir.glob("audio-base-*")
                    if path.is_dir()
                ),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for path in base_candidates[3:]:
            try:
                shutil.rmtree(path)
            except OSError:
                pass
        voice_cache = preview_dir / "voice-cache"
        try:
            voice_candidates = sorted(
                voice_cache.glob("*.mp3"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for path in voice_candidates[256:]:
            try:
                path.unlink()
            except OSError:
                pass

    def release(self) -> None:
        with self._lock:
            self._generation += 1
            process_id = self._active_process_id
            self._active_process_id = ""
            self._busy = False
            self._progress = 0.0
            self._stage = ""
            self._error = ""
            self._source = ""
            self._base_source = ""
            self._audio_source = ""
            self._start_seconds = 0.0
            self._duration_seconds = 0.0
            self._video_id = ""
            self._request_fingerprint = ""
            self._published_output_identity = {}
            self._last_progress_emit = 0.0
            pinned_video_id = self._pinned_video_id
            self._pinned_video_id = ""
        if process_id:
            cancel_video(process_id)
        if pinned_video_id:
            manual_artifacts.unpin(pinned_video_id, self._pin_owner)
        self._host.editorPreviewChanged.emit()

    def clear_cache(self, video_id: str) -> int:
        """Remove inactive editor proxies without touching media currently open in QML."""
        requested_id = str(video_id or "")
        if not requested_id:
            return 0
        with self._lock:
            if requested_id == self._video_id and self._busy:
                return 0
            pinned_paths: set[Path] = set()
            if requested_id == self._video_id:
                for source in (self._source, self._base_source, self._audio_source):
                    local = QUrl(source).toLocalFile() if source else ""
                    if local:
                        pinned_paths.add(Path(local).resolve())
        preview_root = Path(video_store.get_video_dir(requested_id)) / "temp" / "editor-preview"
        if not preview_root.is_dir():
            return 0
        removed = 0
        for child in tuple(preview_root.iterdir()):
            try:
                resolved_child = child.resolve()
                if any(path == resolved_child or path.is_relative_to(resolved_child) for path in pinned_paths):
                    continue
                size = (
                    sum(item.stat().st_size for item in child.rglob("*") if item.is_file())
                    if child.is_dir()
                    else child.stat().st_size
                )
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                removed += size
            except OSError:
                continue
        return removed
