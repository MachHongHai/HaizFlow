from __future__ import annotations

import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_qt_collection_verifies_published_hash_and_keeps_license_text(tmp_path):
    collector = script("collect-qt-sources")
    source = tmp_path / "input.tar.xz"
    with tarfile.open(source, "w:xz") as archive:
        data = b"Independent LGPL rights"
        member = tarfile.TarInfo("pyside-setup/LICENSES/LGPL-3.0-only.txt")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    content = source.read_bytes()
    metadata = ("<span>SHA-256\nHash</span>: <tt>" + hashlib.sha256(content).hexdigest() + "</tt>").encode()
    with patch.object(collector, "ROOT", tmp_path), patch.object(collector, "MODULES", ()), \
            patch.object(collector.urllib.request, "urlopen", side_effect=lambda url, **_: io.BytesIO(metadata if url.endswith(".mirrorlist") else content)):
        result = collector.collect(tmp_path / "build/qt-sources")
    assert len(result["sources"]) == 1
    assert (tmp_path / "build/qt-sources/licenses/pyside-setup/LICENSES/LGPL-3.0-only.txt").read_bytes() == data


def test_qt_collection_does_not_accept_missing_hash(tmp_path):
    collector = script("collect-qt-sources")
    with patch.object(collector, "ROOT", tmp_path), patch.object(collector, "MODULES", ()), \
            patch.object(collector.urllib.request, "urlopen", return_value=io.BytesIO(b"No hash")), \
            pytest.raises(ValueError, match="published source hash"):
        collector.collect(tmp_path / "build/qt-sources")


def test_qt_collection_cannot_write_into_application_or_user_directory(tmp_path):
    collector = script("collect-qt-sources")
    with patch.object(collector, "ROOT", tmp_path), pytest.raises(ValueError, match="below build"):
        collector.collect(tmp_path / "data")


def test_msys_package_metadata_sections_keep_exact_identity(tmp_path):
    collector = script("collect-built-ffmpeg")
    desc = tmp_path / "desc"
    desc.write_text("%NAME%\nmingw-w64-x86_64-libass\n\n%VERSION%\n0.17.5-1\n\n%BASE%\nmingw-w64-libass\n", encoding="utf-8")
    assert collector.sections(desc) == {"NAME": ["mingw-w64-x86_64-libass"], "VERSION": ["0.17.5-1"], "BASE": ["mingw-w64-libass"]}


def test_internal_and_public_installer_names_are_distinct():
    text = (ROOT / "scripts/build-installer.ps1").read_text(encoding="utf-8")
    assert 'if ($EngineeringBuild) { "HaizFlow-$Version-DEVELOPMENT-Setup" } else { "HaizFlow-$Version-Setup" }' in text
    assert "-UNSIGNED-Setup" not in text
    assert "Public unsigned installer" in text
