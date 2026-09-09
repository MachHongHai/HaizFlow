#!/usr/bin/env python3
"""Write the command contract embedded in one frozen engine archive."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

PACKS = {
    "cpu": "engine-cpu-py313",
    "cuda128": "engine-cuda128-py313",
    "vision": "engine-vision-onnx",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PACKS), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    executable = "HaizFlowEngine.exe"
    commands = {
        "pack_id": PACKS[args.profile],
        "profile": args.profile,
        "version": str(args.version),
        "protocol_version": 1,
        "smoke_command": [executable, "--smoke", "--profile", args.profile],
        "rpc_command": [executable, "--rpc"],
    }
    if args.profile in {"cpu", "cuda128"}:
        commands.update(
            {
                "hymt2_server": [executable, "--hymt2-worker", "--server"],
                "omnivoice_worker": [executable, "--omnivoice-worker"],
                "omnivoice_server": [executable, "--omnivoice-server"],
                "demucs": [executable, "--demucs-separate"],
                "demucs_task": [executable],
                "transcribe": [executable],
                "runtime_probe": [executable, "--runtime-probe"],
            }
        )
    else:
        commands["subtitle_ocr"] = [executable]

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".engine-", suffix=".json.tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(commands, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
