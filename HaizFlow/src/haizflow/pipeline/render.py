import os
import subprocess
import tempfile
from dataclasses import dataclass, replace
from datetime import timedelta

import srt

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS
from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.schemas.video import CropSettings, SubtitleStyle
from haizflow.services.video_store import log_to_video
from haizflow.utils.ffmpeg import (
    get_media_stream_types,
    get_video_dimensions,
    get_video_duration,
    preferred_video_encoder,
)


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def _ass_timestamp(value) -> str:
    total_centiseconds = round(value.total_seconds() * 100)
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"


@dataclass(frozen=True)
class SubtitleRegionLayout:
    x: float
    y: float
    width: float
    height: float


def _wrap_subtitle_for_region(
    text: str, layout: SubtitleRegionLayout, preferred_font_size: int, outline: int,
) -> tuple[str, int, int]:
    """Fit a cue on one centred line inside an OCR blur region."""
    content = " ".join(text.split())
    if not content:
        return "", preferred_font_size, 100
    inner_width = max(24, layout.width - 8)
    inner_height = max(20, layout.height - 4)
    # Arial Bold averages roughly 0.50 em per character for normal subtitle
    # text.  This intentional approximation produces stable sizing without a
    # platform-specific font measurement dependency in the render worker.
    width_limited = int(inner_width / max(1.0, len(content) * 0.50))
    height_limited = int((inner_height - outline * 2) / 1.12)
    # Keep glyphs close to the height of the removed source caption.  Long
    # sentences are split into timed phrases before reaching this function, so
    # only a mild horizontal condensation should ever be needed.
    font_ceiling = min(preferred_font_size, height_limited)
    font_size = max(10, min(font_ceiling, max(width_limited, int(width_limited / 0.80))))
    scale_x = max(78, min(100, round(width_limited * 100 / max(1, font_size))))
    return content, font_size, scale_x


def _split_subtitle_words(text: str, max_chars: int) -> list[str]:
    """Split into balanced, natural phrases that each fit one line."""
    words = " ".join(text.split()).split(" ")
    if not words or words == [""]:
        return [""]
    pieces: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)

    # Avoid flashing a trailing one-word fragment when it can be joined to the
    # previous phrase with only a small amount of horizontal condensation.
    if len(pieces) >= 2 and len(pieces[-1]) < max(4, round(max_chars * 0.40)):
        combined = f"{pieces[-2]} {pieces[-1]}"
        if len(combined) <= round(max_chars * 1.15):
            pieces[-2:] = [combined]
    return pieces or [""]


def _subtitle_parts_for_region(subtitle, layout: SubtitleRegionLayout, subtitle_style: SubtitleStyle):
    """Split a long cue over time, never into two simultaneous text rows."""
    content = " ".join(subtitle.content.split())
    inner_width = max(24, layout.width - 8)
    inner_height = max(20, layout.height - 4)
    display_font = min(
        subtitle_style.font_size,
        int((inner_height - subtitle_style.outline * 2) / 1.12),
    )
    display_font = max(10, display_font)
    # Split early enough that each phrase keeps large, normally proportioned
    # glyphs.  The phrases replace one another; they never form two rows.
    max_chars = max(5, int(inner_width / (display_font * 0.50 * 0.80)))
    parts = _split_subtitle_words(content, max_chars)
    duration_seconds = max(0.0, (subtitle.end - subtitle.start).total_seconds())
    if len(parts) == 1:
        text, font_size, scale_x = _wrap_subtitle_for_region(
            content, layout, subtitle_style.font_size, subtitle_style.outline,
        )
        return [(subtitle.start, subtitle.end, text, font_size, scale_x)]

    total_weight = sum(max(1, len(part)) for part in parts)
    cursor = subtitle.start
    result = []
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            end = subtitle.end
        else:
            fraction = max(1, len(part)) / total_weight
            end = cursor + timedelta(seconds=duration_seconds * fraction)
        text, font_size, scale_x = _wrap_subtitle_for_region(
            part, layout, subtitle_style.font_size, subtitle_style.outline,
        )
        result.append((cursor, end, text, font_size, scale_x))
        cursor = end
    return result


