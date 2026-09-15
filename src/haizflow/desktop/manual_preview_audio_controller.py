"""One PCM output for Manual preview; media decoders never own result audio."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

from haizflow.utils.ffmpeg import _binary

RATE = 48000


def voice_segment_is_compatible(current_segment, source_segment, multiple_speakers=False):
    """Whether a cached voice clip still represents this visible sentence."""
    if " ".join(str(current_segment.get("text") or "").split()) != " ".join(
        str(source_segment.get("text") or "").split()
    ):
        return False
    if not multiple_speakers:
        return True
    return (
        abs(float(current_segment.get("start") or 0) - float(source_segment.get("start") or 0))
        < .001
        and abs(float(current_segment.get("end") or 0) - float(source_segment.get("end") or 0))
        < .001
    )


def mix_frames(tracks, cursor, count, volumes, muted_ids=frozenset()):
    """Mix a bounded interleaved stereo buffer without changing track clocks."""
    result = np.zeros((count, 2), dtype=np.float32)
    for track in tracks:
        if track["id"] in muted_ids:
            continue
        samples = track["samples"]
        if len(samples) == 0:
            continue
        offset = cursor - track["start"]
        begin = max(0, -offset)
        end = count if track.get("loop") else min(count, len(samples) - offset)
        if end <= begin:
            continue
        gain = volumes[track["kind"]]
        if track.get("loop"):
            indices = np.arange(offset + begin, offset + end) % len(samples)
            result[begin:end] += samples[indices].astype(np.float32) * gain
        else:
            result[begin:end] += samples[offset + begin:offset + end].astype(np.float32) * gain
    return np.clip(result, -32768, 32767).astype("<i2").tobytes()


class ManualPreviewAudioController(QObject):
    errorChanged = Signal(str)
    _ready = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sink = None
        self._device = None
        self._tracks = []
        self._muted_ids = set()
        self._deferred_ids = set()
        self._generation = 0
        self._video_id = ""
        self._key = ""
        self._cursor = 0
        self._playing = False
        self._muted = False
        self._volumes = {"source": .6, "voice": 1.0, "music": .3}
        self._cache = OrderedDict()
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="manual-audio")
        self._future = None
        self._ready.connect(self._accept)
        self._timer = QTimer(self)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._pump)

    def _decode(self, path, duration=None, fit=False):
        path = Path(path)
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns, duration, fit)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        command = [_binary("ffmpeg"), "-v", "error", "-i", str(path), "-vn"]
        if duration is not None:
            from pydub import AudioSegment

            from haizflow.pipeline.audio_timeline import _atempo_filters, trim_silence
            audio = trim_silence(AudioSegment.from_file(path))
            # Use the same pitch-preserving tempo policy as exported voice.
            # Manual narration and ASS karaoke share the subtitle slot clock.
            # Always fit the non-destructive playback copy to that exact slot;
            # the immutable provider clip remains unchanged in cache.
            target = max(1, duration)
            speed = len(audio) / target
            with tempfile.TemporaryDirectory(prefix="haizflow-preview-voice-") as work:
                source = Path(work) / "voice.wav"
                audio.export(source, format="wav").close()
                command = [_binary("ffmpeg"), "-v", "error", "-i", str(source)]
                if abs(len(audio) - target) > 12:
                    command += ["-af", _atempo_filters(speed)]
                command += ["-t", str(duration / 1000), "-ac", "2", "-ar", str(RATE), "-f", "s16le", "-"]
                output = subprocess.run(command, capture_output=True, check=True, timeout=90,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        else:
            command += ["-ac", "2", "-ar", str(RATE), "-f", "s16le", "-"]
            output = subprocess.run(command, capture_output=True, check=True, timeout=90,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        samples = np.frombuffer(output, dtype="<i2").reshape((-1, 2))
        self._cache[key] = samples
        while sum(v.nbytes for v in self._cache.values()) > 128 * 1024 * 1024 and len(self._cache) > 1:
            self._cache.popitem(last=False)
        return samples

    def request(self, video, segments, voice_enabled=True):
        if not video or video.project_type != "manual":
            return
        if self._video_id != video.video_id:
            self.release()
            self._video_id = video.video_id
        from haizflow.pipeline import manual_tools

        active_voice = manual_tools.published_voice_record(video, validate=False) if voice_enabled else None
        active_voice_signature = str((active_voice or {}).get("signature") or "")
        # The picker contains a draft voice until the user confirms generation.
        # Key playback by the published manifest, never by that draft, so merely
        # browsing presets cannot detach or mute the current editor audio.
        files = dict(video.files or {})
        active_artifacts = dict(getattr(video, "active_artifacts", {}) or {})
        audio_inputs = {
            name: files.get(name)
            for name in (
                "input",
                "input_video",
                "source_audio",
                "background_audio",
                "background_music",
            )
            if files.get(name)
        }
        active_audio_artifacts = {
            name: active_artifacts.get(name)
            for name in ("source_audio", "separation")
            if active_artifacts.get(name)
        }
        config = (
            video.video_id,
            bool(active_voice),
            active_voice_signature,
            video.enable_audio_separation,
            audio_inputs,
            active_audio_artifacts,
            segments,
        )
        key = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        current = {str(s.get("segment_id", index)): str(s.get("text", "")) for index, s in enumerate(segments)}
        self._muted_ids = {t["id"] for t in self._tracks if t["kind"] == "voice"
                           and (not voice_enabled or current.get(t["id"]) != t.get("text"))}
        if key == self._key:
            return
        self._key = key
        self._generation += 1
        generation = self._generation
        if self._future is not None:
            self._future.cancel()
        def prepare():
            try:
                if generation != self._generation:
                    return generation, [], ""
                background, _, _ = manual_tools._audio_background(video)
                if generation != self._generation:
                    return generation, [], ""
                tracks = []
                if background:
                    try:
                        tracks.append({"id": "source", "kind": "source", "start": 0,
                                       "samples": self._decode(background)})
                    except subprocess.CalledProcessError:
                        pass  # A silent source video is valid.
                music = (video.files or {}).get("background_music")
                if music:
                    tracks.append({"id": "music", "kind": "music", "start": 0, "loop": True,
                                   "samples": self._decode(music)})
                if generation != self._generation:
                    return generation, [], ""
                clip_outputs = dict((active_voice or {}).get("resolved_outputs") or {})
                manifest_payload = manual_tools._voice_manifest_payload(active_voice)
                signatures = manifest_payload.get("clips") if isinstance(manifest_payload, dict) else []
                signatures = [str(value) for value in signatures] if isinstance(signatures, list) else []
                source_segments = manual_tools.published_voice_source_segments(
                    video, active_voice, validate=False
                )
                multiple = str(manifest_payload.get("speaker_mode") or "single") == "multiple"

                for index, (segment, signature) in enumerate(zip(segments, signatures)):
                    if generation != self._generation:
                        return generation, [], ""
                    if index >= len(source_segments) or not voice_segment_is_compatible(
                        segment, source_segments[index], multiple
                    ):
                        continue
                    clip_path = str(clip_outputs.get(f"clip_{index + 1}") or "")
                    if not clip_path:
                        continue
                    from haizflow.pipeline.audio_timeline import _segment_slot_end_ms
                    start = int(segment["start"] * 1000)
                    end = int(segment["end"] * 1000)
                    next_start = int(segments[index + 1]["start"] * 1000) if index + 1 < len(segments) else end
                    source_track = next((t for t in tracks if t["kind"] == "source"), None)
                    video_end = (len(source_track["samples"]) * 1000 // RATE if source_track
                                 else int(max(s["end"] for s in segments) * 1000))
                    duration = _segment_slot_end_ms(start, end, next_start, video_end,
                                                   is_last=index + 1 == len(segments)) - start
                    if duration <= 0:
                        continue
                    tracks.append({"id": str(segment.get("segment_id", index)), "kind": "voice",
                        "text": str(segment.get("text", "")), "signature": signature,
                        "start": start * RATE // 1000,
                        "samples": self._decode(clip_path, duration,
                                                bool(segment.get("fit_voice_to_timing")))})
                return generation, tracks, ""
            except Exception as exc:
                return generation, [], str(exc)
        self._future = self._executor.submit(prepare)
        self._future.add_done_callback(self._deliver)

    def _deliver(self, future):
        if self._future is future:
            self._future = None
        if not self._closed and not future.cancelled():
            self._ready.emit(future.result())

    @Slot(object)
    def _accept(self, result):
        generation, tracks, error = result
        if generation != self._generation:
            return
        if error:
            self.errorChanged.emit(error)
            return
        previous = {t["id"]: t.get("signature") for t in self._tracks}
        if self._playing:
            self._deferred_ids.update(t["id"] for t in tracks if t["kind"] == "voice"
                and previous.get(t["id"]) != t.get("signature")
                and t["start"] < self._cursor < t["start"] + len(t["samples"]))
        self._tracks = tracks
        self._muted_ids.clear()

    @Slot(int, int, int)
    def setVolumes(self, original, voice, music):
        self._volumes = {k: max(0, min(100, v))/100 for k, v in
                         (("source", original), ("voice", voice), ("music", music))}

    @Slot(float, bool, bool)
    def synchronize(self, seconds, playing, muted):
        self._muted = muted
        if not playing:
            self._playing = False
            self._timer.stop()
            if self._sink:
                self._sink.reset()
                self._device = None
            self._cursor = max(0, round(seconds * RATE))
            return
        if not self._playing:
            self._cursor = max(0, round(seconds * RATE))
            self._deferred_ids.clear()
            self._playing = True
            self._timer.start()
        elif self._sink:
            buffered = (self._sink.bufferSize() - self._sink.bytesFree()) // 4
            if abs((self._cursor - buffered) / RATE - seconds) > .18:
                self.seek(seconds)

    @Slot(float)
    def seek(self, seconds):
        self._cursor = max(0, round(seconds * RATE))
        self._deferred_ids.clear()
        if self._sink:
            self._sink.reset()
            self._device = None

    def _pump(self):
        if not self._playing:
            return
        if self._sink is None:
            device = QMediaDevices.defaultAudioOutput()
            if device.isNull():
                self._timer.stop()
                self.errorChanged.emit("Không tìm thấy thiết bị âm thanh.")
                return
            format = QAudioFormat()
            format.setSampleRate(RATE)
            format.setChannelCount(2)
            format.setSampleFormat(QAudioFormat.Int16)
            self._sink = QAudioSink(device, format, self)
            self._sink.setBufferSize(RATE * 4 // 20)
        if self._device is None:
            self._device = self._sink.start()
        if self._device is None:
            return
        count = min(RATE // 25, self._sink.bytesFree() // 4)
        if count <= 0:
            return
        data = (bytes(count * 4) if self._muted else
                mix_frames(self._tracks, self._cursor, count, self._volumes,
                           self._muted_ids | self._deferred_ids))
        written = self._device.write(data)
        if written > 0:
            self._cursor += written // 4

    @Slot()
    def release(self):
        self._generation += 1
        if self._future is not None:
            self._future.cancel()
            self._future = None
        self._key = ""
        self._playing = False
        self._timer.stop()
        if self._sink:
            self._sink.stop()
            self._sink.deleteLater()
            self._sink = None
        self._device = None
        self._tracks = []
        self._muted_ids.clear()
        self._deferred_ids.clear()

    def close(self):
        self._closed = True
        self.release()
        self._executor.shutdown(wait=False, cancel_futures=True)
