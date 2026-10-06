"""Multipart engine integrity, cancellation and disk-estimate regressions."""

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from haizflow.core.resource_archive import ArchivePart, archive_matches, join_archive_parts, parse_archive_parts
from haizflow.services.resource_packs import ResourcePackDefinition, ResourcePackManager

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def split_fixture(tmp_path):
    archive = tmp_path / "engine.zip"
    archive.write_bytes(b"12345678abcdefghABCDEFGH")
    index = load_script("split-resource-archive.py").split_archive(archive, tmp_path / "parts", part_bytes=8)
    record = dict(url="", sha256=index["sha256"], download_size=index["download_size"], parts=[
        dict(url="https://example.test/" + row["file"], size=row["size"], sha256=row["sha256"])
        for row in index["parts"]
    ])
    sources = tuple((tmp_path / "parts" / row["file"], part)
                    for row, part in zip(index["parts"], parse_archive_parts(record)))
    return archive, record, sources


def test_split_join_preserves_exact_archive_bytes(tmp_path):
    archive, record, sources = split_fixture(tmp_path)
    destination = tmp_path / "joined.zip"
    join_archive_parts(sources, destination, size=record["download_size"], sha256=record["sha256"])
    assert destination.read_bytes() == archive.read_bytes()
    assert archive_matches(destination, size=record["download_size"], sha256=record["sha256"])
    assert not list(tmp_path.glob(".engine-join-*"))


def test_corrupt_part_cannot_replace_previous_archive(tmp_path):
    _, record, sources = split_fixture(tmp_path)
    destination = tmp_path / "joined.zip"
    destination.write_bytes(b"PREVIOUS VERIFIED ARCHIVE")
    sources[1][0].write_bytes(b"XXXXXXXX")
    with pytest.raises(ValueError, match="pinned size/SHA-256"):
        join_archive_parts(sources, destination, size=record["download_size"], sha256=record["sha256"])
    assert destination.read_bytes() == b"PREVIOUS VERIFIED ARCHIVE"
    assert all(path.exists() for path, _part in sources)
    assert not list(tmp_path.glob(".engine-join-*"))


def test_cancelled_join_preserves_resumable_parts(tmp_path):
    _, record, sources = split_fixture(tmp_path)
    destination = tmp_path / "joined.zip"
    with pytest.raises(InterruptedError):
        join_archive_parts(sources, destination, size=record["download_size"], sha256=record["sha256"],
                           cancelled=lambda: True)
    assert not destination.exists()
    assert all(path.exists() for path, _part in sources)
    assert not list(tmp_path.glob(".engine-join-*"))


def test_overall_hash_is_required_even_when_parts_match(tmp_path):
    _, record, sources = split_fixture(tmp_path)
    with pytest.raises(ValueError, match="Complete archive"):
        join_archive_parts(sources, tmp_path / "joined.zip", size=record["download_size"], sha256="0" * 64)
    assert not (tmp_path / "joined.zip").exists()


@pytest.mark.parametrize("change", [
    lambda r: r.update(url="https://example.test/whole.zip"),
    lambda r: r.update(download_size=999),
    lambda r: r["parts"][0].update(url="http://example.test/a"),
    lambda r: r["parts"][0].update(url="https://user:secret@example.test/a"),
    lambda r: r["parts"][0].update(size=True),
    lambda r: r["parts"][0].update(size=2 * 1024**3),
    lambda r: r["parts"][0].update(sha256="invalid"),
    lambda r: r["parts"][1].update(url=r["parts"][0]["url"]),
])
def test_malformed_catalog_parts_fail_closed(tmp_path, change):
    _, record, _sources = split_fixture(tmp_path)
    change(record)
    with pytest.raises(ValueError):
        parse_archive_parts(record)


