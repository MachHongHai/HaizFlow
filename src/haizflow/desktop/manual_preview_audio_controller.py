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
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
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
        clip_frames = int(track.get("duration_frames") or 0)
        if clip_frames and offset >= clip_frames:
            continue
        end = count if track.get("loop") else min(count, len(samples) - offset)
        if clip_frames:
            end = min(end, clip_frames - offset)
        if end <= begin:
            continue
        gain = float(volumes[track["kind"]]) * float(track.get("gain", 1.0))
        if track.get("loop"):
            indices = np.arange(offset + begin, offset + end) % len(samples)
            chunk = samples[indices].astype(np.float32)
        else:
            chunk = samples[offset + begin:offset + end].astype(np.float32)
        local = np.arange(offset + begin, offset + end, dtype=np.float32)
        envelope = np.full((end - begin,), gain, dtype=np.float32)
        fade_in = int(track.get("fade_in_frames") or 0)
        fade_out = int(track.get("fade_out_frames") or 0)
        if fade_in:
            envelope *= np.clip(local / max(1, fade_in), 0.0, 1.0)
        effective_length = clip_frames or len(samples)
        if fade_out:
            envelope *= np.clip((effective_length - local) / max(1, fade_out), 0.0, 1.0)
        if track.get("duck_ranges"):
            timeline = np.arange(cursor + begin, cursor + end, dtype=np.float32)
            reduction = float(track.get("duck_gain", 1.0))
            attack = max(1, int(track.get("duck_attack_frames") or 1))
            release = max(1, int(track.get("duck_release_frames") or 1))
            duck_envelope = np.ones((end - begin,), dtype=np.float32)
            for voice_start, voice_end in track["duck_ranges"]:
                attack_gain = 1.0 - (1.0 - reduction) * np.clip(
                    (timeline - (voice_start - attack)) / attack, 0.0, 1.0
                )
                release_gain = reduction + (1.0 - reduction) * np.clip(
                    (timeline - voice_end) / release, 0.0, 1.0
                )
                range_gain = np.where(timeline < voice_start, attack_gain,
                    np.where(timeline <= voice_end, reduction, release_gain))
                active = (timeline >= voice_start - attack) & (timeline <= voice_end + release)
                duck_envelope = np.minimum(duck_envelope, np.where(active, range_gain, 1.0))
            envelope *= duck_envelope
        result[begin:end] += chunk * envelope[:, None]
    return np.clip(result, -32768, 32767).astype("<i2").tobytes()


def apply_source_decisions(samples, decisions):
    """Return source PCM in sequence order without creating another decoder."""
    if not decisions:
        return samples
    ranges = []
    for decision in sorted(decisions, key=lambda item: int(item.get("sequence_start_ms", 0))):
        start = max(0, int(int(decision.get("source_start_ms", 0)) * RATE / 1000))
        end = min(len(samples), int(int(decision.get("source_end_ms", 0)) * RATE / 1000))
        if end > start:
            ranges.append(samples[start:end])
    return np.concatenate(ranges) if ranges else np.empty((0, 2), dtype="<i2")


