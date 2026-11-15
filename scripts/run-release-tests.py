"""Run every collected module in a fresh process and verify the exact test inventory.

Qt keeps process-wide registries and deferred callbacks across QML engines. Tests
with synthetic controllers must not share those registries across modules.
Integration cases inside each complete module still run together, unmodified.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Inventory:
    def __init__(self, output: Path):
        self.output = output

    def pytest_collection_finish(self, session):
        modules: dict[str, list[str]] = {}
        for item in session.items:
            path = Path(item.path).resolve()
            if not path.is_relative_to(ROOT / "tests"):
                raise ValueError("Release tests must remain in the repository's tests directory.")
            modules.setdefault(path.relative_to(ROOT).as_posix(), []).append(item.nodeid)
        self.output.write_text(json.dumps(modules, ensure_ascii=False, indent=2), encoding="utf-8")


def run_pytest(args) -> int:
    import pytest

    arguments = [str(args.run_module or args.tests), "-q", "-p", "no:cacheprovider"]
    if args.run_module:
        arguments += ["--basetemp", str(args.temporary), "--junitxml", str(args.junit)]
    else:
        arguments += ["--collect-only"]
    return int(pytest.main(arguments, plugins=[Inventory(args.inventory)]))


def run_suite(args) -> int:
    args.temporary.mkdir(parents=True, exist_ok=False)
    args.reports.mkdir(parents=True, exist_ok=False)
    inventory_path = args.reports / "collected.json"
    collector_log = args.reports / "collection.log"
    with collector_log.open("wb") as output:
        result = subprocess.run([sys.executable, __file__, "--tests", str(args.tests),
            "--inventory", str(inventory_path)], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=300)
    if result.returncode:
        print(f"Test collection failed; inspect {collector_log}", flush=True)
        return 1
    expected = json.loads(inventory_path.read_text("utf-8"))
    if not expected or any(not names for names in expected.values()):
        raise ValueError("The release test inventory is empty or incomplete.")
    total = sum(map(len, expected.values()))
    print(f"Collected {total} cases in {len(expected)} complete modules. Reports: {args.reports}", flush=True)

    def run_module(entry):
        index, (module, names) = entry
        label = f"{index:03d}-{Path(module).stem}"
        work = args.temporary / f"{index:03d}"
        work.mkdir()
        log = args.reports / (label + ".log")
        actual_inventory = args.reports / (label + ".json")
        started = time.monotonic()
        timed_out = False
        with log.open("wb") as output:
            process = subprocess.Popen([sys.executable, __file__, "--run-module", str(ROOT / module),
                "--inventory", str(actual_inventory), "--temporary", str(work / "p"),
                "--junit", str(args.reports / (label + ".xml"))], cwd=ROOT,
                stdout=output, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                code = process.wait(timeout=900)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait(timeout=30)
                code = process.returncode
        actual = json.loads(actual_inventory.read_text("utf-8")) if actual_inventory.is_file() else {}
        same_inventory = set(actual) == {module} and Counter(actual[module]) == Counter(names)
        passed = code == 0 and same_inventory and not timed_out
        print(f"{'PASS' if passed else 'FAIL'} {module}: {len(names)} cases ({time.monotonic() - started:.1f}s)", flush=True)
        if not passed:
            print(f"exit={code}, exact_inventory={same_inventory}, timeout={timed_out}; log={log}", flush=True)
            for line in log.read_text("utf-8", errors="replace").splitlines()[-55:]:
                print(line[:700], flush=True)
        return dict(module=module, cases=len(names), passed=passed, exit_code=code,
                    exact_inventory=same_inventory, timeout=timed_out, log=str(log))

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run_module, enumerate(sorted(expected.items()))))
    passed = all(result["passed"] for result in results)
    report = dict(passed=passed, collected_cases=total, complete_modules=len(results), modules=results)
    (args.reports / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Release test inventory: {total} cases, {len(results)} modules, no deselection; passed={passed}.", flush=True)
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", type=Path, default=ROOT / "tests")
    parser.add_argument("--temporary", type=Path)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--run-module", type=Path)
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args()
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if args.inventory:
        return run_pytest(args)
    if not args.temporary or not args.reports:
        parser.error("--temporary and --reports are required")
    return run_suite(args)


if __name__ == "__main__":
    raise SystemExit(main())