def test_manifest_verifier_accepts_pinned_multipart_and_rejects_wrong_size(tmp_path):
    _, record, _sources = split_fixture(tmp_path)
    verifier = load_script("verify-resource-pack-manifest.py")
    record.update(version="1", installed_size=100)
    payload = dict(schema=1, protocol_version=1, packs={key: record for key in verifier.ENGINE_PACKS})
    path = tmp_path / "packs.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert verifier.validate_manifest(path, strict=True)["release_ready"] == 3
    record["download_size"] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Part sizes"):
        verifier.validate_manifest(path, strict=True)


def test_multipart_disk_reserve_and_resumed_download_are_counted(tmp_path):
    parts = (ArchivePart("https://example.test/a", 8, "0" * 64), ArchivePart("https://example.test/b", 8, "1" * 64))
    definition = ResourcePackDefinition("engine-test", "Test", "processor", "1", "engine",
        engine_modules=("fake",), download_size=16, installed_size=100, archive_parts=parts, archive_sha256="2" * 64)
    manager = ResourcePackManager((definition,))
    (tmp_path / "engine-test-1.zip.001").write_bytes(b"12345678")
    (tmp_path / "engine-test-1.zip.002.part").write_bytes(b"abc")
    with (patch("haizflow.services.resource_packs.resource_packages_dir", return_value=tmp_path),
          patch.object(manager, "status", return_value="missing"),
          patch.object(manager, "installed_bytes", return_value=0),
          patch("haizflow.services.resource_packs.shutil.disk_usage", return_value=SimpleNamespace(free=10**12))):
        assert manager.download_bytes("engine-test") == 5
        summary = manager.requirement_summary(("engine-test",))
    assert summary["downloadBytes"] == 5
    assert summary["assemblyBytes"] == 16
    assert summary["installedBytes"] == 100


def test_splitter_never_overwrites_finalized_parts(tmp_path):
    archive, _record, _sources = split_fixture(tmp_path)
    with pytest.raises(ValueError, match="never overwrite"):
        load_script("split-resource-archive.py").split_archive(archive, tmp_path / "parts", part_bytes=8)


def test_file_hash_check_rejects_same_size_corruption(tmp_path):
    path = tmp_path / "archive"
    path.write_bytes(b"bad")
    assert not archive_matches(path, size=3, sha256=hashlib.sha256(b"yes").hexdigest())


