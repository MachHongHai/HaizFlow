"""Assemble verified Core + independent bootstrap; never packages user runtime."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.update.filesystem import atomic_json, no_links, sha256, version
from haizflow.update.packages import generate, reconstruct
from haizflow.update.state import Layout, provision


def assemble(core: Path, launcher: Path, updater: Path, output: Path, assets: Path, *, engineering=False):
    spec = importlib.util.spec_from_file_location("release_finalize", ROOT / "scripts" / "finalize-release.py")
    finalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finalizer)
    finalizer.verify_installer_eligibility(core, engineering=engineering)
    info = json.loads((core / "BUILD-INFO.json").read_text(encoding="utf-8"))
    target = version(info["version"])
    if info.get("entrypoint") != "HaizFlowCore.exe":
        raise ValueError("Build a real HaizFlowCore executable with -CoreLayout; do not rename a flat build.")
    for directory, executable in ((launcher, "HaizFlow.exe"), (updater, "HaizFlowUpdater.exe")):
        no_links(directory)
        if not (directory / executable).is_file() or not (directory / "_internal").is_dir():
            raise ValueError("Independent onedir bootstrap is missing: " + str(directory))
        if any(path.name.startswith("PySide6") or path.name.startswith("torch") for path in directory.rglob("*")):
            raise ValueError("Bootstrap must not depend on GUI or AI runtimes.")
    no_links(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new staging directory.")
    manifest = generate(None, core, assets, base_version=None, target_version=target)
    shutil.copytree(launcher, output)
    shutil.copytree(updater, output / "updater")
    reconstruct(assets / manifest.data["package_name"], manifest, output / "versions" / target)
    provision(output)
    Layout(output).validate_core(target)
    for name in ("LICENSE.txt", "NOTICE.txt", "THIRD_PARTY_NOTICES.md", "INSTALL-REQUIREMENTS.json"):
        shutil.copy2(core / name, output / name)
    info.update(layout="versioned", engineering=bool(engineering))
    atomic_json(output / "BUILD-INFO.json", info)
    files = sorted(path for path in output.rglob("*") if path.is_file())
    (output / "SHA256SUMS.txt").write_text("".join(
        f"{sha256(path)} *{path.relative_to(output).as_posix()}\n" for path in files), encoding="utf-8")
    print(json.dumps(dict(artifact=str(output), full_core_package=manifest.data["package_name"],
                         core_bytes=manifest.data["package_size"], engineering=engineering), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("core", "launcher", "updater", "output", "assets"):
        parser.add_argument("--" + argument, type=Path, required=True)
    parser.add_argument("--engineering", action="store_true")
    args = parser.parse_args()
    assemble(args.core, args.launcher, args.updater, args.output, args.assets, engineering=args.engineering)
