"""Legacy launchers are upgraded without replacing their loaded runtime or user data."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from haizflow.update import bootstrap_refresh as refresh
from haizflow.update.filesystem import UpdateError, atomic_json, file_lock, sha256
from haizflow.update.packages import generate, reconstruct
from haizflow.update.state import Layout, provision

VERSION = "1.0.6"
COMMIT = "a" * 40


@pytest.fixture
def installation(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "HaizFlowCore.exe").write_bytes(b"NEW CORE")
    atomic_json(raw / "BUILD-INFO.json", {"application": "HaizFlow", "version": VERSION, "git_commit": COMMIT})
    for directory, executable, _ in refresh.ENTRIES:
        source = raw / "bootstrap-update" / directory
        (source / ("_bootstrap-" + VERSION)).mkdir(parents=True)
        (source / executable).write_bytes(("NEW " + executable).encode())
        (source / ("_bootstrap-" + VERSION) / "python313.dll").write_bytes(b"NEW RUNTIME")
        atomic_json(
            source / "BOOTSTRAP-INFO.json",
            dict(
                schema=1,
                application="HaizFlow",
                entrypoint=executable,
                version=VERSION,
                git_commit=COMMIT,
                git_dirty=False,
                engineering=False,
                contents_directory="_bootstrap-" + VERSION,
                packaging="PyInstaller onedir",
            ),
        )
        rows = sorted(path for path in source.rglob("*") if path.is_file())
        (source / "SHA256SUMS.txt").write_text(
            "".join(f"{sha256(path)} *{path.relative_to(source).as_posix()}\n" for path in rows)
        )
    root = tmp_path / "install"
    provision(root)
    layout = Layout(root)
    manifest = generate(None, raw, tmp_path / "packages", base_version=None, target_version=VERSION)
    reconstruct(tmp_path / "packages" / manifest.data["package_name"], manifest, layout.core(VERSION), None)
    layout.seed(VERSION)
    for _, executable, destination in refresh.ENTRIES:
        target = root / destination
        (target / "_internal").mkdir(parents=True, exist_ok=True)
        (target / "_internal" / "python313.dll").write_bytes(b"OLD LOADED RUNTIME")
        (target / executable).write_bytes(("OLD " + executable).encode())
    (layout.runtime / "data").mkdir(parents=True)
    (layout.runtime / "data" / "project.json").write_bytes(b"USER PROJECT DATA")
    return layout


def test_launcher_and_updater_receive_new_binary_but_old_runtime_and_data_stay(installation):
    layout = installation
    before_pointer = layout.active_path.read_bytes()
    before_core = {row["path"]: row["sha256"] for row in refresh.inventory(layout.core(VERSION))}
    assert refresh.install(layout, layout.core(VERSION))
    for _, executable, destination in refresh.ENTRIES:
        target = layout.root / destination
        assert (target / executable).read_bytes() == ("NEW " + executable).encode()
        assert (target / "_internal/python313.dll").read_bytes() == b"OLD LOADED RUNTIME"
        assert (target / ("_bootstrap-" + VERSION) / "python313.dll").read_bytes() == b"NEW RUNTIME"
    state = json.loads((layout.state / "bootstrap-version.json").read_text())
    assert (layout.state / "bootstrap-backups" / state["backup"] / "HaizFlow.exe").read_bytes() == b"OLD HaizFlow.exe"
    assert (layout.runtime / "data/project.json").read_bytes() == b"USER PROJECT DATA"
    assert layout.active_path.read_bytes() == before_pointer
    assert {row["path"]: row["sha256"] for row in refresh.inventory(layout.core(VERSION))} == before_core
    assert not refresh.install(layout, layout.core(VERSION))


def test_partial_replacement_failure_restores_both_original_executables(installation, monkeypatch):
    layout = installation
    replace = os.replace

    def fail_second(source, target):
        if Path(source).name == "HaizFlowUpdater.exe.new":
            raise PermissionError("Still locked")
        return replace(source, target)

    monkeypatch.setattr(refresh.os, "replace", fail_second)
    with pytest.raises(PermissionError, match="Still locked"):
        refresh.install(layout, layout.core(VERSION))
    for _, executable, destination in refresh.ENTRIES:
        assert (layout.root / destination / executable).read_bytes() == ("OLD " + executable).encode()
    assert not (layout.state / "bootstrap-version.json").exists()


def test_bad_payload_is_rejected_without_modifying_the_root(installation):
    layout = installation
    (layout.core(VERSION) / "bootstrap-update/HaizFlow/HaizFlow.exe").write_bytes(b"TAMPERED")
    with pytest.raises(UpdateError):
        refresh.install(layout, layout.core(VERSION))
    assert (layout.root / "HaizFlow.exe").read_bytes() == b"OLD HaizFlow.exe"


def test_versioned_runtime_collision_is_not_overwritten(installation):
    layout = installation
    conflict = layout.root / ("_bootstrap-" + VERSION)
    conflict.mkdir()
    (conflict / "foreign.txt").write_bytes(b"KEEP")
    with pytest.raises(UpdateError, match="không khớp"):
        refresh.install(layout, layout.core(VERSION))
    assert (conflict / "foreign.txt").read_bytes() == b"KEEP"
    assert (layout.root / "HaizFlow.exe").read_bytes() == b"OLD HaizFlow.exe"


def test_unconfirmed_or_superseded_core_cannot_change_the_launcher(installation):
    layout = installation
    pointer = layout.active()
    pointer["known_good"] = ["1.0.2"]
    atomic_json(layout.active_path, pointer)
    assert not refresh.install(layout, layout.core(VERSION))
    assert (layout.root / "HaizFlow.exe").read_bytes() == b"OLD HaizFlow.exe"


@pytest.mark.parametrize("lock", ["launcher.lock", "updater.lock", "update.lock"])
def test_live_launcher_or_updater_is_never_replaced(installation, lock):
    layout = installation
    with file_lock(layout.state / lock):
        with pytest.raises(UpdateError, match="chưa đóng"):
            refresh.run(layout.core(VERSION), timeout=0.12)
    assert (layout.root / "HaizFlow.exe").read_bytes() == b"OLD HaizFlow.exe"


def test_source_mode_does_not_schedule_or_touch_user_installations(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    launch = Mock()
    monkeypatch.setattr(refresh.subprocess, "Popen", launch)
    assert not refresh.schedule()
    launch.assert_not_called()


def test_running_only_after_desktop_shutdown_and_validated_entrypoint():
    root = Path(__file__).parents[1]
    main = (root / "src/haizflow/desktop/main.py").read_text("utf-8")
    assert main.index("controller.shutdown()") < main.index("schedule()")
    assert "if not smoke_test and exit_code == 0:" in main
    entry = (root / "haizflow_desktop.py").read_text("utf-8")
    assert 'if sys.argv[1:] == ["--refresh-bootstrap"]:' in entry
