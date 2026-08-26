import os
import json
from pydub import AudioSegment
import subprocess
import tempfile
import math
import time
from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS
from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.services.video_store import log_to_video
from haizflow.utils.ffmpeg import get_video_duration


_FINAL_AUDIO_TAIL_MARGIN_MS = 120
_ATOMIC_REPLACE_ATTEMPTS = 8


def _replace_exported_audio(temporary_path: str, output_path: str) -> None:
    """Replace a generated WAV after transient Windows media-handle locks clear."""
    last_error: OSError | None = None
    for attempt in range(_ATOMIC_REPLACE_ATTEMPTS):
        try:
            os.replace(temporary_path, output_path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt + 1 >= _ATOMIC_REPLACE_ATTEMPTS:
                break
            time.sleep(0.08 * (attempt + 1))
    if last_error is not None:
        raise last_error


def _apply_volume(audio: AudioSegment, volume: int, label: str, video_id: str) -> AudioSegment:
    """Apply a linear percentage without changing track selection."""
    volume = max(0, min(100, int(volume)))
    if volume == 0:
        log_to_video(video_id, f"{label} volume set to 0%. Muting this track.")
        return audio - 100
    db_change = 20 * math.log10(volume / 100.0)
    log_to_video(video_id, f"{label} volume set to {volume}%. Applying {db_change:.2f} dB.")
    return audio + db_change


def _fit_to_duration(audio: AudioSegment, duration_ms: int) -> AudioSegment:
    """Loop a non-empty music source, then trim it exactly to the video."""
    if len(audio) <= 0:
        raise RuntimeError("Background music contains no playable audio.")
    return (audio * max(1, math.ceil(duration_ms / len(audio))))[:duration_ms]


def _segment_slot_end_ms(
    start_ms: int,
    segment_end_ms: int,
    next_start_ms: int,
    video_duration_ms: int,
    *,
    is_last: bool,
) -> int:
    """Return the end of the original spoken window for one dubbed line.

    The previous implementation used the next line's start as the slot end.
    That prevented overlap, but let translated speech occupy pauses after the
    actor had stopped speaking.  Matching the source segment's own end keeps
    both ends of the dubbed line synchronized with fast dialogue.

    Invalid legacy timestamps fall back to the next safe boundary so an old
    project remains recoverable.
    """
    video_duration_ms = max(0, video_duration_ms)
    hard_end_ms = video_duration_ms
    if next_start_ms > start_ms:
        hard_end_ms = min(hard_end_ms, next_start_ms)

    if segment_end_ms > start_ms:
        return min(hard_end_ms, segment_end_ms)

    fallback_end_ms = min(video_duration_ms, max(start_ms, next_start_ms))
    if is_last and fallback_end_ms - start_ms > _FINAL_AUDIO_TAIL_MARGIN_MS * 2:
        fallback_end_ms -= _FINAL_AUDIO_TAIL_MARGIN_MS
    return fallback_end_ms

def trim_silence(audio: AudioSegment, silence_threshold_db: float = -50.0) -> AudioSegment:
    """Trims leading and trailing silence from an AudioSegment to remove delay and trailing padding."""
    start_trim = 0
    chunk_size = 10
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i:i+chunk_size]
        if chunk.dBFS > silence_threshold_db:
            # Keep a small 30ms buffer to avoid abrupt cut-off
            start_trim = max(0, i - 30)
            break
            
    end_trim = len(audio)
    for i in range(len(audio), 0, -chunk_size):
        chunk = audio[i - chunk_size : i]
        if chunk.dBFS > silence_threshold_db:
            # Keep a small 50ms buffer at the end
            end_trim = min(len(audio), i + 50)
            break
            
    if start_trim < end_trim:
        return audio[start_trim:end_trim]
    return audio


def _atempo_filters(speed_factor: float) -> str:
    """Build a quality-preserving FFmpeg tempo chain for any required speed."""
    filters = []
    while speed_factor > 2.0:
        filters.append("atempo=2.0")
        speed_factor /= 2.0
    filters.append(f"atempo={max(speed_factor, 1.0):.6f}")
    return ",".join(filters)


def _trim_tempo_rounding(audio: AudioSegment, max_duration_ms: int) -> AudioSegment:
    """Trim only FFmpeg's small resampling tail, never meaningful speech."""
    overflow_ms = len(audio) - max_duration_ms
    if overflow_ms <= 0:
        return audio
    tolerance_ms = max(20, int(max_duration_ms * 0.05))
    if overflow_ms > tolerance_ms:
        raise RuntimeError(
            f"FFmpeg tempo output is {len(audio)}ms, exceeding its "
            f"{max_duration_ms}ms slot by {overflow_ms}ms."
        )
    return audio[:max_duration_ms]


