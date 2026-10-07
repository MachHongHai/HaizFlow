import json
from unittest.mock import Mock

from haizflow.services import editor_view_state


def test_editor_navigation_is_per_video_and_survives_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(editor_view_state.video_store, "get_video", lambda name: name in {"a", "b"})
    monkeypatch.setattr(editor_view_state.video_store, "get_video_dir", lambda name: str(tmp_path / name))
    update = Mock()
    monkeypatch.setattr(editor_view_state.video_store, "update_video", update)
    assert editor_view_state.load("a") == {}
    assert editor_view_state.save("a", {"stage": 4, "monitor": "result", "rightActive": "tasks"})
    assert editor_view_state.save("b", {"stage": 3, "monitor": "source", "rightActive": "properties"})
    assert editor_view_state.load("a")["stage"] == 4
    assert editor_view_state.load("b") == {"stage": 3, "monitor": "source", "rightActive": "properties"}
    path = tmp_path / "a/editor/view.json"
    stamp = path.stat().st_mtime_ns
    assert editor_view_state.save("a", editor_view_state.load("a"))
    assert path.stat().st_mtime_ns == stamp
    update.assert_not_called()
    assert not editor_view_state.save("missing", {"stage": 1})
    path.write_text(json.dumps({"stage": 99, "monitor": "bad"}), encoding="utf-8")
    assert editor_view_state.load("a")["stage"] == 0
    path.write_text("{corrupt", encoding="utf-8")
    assert editor_view_state.load("a") == {}


def test_ocr_restore_updates_snapshot_before_notifying_ui(monkeypatch):
    from types import SimpleNamespace
    from haizflow.desktop.qml_controller import HaizFlowController

    old = SimpleNamespace(video_id="a", original_subtitle_region_override={"x_percent": 10})
    restored = SimpleNamespace(video_id="a", original_subtitle_region_override={})
    host = SimpleNamespace(_selected_video=lambda: old,
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        _selected_video_snapshot=old, selectedVideoChanged=SimpleNamespace(emit=Mock()))
    monkeypatch.setattr("haizflow.desktop.qml_controller.video_store.update_video", lambda *_a, **_kw: restored)
    def assert_updated():
        assert host._selected_video_snapshot.original_subtitle_region_override == {}

    host.selectedVideoChanged.emit.side_effect = assert_updated
    assert HaizFlowController.setOriginalSubtitleRegion(host, {})
    assert host._selected_video_snapshot is restored
    host.selectedVideoChanged.emit.assert_called_once()


def test_workspace_saves_old_identity_and_restores_stage_on_navigation():
    from pathlib import Path

    qml = (Path(__file__).parents[1] / "src/haizflow/desktop/qml/ManualWorkspace.qml").read_text(encoding="utf-8")
    assert "AppController.saveEditorViewState(previewVideoId" in qml
    assert "selectedStageIndex = Number(view.stage || 0)" in qml
    switch = qml.split("if (root.previewVideoId !== AppController.selectedVideoId) {", 1)[1]
    assert switch.index("root.saveEditorView()") < switch.index("root.previewVideoId =")
    assert switch.index("root.previewVideoId =") < switch.index("root.restoreEditorView()")
