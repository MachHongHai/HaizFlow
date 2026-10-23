"""Startup verification stays complete, deterministic, and resource bounded."""
import hashlib
import os
import subprocess
import threading
from unittest.mock import patch

import pytest

from haizflow.update.filesystem import UpdateError
from haizflow.update.manifest import Manifest, inventory


def test_parallel_inventory_matches_serial_and_ignores_only_reserved_metadata(tmp_path):
    for name, payload in (("z.dat", b"z"), ("dir/a.dll", b"a" * 100), ("empty", b"")):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    for name in ("core-complete.json", "core-manifest.json"):
        (tmp_path / name).write_text("{}")
    assert inventory(tmp_path, hash_workers=4) == inventory(tmp_path)
    assert [item["path"] for item in inventory(tmp_path, hash_workers=4)] == [
        "dir/a.dll", "empty", "z.dat",
    ]


def test_hash_reads_overlap_but_never_exceed_four_workers(tmp_path):
    for index in range(32):
        (tmp_path / f"{index:02}.dat").write_bytes(b"payload")
    gate = threading.Barrier(4, timeout=5)
    lock = threading.Lock()
    active = peak = 0

    def hash_file(_path):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            gate.wait()
            return hashlib.sha256(b"payload").hexdigest()
        finally:
            with lock:
                active -= 1

    with patch("haizflow.update.manifest.sha256", side_effect=hash_file) as hashed:
        result = inventory(tmp_path, hash_workers=100)
    assert len(result) == hashed.call_count == 32
    assert peak == 4


def test_parallel_hash_failure_is_not_swallowed(tmp_path):
    (tmp_path / "file.dll").write_bytes(b"payload")
    with patch("haizflow.update.manifest.sha256", side_effect=OSError("locked")):
        with pytest.raises(OSError, match="locked"):
            inventory(tmp_path, hash_workers=4)


@pytest.mark.parametrize("change", ["same_size", "missing", "extra"])
def test_parallel_verification_still_rejects_changed_file_sets(tmp_path, change):
    file = tmp_path / "HaizFlowCore.exe"
    file.write_bytes(b"original")
    manifest = Manifest({"target_files": inventory(tmp_path)})
    if change == "same_size":
        file.write_bytes(b"modified")
    elif change == "missing":
        file.unlink()
    else:
        (tmp_path / "injected.dll").write_bytes(b"extra")
    with pytest.raises(UpdateError):
        manifest.verify_tree(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction safety")
def test_parallel_inventory_refuses_nested_junction(tmp_path):
    core = tmp_path / "core"
    outside = tmp_path / "outside"
    core.mkdir()
    outside.mkdir()
    (outside / "secret.dll").write_bytes(b"must not read")
    link = core / "link"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True, check=False,
    )
    if result.returncode:
        pytest.skip("Junction creation unavailable")
    try:
        with pytest.raises(UpdateError, match="junction"):
            inventory(core, hash_workers=4)
    finally:
        # Unlink only the test junction; never recurse into its target.
        os.rmdir(link)
    assert (outside / "secret.dll").read_bytes() == b"must not read"
