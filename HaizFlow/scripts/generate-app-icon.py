"""Generate the multi-resolution HaizFlow Windows icon from the brand mark."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


ICON_SIZES = (16, 32, 48, 64, 256)
# Windows reserves its own taskbar safe area.  Crop the decorative outer card
# first so the HaizFlow glyph has the same visual weight as peer applications.
ICON_CARD_CROP_INSET = 112
ICON_CONTENT_SCALE = 1.0
DEFAULT_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "haizflow"
    / "desktop"
    / "assets"
    / "branding"
    / "haizflow-mark.png"
)


def _load_mark(source: Path) -> Image.Image:
    if not source.is_file():
        raise RuntimeError(f"HaizFlow brand mark is missing: {source}")
    with Image.open(source) as image:
        mark = image.convert("RGBA")
    if mark.width != mark.height:
        raise RuntimeError(f"HaizFlow brand mark must be square: {source}")
    if mark.getbbox() is None:
        raise RuntimeError(f"HaizFlow brand mark is fully transparent: {source}")
    return mark


def _fit_mark_for_windows_taskbar(mark: Image.Image, size: int) -> Image.Image:
    """Fill Windows' icon safe area instead of preserving source transparency."""
    alpha_bounds = mark.getchannel("A").getbbox()
    if alpha_bounds is None:
        raise RuntimeError("HaizFlow brand mark is fully transparent")
    cropped = mark.crop(alpha_bounds)
    crop_inset = min(ICON_CARD_CROP_INSET, (min(cropped.size) - 1) // 2)
    if crop_inset:
        cropped = cropped.crop(
            (crop_inset, crop_inset, cropped.width - crop_inset, cropped.height - crop_inset)
        )
    canvas = Image.new("RGBA", (size, size))
    target_size = max(1, round(size * ICON_CONTENT_SCALE))
    scale = min(target_size / cropped.width, target_size / cropped.height)
    resized = cropped.resize(
        (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return canvas


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args(argv)

    mark = _load_mark(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    icon_frames = [_fit_mark_for_windows_taskbar(mark, size) for size in ICON_SIZES]
    icon_frames[-1].save(
        args.output,
        format="ICO",
        sizes=[(size, size) for size in ICON_SIZES],
        bitmap_format="png",
        append_images=icon_frames[:-1],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
