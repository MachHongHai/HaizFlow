import threading
import time

from haizflow.services import editor_view_state


def test_navigation_writes_are_coalesced_and_video_owned(monkeypatch):
    calls = []
    monkeypatch.setattr(editor_view_state, "save", lambda video_id, state: calls.append((video_id, state)) or True)
    writer = editor_view_state.EditorViewStateWriter(delay=10)
    try:
        for stage in range(7):
            assert writer.schedule("a", {"stage": stage})
        assert writer.schedule("b", {"stage": 2, "monitor": "source"})
        assert writer.load("a")["stage"] == 6
        assert writer.load("b")["monitor"] == "source"
        assert calls == []
    finally:
        writer.close()
    assert [(key, value["stage"]) for key, value in calls] == [("a", 6), ("b", 2)]
    assert not writer.schedule("a", {"stage": 1})


def test_slow_disk_never_blocks_navigation(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def save(*_):
        entered.set()
        assert release.wait(3)
        return True

    monkeypatch.setattr(editor_view_state, "save", save)
    writer = editor_view_state.EditorViewStateWriter(delay=0)
    try:
        writer.schedule("a", {"stage": 1})
        assert entered.wait(2)
        start = time.monotonic()
        writer.schedule("a", {"stage": 2})
        assert writer.load("a")["stage"] == 2
        assert time.monotonic() - start < .1
    finally:
        release.set()
        writer.close()
