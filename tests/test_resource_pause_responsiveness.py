import hashlib
import io
import json
import subprocess
import threading
from unittest.mock import Mock, patch

import pytest

from haizflow.core.model_integrity import observe_verification
from haizflow.core.resource_archive import archive_matches
from haizflow.desktop.resource_progress import InstallProgress, progress_copy
from haizflow.services import model_bootstrap as bootstrap
from haizflow.services.resource_packs import ResourcePackDefinition, ResourcePackManager


def test_fresh_download_hashes_incoming_bytes_without_a_second_disk_read(tmp_path):
    payload = b"model" * 1000
    asset = bootstrap.ModelAsset("test", "Test", "https://huggingface.co/test/file", "file", len(payload),
                                 hashlib.sha256(payload).hexdigest())

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Length": str(len(payload))}

        def geturl(self):
            return asset.url

        def getcode(self):
            return self.status

        def read(self, *_args):
            raise AssertionError("A large blocking read was used instead of read1")

        def read1(self, size):
            assert size <= 256 * 1024
            return super().read(min(size, 1024))

    with patch.object(bootstrap, "_open_download", return_value=Response(payload)), \
            patch.object(bootstrap, "_sha256", side_effect=AssertionError("Fresh download reread from disk")):
        bootstrap.install_model_assets(tmp_path, [asset], progress=lambda _event: None)
    assert (tmp_path / "file").read_bytes() == payload


def test_hashing_and_complete_partial_promotion_can_be_paused(tmp_path):
    payload = b"x" * (8 * 1024 * 1024)
    path = tmp_path / "file.part"
    path.write_bytes(payload)
    cancelled = threading.Event()
    with pytest.raises(bootstrap.ModelBootstrapCancelled):
        bootstrap._sha256(path, cancel_event=cancelled, progress=lambda *_args: cancelled.set())
    assert path.exists()
    asset = bootstrap.ModelAsset("test", "Test", "https://huggingface.co/test/file", "file", len(payload),
                                 hashlib.sha256(payload).hexdigest())
    with pytest.raises(bootstrap.ModelBootstrapCancelled):
        bootstrap._prepare_partial(tmp_path / "file", asset, cancel_event=cancelled)
    assert not (tmp_path / "file").exists()
    cancelled.clear()
    assert bootstrap._prepare_partial(tmp_path / "file", asset, cancel_event=cancelled) == len(payload)
    assert (tmp_path / "file").read_bytes() == payload


def test_inventory_integrity_hashes_are_scoped_and_cancellable(tmp_path):
    from haizflow.core.model_integrity import _sha256

    path = tmp_path / "model"
    path.write_bytes(b"data")
    with observe_verification(lambda *_args: (_ for _ in ()).throw(bootstrap.ModelBootstrapCancelled("Paused"))):
        with pytest.raises(bootstrap.ModelBootstrapCancelled):
            _sha256(path)
    assert _sha256(path) == hashlib.sha256(b"data").hexdigest()


def test_cached_archive_verification_can_be_paused(tmp_path):
    path = tmp_path / "engine.zip"
    path.write_bytes(b"data")
    with pytest.raises(InterruptedError):
        archive_matches(path, size=4, sha256=hashlib.sha256(b"data").hexdigest(), cancelled=lambda: True)


def test_assembly_advances_and_unknown_finalization_is_animated():
    tracker = InstallProgress((("engine-test", 100),))
    before = tracker.update("engine-test", bootstrap.ModelProgress("downloading", "", "", 100, 100, "transfer"))
    after = tracker.update("engine-test", bootstrap.ModelProgress("verifying", "", "", 50, 100, "assembly"))
    assert before < after
    copy = progress_copy("engine-test", bootstrap.ModelProgress("verifying", "", "", 0, 0, "finalizing"))
    assert copy["indeterminate"]


def test_engine_probe_is_stopped_when_pause_is_requested(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "engine.exe").write_bytes(b"fixture")
    (staging / "engine.json").write_text(json.dumps(dict(
        pack_id="engine-vision-onnx", profile="vision", version="1", protocol_version=1,
        smoke_command=["engine.exe", "--smoke"], rpc_command=["engine.exe", "--rpc"],
        subtitle_ocr=["engine.exe", "--subtitle-ocr"],
    )), encoding="utf-8")
    definition = ResourcePackDefinition("engine-vision-onnx", "Vision", "processor", "1", "engine")
    manager = ResourcePackManager([definition])
    cancelled = threading.Event()
    process = Mock(returncode=None)
    process.poll.side_effect = lambda: process.returncode

    def communicate(**_kwargs):
        if process.returncode is None:
            cancelled.set()
            raise subprocess.TimeoutExpired("fixture", .1)
        return "", ""

    process.communicate.side_effect = communicate
    with patch("haizflow.services.resource_packs.subprocess.Popen", return_value=process), \
            patch("haizflow.pipeline.process_registry._kill_process_tree",
                  side_effect=lambda _process: setattr(process, "returncode", -1)) as kill:
        with pytest.raises(bootstrap.ModelBootstrapCancelled):
            manager._verify_engine_staging(definition, staging, cancel_event=cancelled)
    kill.assert_called_once_with(process)
    assert not list(tmp_path.glob(".engine-smoke-*"))
