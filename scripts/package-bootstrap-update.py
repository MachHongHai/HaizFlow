"""Copy an independently verified versioned bootstrap into the immutable Core."""

import argparse
import importlib.util
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.update.bootstrap_refresh import ENTRIES, verify_payload  # noqa: E402
from haizflow.update.filesystem import no_links  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    args = parser.parse_args()
    no_links(args.bootstrap)
    no_links(args.core)
    if not (args.core / "HaizFlowCore.exe").is_file():
        raise ValueError("Expected a raw Core build, not an installed app.")
    value = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    spec = importlib.util.spec_from_file_location("bootstrap_finalizer", ROOT / "scripts/finalize-bootstrap.py")
    finalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finalizer)
    target = args.core / "bootstrap-update"
    if target.exists():
        raise ValueError("Bootstrap payload already exists; refusing to overwrite it.")
    for directory, executable, _ in ENTRIES:
        source = args.bootstrap / directory
        finalizer.verify(source, executable, source_commit=commit, version=value, engineering=False)
        shutil.copytree(source, target / directory)
    verify_payload(args.core, value, commit)
    print("New launcher/updater and isolated runtime are included in Full and Delta Core updates.")


if __name__ == "__main__":
    main()