def _write_positioned_ass(
    srt_path: str,
    ass_path: str,
    subtitle_style: SubtitleStyle,
    width: int,
    height: int,
    region_layout: SubtitleRegionLayout | None = None,
):
    """Convert SRT to ASS so a dragged preview position is reproduced exactly in FFmpeg."""
    with open(srt_path, "r", encoding="utf-8") as file:
        subtitles = list(srt.parse(file.read()))
    if not subtitles:
        raise RuntimeError("Final render requires at least one valid subtitle cue.")
    x = round(width * subtitle_style.position_x_percent / 100)
    y = round(height * subtitle_style.position_y_percent / 100)
    header = "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,Arial,{subtitle_style.font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,{subtitle_style.outline},1,{5 if region_layout else 2},0,0,{subtitle_style.margin_bottom},1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ])
    lines = [header]
    for subtitle in subtitles:
        if region_layout:
            for start_time, end_time, content, font_size, scale_x in _subtitle_parts_for_region(
                subtitle, region_layout, subtitle_style,
            ):
                lines.append(
                    f"Dialogue: 0,{_ass_timestamp(start_time)},{_ass_timestamp(end_time)},Default,,0,0,0,,"
                    f"{{\\an5\\pos({x},{y})\\fs{font_size}\\fscx{scale_x}}}{_escape_ass_text(content)}"
                )
        else:
            start = _ass_timestamp(subtitle.start)
            end = _ass_timestamp(subtitle.end)
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\pos({x},{y})}}{_escape_ass_text(subtitle.content)}")
    with open(ass_path, "w", encoding="utf-8-sig") as file:
        file.write("\n".join(lines))


def _crop_filter(crop: CropSettings) -> str | None:
    if any((crop.left_percent, crop.right_percent, crop.top_percent, crop.bottom_percent)):
        left = max(0, min(84, crop.left_percent))
        right = max(0, min(84, crop.right_percent))
        top = max(0, min(84, crop.top_percent))
        bottom = max(0, min(84, crop.bottom_percent))
        width_ratio = max(0.15, (100 - left - right) / 100)
        height_ratio = max(0.15, (100 - top - bottom) / 100)
        return (
            f"crop=trunc(iw*{width_ratio:.4f}/2)*2:trunc(ih*{height_ratio:.4f}/2)*2:"
            f"trunc(iw*{left / 100:.4f}/2)*2:trunc(ih*{top / 100:.4f}/2)*2"
        )
    if crop.zoom_percent <= 100:
        return None
    zoom = crop.zoom_percent / 100
    x_factor = max(0, min(1, (crop.pan_x_percent + 100) / 200))
    y_factor = max(0, min(1, (crop.pan_y_percent + 100) / 200))
    return (
        f"crop=trunc(iw/{zoom}/2)*2:trunc(ih/{zoom}/2)*2:"
        f"(iw-ow)*{x_factor:.4f}:(ih-oh)*{y_factor:.4f}"
    )


def _ffmpeg_path(path: str, working_dir: str) -> str:
    """Prefer relative paths, but keep cross-drive Windows paths valid."""
    try:
        return os.path.relpath(path, start=working_dir).replace("\\", "/")
    except ValueError:
        return os.path.abspath(path).replace("\\", "/")


