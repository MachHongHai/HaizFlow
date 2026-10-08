"""Local synthetic-version fixtures using real frozen Core/launcher; no network."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.update.filesystem import atomic_json, no_links, remove_owned, sha256
from haizflow.update.manifest import inventory
from haizflow.update.manifest import Manifest
from haizflow.update.packages import generate
from haizflow.update.state import Layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--base-artifact", type=Path)
    parser.add_argument("--update-package", type=Path)
    parser.add_argument("--update-manifest", type=Path)
    parser.add_argument("--require-unsigned", action="store_true",
                        help="Require NotSigned for Core, launcher and updater before testing")
    parser.add_argument("--process-timeout", type=float, default=300,
                        help="Outer launch bound, including pre-start inventory hashing; health remains 30 seconds")
    args = parser.parse_args()
    real_release_delta = args.base_artifact is not None
    if any((args.base_artifact, args.update_package, args.update_manifest)) and not all(
            (args.base_artifact, args.update_package, args.update_manifest)):
        parser.error("Provide base artifact, update package and update manifest together.")
    if not 30 <= args.process_timeout <= 900:
        parser.error("--process-timeout must be between 30 and 900 seconds")
    artifact = args.artifact.absolute()
    no_links(artifact)
    current_version = json.loads((artifact / "BUILD-INFO.json").read_text("utf-8"))["version"]
    base_artifact = args.base_artifact.absolute() if real_release_delta else artifact
    no_links(base_artifact)
    base_version = json.loads((base_artifact / "BUILD-INFO.json").read_text("utf-8"))["version"]
    def next_patch(value):
        major, minor, patch = map(int, value.split("."))
        return f"{major}.{minor}.{patch + 1}"
    target_version = current_version if real_release_delta else next_patch(base_version)
    broken_version = next_patch(target_version)
    if not (artifact / "update-layout.json").is_file():
        raise ValueError("A versioned frozen artifact is required.")
    unsigned_verified = False
    if args.require_unsigned:
        if sys.platform != "win32":
            raise RuntimeError("Authenticode status inspection requires Windows.")
        executables = (artifact / "HaizFlow.exe", artifact / "updater/HaizFlowUpdater.exe",
                       artifact / "versions" / current_version / "HaizFlowCore.exe")
        for executable in executables:
            environment = os.environ.copy()
            # pwsh 7's inherited module path can make Windows PowerShell 5 try
            # to load incompatible security cmdlets. Use its own built-in path.
            shell = shutil.which("pwsh.exe") or "powershell.exe"
            if shell.lower().endswith("powershell.exe"):
                environment.pop("PSModulePath", None)
            environment["HAIZFLOW_TEST_SIGN_TARGET"] = str(executable)
            check = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command",
                "$signature = Get-AuthenticodeSignature -LiteralPath $env:HAIZFLOW_TEST_SIGN_TARGET; if (!$signature) { exit 2 }; $signature.Status.ToString() | ConvertTo-Json; exit 0"],
                env=environment, capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if check.returncode or json.loads(check.stdout) != "NotSigned":
                raise RuntimeError("Expected an unsigned frozen executable: " + str(executable)
                    + f"; status command exit={check.returncode}, output={check.stdout!r}, error={check.stderr[-500:]!r}")
        unsigned_verified = True
        print("Core, launcher and updater are all NotSigned; testing unsigned delta.", flush=True)
    parent = ROOT / "build/frozen-delta-smoke"
    root = parent / uuid.uuid4().hex
    report = ROOT / "build/frozen-delta-reports" / root.name
    report.mkdir(parents=True)
    install = root / "installation"
    source = root / "target-fixture"
    assets = root / "packages"
    passed = False
    try:
        shutil.copytree(base_artifact, install)
        layout = Layout(install)
        layout.seed(base_version)
        fixture = layout.runtime / "data/user-fixture.json"
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(b"USER DATA MUST SURVIVE DELTA AND ROLLBACK")
        external = root / "external-project/project.json"
        external.parent.mkdir()
        external.write_bytes(b"EXTERNAL PROJECT")
        before = {str(path): sha256(path) for path in (fixture, external)}
        # Installed metadata files are never input files of another manifest.
        shutil.copytree(artifact / "versions" / current_version, source,
                        ignore=shutil.ignore_patterns("core-manifest.json", "core-complete.json"))
        if real_release_delta:
            manifest = Manifest.parse(json.loads(args.update_manifest.read_text("utf-8")))
            assert manifest.data["base_version"] == (base_version if manifest.data["package_type"] == "delta" else None)
            assert manifest.data["target_version"] == target_version
            layout.prepare(args.update_package, manifest)
        else:
            (source / "delta-fixture.txt").write_bytes(b"NEW CORE FIXTURE DATA")
            manifest = generate(layout.core(base_version), source, assets,
                                base_version=base_version, target_version=target_version)
            layout.prepare(assets / manifest.data["package_name"], manifest)
        print("Delta reconstructed with exact inventory; activating real Core fixture.", flush=True)
        assert inventory(layout.core(target_version)) == inventory(source)
        with layout.lock():
            layout.activate(core_exited=True)

        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["TEMP"] = environment["TMP"] = str(root / "temp")
        (root / "temp").mkdir()
        def launch(label):
            with (report / (label + ".stdout.log")).open("wb") as out, (report / (label + ".stderr.log")).open("wb") as err:
                result = subprocess.run([str(install / "HaizFlow.exe"), "--ui-smoke-test", "--health-timeout", "30"],
                                        env=environment, stdout=out, stderr=err, timeout=args.process_timeout,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise RuntimeError(f"Frozen launcher failed: {label}, exit={result.returncode}")

        launch("delta-success")
        assert layout.active()["active"] == target_version and layout.journal()["state"] == "confirmed"
        assert inventory(layout.core(target_version)) == inventory(source), "Startup changed immutable Core files"
        print("Real Core health confirmed; testing failed-start rollback.", flush=True)

        # A checksum-valid but unlaunchable future Core must roll back once.
        (source / "HaizFlowCore.exe").write_bytes(b"INTENTIONALLY NOT A WINDOWS EXECUTABLE")
        broken = generate(layout.core(target_version), source, assets,
                          base_version=target_version, target_version=broken_version)
        layout.prepare(assets / broken.data["package_name"], broken)
        with layout.lock():
            layout.activate(core_exited=True)
        launch("rollback-success")
        assert layout.active()["active"] == target_version and layout.journal()["state"] == "rolled_back"
        assert before == {str(path): sha256(path) for path in (fixture, external)}
        atomic_json(report / "result.json", dict(passed=True, actual_frozen_binaries=True,
            synthetic_versions=not real_release_delta,
            real_release_delta=real_release_delta and manifest.data["package_type"] == "delta",
            real_release_full=real_release_delta and manifest.data["package_type"] == "full",
            synthetic_rollback=True, base_version=base_version, target_version=target_version,
            network_tested=False, delta_size=manifest.data["package_size"],
            target_inventory_exact=True, startup_core_immutable=True, rollback=True, user_data_preserved=True,
            unsigned_binaries_verified=unsigned_verified))
        passed = True
        print("Real frozen delta reconstruction/health/rollback passed. Reports: " + str(report), flush=True)
    finally:
        if passed:
            remove_owned(parent, root)
        else:
            print("Failed frozen fixture preserved: " + str(root), flush=True)


if __name__ == "__main__":
    main()
