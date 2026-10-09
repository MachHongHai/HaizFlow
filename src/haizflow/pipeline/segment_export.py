"""Local bounded editor export. No inference, whole render, or cache publication."""

import subprocess
import threading
import uuid
from fractions import Fraction

from haizflow.pipeline import manual_tools
from haizflow.pipeline.process_registry import cancel_video, clean_video, start_video
from haizflow.pipeline.sequence_compiler import (
    _run, apply_overlays, finish_export_resolution, resolved_subtitle_style,
    subtitle_style_overrides, write_subtitles,
)
from haizflow.services import manual_artifacts, video_store
from haizflow.services.video_export import ExportCancelled, preset_settings
from haizflow.utils.ffmpeg import (
    _binary, get_media_stream_types, get_video_dimensions, get_video_duration, validate_video_integrity,
)


def source_spans(document, start, end):
    """Intersect the edit map with one window, retaining gaps and source coordinates."""
    cursor = start
    result = []
    if not document.sequence.edit_decisions:
        return [(start, end, start)]
    for decision in sorted(document.sequence.edit_decisions, key=lambda item: item.sequence_start_ms):
        left = max(start, decision.sequence_start_ms)
        right = min(end, decision.sequence_start_ms + decision.source_end_ms - decision.source_start_ms)
        if right <= left:
            continue
        if left < cursor:
            raise ValueError("Overlapping source ranges in editor sequence.")
        if left > cursor:
            result.append((cursor, left, None))
        result.append((left, right, decision.source_start_ms + left - decision.sequence_start_ms))
        cursor = right
    if cursor < end:
        result.append((cursor, end, None))
    return result


