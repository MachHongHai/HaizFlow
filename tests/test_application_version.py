"""Application version must describe the running source/Core, not pip metadata."""
import json
import runpy
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src/haizflow/__init__.py"


def load_version(core, *, frozen=True):
    with (patch.object(sys, "frozen", frozen, create=True),
          patch.object(sys, "executable", str(core / "HaizFlowCore.exe")),
          patch("importlib.metadata.version", return_value="0.1.0")):
        return runpy.run_path(str(ENTRY))["__version__"]


def test_source_version_ignores_stale_editable_metadata(tmp_path):
    expected = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert load_version(tmp_path, frozen=False) == expected


def test_updated_core_uses_own_build_info_not_original_install(tmp_path):
    (tmp_path / "BUILD-INFO.json").write_text(json.dumps({"application": "HaizFlow", "version": "0.1.4"}))
    for value in ("0.1.4", "0.1.5"):
        core = tmp_path / "versions" / value
        core.mkdir(parents=True)
        (core / "BUILD-INFO.json").write_text(json.dumps({"application": "HaizFlow", "version": value}))
        assert load_version(core) == value


@pytest.mark.parametrize("data", [[], {"application": "Other", "version": "0.1.5"},
                                  {"application": "HaizFlow", "version": "0.1.4"},
                                  {"application": "HaizFlow", "version": "invalid"}])
def test_invalid_or_mismatched_running_core_metadata_is_rejected(tmp_path, data):
    core = tmp_path / "versions/0.1.5"
    core.mkdir(parents=True)
    (core / "BUILD-INFO.json").write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_version(core)


def test_flat_frozen_artifact_uses_build_info(tmp_path):
    (tmp_path / "BUILD-INFO.json").write_text(json.dumps({"application": "HaizFlow", "version": "0.1.5"}))
    assert load_version(tmp_path) == "0.1.5"
