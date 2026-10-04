"""Compose installer-sized artwork without stretching the original brand mark."""
from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image


def generate(source: Path, output: Path) -> None:
    mark = Image.open(source).convert("RGBA")
    output.mkdir(parents=True, exist_ok=True)
    for name, size, extent, background in (
        ("sidebar.png", (328, 628), 152, "#11100F"),
        ("header.png", (128, 128), 72, "#1B1A18"),
    ):
        canvas = Image.new("RGBA", size, background)
        logo = mark.copy()
        logo.thumbnail((extent, extent), Image.Resampling.LANCZOS)
        position = ((size[0] - logo.width) // 2, (size[1] - logo.height) // 2)
        canvas.alpha_composite(logo, position)
        canvas.convert("RGB").save(output / name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    generate(arguments.source, arguments.output)
