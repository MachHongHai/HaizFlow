"""HaizFlow desktop application and local media-processing pipeline."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

try:
    __version__ = version("haizflow")
except PackageNotFoundError:
    # Source checkouts use the same canonical metadata as packaged builds.
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject.is_file():
        __version__ = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    else:
        __version__ = "0.0.0+local"
