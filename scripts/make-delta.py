"""Generate local full + optional file-level delta Core packages (no build/upload)."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from haizflow.update.packages import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-version")
    parser.add_argument("--target-version")
    parser.add_argument("--project-schema", type=int, default=4)
    parser.add_argument("--video-schema", type=int, default=19)
    args = parser.parse_args()
    target_version = args.target_version or args.target.name.removeprefix("core-")
    base_version = args.base_version or (args.base.name.removeprefix("core-") if args.base else None)
    full = generate(None, args.target, args.output, base_version=None, target_version=target_version,
                    project_schema=args.project_schema, video_schema=args.video_schema)
    result = {"full": full.data["package_name"], "full_bytes": full.data["package_size"]}
    if args.base:
        delta = generate(args.base, args.target, args.output, base_version=base_version,
                         target_version=target_version, project_schema=args.project_schema, video_schema=args.video_schema)
        result.update(delta=delta.data["package_name"], delta_bytes=delta.data["package_size"],
                      saved_bytes=full.data["package_size"] - delta.data["package_size"],
                      saved_percent=round(100 * (1 - delta.data["package_size"] / full.data["package_size"]), 1))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
