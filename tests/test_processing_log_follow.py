"""Qt follows subprocess log lines before the model worker exits."""

import queue
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.desktop.activity_log import ActivityLogBuffer
from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController


@pytest.fixture
def log_session(tmp_path, monkeypatch):
    path = tmp_path / "logs.txt"
    path.write_text("APP: recognition started\n", encoding="utf-8")
    host = SimpleNamespace(
        _selected_video_id="a", _log_queue=queue.Queue(),
        _log_buffer=ActivityLogBuffer(), _logs="",
        activity_events=Mock(), logsChanged=Mock(),
    )
    monkeypatch.setattr(
        "haizflow.desktop.processing_lifecycle_controller.video_store.get_video_logs_path",
        lambda _video_id: str(path),
    )
    return host, ProcessingLifecycleController(host), path


def test_whisper_visible_while_subprocess_still_running(log_session):
    host, controller, path = log_session
    script = (
        "import sys\n"
        "with open(sys.argv[1], 'a', encoding='utf-8') as f:\n"
        "    f.write('WHISPER: loading model\\n'); f.flush()\n"
        "print('written', flush=True)\n"
        "sys.stdin.readline()\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-u", "-c", script, str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout.readline().strip() == "written"
        assert child.poll() is None
        controller.drain_log_queue()
        assert host._logs.splitlines() == ["APP: recognition started", "WHISPER: loading model"]
        with path.open("a", encoding="utf-8") as file:
            file.write("TRANSLATE: loading model\n")
        controller.drain_log_queue()
        assert host._logs.splitlines()[-2:] == ["WHISPER: loading model", "TRANSLATE: loading model"]
        assert child.poll() is None
    finally:
        child.communicate("finish\n", timeout=5)


def test_delayed_parent_callback_does_not_duplicate_disk_entry(log_session):
    host, controller, _ = log_session
    controller.drain_log_queue()
    host.logsChanged.reset_mock()
    host._log_queue.put(("video_log", "a", "APP: recognition started"))
    controller.drain_log_queue()
    assert host._logs == "APP: recognition started"
    host.logsChanged.emit.assert_not_called()


def test_unchanged_file_is_not_reread(log_session, monkeypatch):
    _, controller, _ = log_session
    reader = Mock(wraps=ActivityLogBuffer.read_tail)
    monkeypatch.setattr(ActivityLogBuffer, "read_tail", reader)
    controller.drain_log_queue()
    controller.drain_log_queue()
    controller.drain_log_queue()
    assert reader.call_count == 1


def test_delayed_other_project_event_is_ignored(log_session):
    host, controller, _ = log_session
    host._log_queue.put(("video_log", "b", "OTHER: private project"))
    controller.drain_log_queue()
    assert "OTHER" not in host._logs


def test_clear_forces_cache_revision_reload(log_session):
    host, controller, _ = log_session
    controller.drain_log_queue()
    controller.clear_logs()
    controller.drain_log_queue()
    assert host._logs == "APP: recognition started"


def test_missing_file_preserves_callback_fallback(log_session):
    host, controller, path = log_session
    path.unlink()
    host._log_queue.put(("video_log", "a", "APP: callback"))
    controller.drain_log_queue()
    assert host._logs == "APP: callback"
