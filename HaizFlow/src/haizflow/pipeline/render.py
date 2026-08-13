import math
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from threading import Event, Thread
from typing import Callable

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


KARAOKE_FONT_NAME = "Bangers"
KARAOKE_FONT_FILENAME = "Bangers-Regular.ttf"
WATERMARK_FONT_FILENAME = "arialbi.ttf"


def _karaoke_font_directory() -> Path:
    directory = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    font_path = directory / KARAOKE_FONT_FILENAME
    if not font_path.is_file():
        raise RuntimeError(f"Bundled karaoke subtitle font is missing: {font_path}")
    return directory


def _watermark_font_path() -> Path:
    """Prefer Windows' clean bold-italic face, with a bundled fallback."""
    windows_directory = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Fonts"
    bold_italic = windows_directory / WATERMARK_FONT_FILENAME
    if bold_italic.is_file():
        return bold_italic
    # The frozen application is Windows-first, but retaining a bundled font
    # keeps command-line renders usable on a machine without Arial installed.
    return _karaoke_font_directory() / KARAOKE_FONT_FILENAME


def _karaoke_outline(font_size: int, configured_outline: int) -> int:
    """Return a compact heavy outline suited to short-video captions."""
    return max(configured_outline, min(10, max(3, round(font_size * 0.09))))


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def _ass_timestamp(value) -> str:
    total_centiseconds = round(value.total_seconds() * 100)
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"


