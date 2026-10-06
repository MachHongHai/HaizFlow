import importlib.util
import json
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
SPEC = importlib.util.spec_from_file_location("finalize_bootstrap", ROOT / "scripts/finalize-bootstrap.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


@pytest.fixture
def payload(tmp_path):
    artifact = tmp_path / "launcher"
    (artifact / "_internal").mkdir(parents=True)
    (artifact / "HaizFlow.exe").write_bytes(b"launcher fixture")
    (artifact / "_internal/python313.dll").write_bytes(b"python fixture")
    with patch.object(bootstrap, "git", side_effect=lambda *args: "test-commit" if args == ("rev-parse", "HEAD") else ""):
        bootstrap.finalize(artifact, "HaizFlow.exe", source_commit="test-commit", engineering=False)
    return artifact


def verify(artifact, **changes):
    args = dict(source_commit="test-commit", version=CURRENT_VERSION, engineering=False)
    bootstrap.verify(artifact, "HaizFlow.exe", **dict(args, **changes))


def test_finalized_bootstrap_matches_core(payload):
    verify(payload)


@pytest.mark.parametrize("changes", [{"source_commit": "other"}, {"version": "99.0.0"}, {"engineering": True}])
def test_other_source_version_or_mode_rejected(payload, changes):
    with pytest.raises(ValueError, match="provenance"):
        verify(payload, **changes)


@pytest.mark.parametrize("directory", ["runtime", "update-state"])
def test_user_created_directory_rejected_even_empty(payload, directory):
    (payload / directory).mkdir()
    with pytest.raises(ValueError, match="user data"):
        verify(payload)


@pytest.mark.parametrize("mutation", ["modified", "added", "deleted"])
def test_checksum_and_exact_file_set_enforced(payload, mutation):
    if mutation == "modified":
        (payload / "HaizFlow.exe").write_bytes(b"tampered")
    elif mutation == "added":
        (payload / "extra.bin").write_bytes(b"unexpected")
    else:
        (payload / "_internal/python313.dll").unlink()
    with pytest.raises(ValueError, match="checksum"):
        verify(payload)


def test_dirty_public_provenance_rejected(payload):
    metadata = payload / "BOOTSTRAP-INFO.json"
    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["git_dirty"] = True
    metadata.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="dirty"):
        verify(payload)


def test_changed_commit_during_build_rejected(payload):
    with patch.object(bootstrap, "git", return_value="other-commit"), pytest.raises(ValueError, match="changed"):
        bootstrap.finalize(payload, "HaizFlow.exe", source_commit="test-commit", engineering=True)


def test_signed_bootstrap_also_requires_public_legal_gate():
    script = (ROOT / "scripts/build-bootstrap.ps1").read_text(encoding="utf-8")
    assert "if (!$AllowUnsigned) {" in script
    assert "--public-release" in script
    assert "finalize-bootstrap.py" in script