def _crop_geometry(width: int, height: int, crop: CropSettings) -> tuple[float, float, float, float]:
    """Mirror the crop filter closely enough to map a detected source region."""
    if any((crop.left_percent, crop.right_percent, crop.top_percent, crop.bottom_percent)):
        left = max(0, min(84, crop.left_percent)) / 100
        right = max(0, min(84, crop.right_percent)) / 100
        top = max(0, min(84, crop.top_percent)) / 100
        bottom = max(0, min(84, crop.bottom_percent)) / 100
        return width * left, height * top, width * max(0.15, 1 - left - right), height * max(0.15, 1 - top - bottom)
    if crop.zoom_percent <= 100:
        return 0, 0, width, height
    zoom = crop.zoom_percent / 100
    cropped_width, cropped_height = width / zoom, height / zoom
    x_factor = max(0, min(1, (crop.pan_x_percent + 100) / 200))
    y_factor = max(0, min(1, (crop.pan_y_percent + 100) / 200))
    return (width - cropped_width) * x_factor, (height - cropped_height) * y_factor, cropped_width, cropped_height


def _output_subtitle_region_layout(
    region: dict | None,
    source_width: int,
    source_height: int,
    output_format: str,
    crop: CropSettings,
    output_width: int,
    output_height: int,
) -> SubtitleRegionLayout | None:
    """Map the source blur rectangle into the final video coordinate system."""
    if not region:
        return None
    try:
        source_x = source_width * float(region["x_percent"]) / 100
        source_y = source_height * float(region["y_percent"]) / 100
        source_region_width = source_width * float(region["width_percent"]) / 100
        source_region_height = source_height * float(region["height_percent"]) / 100
    except (KeyError, TypeError, ValueError):
        return None
    crop_x, crop_y, crop_width, crop_height = _crop_geometry(source_width, source_height, crop)
    x = (source_x - crop_x) / max(1, crop_width) * output_width
    y = (source_y - crop_y) / max(1, crop_height) * output_height
    width = source_region_width / max(1, crop_width) * output_width
    height = source_region_height / max(1, crop_height) * output_height
    if output_format == "tiktok_9_16_crop":
        scale = max(1080 / crop_width, 1920 / crop_height)
        x = (source_x - crop_x) * scale - (crop_width * scale - output_width) / 2
        y = (source_y - crop_y) * scale - (crop_height * scale - output_height) / 2
        width, height = source_region_width * scale, source_region_height * scale
    elif output_format == "blur_background_9_16":
        scale = min(1080 / crop_width, 1920 / crop_height)
        x = (source_x - crop_x) * scale + (output_width - crop_width * scale) / 2
        y = (source_y - crop_y) * scale + (output_height - crop_height * scale) / 2
        width, height = source_region_width * scale, source_region_height * scale
    left, top = max(0, x), max(0, y)
    right, bottom = min(output_width, x + width), min(output_height, y + height)
    if right - left < 24 or bottom - top < 20:
        return None
    return SubtitleRegionLayout(left, top, right - left, bottom - top)