def _source_picture(source, document, range_ms, directory, process_id, progress):
    spans = source_spans(document, *range_ms)
    if len(spans) == 1 and spans[0][2] is not None:
        return source, spans[0][2] / 1000
    width, height = get_video_dimensions(source)
    probe = subprocess.run([_binary("ffprobe"), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,r_frame_rate", "-of", "default=nw=1:nk=1", source],
        capture_output=True, text=True, timeout=15, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    frame_rate = None
    for raw in probe.stdout.splitlines():
        try:
            candidate = Fraction(raw.strip())
            if candidate > 0:
                frame_rate = candidate
                break
        except (ValueError, ZeroDivisionError):
            continue
    if frame_rate is None:
        raise RuntimeError("Cannot determine the source frame rate for segment assembly.")
    fps_filter = f"fps={frame_rate}"
    last_decision = max(document.sequence.edit_decisions, key=lambda item: item.sequence_start_ms, default=None)
    parts = []
    for index, (left, right, source_start) in enumerate(spans):
        part = directory / f"picture-{index}.mp4"
        duration = (right - left) / 1000
        command = [_binary("ffmpeg"), "-y", "-v", "error"]
        if source_start is None:
            last_end = (last_decision.sequence_start_ms + last_decision.source_end_ms - last_decision.source_start_ms
                        if last_decision else 0)
            if last_decision and left >= last_end:
                # The established source compiler holds the last frame when
                # voice/music extends beyond the picture. Preserve that tail.
                command += ["-ss", str(max(0, last_decision.source_end_ms / 1000 - 1 / float(frame_rate))), "-i", source]
                video_filter = f"{fps_filter},tpad=stop_mode=clone:stop_duration={duration}"
            else:
                command += ["-f", "lavfi", "-i", f"color=black:s={width}x{height}:r={frame_rate}"]
                video_filter = fps_filter
        else:
            command += ["-ss", str(source_start / 1000), "-i", source]
            video_filter = fps_filter
        command += ["-t", str(duration), "-an", "-vf", video_filter, "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(part)]
        _run(command, cwd=str(directory), process_id=process_id, label="Segment source picture",
             duration=duration, progress_callback=lambda value: progress(5 + round(10 * (index + value) / len(spans))))
        parts.append(part)
    concat = directory / "pictures.txt"
    concat.write_text("".join("file '" + part.as_posix().replace("'", "'\\''") + "'\n" for part in parts), encoding="utf-8")
    output = directory / "picture.mp4"
    _run([_binary("ffmpeg"), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
          "-an", "-c:v", "copy", str(output)], cwd=str(directory), process_id=process_id, label="Segment source assembly")
    return str(output), 0.0


def _source_bed(video, document, range_ms, directory, process_id):
    from haizflow.pipeline.audio_timeline import _decode_window, _window_fades
    from haizflow.utils.audio import AudioSegment

    start, end = range_ms
    tracks = {track.track_id: track for track in document.tracks}
    clip = next((clip for clip in document.clips if clip.track_id == "source-audio" and clip.enabled and not clip.muted), None)
    track = tracks.get("source-audio")
    if not clip or not track or not track.visible or track.muted:
        return None
    background, _, _ = manual_tools._audio_background(video)
    if "audio" not in get_media_stream_types(background):
        return None
    bed = AudioSegment.silent(duration=end - start, frame_rate=48000).set_channels(2)
    # Existing source audio is placed after the source edit map, in sequence time.
    for left, right, source_start in source_spans(document, max(0, start - clip.start_ms),
                                                max(0, min(end - clip.start_ms, clip.duration_ms))):
        if source_start is None:
            continue
        audio = _decode_window(background, source_start, right - left, process_id)
        audio = _window_fades(audio, left, clip.duration_ms, clip.fade_in_ms, clip.fade_out_ms)
        bed = bed.overlay(audio, position=max(0, left + clip.start_ms - start))
    path = directory / "source-bed.wav"
    stream = bed.export(path, format="wav")
    stream.close()
    return str(path)


def render_segment(video, document, range_ms, output, token, progress):
    """Only encode/mix the requested interval; preserve absolute subtitle clocks."""
    start, end = range_ms
    duration = (end - start) / 1000
    directory = output.parent
    process_id = "segment-" + uuid.uuid4().hex
    stop = threading.Event()
    report = progress or (lambda _value: None)

    def watch_cancel():
        while not stop.wait(.05):
            if token.is_set():
                cancel_video(process_id)
                return

    start_video(process_id)
    monitor = threading.Thread(target=watch_cancel, name="segment-cancellation", daemon=True)
    monitor.start()
    try:
        if token.is_set():
            raise ExportCancelled("Export cancelled.")
        video_store.log_to_video(video.video_id, f"Segment export window: {start}–{end} ms; no full-video render.")
        report(1)
        source, source_start = _source_picture(manual_tools._video_input(video), document, range_ms,
                                               directory, process_id, report)
        report(15)
        audio_path = directory / "audio.wav"
        audio = manual_artifacts.resolve(video.video_id, "audio_mix", manual_tools.audio_signature(video))
        if audio:
            from haizflow.pipeline.audio_timeline import _decode_window

            mixed = _decode_window(audio["resolved_outputs"]["audio"], start, end - start, process_id)
            stream = mixed.export(audio_path, format="wav")
            stream.close()
        else:
            bed = _source_bed(video, document, range_ms, directory, process_id)
            manual_tools._compose_manual_audio(video, audio_path, directory, document=document,
                range_ms=range_ms, bounded_video=source, bounded_background=bed, process_id=process_id)
        report(20)
        # Keep full cue durations/timestamps at window edges. This preserves
        # karaoke progress rather than restarting a partly spoken sentence.
        cues = document.model_copy(deep=True)
        cues.clips = [clip for clip in cues.clips if clip.kind != "subtitle" or (
            clip.start_ms < end and clip.start_ms + clip.duration_ms > start)]
        subtitles = directory / "subtitles.srt"
        if not write_subtitles(cues, subtitles):
            subtitles.write_text("1\n00:00:00,000 --> 00:00:00,080\n\u200b\n", encoding="utf-8")
        region = manual_tools._ocr_region(video)
        if region:
            region = {**region, "timeline_offset_seconds": start / 1000}
        quality = preset_settings(video.export_preset)["crf"]
        base = directory / "base.mp4"
        manual_tools.render_video(source, str(audio_path), str(subtitles), str(base), video.output_format,
            resolved_subtitle_style(cues, video.subtitle_style), video.crop, video.video_id, region, video.watermark_text,
            subtitle_layout_override=bool(video.subtitle_layout_override),
            source_start_seconds=source_start, source_duration_seconds=duration, process_registry_id=process_id,
            subtitle_timeline_offset_seconds=start / 1000,
            original_subtitle_removal_mode=video.original_subtitle_removal_mode,
            subtitle_style_overrides=subtitle_style_overrides(cues), encoding_quality=quality,
            **{name: getattr(video, name) for name in (
                "watermark_scale_percent", "watermark_kind", "watermark_opacity_percent", "watermark_outline_percent",
                "watermark_font_family", "watermark_text_color", "watermark_bold", "watermark_italic")},
            watermark_image_path=str(video.files.get("watermark_image") or ""),
            watermark_video_path=str(video.files.get("watermark_video") or ""),
            progress_callback=lambda value: report(20 + round(65 * value)))
        overlays = directory / "overlays.mp4"
        apply_overlays(str(base), str(overlays), document, process_id, encoding_quality=quality,
                       timeline_offset_seconds=start / 1000, progress_callback=lambda value: report(85 + round(7 * value)))
        finish_export_resolution(str(overlays), str(output), video.export_preset, process_id,
                                 progress_callback=lambda value: report(92 + round(5 * value)))
        validate_video_integrity(str(output))
        if abs(get_video_duration(str(output)) - duration) > .25:
            raise RuntimeError("Exported result segment duration does not match its timeline.")
        report(98)
    except Exception:
        if token.is_set():
            raise ExportCancelled("Export cancelled.") from None
        raise
    finally:
        stop.set()
        monitor.join(timeout=1)
        clean_video(process_id)
