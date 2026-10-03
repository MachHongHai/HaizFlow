"""Contain this checkout's virtual-environment caches before Python imports.

Configures only .venv, never global Windows/Python settings. The generated
startup files are ignored development state, not release payload.
"""

from __future__ import annotations

import configparser
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    expected = (ROOT / ".venv").resolve()
    if Path(sys.prefix).resolve() != expected:
        raise SystemExit("Run this script with this checkout's .venv Python.")
    from haizflow import config
    from haizflow.core.paths import engines_dir, resource_packages_dir

    paths = [
        config.APP_DATA_DIR,
        config.MODELS_DIR,
        config.CACHE_DIR,
        config.TMP_DIR,
        str(engines_dir()),
        str(resource_packages_dir()),
    ]
    # This is a dev-specific opt-in. Do not impose a drive letter on the
    # application or on users who intentionally install on the system drive.
    if sys.platform == "win32" and any(Path(value).drive.casefold() == "c:" for value in paths):
        raise SystemExit("Development storage still points to C:. Select another HAIZFLOW_HOME/resource root first.")
    environment = dict(config._RUNTIME_ENVIRONMENT)
    site = expected / (
        "Lib/site-packages"
        if sys.platform == "win32"
        else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    )
    if not site.is_dir():
        raise SystemExit("Virtual-environment site-packages is missing.")
    module = site / "_haizflow_dev_storage.py"
    module.write_text(
        '"""Generated local development cache containment; not shipped."""\n'
        "import os\n"
        'if os.environ.get("HAIZFLOW_SMOKE_TEST") != "1":\n'
        '    os.environ.setdefault("HAIZFLOW_NATIVE_WINDOWS_USERPROFILE", os.environ.get("USERPROFILE", ""))\n'
        f"    os.environ.update({environment!r})\n",
        encoding="utf-8",
    )
    (site / "haizflow_dev_storage.pth").write_text("import _haizflow_dev_storage\n", encoding="utf-8")
    pip_config = expected / "pip.ini" if sys.platform == "win32" else expected / "pip.conf"
    parser = configparser.RawConfigParser()
    parser.read(pip_config, encoding="utf-8")
    if not parser.has_section("global"):
        parser.add_section("global")
    parser.set("global", "cache-dir", config.PIP_CACHE_DIR)
    with pip_config.open("w", encoding="utf-8") as stream:
        parser.write(stream)
    print(f"Local dev storage: {config.APP_DATA_DIR}")
    print(f"pip cache: {config.PIP_CACHE_DIR}")
    print(f"Temporary files: {config.TMP_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
