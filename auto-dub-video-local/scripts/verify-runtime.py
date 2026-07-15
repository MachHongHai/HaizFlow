import argparse
import importlib.metadata
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def expected_packages() -> dict[str, str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected = {}
    for value in project.get("dependencies", []):
        requirement = Requirement(value)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        exact_versions = [item.version for item in requirement.specifier if item.operator == "=="]
        if len(exact_versions) != 1:
            raise RuntimeError(f"Runtime dependency must have one exact version: {value}")
        expected[requirement.name] = exact_versions[0]
    return expected


def check(condition: bool, message: str, failures: list[str]) -> None:
    marker = "OK" if condition else "FAIL"
    print(f"[{marker}] {message}")
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the AutoDub source/build runtime.")
    parser.add_argument("--for-build", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    check((3, 11) <= sys.version_info[:2] <= (3, 13), f"Python {sys.version.split()[0]}", failures)
    expected_venv = (ROOT / ".venv").resolve()
    check(Path(sys.prefix).resolve() == expected_venv, f"Project virtual environment: {expected_venv}", failures)

    for distribution, expected in expected_packages().items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            actual = "missing"
        check(actual == expected or actual.startswith(expected + "+"), f"{distribution} {actual} (expected {expected})", failures)

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    try:
        from PySide6 import QtCore, QtMultimedia, QtQml, QtQuick  # noqa: F401

        check(True, "Qt Core/QML/Quick/Multimedia imports", failures)
    except Exception as exc:
        check(False, f"Qt imports: {exc}", failures)

    try:
        import torch

        torch_build = "CUDA-capable" if torch.version.cuda else "CPU-only"
        check(bool(torch.version.cuda), f"Unified Torch build: {torch_build}", failures)
        print(f"[INFO] CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"[INFO] CUDA device: {torch.cuda.get_device_name(0)}")
    except Exception as exc:
        check(False, f"Torch import: {exc}", failures)

    try:
        import torchcodec  # noqa: F401

        print("[OK] Optional TorchCodec native decoder")
    except Exception:
        print(
            "[WARN] Optional TorchCodec decoder is unavailable because the bundled FFmpeg is a static build. "
            "The pipeline supplies preloaded waveforms to WhisperX and does not depend on this decoder."
        )

    from autodub.config import HF_HOME, RUNTIME_DATA_DIR, TORCH_HOME

    check(Path(RUNTIME_DATA_DIR).is_absolute(), f"Runtime data: {RUNTIME_DATA_DIR}", failures)
    check(Path(HF_HOME).is_absolute(), f"Hugging Face cache: {HF_HOME}", failures)
    check(Path(TORCH_HOME).is_absolute(), f"Torch cache: {TORCH_HOME}", failures)

    for executable in ("ffmpeg.exe", "ffprobe.exe"):
        path = ROOT / "runtime" / "bin" / executable
        check(path.is_file(), f"Bundled media tool: {path}", failures)

    pip_check = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    check(pip_check.returncode == 0, pip_check.stdout.strip() or pip_check.stderr.strip() or "pip check", failures)

    if args.for_build:
        check((ROOT / "src" / "autodub" / "desktop" / "qml" / "Main.qml").is_file(), "QML source tree", failures)
        check(importlib.metadata.version("pyinstaller") == "6.21.0", "PyInstaller 6.21.0", failures)

    if failures:
        print(f"Runtime verification failed with {len(failures)} issue(s).")
        return 1
    print("Runtime verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
