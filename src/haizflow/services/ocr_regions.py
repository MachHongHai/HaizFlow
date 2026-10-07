"""Editable source-caption coverage, stored separately from immutable OCR results."""

import math

from haizflow.schemas.video import CropSettings


def normalize_region(value: dict) -> dict[str, float]:
    keys = ("x_percent", "y_percent", "width_percent", "height_percent")
    try:
        region = {key: float(value[key]) for key in keys}
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid OCR rectangle.") from None
    if not all(math.isfinite(item) for item in region.values()):
        raise ValueError("Invalid OCR rectangle.")
    x, y, width, height = (region[key] for key in keys)
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 100.001 or y + height > 100.001:
        raise ValueError("OCR rectangle must stay inside the source frame.")
    return {key: round(item, 5) for key, item in region.items()}


def effective_region(video, detected: dict | None = None) -> dict | None:
    override = getattr(video, "original_subtitle_region_override", None)
    if override:
        try:
            return normalize_region(override)
        except ValueError:
            pass
    return detected


def source_frame_in_output(width: int, height: int, output_format: str, crop: CropSettings | dict) -> dict[str, float]:
    """Describe the full source frame in output coordinates, before clipping.

    Keeping the unclipped affine frame lets dragging a box on a cropped preview
    round-trip back to source percentages without changing its hidden edges.
    """
    from haizflow.pipeline.render import _crop_geometry

    if isinstance(crop, dict):
        crop = CropSettings.model_validate(crop)
    width, height = max(1, width), max(1, height)
    crop_x, crop_y, crop_width, crop_height = _crop_geometry(width, height, crop)
    output_width = max(2, int(crop_width) // 2 * 2)
    output_height = max(2, int(crop_height) // 2 * 2)
    if output_format in {"tiktok_9_16_crop", "blur_background_9_16"}:
        output_width, output_height = 1080, 1920
        scale = (max if output_format == "tiktok_9_16_crop" else min)(
            output_width / crop_width, output_height / crop_height)
        scale_x = scale_y = scale
        offset_x = (output_width - crop_width * scale) / 2
        offset_y = (output_height - crop_height * scale) / 2
    else:
        scale_x, scale_y = output_width / crop_width, output_height / crop_height
        offset_x = offset_y = 0.0
    return {
        "x_percent": (offset_x - crop_x * scale_x) * 100 / output_width,
        "y_percent": (offset_y - crop_y * scale_y) * 100 / output_height,
        "width_percent": width * scale_x * 100 / output_width,
        "height_percent": height * scale_y * 100 / output_height,
    }
