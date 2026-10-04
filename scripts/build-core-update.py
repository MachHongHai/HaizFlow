"""Generate Full/Delta from finalized raw Core artifacts, never user data."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.update.filesystem import no_links, version
from haizflow.update.packages import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engineering", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("release_finalize", ROOT / "scripts/finalize-release.py")
    finalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finalizer)
    finalizer.verify_installer_eligibility(args.target, engineering=args.engineering)
    target = json.loads((args.target / "BUILD-INFO.json").read_text(encoding="utf-8"))
    if target.get("entrypoint") != "HaizFlowCore.exe" or (args.target / "core-manifest.json").exists():
        raise ValueError("Use the raw finalized dist/HaizFlowCore artifact, not an installed version tree.")
    base_version = None
    if args.base:
        no_links(args.base)
        finalizer.verify_manifest(args.base)
        base = json.loads((args.base / "BUILD-INFO.json").read_text(encoding="utf-8"))
        if (base.get("application") != "HaizFlow" or base.get("entrypoint") != "HaizFlowCore.exe"
                or base.get("packaging") != "PyInstaller onedir"
                or (base.get("git_dirty") and not args.engineering)
                or (args.base / "runtime").exists() or (args.base / "update-state").exists()
                or (args.base / "core-manifest.json").exists()):
            raise ValueError("Base must be the preserved finalized raw Core from the previous release.")
        base_version = version(base["version"])
    manifest = generate(args.base, args.target, args.output, base_version=base_version,
                        target_version=version(target["version"]))
    print(json.dumps({"package": manifest.data["package_name"],
                      "sha256": manifest.data["package_sha256"],
                      "size": manifest.data["package_size"]}, indent=2))


if __name__ == "__main__":
    main()