def test_multipart_install_extracts_only_after_verification_and_reuses_zip(tmp_path):
    archive = tmp_path / "engine.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("engine.json", "{}")
        bundle.writestr("engine.exe", b"TEST EXECUTABLE FIXTURE")
    part_index = load_script("split-resource-archive.py").split_archive(
        archive, tmp_path / "parts", part_bytes=archive.stat().st_size // 2)
    parts = tuple(ArchivePart("https://example.test/" + row["file"], row["size"], row["sha256"])
                  for row in part_index["parts"])
    packages = tmp_path / "packages"
    packages.mkdir()
    definition = ResourcePackDefinition("engine-test", "Test", "processor", "1", "engine",
        engine_modules=("fake",), download_size=archive.stat().st_size, installed_size=100,
        archive_parts=parts, archive_sha256=part_index["sha256"])
    manager = ResourcePackManager((definition,))

    def fake_download(root, assets, **_kwargs):
        for asset, row in zip(assets, part_index["parts"]):
            (root / asset.relative_path).write_bytes((tmp_path / "parts" / row["file"]).read_bytes())

    with (patch("haizflow.services.resource_packs.resource_packages_dir", return_value=packages),
          patch("haizflow.services.resource_packs.engines_dir", return_value=tmp_path / "engines"),
          patch.object(manager, "requirement_summary", return_value=dict(freeBytes=10**12, requiredBytes=1)),
          patch.object(manager, "_verify_engine_staging") as verify,
          patch("haizflow.services.resource_packs.install_model_assets", side_effect=fake_download) as download):
        manager.install("engine-test", lambda *_args: None)
        assert download.call_count == 1
        assert verify.call_count == 1
        assert (packages / "engine-test-1.zip").read_bytes() == archive.read_bytes()
        assert not list(packages.glob("*.00*"))
        target = tmp_path / "engines" / "engine-test" / "1"
        assert (target / "engine.exe").read_bytes() == b"TEST EXECUTABLE FIXTURE"
        assert (target / "complete.json").exists()
        manager.install("engine-test", lambda *_args: None)
        assert download.call_count == 1, "A valid assembled ZIP must avoid redownloading removed parts"


def test_engine_install_smoke_uses_isolated_writable_paths(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "engine.exe").write_bytes(b"MOCK EXECUTABLE")
    (staging / "engine.json").write_text(json.dumps(dict(
        pack_id="engine-vision-onnx", profile="vision", version="1", protocol_version=1,
        smoke_command=["engine.exe", "--smoke"], rpc_command=["engine.exe", "--rpc"],
        subtitle_ocr=["engine.exe", "--subtitle-ocr"],
    )), encoding="utf-8")
    definition = ResourcePackDefinition("engine-vision-onnx", "Vision", "processor", "1", "engine")
    manager = ResourcePackManager((definition,))
    smoke_paths = []

    def fake_run(*_args, **kwargs):
        environment = kwargs["env"]
        path = Path(environment["HAIZFLOW_HOME"])
        assert path.parent == staging.parent and path != staging
        assert environment["HAIZFLOW_SMOKE_TEST"] == "1"
        (path / "temporary-cache").write_bytes(b"isolated")
        smoke_paths.append(path)
        return SimpleNamespace(returncode=0, communicate=lambda **_kwargs: ("", ""), poll=lambda: 0)

    with patch("haizflow.services.resource_packs.subprocess.Popen", side_effect=fake_run):
        manager._verify_engine_staging(definition, staging)
    assert not (staging / "runtime").exists()
    assert all(not path.exists() for path in smoke_paths)


@pytest.mark.parametrize("failure", ["promotion", "cancel", "smoke"])
def test_engine_install_failure_preserves_previous_engine(tmp_path, failure):
    import os
    import zipfile

    from haizflow.services.model_bootstrap import ModelBootstrapCancelled
    from haizflow.services.resource_packs import ResourcePackError

    packages = tmp_path / "packages"
    packages.mkdir()
    archive = packages / "engine-test-1.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("engine.exe", b"NEW ENGINE")
    definition = ResourcePackDefinition("engine-test", "Test", "processor", "1", "engine",
        engine_modules=("fake",), download_size=archive.stat().st_size, installed_size=100,
        archive_url="https://example.invalid/engine.zip", archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    manager = ResourcePackManager((definition,))
    target = tmp_path / "engines" / "engine-test" / "1"
    target.mkdir(parents=True)
    (target / "engine.exe").write_bytes(b"PREVIOUS ENGINE")
    replace = os.replace

    def verify(*_args, **_kwargs):
        if failure == "cancel":
            manager.cancel("engine-test")
        elif failure == "smoke":
            raise ResourcePackError("Synthetic smoke failure")

    def promotion(source, destination):
        if failure == "promotion" and Path(source).name.endswith(".partial") and Path(destination) == target:
            raise PermissionError("Synthetic promotion failure")
        return replace(source, destination)

    expected = {"promotion": PermissionError, "cancel": ModelBootstrapCancelled, "smoke": ResourcePackError}[failure]
    with (patch("haizflow.services.resource_packs.resource_packages_dir", return_value=packages),
          patch("haizflow.services.resource_packs.engines_dir", return_value=tmp_path / "engines"),
          patch.object(manager, "requirement_summary", return_value=dict(freeBytes=10**12, requiredBytes=1)),
          patch.object(manager, "_verify_engine_staging", side_effect=verify),
          patch("haizflow.services.resource_packs.install_model_assets"),
          patch("haizflow.services.resource_packs.os.replace", side_effect=promotion)):
        with pytest.raises(expected):
            manager.install("engine-test", lambda *_args: None)
        assert (target / "engine.exe").read_bytes() == b"PREVIOUS ENGINE"
        assert "engine-test" not in manager._active
        assert "engine-test" not in manager._cancel_events
        assert not list(target.parent.glob("*.partial"))
        assert not list(target.parent.glob("*.rollback"))
