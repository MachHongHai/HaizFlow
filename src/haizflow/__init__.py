"""HaizFlow desktop application and local media-processing pipeline."""

import json
import re
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _application_version() -> str:
    # Distribution metadata can be stale in an editable build environment.
    # Read the running artifact, never the install root's original BUILD-INFO
    # or active pointer (which may already point to a different Core).
    if getattr(sys, "frozen", False):
        core = Path(sys.executable).absolute().parent
        build_info = core / "BUILD-INFO.json"
        if build_info.is_file():
            data = json.loads(build_info.read_text(encoding="utf-8"))
            value = data.get("version") if isinstance(data, dict) else None
            if (not isinstance(data, dict) or data.get("application") != "HaizFlow"
                    or not isinstance(value, str)
                    or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value)
                    or (core.parent.name == "versions" and core.name != value)):
                raise ValueError("Thông tin phiên bản bản cài đặt không hợp lệ.")
            return value
    # Source checkouts use canonical project metadata, even when an older
    # editable installation is present in the interpreter.
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not getattr(sys, "frozen", False) and pyproject.is_file():
        return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    try:
        return version("haizflow")
    except PackageNotFoundError:
        return "0.0.0+local"


__version__ = _application_version()
