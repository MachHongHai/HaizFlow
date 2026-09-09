"""Generate the PyInstaller Windows version resource from pyproject.toml."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in version.split(".") if part.isdigit()]
    return tuple((parts + [0, 0, 0, 0])[:4])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = str(metadata["version"])
    major, minor, patch, build = version_tuple(version)
    resource = f'''# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build}),
    prodvers=({major}, {minor}, {patch}, {build}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'HaizFlow'),
        StringStruct('FileDescription', 'HaizFlow desktop video dubbing'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'HaizFlow'),
        StringStruct('OriginalFilename', 'HaizFlow.exe'),
        StringStruct('ProductName', 'HaizFlow'),
        StringStruct('ProductVersion', '{version}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(resource, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