def compress_to_fit(audio: AudioSegment, max_duration_ms: int, temp_dir: str, video_id: str) -> AudioSegment:
    """Tempo-compress speech without deleting its ending or changing its pitch."""
    target_duration_ms = max(1, max_duration_ms - 20)
    speed_factor = len(audio) / target_duration_ms
    if speed_factor <= 1.0:
        return audio

    input_handle, input_path = tempfile.mkstemp(prefix="tempo-input-", suffix=".wav", dir=temp_dir)
    os.close(input_handle)
    output_handle, output_path = tempfile.mkstemp(prefix="tempo-output-", suffix=".wav", dir=temp_dir)
    os.close(output_handle)
    try:
        audio.export(input_path, format="wav")
        process = subprocess.Popen(
            [
                "ffmpeg", "-y", "-v", "error", "-i", input_path,
                "-filter:a", _atempo_filters(speed_factor),
                "-ac", "1", "-ar", "16000", output_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _stdout, stderr = communicate_process(
            video_id,
            process,
            label="FFmpeg speech tempo compression",
            timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
        )
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg speech tempo compression failed with exit code {process.returncode}: {stderr}")
        check_cancellation(video_id)
        fitted = AudioSegment.from_file(output_path)
        return _trim_tempo_rounding(fitted, max_duration_ms)
    finally:
        for path in (input_path, output_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

def build_audio_timeline(
    segments_json_path: str,
    voice_parts_dir: str,
    video_path: str,
    output_wav_path: str,
    video_id: str,
    background_audio_path: str | None = None,
    original_video_volume: int = 60,
    background_music_path: str | None = None,
    background_music_volume: int = 30,
    tts_volume: int = 100,
    prepared_base_audio_path: str | None = None,
    process_registry_id: str | None = None,
):
    """Overlays generated voice MP3 parts on top of the original/background audio track based on timestamps."""
    cancellation_id = process_registry_id or video_id
    log_to_video(video_id, "Starting build of the audio timeline...")
    
    # Retrieve duration to build the baseline silence track
    video_dur = get_video_duration(video_path)
    log_to_video(video_id, f"Base video duration: {video_dur:.2f} seconds")
    
    video_dur_ms = int(video_dur * 1000)
    if video_dur_ms <= 0:
        raise RuntimeError("Unable to determine a positive source-video duration for the audio timeline.")

    with open(segments_json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("Audio timeline requires at least one translated voice segment.")
        
    # Editor previews reuse this decoded/volume-adjusted base. Reopening a
    # timeline or changing one sentence no longer decodes the full source and
    # background music before every TTS overlay.
    base_cache_hit = bool(
        prepared_base_audio_path
        and os.path.isfile(prepared_base_audio_path)
        and os.path.getsize(prepared_base_audio_path) > 44
    )
    if base_cache_hit:
        base_audio = AudioSegment.from_file(prepared_base_audio_path)
        log_to_video(video_id, f"Reusing prepared preview audio base: {prepared_base_audio_path}")
    elif background_audio_path:
        if not os.path.exists(background_audio_path) or os.path.getsize(background_audio_path) <= 0:
            raise FileNotFoundError(f"Required original/background audio track is missing: {background_audio_path}")
        log_to_video(video_id, f"Loading background/original audio track: {background_audio_path}")
        try:
            bg_audio = AudioSegment.from_file(background_audio_path)
            bg_audio = _apply_volume(bg_audio, original_video_volume, "Source audio", video_id)
            # Convert background audio to mono and 16000Hz (the format whisperX/edge-tts uses)
            base_audio = bg_audio.set_frame_rate(16000).set_channels(1)
            log_to_video(video_id, f"Original/background audio loaded and pre-processed. Duration: {len(base_audio)}ms")
        except Exception as exc:
            raise RuntimeError(f"Could not load required original/background audio track: {exc}") from exc
    else:
        base_audio = AudioSegment.silent(duration=video_dur_ms, frame_rate=16000)

    # The final audio must always match the video. Source tracks can occasionally
    # be a few milliseconds longer than the video container reports.
    base_audio = base_audio[:video_dur_ms]
    if len(base_audio) < video_dur_ms:
        base_audio += AudioSegment.silent(
            duration=video_dur_ms - len(base_audio),
            frame_rate=16000,
        )

    # The user-selected track never enters Demucs.  AudioSegment decodes both
    # audio and video containers through FFmpeg, so MP3, MP4 and other
    # FFmpeg-supported formats follow the same safe final-mix path.
    if background_music_path and not base_cache_hit:
        if not os.path.isfile(background_music_path) or os.path.getsize(background_music_path) <= 0:
            raise FileNotFoundError(f"Required background music track is missing: {background_music_path}")
        try:
            music = AudioSegment.from_file(background_music_path)
            music = _fit_to_duration(music, video_dur_ms).set_frame_rate(16000).set_channels(1)
            music = _apply_volume(music, background_music_volume, "Background music", video_id)
            base_audio = base_audio.overlay(music)
            log_to_video(video_id, f"Mixed background music: {background_music_path}")
        except Exception as exc:
            raise RuntimeError(f"Could not load background music: {exc}") from exc

    if prepared_base_audio_path and not base_cache_hit:
        cache_directory = os.path.dirname(os.path.abspath(prepared_base_audio_path))
        os.makedirs(cache_directory, exist_ok=True)
        cache_handle, staged_cache = tempfile.mkstemp(
            prefix=".audio-base-",
            suffix=".wav",
            dir=cache_directory,
        )
        os.close(cache_handle)
        try:
            base_audio[:video_dur_ms].export(
                staged_cache,
                format="wav",
                parameters=["-ac", "1", "-ar", "16000"],
            )
            check_cancellation(cancellation_id)
            if os.path.getsize(staged_cache) <= 44:
                raise RuntimeError("Prepared audio-base cache is empty.")
            _replace_exported_audio(staged_cache, prepared_base_audio_path)
            staged_cache = ""
        finally:
            if staged_cache:
                try:
                    os.remove(staged_cache)
                except FileNotFoundError:
                    pass
    
    total = len(segments)
    for idx, seg in enumerate(segments, 1):
        part_filename = f"voice_{idx:04d}.mp3"
        part_path = os.path.join(voice_parts_dir, part_filename)
        
        if not os.path.exists(part_path) or os.path.getsize(part_path) == 0:
            raise RuntimeError(f"Missing or empty generated voice segment {idx}: {part_filename}")
            
        start_ms = max(0, int(seg["start"] * 1000))
        
        if start_ms >= video_dur_ms:
            log_to_video(video_id, f"[{idx}/{total}] Skipping TTS: its slot starts after the video ends.")
            continue
        
        # Keep the dubbed line inside the source actor's spoken window. The
        # next start remains a hard boundary for malformed/overlapping timing.
        segment_end_ms = int(float(seg.get("end", seg["start"])) * 1000)
        if idx < total:
            next_start_ms = int(segments[idx]["start"] * 1000)
        else:
            next_start_ms = video_dur_ms
            
        # Keep each line anchored to its original timestamp. A long translation
        # must not push every following line later and create a cascade of cuts.
        slot_end_ms = _segment_slot_end_ms(
            start_ms,
            segment_end_ms,
            next_start_ms,
            video_dur_ms,
            is_last=idx == total,
        )
        available_dur = slot_end_ms - start_ms
        if available_dur <= 0:
            log_to_video(video_id, f"[{idx}/{total}] Skipping TTS: no available timeline slot.")
            continue
        
        try:
            check_cancellation(cancellation_id)
            tts_segment = AudioSegment.from_file(part_path)
            # Trim leading/trailing silence from the generated TTS audio to remove delay/gaps
            tts_segment = trim_silence(tts_segment)
            tts_segment = _apply_volume(tts_segment, tts_volume, "TTS", video_id)
            tts_dur = len(tts_segment)
            
            # Fit speech with FFmpeg's pitch-preserving atempo filter. Unlike
            # slicing an AudioSegment, this keeps the end of every spoken line.
            if tts_dur > available_dur:
                speed_factor = tts_dur / available_dur
                log_to_video(
                    video_id,
                    f"[{idx}/{total}] TTS overran its {available_dur}ms source-speech window. "
                    f"Applying pitch-preserving tempo {speed_factor:.2f}x without trimming.",
                )
                tts_segment = compress_to_fit(tts_segment, available_dur, voice_parts_dir, cancellation_id)

            base_audio = base_audio.overlay(tts_segment, position=start_ms)
        except Exception as exc:
            raise RuntimeError(f"Failed to overlay required voice segment {idx} ({part_filename}): {exc}") from exc

    # Export mono 16kHz WAV file atomically so resume never sees a partial file.
    check_cancellation(cancellation_id)
    output_directory = os.path.dirname(os.path.abspath(output_wav_path))
    os.makedirs(output_directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(
        prefix=".audio-timeline-",
        suffix=".wav",
        dir=output_directory,
    )
    os.close(handle)
    try:
        base_audio[:video_dur_ms].export(
            temporary_path,
            format="wav",
            parameters=["-ac", "1", "-ar", "16000"],
        )
        check_cancellation(cancellation_id)
        if os.path.getsize(temporary_path) <= 44:
            raise RuntimeError("Audio timeline export produced an empty WAV file.")
        _replace_exported_audio(temporary_path, output_wav_path)
        temporary_path = ""
    finally:
        if temporary_path:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
    log_to_video(video_id, f"Successfully exported dubbed audio to: {output_wav_path}")
