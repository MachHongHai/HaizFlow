"""Storage relocation progress, pointer switching and worker handoff."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock

from haizflow.desktop.resource_pack_controller import ResourcePackController
from haizflow.services.resource_packs import ResourcePackManager, ResourcePackError
import pytest
from PySide6.QtCore import QObject, Signal


class Host(QObject):
    appAlertRequested = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self._settings_language = "vi"
        self._processing_queue = SimpleNamespace(has_work=False)
        self._smart_warmup = None


def test_manual_and_auto_reject_processing_before_preflight_during_storage_move():
    from haizflow.desktop.project_commands_controller import ProjectCommandsController
    from haizflow.desktop.qml_controller import HaizFlowController

    host = SimpleNamespace(_resource_packs=SimpleNamespace(storageMoving=True),
                           appAlertRequested=Mock())
    assert not ProjectCommandsController._resources_ready_for_videos(host, [])
    assert not HaizFlowController.runManualTool(host, "voice")
    assert host.appAlertRequested.emit.call_count == 2


def test_storage_move_finishes_cleanup_before_resuming_workers(tmp_path, monkeypatch):
    from haizflow import config

    monkeypatch.setattr(config, "refresh_resource_paths", Mock())
    root = tmp_path / "app"
    monkeypatch.setenv("HAIZFLOW_HOME", str(root))
    monkeypatch.setenv("RUNTIME_DATA_DIR", str(root / "data"))
    monkeypatch.delenv("HAIZFLOW_RESOURCE_ROOT", raising=False)
    monkeypatch.delenv("MODELS_DIR", raising=False)
    (root / "models").mkdir(parents=True)
    (root / "models/model.bin").write_bytes(b"model" * 1000000)
    (root / "projects").mkdir()
    (root / "projects/project.json").write_bytes(b"USER DATA")
    host = Host()
    controller = ResourcePackController(host, ResourcePackManager())
    controller._inventory_thread.join(5)
    controller._maintenance_thread.join(5)
    controller.drain_events()
    suspended, proceed = threading.Event(), threading.Event()

    def suspend():
        suspended.set()
        assert proceed.wait(5)

    def resume():
        assert not (root / "models").exists()
        assert (tmp_path / "destination/HaizFlowResources/models/model.bin").is_file()

    host._smart_warmup = SimpleNamespace(suspend_for_storage_move=suspend,
                                        resume_after_storage_move=Mock(side_effect=resume))
    try:
        assert controller.moveResourceStorage(str(tmp_path / "destination"))
        assert suspended.wait(2)
        assert controller.storageMoving and controller.busy
        assert controller.activityProgress == -1
        assert not controller.moveResourceStorage(str(tmp_path / "second"))
        proceed.set()
        controller._move_thread.join(10)
        assert not controller._move_thread.is_alive()
        events = list(controller._events.queue)
        assert {event.get("phase") for event in events if event["kind"] == "move_progress"} == {"copy", "verify", "switch", "cleanup"}
        controller.drain_events()
        assert not controller.storageMoving
        assert controller.storageLocation == str(tmp_path / "destination/HaizFlowResources")
        assert (root / "projects/project.json").read_bytes() == b"USER DATA"
        host._smart_warmup.resume_after_storage_move.assert_called_once()
    finally:
        proceed.set()
        controller.shutdown()


def test_pinned_environment_is_rejected_before_creating_destination(tmp_path, monkeypatch):
    monkeypatch.setenv("HAIZFLOW_RESOURCE_ROOT", str(tmp_path / "pinned"))
    destination = tmp_path / "destination"
    with pytest.raises(ResourcePackError, match="cố định"):
        ResourcePackManager().move_storage(destination)
    assert not destination.exists()


def test_cached_model_aliases_follow_new_storage_without_importing_runtimes(tmp_path, monkeypatch):
    import sys
    from haizflow import config

    old, new = "old-models", str(tmp_path / "models")
    loaded = SimpleNamespace(MODELS_DIR=old)
    monkeypatch.setattr(config, "MODELS_DIR", old)
    monkeypatch.setattr(config, "WHISPER_MODELS_DIR", "old-whisper")
    monkeypatch.setattr(config, "models_dir", lambda: tmp_path / "models")
    monkeypatch.setitem(sys.modules, "haizflow.pipeline.transcribe", loaded)
    config.refresh_resource_paths()
    assert config.MODELS_DIR == loaded.MODELS_DIR == new
    assert config.WHISPER_MODELS_DIR == str(tmp_path / "models/whisper")
