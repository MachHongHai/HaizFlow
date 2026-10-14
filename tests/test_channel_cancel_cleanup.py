"""Each channel attempt owns its workspace, including failure/late callbacks."""

import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QGuiApplication

from hflow.desktop.channel_import import ChannelImportCoordinator
from hflow.schemas.channel_import import ChannelImportRequest, ChannelVideoCandidate
from hflow.services.channel_import import download_workspace, new_session


@pytest.mark.parametrize("outcome", ["cancelled", "failed", "import_failed", "late_cancel", "unknown_session"])
def test_channel_terminal_callback_removes_only_that_attempt(tmp_path, outcome):
    app = QGuiApplication.instance() or QGuiApplication([])
    coordinator = ChannelImportCoordinator()
    session = new_session("test-only", str(tmp_path), ChannelImportRequest(url="https://www.youtube.com/@test"))
    candidate = ChannelVideoCandidate(remote_video_id="v1", source_url="https://www.youtube.com/watch?v=v1",
                                      title="test", platform="YouTube")
    session.candidates = [candidate]
    coordinator._sessions[session.session_id] = session
    coordinator._rebuild_session_cache(session)
    coordinator._save_session = Mock()
    first = Path(download_workspace(str(tmp_path), session.session_id, "v1"))
    second = Path(download_workspace(str(tmp_path), session.session_id, "v1"))
    (first / "partial.mp4").write_bytes(b"partial")
    (second / "new-download.mp4").write_bytes(b"keep")
    assert first != second
    coordinator._workspaces[(session.session_id, "v1")] = str(first)
    received = []
    coordinator.videoReady.connect(lambda *_args: received.append(True))
    try:
        if outcome == "import_failed":
            coordinator.complete_video(session.session_id, "v1", False, "storage failure")
        elif outcome == "late_cancel":
            cancellation = threading.Event()
            cancellation.set()
            coordinator._cancel_events[session.session_id] = cancellation
            coordinator._handle_download_resolved(session.session_id, candidate.model_dump(), str(first / "partial.mp4"))
        else:
            if outcome == "unknown_session":
                coordinator._sessions.pop(session.session_id)
            coordinator._handle_download_rejected(session.session_id, "v1", "error", outcome == "cancelled")
        assert not first.exists()
        assert (second / "new-download.mp4").read_bytes() == b"keep"
        assert (session.session_id, "v1") not in coordinator._workspaces
        assert not received
    finally:
        coordinator.shutdown()
        app.processEvents()