def _karaoke_units(text: str) -> list[str]:
    """Return readable karaoke units while preserving visible spaces."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    words = normalized.split(" ")
    if len(words) > 1:
        return [word + (" " if index < len(words) - 1 else "") for index, word in enumerate(words)]
    # Scripts such as Chinese, Japanese and Thai commonly arrive without
    # spaces. Highlighting their visible characters is more natural than
    # treating the entire sentence as one indivisible karaoke unit.
    return list(normalized)


def _allocate_centiseconds(units: list[str], duration_seconds: float) -> list[int]:
    """Allocate the complete cue duration without cumulative rounding drift."""
    if not units:
        return []
    total = max(len(units), round(max(0.01, duration_seconds) * 100))
    weights = [max(1, sum(character.isalnum() for character in unit)) for unit in units]
    remaining = total - len(units)
    weight_total = sum(weights)
    raw_extras = [remaining * weight / weight_total for weight in weights]
    durations = [1 + math.floor(value) for value in raw_extras]
    missing = total - sum(durations)
    for index in sorted(
        range(len(units)),
        key=lambda item: raw_extras[item] - math.floor(raw_extras[item]),
        reverse=True,
    )[:missing]:
        durations[index] += 1
    return durations


def _karaoke_ass_text(text: str, duration_seconds: float) -> str:
    """Create a white-to-gold left-to-right ASS karaoke sweep."""
    units = _karaoke_units(text)
    durations = _allocate_centiseconds(units, duration_seconds)
    return "".join(
        f"{{\\kf{duration}}}{_escape_ass_text(unit)}"
        for unit, duration in zip(units, durations)
    )


@dataclass(frozen=True)
class SubtitleRegionLayout:
    x: float
    y: float
    width: float
    height: float
    line_height: float | None = None


def _wrap_subtitle_for_region(
    text: str, layout: SubtitleRegionLayout, preferred_font_size: int, outline: int,
) -> tuple[str, int, int]:
    """Fit one undistorted text line inside the exact OCR region."""
    content = " ".join(text.split())
    if not content:
        return "", preferred_font_size, 100
    inner_width = max(24, layout.width - outline * 4)
    text_row_height = min(layout.height, layout.line_height or layout.height)
    inner_height = max(20, text_row_height - outline * 2)
    # Arial Bold averages about 0.48 em per character for subtitle prose. Keep
    # ScaleX at 100% so long text is fitted by a proportional font reduction,
    # never by stretching or squeezing glyph shapes.
    width_limited = int(inner_width / max(1.0, len(content) * 0.48))
    height_limited = int(inner_height / 1.05)
    font_size = max(10, min(preferred_font_size, height_limited, width_limited))
    return content, font_size, 100


def _split_subtitle_words(text: str, max_chars: int, *, strict_max_chars: bool = False) -> list[str]:
    """Split into balanced, natural phrases that each fit one line."""
    words = " ".join(text.split()).split(" ")
    if not words or words == [""]:
        return [""]
    if len(words) == 1 and len(words[0]) > max_chars:
        # Chinese and other scripts may not separate words with spaces. Keep
        # their glyph order and split into balanced timed character groups.
        characters = words[0]
        part_count = max(1, math.ceil(len(characters) / max_chars))
        base_size, remainder = divmod(len(characters), part_count)
        pieces = []
        cursor = 0
        for index in range(part_count):
            size = base_size + (1 if index < remainder else 0)
            pieces.append(characters[cursor:cursor + size])
            cursor += size
        return pieces
    content_length = len(" ".join(words))
    soft_limit = max_chars if strict_max_chars else max(max(len(word) for word in words), round(max_chars * 1.30))
    minimum_parts = max(1, math.ceil(content_length / soft_limit))

    # Find the smallest feasible phrase count, then choose the most even word
    # partition. Even phrases fill the detected row naturally and avoid a lone
    # word flashing at an oversized font between otherwise readable phrases.
    for part_count in range(minimum_parts, len(words) + 1):
        target_length = content_length / part_count
        cache: dict[tuple[int, int], tuple[float, list[str]] | None] = {}

        def solve(start: int, remaining: int) -> tuple[float, list[str]] | None:
            key = (start, remaining)
            if key in cache:
                return cache[key]
            if remaining == 0:
                return (0.0, []) if start == len(words) else None
            if len(words) - start < remaining:
                return None
            best: tuple[float, list[str]] | None = None
            last_end = len(words) - remaining + 1
            for end in range(start + 1, last_end + 1):
                phrase = " ".join(words[start:end])
                if len(phrase) > soft_limit and end > start + 1:
                    break
                tail = solve(end, remaining - 1)
                if tail is None:
                    continue
                singleton_penalty = target_length ** 2 if end == start + 1 and len(words) >= part_count * 2 else 0
                cost = (len(phrase) - target_length) ** 2 + singleton_penalty + tail[0]
                if best is None or cost < best[0]:
                    best = (cost, [phrase, *tail[1]])
            cache[key] = best
            return best

        result = solve(0, part_count)
        if result is not None:
            return result[1]
    return words


def _merge_contiguous_subtitles(subtitles: list[srt.Subtitle]) -> list[srt.Subtitle]:
    """Rejoin sentence fragments split only to preserve source timestamps."""
    if not subtitles:
        return []
    merged: list[srt.Subtitle] = []
    current = subtitles[0]
    for following in subtitles[1:]:
        current_text = " ".join(current.content.split())
        following_text = " ".join(following.content.split())
        gap_seconds = (following.start - current.end).total_seconds()
        combined_duration = (following.end - current.start).total_seconds()
        combined_length = len(current_text) + 1 + len(following_text)
        ends_sentence = bool(re.search(r"[.!?。！？…][\"'”’)]*$", current_text))
        if (
            -0.12 <= gap_seconds <= 0.12
            and not ends_sentence
            and combined_duration <= 8.0
            and combined_length <= 180
        ):
            current = srt.Subtitle(
                index=current.index,
                start=current.start,
                end=max(current.end, following.end),
                content=f"{current_text} {following_text}".strip(),
            )
        else:
            merged.append(current)
            current = following
    merged.append(current)
    return merged


def _subtitle_parts_for_region(
    subtitle,
    layout: SubtitleRegionLayout,
    subtitle_style: SubtitleStyle,
    *,
    fixed_font_size: bool = False,
):
    """Split a long cue over time, never into two simultaneous text rows."""
    content = " ".join(subtitle.content.split())
    inner_width = max(24, layout.width - subtitle_style.outline * 4)
    text_row_height = min(layout.height, layout.line_height or layout.height)
    inner_height = max(20, text_row_height - subtitle_style.outline * 2)
    display_font = (
        subtitle_style.font_size
        if fixed_font_size
        else min(subtitle_style.font_size, int(inner_height / 1.05))
    )
    display_font = max(10, display_font)
    # Split early enough that each phrase keeps large, normally proportioned
    # glyphs.  The phrases replace one another; they never form two rows.
    # Prefer readable multi-word phrases. If the region is narrow, the fitting
    # step reduces the font mildly instead of flashing isolated words.
    max_chars = max(10, int(inner_width / (display_font * 0.48)))
    parts = _split_subtitle_words(content, max_chars, strict_max_chars=fixed_font_size)
    duration_seconds = max(0.0, (subtitle.end - subtitle.start).total_seconds())
    if fixed_font_size:
        total_weight = sum(max(1, len(part)) for part in parts)
        cursor = subtitle.start
        result = []
        for index, part in enumerate(parts):
            if index == len(parts) - 1:
                end = subtitle.end
            else:
                end = cursor + timedelta(seconds=duration_seconds * max(1, len(part)) / total_weight)
            result.append((cursor, end, part, subtitle_style.font_size, 100))
            cursor = end
        return result
    if len(parts) == 1:
        text, font_size, scale_x = _wrap_subtitle_for_region(
            content, layout, subtitle_style.font_size, subtitle_style.outline,
        )
        return [(subtitle.start, subtitle.end, text, font_size, scale_x)]

    fitted_parts = [
        _wrap_subtitle_for_region(
            part, layout, subtitle_style.font_size, subtitle_style.outline,
        )
        for part in parts
    ]
    # Keep one font size throughout a source cue. Changing size every few
    # words creates a distracting zoom/pulse effect even when every phrase
    # individually fits. The longest phrase establishes the stable size.
    stable_font_size = min(item[1] for item in fitted_parts)
    total_weight = sum(max(1, len(part)) for part in parts)
    cursor = subtitle.start
    result = []
    for index, (part, fitted) in enumerate(zip(parts, fitted_parts)):
        if index == len(parts) - 1:
            end = subtitle.end
        else:
            fraction = max(1, len(part)) / total_weight
            end = cursor + timedelta(seconds=duration_seconds * fraction)
        text, _font_size, _scale_x = fitted
        result.append((cursor, end, text, stable_font_size, 100))
        cursor = end
    return result


def _write_positioned_ass(
    srt_path: str,
    ass_path: str,
    subtitle_style: SubtitleStyle,
    width: int,
    height: int,
    region_layout: SubtitleRegionLayout | None = None,
    fixed_font_size: bool = False,
):
    """Convert SRT to ASS so a dragged preview position is reproduced exactly in FFmpeg."""
    with open(srt_path, "r", encoding="utf-8") as file:
        subtitles = list(srt.parse(file.read()))
    if not subtitles:
        raise RuntimeError("Final render requires at least one valid subtitle cue.")
    style_outline = _karaoke_outline(
        subtitle_style.font_size, subtitle_style.outline,
    )
    header = "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        # ASS karaoke renders not-yet-spoken glyphs with SecondaryColour and
        # sweeps PrimaryColour across each word. Bangers supplies the chunky,
        # naturally slanted display shape used by modern short-video captions.
        f"Style: Default,{KARAOKE_FONT_NAME},{subtitle_style.font_size},&H0000EFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,{style_outline},2,5,0,0,{subtitle_style.margin_bottom},1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ])
    lines = [header]
    if region_layout:
        subtitles = _merge_contiguous_subtitles(subtitles)
    for subtitle in subtitles:
        x = round(width * subtitle_style.position_x_percent / 100)
        y = round(height * subtitle_style.position_y_percent / 100)
        if region_layout:
            for start_time, end_time, content, font_size, scale_x in _subtitle_parts_for_region(
                subtitle,
                region_layout,
                subtitle_style,
                fixed_font_size=fixed_font_size,
            ):
                karaoke = _karaoke_ass_text(content, (end_time - start_time).total_seconds())
                cue_outline = _karaoke_outline(font_size, subtitle_style.outline)
                lines.append(
                    f"Dialogue: 0,{_ass_timestamp(start_time)},{_ass_timestamp(end_time)},Default,,0,0,0,,"
                    f"{{\\an5\\pos({x},{y})\\fs{font_size}\\fscx{scale_x}\\bord{cue_outline}\\shad2}}{karaoke}"
                )
        else:
            start_time = _ass_timestamp(subtitle.start)
            end_time = _ass_timestamp(subtitle.end)
            karaoke = _karaoke_ass_text(
                subtitle.content, (subtitle.end - subtitle.start).total_seconds(),
            )
            lines.append(
                f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,"
                f"{{\\an5\\pos({x},{y})\\bord{style_outline}\\shad2}}{karaoke}"
            )
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
        source_line_height = source_height * float(
            region.get("line_height_percent", region["height_percent"])
        ) / 100
    except (KeyError, TypeError, ValueError):
        return None
    crop_x, crop_y, crop_width, crop_height = _crop_geometry(source_width, source_height, crop)
    x = (source_x - crop_x) / max(1, crop_width) * output_width
    y = (source_y - crop_y) / max(1, crop_height) * output_height
    width = source_region_width / max(1, crop_width) * output_width
    height = source_region_height / max(1, crop_height) * output_height
    line_height = source_line_height / max(1, crop_height) * output_height
    if output_format == "tiktok_9_16_crop":
        scale = max(1080 / crop_width, 1920 / crop_height)
        x = (source_x - crop_x) * scale - (crop_width * scale - output_width) / 2
        y = (source_y - crop_y) * scale - (crop_height * scale - output_height) / 2
        width, height = source_region_width * scale, source_region_height * scale
        line_height = source_line_height * scale
    elif output_format == "blur_background_9_16":
        scale = min(1080 / crop_width, 1920 / crop_height)
        x = (source_x - crop_x) * scale + (output_width - crop_width * scale) / 2
        y = (source_y - crop_y) * scale + (output_height - crop_height * scale) / 2
        width, height = source_region_width * scale, source_region_height * scale
        line_height = source_line_height * scale
    left, top = max(0, x), max(0, y)
    right, bottom = min(output_width, x + width), min(output_height, y + height)
    if right - left < 24 or bottom - top < 20:
        return None
    return SubtitleRegionLayout(left, top, right - left, bottom - top, line_height)


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
    # The removal region can contain two or three source rows. Replacement
    # glyphs should match one source row rather than scale with the whole block.
    detected_line_height = region_layout.line_height or region_layout.height
    # ASS font size is larger than the visible glyph box. A modest 66% of the
    # OCR row height gives the replacement line more presence inside the
    # covered region while leaving room for its outline and karaoke sweep.
    font_size = max(12, min(112, round(detected_line_height * 0.66)))
    outline = _karaoke_outline(font_size, subtitle_style.outline)
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


def _default_subtitle_layout(
    subtitle_style: SubtitleStyle, output_width: int, output_height: int,
) -> SubtitleRegionLayout:
    """Reserve a wide single caption row when the source has no subtitles."""
    width = max(160, output_width * max(0.82, subtitle_style.box_width_percent / 100))
    height = max(72, output_height * 0.07)
    x = (output_width - width) / 2
    y = output_height * subtitle_style.position_y_percent / 100 - height / 2
    y = max(height / 2, min(output_height - height / 2, y))
    return SubtitleRegionLayout(x, y, min(width, output_width), height)


def _manual_subtitle_layout(
    subtitle_style: SubtitleStyle, output_width: int, output_height: int,
) -> SubtitleRegionLayout:
    """Map the user-edited preview frame into output-video coordinates."""
    width = max(24, output_width * subtitle_style.box_width_percent / 100)
    height = max(20, output_height * subtitle_style.box_height_percent / 100)
    width = min(width, output_width)
    height = min(height, output_height)
    center_x = output_width * subtitle_style.position_x_percent / 100
    center_y = output_height * subtitle_style.position_y_percent / 100
    x = max(0, min(output_width - width, center_x - width / 2))
    y = max(0, min(output_height - height, center_y - height / 2))
    return SubtitleRegionLayout(x, y, width, height)


def _source_subtitle_removal_region(region: dict | None, source_width: int, source_height: int) -> tuple[int, int, int, int] | None:
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


def _subtitle_blur_filter(width: int, height: int) -> str:
    """Build a strong blur that fully suppresses burned-in subtitle detail."""
    shortest_side = max(2, min(width, height))
    # Outlined meme captions retain a recognizable silhouette with a small
    # radius. Scale aggressively with the detected text row while keeping the
    # operation bounded because it runs only on the cropped subtitle region.
    sigma = max(3, min(64, round(shortest_side * 0.18)))
    return f"gblur=sigma={sigma}:steps=4"


def _feathered_blur_region(
    region: tuple[int, int, int, int], source_width: int, source_height: int,
) -> tuple[int, int, int, int, int]:
    """Keep the blur box exact and blend its edge only inside that box."""
    x, y, width, height = region
    feather = max(2, min(16, round(min(width, height) * 0.08)))
    if feather % 2:
        feather += 1
    exact_x = max(0, min(source_width - 2, x)) // 2 * 2
    exact_y = max(0, min(source_height - 2, y)) // 2 * 2
    exact_width = max(2, min(width, source_width - exact_x)) // 2 * 2
    exact_height = max(2, min(height, source_height - exact_y)) // 2 * 2
    return exact_x, exact_y, exact_width, exact_height, feather


def _subtitle_blur_prefix(
    region: tuple[int, int, int, int], source_width: int, source_height: int,
) -> str:
    """Build one stable blur that completely suppresses text inside the OCR box."""
    x, y, width, height, feather = _feathered_blur_region(
        region, source_width, source_height,
    )
    blur_filter = _subtitle_blur_filter(width, height)
    # Blur an expanded sample so glyphs touching an OCR-box edge can mix with
    # real neighbouring picture pixels. Crop back to the exact OCR box before
    # overlaying, so stronger removal never enlarges the visible replacement.
    sample_padding = max(4, min(96, round(min(width, height) * 0.55)))
    if sample_padding % 2:
        sample_padding += 1
    sample_x = max(0, x - sample_padding) // 2 * 2
    sample_y = max(0, y - sample_padding) // 2 * 2
    sample_right = min(source_width, x + width + sample_padding)
    sample_bottom = min(source_height, y + height + sample_padding)
    sample_width = max(2, (sample_right - sample_x) // 2 * 2)
    sample_height = max(2, (sample_bottom - sample_y) // 2 * 2)
    inner_x = x - sample_x
    inner_y = y - sample_y
    edge_distance = "min(min(X,W-1-X),min(Y,H-1-Y))"
    # Keep a subtle edge transition without restoring high-contrast source
    # glyphs. The previous zero weight at the boundary left letters visible.
    blur_weight = f"0.94+0.06*min(1,{edge_distance}/{feather})"
    blend_filter = f"blend=all_expr='A*(1-({blur_weight}))+B*({blur_weight})'"
    return (
        f"[0:v]split=3[source_clean][source_region][source_blur];"
        f"[source_region]crop={width}:{height}:{x}:{y}[original_region];"
        f"[source_blur]crop={sample_width}:{sample_height}:{sample_x}:{sample_y},"
        f"{blur_filter},crop={width}:{height}:{inner_x}:{inner_y}[subtitle_blur];"
        f"[original_region][subtitle_blur]{blend_filter}[subtitle_blended];"
        f"[source_clean][subtitle_blended]overlay={x}:{y}[source_without_original];"
    )


def _subtitle_patch_source_y(
    region: tuple[int, int, int, int], source_height: int,
) -> int | None:
    """Choose a clean adjacent strip without overlapping the subtitle box."""
    _x, y, _width, height = region
    gap = max(2, min(12, round(height * 0.08)))
    room_above = y
    room_below = source_height - (y + height)
    required_room = height + gap
    if room_above < required_room and room_below < required_room:
        return None
    # Sample toward the larger uninterrupted side. Besides avoiding frame
    # edges, this makes lower captions copy from above and upper captions copy
    # from below, where perspective and lighting are normally most similar.
    if room_above >= room_below and room_above >= required_room:
        return y - height - gap
    if room_below >= required_room:
        return y + height + gap
    return y - height - gap


def _subtitle_patch_prefix(
    region: tuple[int, int, int, int], source_width: int, source_height: int,
) -> str:
    """Cover the OCR box with real pixels from an adjacent picture strip."""
    x, y, width, height = region
    x = max(0, min(source_width - 2, x))
    y = max(0, min(source_height - 2, y))
    width = max(2, min(width, source_width - x))
    height = max(2, min(height, source_height - y))
    patch_y = _subtitle_patch_source_y((x, y, width, height), source_height)
    if patch_y is None:
        return _subtitle_blur_prefix((x, y, width, height), source_width, source_height)
    feather = max(2, min(8, round(min(width, height) * 0.06)))
    edge_distance = "min(min(X,W-1-X),min(Y,H-1-Y))"
    return (
        f"[0:v]split=2[source_clean][source_patch];"
        f"[source_patch]crop={width}:{height}:{x}:{patch_y},format=rgba,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
        f"a='255*min(1,{edge_distance}/{feather})'[subtitle_patch];"
        f"[source_clean][subtitle_patch]overlay={x}:{y}[source_without_original];"
    )


def _original_subtitle_removal_prefix(
    region: tuple[int, int, int, int], source_width: int, source_height: int,
    mode: str,
) -> str:
    if str(mode or "").strip().lower() in {"patch", "inpaint"}:
        return _subtitle_patch_prefix(region, source_width, source_height)
    return _subtitle_blur_prefix(region, source_width, source_height)


def _watermark_filter(text: str, output_width: int, output_height: int) -> str:
    """Return a polished, continuously moving creator watermark filter."""
    normalized = " ".join(str(text or "").split())[:80]
    if not normalized:
        return ""
    # Quote every character with filter-graph meaning. The text is persisted
    # as one line, so the watermark cannot inject another FFmpeg filter.
    escaped = (
        normalized.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(";", "\\;")
    )
    # Keep the mark deliberately secondary to the picture: it must remain
    # recognizable after recompression, but never read like a headline in the
    # middle of the video.
    font_size = max(15, min(38, round(min(output_width, output_height) * 0.029)))
    border_width = max(1, min(3, round(font_size * 0.065)))
    font_path = str(_watermark_font_path()).replace("\\", "/")
    escaped_font_path = (
        font_path.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(";", "\\;")
    )
    # Two unequal periods keep the mark drifting through the whole frame
    # instead of settling on a predictable diagonal or covering one subject.
    x = "(W-text_w)*(0.08+0.84*(0.5+0.5*sin(2*PI*t/31)))"
    y = "(H-text_h)*(0.10+0.80*(0.5+0.5*sin(2*PI*t/43+1.2)))"
    return (
        f"drawtext=fontfile='{escaped_font_path}':text='{escaped}':"
        f"fontsize={font_size}:fontcolor=white@0.46:borderw={border_width}:"
        f"bordercolor=black@0.48:shadowx=1:shadowy=1:shadowcolor=black@0.22:"
        f"x='{x}':y='{y}'"
    )


def _ffmpeg_progress_fraction(progress_text: str, duration: float) -> float | None:
    """Return the latest completed fraction from an FFmpeg progress file."""
    if duration <= 0:
        return None
    values = {}
    for line in progress_text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    try:
        if "out_time_us" in values:
            seconds = int(values["out_time_us"]) / 1_000_000
        elif "out_time_ms" in values:
            # FFmpeg retains the historical ``_ms`` name although this value
            # is expressed in microseconds in current builds.
            seconds = int(values["out_time_ms"]) / 1_000_000
        elif "out_time" in values:
            hours, minutes, seconds_part = values["out_time"].split(":")
            seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds_part)
        else:
            return None
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, seconds / duration))


def render_video(video_path: str, voice_wav_path: str, srt_path: str, output_path: str, output_format: str, subtitle_style: SubtitleStyle, crop: CropSettings, video_id: str, original_subtitle_region: dict | None = None, watermark_text: str = "", subtitle_layout_override: bool = False, progress_callback: Callable[[float], None] | None = None, original_subtitle_removal_mode: str = "blur"):
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
    effective_style = subtitle_style if subtitle_layout_override else _style_for_original_subtitle_region(
        subtitle_style, region_layout, subtitle_width, subtitle_height,
    )
    # A virtual layout keeps captions in one large row even when OCR finds no
    # original subtitle box. Long text is shown as sequential phrases instead
    # of wrapping into two simultaneous lines.
    ass_layout = (
        _manual_subtitle_layout(effective_style, subtitle_width, subtitle_height)
        if subtitle_layout_override
        else region_layout or _default_subtitle_layout(effective_style, subtitle_width, subtitle_height)
    )
    _write_positioned_ass(
        srt_path,
        ass_path,
        effective_style,
        subtitle_width,
        subtitle_height,
        ass_layout,
        # One style is shared by every cue. Long translations are divided into
        # sequential phrases instead of changing font size or aspect ratio.
        fixed_font_size=True,
    )
    rel_video = _ffmpeg_path(video_path, video_temp_dir)
    rel_voice = _ffmpeg_path(voice_wav_path, video_temp_dir)
    rel_ass = _ffmpeg_path(ass_path, video_temp_dir)
    rel_font_directory = _ffmpeg_path(
        str(_karaoke_font_directory()), video_temp_dir,
    )
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
    font_filter_path = rel_font_directory.replace(":", "\\:").replace("'", "'\\\\''")
    ass_filter = f"ass='{ass_filter_path}':fontsdir='{font_filter_path}'"
    watermark_filter = _watermark_filter(watermark_text, subtitle_width, subtitle_height)
    filters = []
    crop_filter = _crop_filter(crop)
    if crop_filter:
        filters.append(crop_filter)
    source_duration = get_video_duration(video_path)
    if source_duration <= 0:
        raise RuntimeError("Unable to determine the source video duration before rendering.")
    removal_region = _source_subtitle_removal_region(
        original_subtitle_region, source_width, source_height,
    )
    requested_removal_mode = str(original_subtitle_removal_mode).strip().lower()
    removal_mode = "patch" if requested_removal_mode in {"patch", "inpaint"} else "blur"
    if removal_region:
        x, y, width, height = removal_region
        log_to_video(
            video_id,
            f"Applying original subtitle {removal_mode} treatment to source pixels "
            f"({x},{y}) {width}x{height}; replacement-subtitle layout is independent.",
            component="RENDER",
        )
    elif original_subtitle_region:
        log_to_video(
            video_id,
            "Original subtitle removal was skipped because the detected region was outside the source frame.",
            level="WARNING",
            component="RENDER",
        )
    if output_format == "blur_background_9_16":
        prefix = ",".join(filters)
        input_label = "[0:v]"
        removal_prefix = ""
        if removal_region:
            removal_prefix = _original_subtitle_removal_prefix(
                removal_region, source_width, source_height, removal_mode,
            )
            input_label = "[source_without_original]"
        source = f"{input_label}{prefix + ',' if prefix else ''}split[base][fg]"
        vf_filter = (
            f"{removal_prefix}{source};[base]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=15:3[bg];"
            f"[fg]scale=1080:1920:force_original_aspect_ratio=decrease[front];[bg][front]overlay=(W-w)/2:(H-h)/2,{ass_filter}"
            f"{',' + watermark_filter if watermark_filter else ''}[outv]"
        )
    else:
        if output_format == "tiktok_9_16_crop":
            filters.extend(["scale=1080:1920:force_original_aspect_ratio=increase", "crop=1080:1920"])
        filters.append(ass_filter)
        if watermark_filter:
            filters.append(watermark_filter)
        if removal_region:
            removal_prefix = _original_subtitle_removal_prefix(
                removal_region, source_width, source_height, removal_mode,
            )
            vf_filter = (
                f"{removal_prefix}[source_without_original]{','.join(filters)}[outv]"
            )
        else:
            vf_filter = ",".join(filters)

    video_encoder, video_encoder_args = preferred_video_encoder()
    cmd_prefix = ["ffmpeg", "-y", "-i", rel_video, "-i", rel_voice]
    if removal_region or output_format == "blur_background_9_16":
        cmd_prefix.extend(["-filter_complex", vf_filter, "-map", "[outv]"])
    else:
        cmd_prefix.extend(["-map", "0:v:0", "-vf", vf_filter])
    cmd_prefix.extend(["-map", "1:a:0", "-t", f"{source_duration:.6f}"])
    audio_args = ["-c:a", "aac", "-b:a", "192k", rel_output]

    def run_render(encoder: str, encoder_args: list[str]):
        progress_handle, progress_path = tempfile.mkstemp(
            prefix=".ffmpeg-progress-",
            suffix=".txt",
            dir=video_temp_dir,
        )
        os.close(progress_handle)
        rel_progress = _ffmpeg_path(progress_path, video_temp_dir)
        command = cmd_prefix + [
            "-progress", rel_progress,
            "-stats_period", "0.5",
            "-nostats",
            "-c:v", encoder, *encoder_args, *audio_args,
        ]
        log_to_video(video_id, f"Running FFmpeg render with {encoder} in Cwd: {video_temp_dir}")
        check_cancellation(video_id)
        stop_monitor = Event()

        def monitor_progress() -> None:
            last_reported = -1.0
            while not stop_monitor.wait(0.4):
                try:
                    progress_text = Path(progress_path).read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                fraction = _ffmpeg_progress_fraction(progress_text, source_duration)
                if fraction is not None and fraction - last_reported >= 0.005:
                    last_reported = fraction
                    if progress_callback:
                        progress_callback(fraction)

        monitor = Thread(target=monitor_progress, name=f"ffmpeg-progress-{video_id}", daemon=True)
        if progress_callback:
            monitor.start()
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=video_temp_dir)
            _stdout, process_stderr = communicate_process(
                video_id,
                process,
                label="FFmpeg video render",
                timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
            )
            check_cancellation(video_id)
            if process.returncode == 0 and progress_callback:
                progress_callback(1.0)
            return process.returncode, process_stderr
        finally:
            stop_monitor.set()
            if monitor.is_alive():
                monitor.join(timeout=1.0)
            try:
                os.remove(progress_path)
            except FileNotFoundError:
                pass

    try:
        return_code, stderr = run_render(video_encoder, video_encoder_args)
        if return_code != 0 and video_encoder != "libx264":
            log_to_video(video_id, f"Hardware encoder {video_encoder} failed; retrying with libx264.")
            return_code, stderr = run_render("libx264", ["-preset", "veryfast", "-crf", "23"])
        if return_code != 0:
            log_to_video(video_id, f"FFmpeg Render Error output:\n{stderr}", level="ERROR", component="RENDER")
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
