"""Generate a deterministic multi-resolution HaizFlow Windows icon."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    size = 256
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            color = (20, 29, 38, 255)
            if 20 <= x <= 236 and 20 <= y <= 236:
                color = (57, 203, 195, 255)
            if 105 <= x <= 188 and abs(y - 128) <= (x - 105) * 52 // 83:
                color = (20, 29, 38, 255)
            pixels.extend((color[2], color[1], color[0], color[3]))
    dib = struct.pack("<IIIHHIIIIII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0)
    mask = bytes((size // 8) * size)
    image = dib + pixels + mask
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(image), 6 + 16)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(header + entry + image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
