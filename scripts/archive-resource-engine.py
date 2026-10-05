"""Stream a frozen engine into a ZIP64 archive without loading DLLs into RAM."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def archive_engine(artifact: Path, output: Path) -> None:
    artifact, output = artifact.resolve(), output.resolve()
    if not (artifact / "engine.json").is_file() or not (artifact / "HaizFlowEngine.exe").is_file():
        raise ValueError("A complete frozen engine is required.")
    if output.is_relative_to(artifact) or output.suffix != ".zip":
        raise ValueError("Archive must be a ZIP outside the engine directory.")
    files = sorted(artifact.rglob("*"))
    if any(path.is_symlink() or path.is_junction() for path in files):
        raise ValueError("Engine payload cannot contain filesystem links.")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True) as bundle:
        for path in files:
            if path.is_file():
                bundle.write(path, path.relative_to(artifact).as_posix())
    with zipfile.ZipFile(output) as bundle:
        bad_file = bundle.testzip()
        if bad_file:
            raise ValueError(f"Archive CRC verification failed: {bad_file}")
    print(f"Verified engine archive: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    archive_engine(arguments.artifact, arguments.output)