class ManualPreviewAudioController(QObject):
    errorChanged = Signal(str)
    positionChanged = Signal()
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
        self._position_seconds = 0.0
        self._playing = False
        self._muted = False
        self._volumes = {"source": .6, "voice": 1.0, "music": .3, "overlay": 1.0}
        self._cache = OrderedDict()
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="manual-audio")
        self._future = None
        self._ready.connect(self._accept)
        self._timer = QTimer(self)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._pump)

    @Property(float, notify=positionChanged)
    def positionSeconds(self):
        """Clock of the samples that have actually reached the audio device.

        The Manual caption renderer follows this clock while playback is
        active.  QMediaPlayer's video position can lead the separate QAudioSink
        by one device buffer, which is especially visible on large karaoke
        captions after a TTS clip has been tempo-fitted to its subtitle slot.
        """
        return self._position_seconds

    def _publish_position(self, seconds):
        value = max(0.0, float(seconds or 0.0))
        if abs(value - self._position_seconds) < 0.012:
            return
        self._position_seconds = value
        self.positionChanged.emit()

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
            # Match export: compress only an overrun. A shorter narration must
            # end naturally and leave the remainder of its slot silent.
            target = max(1, duration)
            speed = len(audio) / target
            with tempfile.TemporaryDirectory(prefix="haizflow-preview-voice-") as work:
                source = Path(work) / "voice.wav"
                audio.export(source, format="wav").close()
                command = [_binary("ffmpeg"), "-v", "error", "-i", str(source)]
                if len(audio) > target + 12:
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
        from haizflow.services import editor_documents

        document = editor_documents.load(video.video_id)
        if document:
            subtitle_clips = sorted(
                (
                    clip for clip in document.clips
                    if clip.track_id == "subtitles" and clip.enabled and clip.segment_id
                ),
                key=lambda clip: (clip.start_ms, clip.clip_id),
            )
            timeline_segments = []
            for clip in subtitle_clips:
                stored = clip.metadata.get("segment_payload")
                item = dict(stored) if isinstance(stored, dict) else {}
                item.update(
                    segment_id=clip.segment_id,
                    text=clip.name,
                    start=clip.start_ms / 1000,
                    end=(clip.start_ms + clip.duration_ms) / 1000,
                )
                timeline_segments.append(item)
            segments = timeline_segments

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
            {
                "sequence": document.sequence.model_dump() if document else {},
                "tracks": [track.model_dump() for track in document.tracks]
                    if document else [],
                "clips": [
                    clip.model_dump()
                    for clip in document.clips
                    if clip.track_id in {"source-audio", "voice", "music"}
                ] if document else [],
                "ducking": (
                    document.audio_ducking_enabled,
                    document.audio_ducking_reduction_db,
                    document.audio_ducking_attack_ms,
                    document.audio_ducking_release_ms,
                ) if document else (),
            },
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
                editor_tracks = {track.track_id: track for track in document.tracks} if document else {}
                solo = {track.track_id for track in editor_tracks.values() if track.solo}

                def audible(track_id):
                    track = editor_tracks.get(track_id)
                    if track is None:
                        return True
                    return track.visible and not track.muted and (not solo or track_id in solo)

                source_clip = next(
                    (clip for clip in document.clips if clip.track_id == "source-audio" and clip.enabled),
                    None,
                ) if document else None
                if background and audible("source-audio") and not (source_clip and source_clip.muted):
                    try:
                        source_samples = self._decode(background)
                        if document:
                            source_samples = apply_source_decisions(
                                source_samples,
                                [item.model_dump() for item in document.sequence.edit_decisions],
                            )
                        baseline = max(1, int(video.original_video_volume or 100))
                        tracks.append({
                            "id": "source",
                            "kind": "source",
                            "start": 0,
                            "gain": (source_clip.volume_percent / baseline) if source_clip else 1.0,
                            "fade_in_frames": int(
                                (source_clip.fade_in_ms if source_clip else 0) * RATE / 1000
                            ),
                            "fade_out_frames": int(
                                (source_clip.fade_out_ms if source_clip else 0) * RATE / 1000
                            ),
                            "samples": source_samples,
                        })
                    except subprocess.CalledProcessError:
                        pass  # A silent source video is valid.
                music_clip = next(
                    (clip for clip in document.clips if clip.track_id == "music" and clip.enabled),
                    None,
                ) if document else None
                music_asset = editor_documents.asset_by_id(document, music_clip.asset_id) \
                    if document and music_clip else None
                music = str(music_asset.path) if music_asset else str((video.files or {}).get("background_music") or "")
                if music and audible("music") and not (music_clip and music_clip.muted):
                    music_samples = self._decode(music)
                    source_in = int((music_clip.source_in_ms if music_clip else 0) * RATE / 1000)
                    music_samples = music_samples[source_in:]
                    baseline = max(1, int(video.background_music_volume or 100))
                    tracks.append({
                        "id": "music",
                        "kind": "music",
                        "start": int((music_clip.start_ms if music_clip else 0) * RATE / 1000),
                        "loop": bool(music_clip.loop) if music_clip else True,
                        "gain": (music_clip.volume_percent / baseline) if music_clip else 1.0,
                        "duration_frames": int((music_clip.duration_ms if music_clip else 0) * RATE / 1000),
                        "fade_in_frames": int((music_clip.fade_in_ms if music_clip else 0) * RATE / 1000),
                        "fade_out_frames": int((music_clip.fade_out_ms if music_clip else 0) * RATE / 1000),
                        "samples": music_samples,
                    })
                overlay_track = editor_tracks.get("overlays")
                overlay_audible = bool(
                    document
                    and (overlay_track is None or overlay_track.visible)
                )
                if overlay_audible:
                    for overlay_clip in document.clips:
                        if (
                            overlay_clip.track_id != "overlays"
                            or overlay_clip.kind != "video"
                            or not overlay_clip.enabled
                            or overlay_clip.muted
                        ):
                            continue
                        overlay_asset = editor_documents.asset_by_id(
                            document, overlay_clip.asset_id
                        )
                        if overlay_asset is None or not overlay_asset.path:
                            continue
                        try:
                            overlay_samples = self._decode(overlay_asset.path)
                        except subprocess.CalledProcessError:
                            continue
                        source_in = int(overlay_clip.source_in_ms * RATE / 1000)
                        overlay_samples = overlay_samples[source_in:]
                        tracks.append({
                            "id": f"overlay:{overlay_clip.clip_id}",
                            "kind": "overlay",
                            "start": int(overlay_clip.start_ms * RATE / 1000),
                            "loop": bool(overlay_clip.loop),
                            "gain": overlay_clip.volume_percent / 100.0,
                            "duration_frames": int(overlay_clip.duration_ms * RATE / 1000),
                            "fade_in_frames": int(overlay_clip.fade_in_ms * RATE / 1000),
                            "fade_out_frames": int(overlay_clip.fade_out_ms * RATE / 1000),
                            "samples": overlay_samples,
                        })
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

                voice_by_segment = {
                    clip.segment_id: clip
                    for clip in document.clips
                    if clip.track_id == "voice" and clip.segment_id
                } if document else {}
                source_by_id = {
                    str(item.get("segment_id") or item.get("id") or ""): index
                    for index, item in enumerate(source_segments)
                }
                for index, segment in enumerate(segments):
                    if generation != self._generation:
                        return generation, [], ""
                    voice_clip = voice_by_segment.get(str(segment.get("segment_id") or ""))
                    if document and (
                        not audible("voice") or not voice_clip or not voice_clip.enabled or voice_clip.muted
                    ):
                        continue
                    source_index = source_by_id.get(str(segment.get("segment_id") or ""), index)
                    if source_index >= len(source_segments) or not voice_segment_is_compatible(
                        segment, source_segments[source_index], multiple
                    ):
                        continue
                    signature = signatures[source_index] if source_index < len(signatures) else ""
                    clip_path = str(clip_outputs.get(f"clip_{source_index + 1}") or "")
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
                    baseline = max(1, int(video.tts_volume or 100))
                    tracks.append({"id": str(segment.get("segment_id", index)), "kind": "voice",
                        "text": str(segment.get("text", "")), "signature": signature,
                        "start": start * RATE // 1000,
                        "gain": (voice_clip.volume_percent / baseline) if voice_clip else 1.0,
                        "duration_frames": duration * RATE // 1000,
                        "fade_in_frames": int((voice_clip.fade_in_ms if voice_clip else 0) * RATE / 1000),
                        "fade_out_frames": int((voice_clip.fade_out_ms if voice_clip else 0) * RATE / 1000),
                        "samples": self._decode(clip_path, duration,
                                                bool(segment.get("fit_voice_to_timing")))})
                if document and document.audio_ducking_enabled:
                    voice_ranges = [
                        (track["start"], track["start"] + int(track.get("duration_frames") or len(track["samples"])))
                        for track in tracks if track["kind"] == "voice"
                    ]
                    for track in tracks:
                        if track["kind"] != "music":
                            continue
                        track["duck_ranges"] = voice_ranges
                        track["duck_gain"] = 10 ** (document.audio_ducking_reduction_db / 20.0)
                        track["duck_attack_frames"] = document.audio_ducking_attack_ms * RATE // 1000
                        track["duck_release_frames"] = document.audio_ducking_release_ms * RATE // 1000
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
            self._publish_position(seconds)
            return
        if not self._playing:
            self._cursor = max(0, round(seconds * RATE))
            self._publish_position(seconds)
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
        self._publish_position(seconds)
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
            buffered = max(0, (self._sink.bufferSize() - self._sink.bytesFree()) // 4)
            self._publish_position(max(0, self._cursor - buffered) / RATE)

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
        self._publish_position(0.0)
        self._tracks = []
        self._muted_ids.clear()
        self._deferred_ids.clear()

    def close(self):
        self._closed = True
        self.release()
        self._executor.shutdown(wait=False, cancel_futures=True)
