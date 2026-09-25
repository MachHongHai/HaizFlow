"""Deterministic text-overlay sprites shared by preview and export."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.pipeline.render import _watermark_font_path
from haizflow.schemas.editor import EditorTextStyle


def sprite_key(text: str, style: EditorTextStyle, width: int, height: int) -> str:
    payload = {
        "version": 1,
        "text": str(text or ""),
        "style": style.model_dump(),
        "width": max(1, int(width)),
        "height": max(1, int(height)),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:32]


def _rgba(value: str, opacity_percent: int = 100) -> tuple[int, int, int, int]:
    try:
        red, green, blue = ImageColor.getrgb(str(value or "#FFFFFF"))[:3]
    except ValueError:
        red, green, blue = 255, 255, 255
    return red, green, blue, round(255 * max(0, min(100, opacity_percent)) / 100)


def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font, maximum_width: float) -> list[str]:
    result: list[str] = []
    for paragraph in str(text or "").splitlines() or [""]:
        words = paragraph.split()
        if not words:
            result.append("")
            continue
        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if draw.textlength(candidate, font=font) <= maximum_width:
                line = candidate
            else:
                result.append(line)
                line = word
        result.append(line)
    return result or [""]


def render_text_overlay_sprite(
    text: str,
    style: EditorTextStyle,
    reference_width: int,
    reference_height: int,
) -> dict:
    """Return one immutable RGBA sprite for the requested style.

    Preview and FFmpeg export both consume this same PNG, removing the font,
    wrapping and outline differences caused by separate QML/drawtext paths.
    """
    reference_width = max(1, int(reference_width))
    reference_height = max(1, int(reference_height))
    key = sprite_key(text, style, reference_width, reference_height)
    directory = Path(RUNTIME_DATA_DIR) / "cache" / "editor-text-sprites" / key
    target = directory / "sprite.png"
    marker = directory / "complete.json"
    if marker.is_file() and target.is_file() and target.stat().st_size > 0:
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            payload["path"] = str(target)
            return payload
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass

    directory.mkdir(parents=True, exist_ok=True)
    font_path = _watermark_font_path(
        style.font_family,
        style.font_weight >= 600,
        style.italic,
    )
    font = ImageFont.truetype(str(font_path), max(6, round(style.font_size)))
    scratch = Image.new("RGBA", (reference_width, reference_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(scratch)
    content = str(text or "").upper() if style.uppercase else str(text or "")
    available_width = max(24, reference_width * style.max_width_percent / 100)
    lines = _wrap_lines(draw, content, font, available_width)
    if style.max_lines > 0:
        lines = lines[: style.max_lines]
    content = "\n".join(lines)
    spacing = max(0, round(style.font_size * (style.line_spacing - 1)))
    stroke_width = max(0, round(style.outline_width))
    bounds = draw.multiline_textbbox(
        (0, 0),
        content or " ",
        font=font,
        spacing=spacing,
        align=style.alignment,
        stroke_width=stroke_width,
    )
    text_width = max(1, bounds[2] - bounds[0])
    text_height = max(1, bounds[3] - bounds[1])
    padding = max(0, round(style.background_padding))
    shadow_extent = max(
        0,
        round(style.shadow_blur * 2),
        abs(round(style.shadow_offset_x)),
        abs(round(style.shadow_offset_y)),
    )
    margin = stroke_width + padding + shadow_extent + 4
    sprite_width = text_width + 2 * margin
    sprite_height = text_height + 2 * margin
    origin = (margin - bounds[0], margin - bounds[1])

    image = Image.new("RGBA", (sprite_width, sprite_height), (0, 0, 0, 0))
    if style.background_opacity_percent > 0:
        background = ImageDraw.Draw(image)
        background.rounded_rectangle(
            (
                margin - padding,
                margin - padding,
                margin + text_width + padding,
                margin + text_height + padding,
            ),
            radius=max(0, round(style.background_radius)),
            fill=_rgba(style.background_color, style.background_opacity_percent),
        )

    if style.shadow_opacity_percent > 0 and (
        style.shadow_offset_x or style.shadow_offset_y or style.shadow_blur
    ):
        shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.multiline_text(
            (origin[0] + style.shadow_offset_x, origin[1] + style.shadow_offset_y),
            content,
            font=font,
            fill=_rgba(style.shadow_color, style.shadow_opacity_percent),
            spacing=spacing,
            align=style.alignment,
            stroke_width=stroke_width,
            stroke_fill=_rgba(style.shadow_color, style.shadow_opacity_percent),
        )
        if style.shadow_blur > 0:
            shadow = shadow.filter(ImageFilter.GaussianBlur(style.shadow_blur))
        image.alpha_composite(shadow)

    image_draw = ImageDraw.Draw(image)
    image_draw.multiline_text(
        origin,
        content,
        font=font,
        fill=_rgba(style.text_color),
        spacing=spacing,
        align=style.alignment,
        stroke_width=stroke_width,
        stroke_fill=_rgba(style.outline_color),
    )
    temporary = target.with_suffix(".png.part")
    image.save(temporary, format="PNG")
    os.replace(temporary, target)
    payload = {
        "key": key,
        "path": str(target),
        "width": sprite_width,
        "height": sprite_height,
        "referenceWidth": reference_width,
        "referenceHeight": reference_height,
    }
    marker_tmp = marker.with_suffix(".json.part")
    marker_tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(marker_tmp, marker)
    return payload
