"""Generate a deterministic multi-resolution HaizFlow Windows icon."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


ICON_SIZES = (16, 32, 48, 64, 256)


def _icon_image(size: int) -> bytes:
    pixels = bytearray()
    border = max(1, round(size * 0.08))
    triangle_start = round(size * 0.41)
    triangle_end = round(size * 0.73)
    triangle_half_height = round(size * 0.20)
    center_y = size // 2
    triangle_width = max(1, triangle_end - triangle_start)
    for y in range(size - 1, -1, -1):
        for x in range(size):
            color = (20, 29, 38, 255)
            if border <= x < size - border and border <= y < size - border:
                color = (57, 203, 195, 255)
            if (
                triangle_start <= x <= triangle_end
                and abs(y - center_y) <= (x - triangle_start) * triangle_half_height // triangle_width
            ):
                color = (20, 29, 38, 255)
            pixels.extend((color[2], color[1], color[0], color[3]))
    mask_stride = ((size + 31) // 32) * 4
    mask = bytes(mask_stride * size)
    dib = struct.pack("<IIIHHIIIIII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0)
    return dib + pixels + mask


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    images = [(size, _icon_image(size)) for size in ICON_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = []
    for size, image in images:
        encoded_size = 0 if size == 256 else size
        entries.append(
            struct.pack("<BBBBHHII", encoded_size, encoded_size, 0, 0, 1, 32, len(image), offset)
        )
        offset += len(image)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(header + b"".join(entries) + b"".join(image for _size, image in images))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
