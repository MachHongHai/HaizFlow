"""Resource cleanup must never infer a deletion path from an empty pointer."""
import json
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest

from haizflow.services.resource_packs import ResourcePackManager, RESOURCE_STATE_VERSION


@pytest.mark.parametrize("previous", [None, "", "relative", "root", "cwd", "nested"])
def test_cleanup_rejects_missing_or_broad_targets(tmp_path, previous):
    source = tmp_path / "source"
    active = tmp_path / "active"
    source.mkdir()
    active.mkdir()
    values = {"root": source.anchor, "cwd": str(Path.cwd()), "nested": str(active / "nested")}
    pointer = tmp_path / "pointer.json"
    payload = dict(version=RESOURCE_STATE_VERSION, path=str(active))
    if previous is not None:
        payload["cleanup_previous"] = values.get(previous, previous)
    pointer.write_text(json.dumps(payload), encoding="utf-8")
    with (patch("haizflow.services.resource_packs.resource_storage_pointer_path", return_value=pointer),
          patch("haizflow.services.resource_packs.shutil.rmtree") as remove):
        ResourcePackManager.cleanup_previous_storage()
    remove.assert_not_called()


@pytest.mark.parametrize("target_matches", [True, False])
def test_cleanup_requires_a_verified_copy_and_keeps_projects(tmp_path, target_matches):
    source = tmp_path / "source"
    active = tmp_path / "active"
    for root in (source, active):
        (root / "models").mkdir(parents=True)
        (root / "models/model.bin").write_bytes(b"MODEL")
        (root / "projects").mkdir()
        (root / "projects/project.json").write_bytes(b"USER PROJECT")
    if not target_matches:
        (active / "models/model.bin").write_bytes(b"CORRUPTED")
    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps(dict(version=RESOURCE_STATE_VERSION, path=str(active), cleanup_previous=str(source))), encoding="utf-8")
    with patch("haizflow.services.resource_packs.resource_storage_pointer_path", return_value=pointer):
        ResourcePackManager.cleanup_previous_storage()
    assert (source / "projects/project.json").read_bytes() == b"USER PROJECT"
    assert (active / "models/model.bin").exists()
    assert (source / "models/model.bin").exists() is not target_matches
    assert ("cleanup_previous" in json.loads(pointer.read_text(encoding="utf-8"))) is not target_matches


def test_cleanup_rejects_reparse_payload(tmp_path):
    from haizflow.update.filesystem import UpdateError

    source = tmp_path / "source"
    active = tmp_path / "active"
    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps(dict(version=RESOURCE_STATE_VERSION, path=str(active), cleanup_previous=str(source))), encoding="utf-8")
    with (patch("haizflow.services.resource_packs.resource_storage_pointer_path", return_value=pointer),
          patch("haizflow.update.filesystem.no_links", side_effect=UpdateError("Synthetic reparse point")),
          patch("haizflow.services.resource_packs.shutil.rmtree") as remove):
        ResourcePackManager.cleanup_previous_storage()
    remove.assert_not_called()


@pytest.mark.parametrize("contents", ["{broken", "null", "[]", '{"version": 1, "path": null, "cleanup_previous": 42}'])
def test_cleanup_rejects_corrupt_pointer_without_deleting(tmp_path, contents):
    pointer = tmp_path / "pointer.json"
    pointer.write_text(contents, encoding="utf-8")
    with (patch("haizflow.services.resource_packs.resource_storage_pointer_path", return_value=pointer),
          patch("haizflow.services.resource_packs.shutil.rmtree") as remove):
        ResourcePackManager.cleanup_previous_storage()
    remove.assert_not_called()


def test_move_storage_restores_existing_destination_on_promotion_failure(tmp_path):
    import os

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    target = destination / "HaizFlowResources"
    for root, data in ((source, b"SOURCE"), (target, b"PREVIOUS DESTINATION")):
        (root / "models").mkdir(parents=True)
        (root / "models/model.bin").write_bytes(data)
    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps(dict(version=RESOURCE_STATE_VERSION, path=str(source))), encoding="utf-8")
    before = pointer.read_bytes()
    replace = os.replace

    def fail_promotion(origin, dest):
        if Path(origin).name.endswith(".partial") and Path(dest) == target:
            raise PermissionError("Synthetic promotion failure")
        return replace(origin, dest)

    manager = ResourcePackManager()
    with (patch.object(ResourcePackManager, "storage_root", new_callable=PropertyMock, return_value=source),
          patch("haizflow.services.resource_packs.resource_storage_pointer_path", return_value=pointer),
          patch("haizflow.services.resource_packs.os.replace", side_effect=fail_promotion)):
        with pytest.raises(PermissionError):
            manager.move_storage(destination)
    assert pointer.read_bytes() == before
    assert (source / "models/model.bin").read_bytes() == b"SOURCE"
    assert (target / "models/model.bin").read_bytes() == b"PREVIOUS DESTINATION"
