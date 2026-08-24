"""Asynchronous, output-faithful preview clips for the subtitle editor."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import threading
import wave
from pathlib import Path

import srt
from PySide6.QtCore import QUrl

from haizflow.pipeline.process_registry import cancel_video, clean_video, start_video
from haizflow.pipeline.audio_timeline import build_audio_timeline
from haizflow.pipeline.render import render_video
from haizflow.pipeline.tts import generate_voice_parts
from haizflow.utils.ffmpeg import get_video_duration
from haizflow.services import video_store


class EditorPreviewController:
    """Render a cached, full-timeline proxy through the production pipeline.

    Requests are generation based. A newer edit cancels the previous FFmpeg
    process and only the latest result may update QML. Files stay inside the
    selected video's workspace, never in the operating-system temp directory.

    The editor intentionally uses one continuous visual proxy and keeps audio
    as separate media layers.  Switching between short proxy windows and the
    source video causes a decoder reset in Qt Multimedia (a black frame) and
    also drops rendered OCR removal, subtitles and watermark outside the
    current window.  A low-resolution full proxy makes seeking deterministic
    and only invalidates when a visual/timeline setting changes.
    """

    def __init__(self, host):
        self._host = host
        self._lock = threading.RLock()
        self._generation = 0
        self._active_process_id = ""
        self._source = ""
        self._audio_source = ""
        self._busy = False
        self._progress = 0.0
        self._stage = ""
        self._error = ""
        self._start_seconds = 0.0
        self._duration_seconds = 0.0
        self._video_id = ""
        self._request_fingerprint = ""
        self._duration_cache: dict[tuple[str, int, int], float] = {}

    @property
    def source(self) -> str:
        with self._lock:
            return self._source

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
    def _ocr_region(video_dir: Path) -> dict:
        try:
            payload = json.loads(
                (video_dir / "temp" / "original_subtitle_region.json").read_text(encoding="utf-8")
            )
            region = payload.get("region", {}) if isinstance(payload, dict) else {}
            return dict(region) if isinstance(region, dict) else {}
        except (OSError, TypeError, json.JSONDecodeError):
            return {}

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
        ocr_region = self._ocr_region(video_dir)
        files = dict(getattr(video, "files", {}) or {})
        settings = {
            "video_id": video.video_id,
            "source_path": os.path.abspath(source_path),
            "source_mtime": os.path.getmtime(source_path),
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
            "ocr_region": ocr_region,
            # Version the proxy cache when its encoding contract changes.
            "preview_encoding": "full-timeline-sdr-yuv420p-v3",
        }
        preview_dir = video_dir / "temp" / "editor-preview"
        request_fingerprint = hashlib.sha256(
            json.dumps(
                settings,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        with self._lock:
            # Text editing, focus changes and draft auto-save can coalesce into
            # the same QML request. Never cancel a useful FFmpeg/TTS worker just
            # to start the exact same work again.
            if request_fingerprint == self._request_fingerprint:
                if self._busy:
                    return True
                if self._stage == "ready" and self._source:
                    return True
            self._generation += 1
            generation = self._generation
            previous_process_id = self._active_process_id
            process_id = f"editor-preview-{video.video_id}-{generation}"
            self._active_process_id = process_id
            self._busy = True
            self._progress = 0.0
            self._stage = "preparing"
            self._error = ""
            self._video_id = video.video_id
            self._request_fingerprint = request_fingerprint
        if previous_process_id:
            cancel_video(previous_process_id)
        self._host.editorPreviewChanged.emit()

        worker = threading.Thread(
            target=self._render,
            args=(generation, process_id, video, settings, preview_dir),
            name=f"editor-preview-{video.video_id[:8]}",
            daemon=True,
        )
        worker.start()
        return True

    def _render(self, generation, process_id, video, settings, preview_dir: Path) -> None:
        try:
            # FFprobe can block on a damaged file.  It must never run on the
            # GUI thread; every request enters this worker before probing.
            total_duration = self._source_duration(settings["source_path"])
            if total_duration <= 0:
                raise RuntimeError("The source video duration could not be read")
            # The playhead is deliberately absent from the signature. Seeking
            # must reuse the same proxy instead of creating a new FFmpeg job.
            settings["start"] = 0.0
            settings["duration"] = round(total_duration, 3)
            signature = hashlib.sha256(
                json.dumps(
                    settings,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:20]
            # render_video creates support files beside its output (ASS fonts,
            # temporary mux output, etc.).  Give every signature its own
            # directory so a cancelled generation can never overwrite the
            # active preview's files.
            render_dir = preview_dir / signature
            output_path = render_dir / "preview.mp4"
            completion_path = render_dir / "preview.complete.json"
            render_dir.mkdir(parents=True, exist_ok=True)
            cache_is_complete = self._preview_cache_is_complete(
                output_path,
                completion_path,
                settings["duration"],
            )
            if not cache_is_complete:
                output_path.unlink(missing_ok=True)
                completion_path.unlink(missing_ok=True)
                # render_video writes its generated ASS and mux intermediates
                # beside the SRT input. Keep every generation fully isolated:
                # fast timeline edits may cancel an older render while its
                # FFmpeg process is still unwinding.
                subtitle_path = render_dir / f"subtitles-{generation}.srt"
                silent_path = render_dir / f"silence-{generation}.wav"
                staged_output = render_dir / f"preview-{generation}.rendering.mp4"
                self._write_window_srt(
                    subtitle_path,
                    settings["segments"],
                    settings["start"],
                    settings["duration"],
                )
                self._write_silent_wav(silent_path, settings["duration"])
                start_video(process_id)
                try:
                    self._set_progress(generation, 0.03, "rendering")
                    render_video(
                        settings["source_path"],
                        str(silent_path),
                        str(subtitle_path),
                        str(staged_output),
                        settings["output_format"],
                        video.subtitle_style,
                        video.crop,
                        video.video_id,
                        settings["ocr_region"] if settings["remove_original_subtitles"] else None,
                        settings["watermark_text"],
                        settings["subtitle_layout_override"],
                        original_subtitle_removal_mode=settings["removal_mode"],
                        source_start_seconds=settings["start"],
                        source_duration_seconds=settings["duration"],
                        process_registry_id=process_id,
                        compatibility_preview=True,
                        progress_callback=lambda fraction: self._set_progress(
                            generation,
                            0.03 + max(0.0, min(1.0, float(fraction))) * 0.62,
                            "rendering",
                        ),
                    )
                    rendered_duration = get_video_duration(str(staged_output))
                    if rendered_duration < settings["duration"] - 0.25:
                        raise RuntimeError(
                            "Editor preview render ended before the source timeline."
                        )
                    # Publish only a complete file. QMediaPlayer must never see
                    # a partially written MP4 after an edit cancels FFmpeg.
                    with self._lock:
                        if generation != self._generation:
                            return
                    os.replace(staged_output, output_path)
                    self._write_completion_marker(
                        completion_path,
                        output_path,
                        rendered_duration,
                    )
                finally:
                    clean_video(process_id)
                    subtitle_path.unlink(missing_ok=True)
                    silent_path.unlink(missing_ok=True)
                    staged_output.unlink(missing_ok=True)
            # Publish the complete visual proxy immediately. Voice generation
            # may take longer (especially a local OmniVoice cold start), so
            # the editor must not stay black while audio catches up.
            self._publish_visual(
                generation,
                output_path,
                settings["start"],
                settings["duration"],
            )
            audio_path = self._prepare_preview_audio(
                generation,
                video,
                settings,
                render_dir,
            )
            self._set_progress(generation, 0.99, "loading")
            self._finish_success(
                generation,
                output_path,
                settings["start"],
                settings["duration"],
                audio_path,
            )
        except Exception as exc:
            self._finish_error(generation, str(exc))

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

    @staticmethod
    def _write_completion_marker(marker_path: Path, output_path: Path, duration: float) -> None:
        payload = {
            "version": 1,
            "duration": round(float(duration), 3),
            "size": output_path.stat().st_size,
        }
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

    def _publish_visual(self, generation: int, output_path: Path, start: float, duration: float) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._source = QUrl.fromLocalFile(str(output_path.resolve())).toString()
            self._start_seconds = start
            self._duration_seconds = duration
            self._progress = max(self._progress, 0.66)
            self._stage = "voice"
        self._host.editorPreviewChanged.emit()

    @staticmethod
    def _load_segments(path: str) -> list[dict]:
        try:
            with open(path, "r", encoding="utf-8") as file:
                value = json.load(file)
            return value if isinstance(value, list) else []
        except (OSError, TypeError, json.JSONDecodeError):
            return []

    @staticmethod
    def _same_spoken_line(current: dict, baseline: dict) -> bool:
        return " ".join(str(current.get("text", "") or "").split()) == " ".join(
            str(baseline.get("text", "") or "").split()
        )

    def _prepare_preview_audio(
        self,
        generation: int,
        video,
        settings: dict,
        render_dir: Path,
    ) -> Path | None:
        """Regenerate only changed voice lines and rebuild the editor mix.

        Existing per-line TTS files are hard-linked into the signature cache;
        a text edit therefore synthesizes only the affected line. Timing-only
        edits reuse every voice clip and only rebuild the inexpensive mix.
        """
        if str(getattr(video, "status", "") or "") != "done":
            return None
        files = dict(getattr(video, "files", {}) or {})
        current_mix = Path(str(files.get("voice_output") or ""))
        transcript_path = str(files.get("transcript_json") or "")
        baseline = self._load_segments(transcript_path)
        segments = settings["segments"]
        if (
            current_mix.is_file()
            and current_mix.stat().st_size > 44
            and len(baseline) == len(segments)
            and all(self._same_spoken_line(item, baseline[index]) for index, item in enumerate(segments))
            and all(
                abs(float(item.get("start", 0) or 0) - float(baseline[index].get("start", 0) or 0)) < 0.001
                and abs(float(item.get("end", 0) or 0) - float(baseline[index].get("end", 0) or 0)) < 0.001
                for index, item in enumerate(segments)
            )
        ):
            return current_mix

        preview_mix = render_dir / "preview-audio.wav"
        if preview_mix.is_file() and preview_mix.stat().st_size > 44:
            return preview_mix

        self._set_progress(generation, 0.68, "voice")
        preview_segments = render_dir / "preview-segments.json"
        preview_segments.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
        preview_parts = render_dir / "voice-parts"
        preview_parts.mkdir(parents=True, exist_ok=True)
        original_parts = Path(video_store.get_video_dir(video.video_id)) / "temp" / "voice_parts"
        for index, segment in enumerate(segments):
            if index >= len(baseline) or not self._same_spoken_line(segment, baseline[index]):
                continue
            source_part = original_parts / f"voice_{index + 1:04d}.mp3"
            target_part = preview_parts / source_part.name
            if target_part.exists() or not source_part.is_file() or source_part.stat().st_size <= 0:
                continue
            try:
                os.link(source_part, target_part)
            except OSError:
                shutil.copy2(source_part, target_part)

        def report_voice(completed: int, total: int) -> None:
            fraction = completed / max(1, total)
            self._set_progress(generation, 0.68 + fraction * 0.20, "voice")

        generate_voice_parts(
            str(preview_segments),
            str(preview_parts),
            settings["tts_voice"],
            video.video_id,
            progress_callback=report_voice,
            provider=settings["tts_provider"],
            target_language=settings["target_language"],
        )
        with self._lock:
            if generation != self._generation:
                return None
        self._set_progress(generation, 0.90, "mixing")
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
        )
        return preview_mix

    def _finish_success(
        self,
        generation: int,
        output_path: Path,
        start: float,
        duration: float,
        audio_path: Path | None = None,
    ) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._source = QUrl.fromLocalFile(str(output_path.resolve())).toString()
            self._start_seconds = start
            self._duration_seconds = duration
            self._audio_source = (
                QUrl.fromLocalFile(str(audio_path.resolve())).toString()
                if audio_path is not None and audio_path.is_file()
                else ""
            )
            self._busy = False
            self._progress = 1.0
            self._stage = "ready"
            self._error = ""
            self._active_process_id = ""
        self._host.editorPreviewChanged.emit()
        self._remove_stale_files(output_path)

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
        with self._lock:
            if generation != self._generation:
                return
            normalized = max(0.0, min(1.0, float(progress)))
            if stage != self._stage or normalized >= self._progress + 0.01:
                self._progress = normalized
                self._stage = stage
                should_emit = True
        if should_emit:
            self._host.editorPreviewChanged.emit()

    @staticmethod
    def _remove_stale_files(current_path: Path) -> None:
        try:
            candidates = sorted(
                current_path.parent.parent.glob("*/preview.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        # Keep the active proxy plus recent Undo/Redo states. Full
        # timeline proxies are intentionally bounded because even low-res
        # versions become large across batch projects.
        for path in candidates[4:]:
            try:
                shutil.rmtree(path.parent)
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
            self._audio_source = ""
            self._start_seconds = 0.0
            self._duration_seconds = 0.0
            self._video_id = ""
            self._request_fingerprint = ""
        if process_id:
            cancel_video(process_id)
        self._host.editorPreviewChanged.emit()