def _style_for_original_subtitle_region(
    subtitle_style: SubtitleStyle,
    region_layout: SubtitleRegionLayout | None,
    output_width: int,
    output_height: int,
) -> SubtitleStyle:
    """Centre generated captions inside the detected blur region."""
    if not region_layout:
        return subtitle_style
    x_percent = round(max(0, min(100, (region_layout.x + region_layout.width / 2) * 100 / output_width)))
    y_percent = round(max(0, min(100, (region_layout.y + region_layout.height / 2) * 100 / output_height)))
    # OCR mode owns the output scale: a small source caption produces a small
    # replacement and a tall source caption produces a correspondingly large
    # one, regardless of the generic subtitle-editor default.
    font_size = max(12, min(120, round(region_layout.height * 0.70)))
    outline = min(subtitle_style.outline, max(1, font_size // 14))
    return subtitle_style.model_copy(update={
        "position_x_percent": x_percent,
        "position_y_percent": y_percent,
        "font_size": font_size,
        "outline": outline,
    }) if hasattr(subtitle_style, "model_copy") else replace(
        subtitle_style,
        position_x_percent=x_percent,
        position_y_percent=y_percent,
        font_size=font_size,
        outline=outline,
    )


def _source_blur_region(region: dict | None, source_width: int, source_height: int) -> tuple[int, int, int, int] | None:
    if not region:
        return None
    try:
        x = int(source_width * float(region["x_percent"]) / 100) // 2 * 2
        y = int(source_height * float(region["y_percent"]) / 100) // 2 * 2
        width = max(2, int(source_width * float(region["width_percent"]) / 100) // 2 * 2)
        height = max(2, int(source_height * float(region["height_percent"]) / 100) // 2 * 2)
    except (KeyError, TypeError, ValueError):
        return None
    width = min(width, source_width - x)
    height = min(height, source_height - y)
    return (x, y, width, height) if width >= 2 and height >= 2 else None


def render_video(video_path: str, voice_wav_path: str, srt_path: str, output_path: str, output_format: str, subtitle_style: SubtitleStyle, crop: CropSettings, video_id: str, original_subtitle_region: dict | None = None):
    """Render cropped video, positioned subtitles, and dubbed audio with FFmpeg."""
    log_to_video(video_id, f"Starting video render. Format selected: '{output_format}'")
    supported_formats = {"keep_ratio", "tiktok_9_16_crop", "blur_background_9_16"}
    if output_format not in supported_formats:
        raise ValueError(f"Unsupported output format: {output_format!r}.")
    if crop.zoom_percent <= 0:
        raise ValueError("Crop zoom must be greater than zero.")
    if not os.path.isfile(voice_wav_path) or os.path.getsize(voice_wav_path) <= 44:
        raise RuntimeError("Final render requires a non-empty dubbed WAV track.")
    if not os.path.isfile(srt_path) or os.path.getsize(srt_path) <= 0:
        raise RuntimeError("Final render requires a non-empty subtitle file.")
    video_temp_dir = os.path.dirname(os.path.abspath(srt_path))
    source_width, source_height = get_video_dimensions(video_path)
    _crop_x, _crop_y, cropped_width, cropped_height = _crop_geometry(source_width, source_height, crop)
    if output_format in {"tiktok_9_16_crop", "blur_background_9_16"}:
        subtitle_width, subtitle_height = 1080, 1920
    else:
        subtitle_width = max(2, int(cropped_width) // 2 * 2)
        subtitle_height = max(2, int(cropped_height) // 2 * 2)

    ass_path = os.path.join(video_temp_dir, "positioned_subtitles.ass")
    region_layout = _output_subtitle_region_layout(
        original_subtitle_region, source_width, source_height, output_format, crop, subtitle_width, subtitle_height,
    )
    effective_style = _style_for_original_subtitle_region(
        subtitle_style, region_layout, subtitle_width, subtitle_height,
    )
    _write_positioned_ass(srt_path, ass_path, effective_style, subtitle_width, subtitle_height, region_layout)
    rel_video = _ffmpeg_path(video_path, video_temp_dir)
    rel_voice = _ffmpeg_path(voice_wav_path, video_temp_dir)
    rel_ass = _ffmpeg_path(ass_path, video_temp_dir)
    output_directory = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_directory, exist_ok=True)
    output_extension = os.path.splitext(output_path)[1] or ".mp4"
    handle, temporary_output = tempfile.mkstemp(
        prefix=".render-",
        suffix=output_extension,
        dir=output_directory,
    )
    os.close(handle)
    rel_output = _ffmpeg_path(temporary_output, video_temp_dir)
    ass_filter_path = rel_ass.replace(":", "\\:").replace("'", "'\\\\''")
    ass_filter = f"ass='{ass_filter_path}'"
    filters = []
    crop_filter = _crop_filter(crop)
    if crop_filter:
        filters.append(crop_filter)
    blur_region = _source_blur_region(original_subtitle_region, source_width, source_height)
    if output_format == "blur_background_9_16":
        prefix = ",".join(filters)
        input_label = "[0:v]"
        blur_prefix = ""
        if blur_region:
            x, y, width, height = blur_region
            blur_prefix = (
                f"[0:v]split=2[source_clean][source_blur];"
                f"[source_blur]crop={width}:{height}:{x}:{y},boxblur=18:4[subtitle_blur];"
                f"[source_clean][subtitle_blur]overlay={x}:{y}[source_without_original];"
            )
            input_label = "[source_without_original]"
        source = f"{input_label}{prefix + ',' if prefix else ''}split[base][fg]"
        vf_filter = (
            f"{blur_prefix}{source};[base]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=15:3[bg];"
            f"[fg]scale=1080:1920:force_original_aspect_ratio=decrease[front];[bg][front]overlay=(W-w)/2:(H-h)/2,{ass_filter}[outv]"
        )
    else:
        if output_format == "tiktok_9_16_crop":
            filters.extend(["scale=1080:1920:force_original_aspect_ratio=increase", "crop=1080:1920"])
        filters.append(ass_filter)
        if blur_region:
            x, y, width, height = blur_region
            vf_filter = (
                f"[0:v]split=2[source_clean][source_blur];"
                f"[source_blur]crop={width}:{height}:{x}:{y},boxblur=18:4[subtitle_blur];"
                f"[source_clean][subtitle_blur]overlay={x}:{y},{','.join(filters)}[outv]"
            )
        else:
            vf_filter = ",".join(filters)

    video_encoder, video_encoder_args = preferred_video_encoder()
    source_duration = get_video_duration(video_path)
    if source_duration <= 0:
        raise RuntimeError("Unable to determine the source video duration before rendering.")
    cmd_prefix = ["ffmpeg", "-y", "-i", rel_video, "-i", rel_voice]
    if blur_region or output_format == "blur_background_9_16":
        cmd_prefix.extend(["-filter_complex", vf_filter, "-map", "[outv]"])
    else:
        cmd_prefix.extend(["-map", "0:v:0", "-vf", vf_filter])
    cmd_prefix.extend(["-map", "1:a:0", "-t", f"{source_duration:.6f}"])
    audio_args = ["-c:a", "aac", "-b:a", "192k", rel_output]

    def run_render(encoder: str, encoder_args: list[str]):
        command = cmd_prefix + ["-c:v", encoder, *encoder_args, *audio_args]
        log_to_video(video_id, f"Running FFmpeg render with {encoder} in Cwd: {video_temp_dir}")
        check_cancellation(video_id)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=video_temp_dir)
        _stdout, process_stderr = communicate_process(
            video_id,
            process,
            label="FFmpeg video render",
            timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
        )
        check_cancellation(video_id)
        return process.returncode, process_stderr

    try:
        return_code, stderr = run_render(video_encoder, video_encoder_args)
        if return_code != 0 and video_encoder != "libx264":
            log_to_video(video_id, f"Hardware encoder {video_encoder} failed; retrying with libx264.")
            return_code, stderr = run_render("libx264", ["-preset", "veryfast", "-crf", "23"])
        if return_code != 0:
            log_to_video(video_id, f"FFmpeg Render Error output:\n{stderr}")
            raise RuntimeError(f"FFmpeg render failed with exit code {return_code}")
        if os.path.getsize(temporary_output) <= 0 or get_video_duration(temporary_output) <= 0:
            raise RuntimeError("FFmpeg render produced an empty or unreadable video.")
        stream_types = get_media_stream_types(temporary_output)
        if not {"video", "audio"}.issubset(stream_types):
            raise RuntimeError(
                "FFmpeg render output is missing its video or dubbed-audio stream."
            )
        os.replace(temporary_output, output_path)
        temporary_output = ""
    finally:
        if temporary_output:
            try:
                os.remove(temporary_output)
            except FileNotFoundError:
                pass
    log_to_video(video_id, f"Successfully rendered final video to: {output_path}")
