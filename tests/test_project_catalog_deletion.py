"""Removing a project keeps the other browser rows and editor owner intact."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QPersistentModelIndex, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem  # noqa: F401 - register Qt Quick before engines
from PySide6.QtTest import QAbstractItemModelTester, QSignalSpy, QTest

from haizflow.desktop.models import ProjectBrowserProxyModel, ProjectGridModel, ProjectListModel
from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
from haizflow.desktop.qml_controller import HaizFlowController  # noqa: F401 - register facade before engines

_APP = None


@pytest.fixture
def app():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    return _APP


def project(key, kind="manual"):
    return dict(key=key, project_name=key, project_type=kind, video_count=1,
                status="done", progress=100, thumbnail_source="", updated_at="2026-11-13")


@pytest.mark.parametrize("model_type", [ProjectListModel, ProjectGridModel])
@pytest.mark.parametrize("removed", [{"p0"}, {"p3"}, {"p9"}, {"p2", "p3", "p7"}, {f"p{i}" for i in range(10)}])
def test_deletion_uses_row_removal_and_keeps_persistent_indexes(app, model_type, removed):
    model = model_type()
    rows = [project(f"p{i}") for i in range(10)]
    model.set_projects(rows)
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Warning)
    reset = QSignalSpy(model.modelReset)
    removal = QSignalSpy(model.rowsRemoved)
    kept = {row["key"]: QPersistentModelIndex(model.index(i, 0)) for i, row in enumerate(rows)
            if row["key"] not in removed}
    result = [dict(row) for row in rows if row["key"] not in removed]
    model.set_projects(result)
    assert reset.count() == 0
    assert removal.count() >= 1
    assert model.rowCount() == len(result)
    for index, row in enumerate(result):
        assert kept[row["key"]].isValid()
        assert kept[row["key"]].row() == index
        assert model.project_at(index) == row
        assert model.update_project(dict(row, progress=91))
        assert model.data(model.index(index, 0), model.ProgressRole) == 91
    assert rows == [project(f"p{i}") for i in range(10)]  # Caller snapshot was not mutated.
    assert tester.model() == model


def test_sorted_filtered_browser_keeps_unaffected_rows_and_updates_roles(app):
    model = ProjectListModel()
    model.set_projects([project("Zulu"), project("Alpha"), project("Beta", "download")])
    browser = ProjectBrowserProxyModel(model)
    browser.typeFilter = "manual"
    browser.sortMode = "name"
    kept = QPersistentModelIndex(browser.index(0, 0))
    assert browser.project_at(0)["key"] == "Alpha"
    reset = QSignalSpy(browser.modelReset)
    model.set_projects([dict(project("Alpha"), status="processing", progress=35), project("Beta", "download")])
    assert reset.count() == 0
    assert kept.isValid() and kept.row() == 0
    assert browser.project_at(0)["status"] == "processing"
    assert browser.rowCount() == 1
    assert browser.typeFilter == "manual" and browser.sortMode == "name"


def test_grid_keeps_visible_delegates_and_scroll_position(app):
    model = ProjectListModel()
    model.set_projects([project(f"p{i:03}") for i in range(100)])
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("projects", model)
    component = QQmlComponent(engine)
    component.setData(b'''
        import QtQuick
        Window {
            width: 800; height: 500; visible: true
            property Item grid: projectGrid
            GridView {
                id: projectGrid
                anchors.fill: parent; cellWidth: 200; cellHeight: 100
                model: projects
                property int creations: 0
                delegate: Rectangle {
                    required property string projectKey
                    width: 200; height: 100
                    objectName: projectKey
                    Component.onCompleted: GridView.view.creations++
                }
            }
        }
    ''', QUrl("inmemory:ProjectDeletion.qml"))
    for _ in range(100):
        if not component.isLoading():
            break
        QTest.qWait(10)
    window = component.create()
    assert window is not None, component.errors()
    grid = window.property("grid")
    try:
        QTest.qWait(60)
        grid.setProperty("contentY", 500)
        QTest.qWait(60)
        # Remove an off-screen card: visible cards must not be reconstructed.
        previous_creations = grid.property("creations")
        assert previous_creations > 0
        previous_y = grid.property("contentY")
        model.set_projects([project(f"p{i:03}") for i in range(99)])
        QTest.qWait(60)
        assert grid.property("contentY") == previous_y
        assert grid.property("creations") == previous_creations
    finally:
        window.deleteLater()
        engine.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def catalog_host(selected):
    model = lambda: SimpleNamespace(set_projects=Mock(), set_videos=Mock())
    return SimpleNamespace(
        _selected_video_id=getattr(selected, "video_id", None), _selected_video_snapshot=selected,
        _catalog_videos={selected.video_id: selected} if selected else {},
        _video_project_key=lambda video: video.project_key,
        _ensure_video_dimensions=Mock(), _refresh_batch_model=Mock(), _project_catalog_state="ready",
        projects=model(), single_projects=model(), manual_projects=model(), batch_projects=model(),
        download_projects=model(), publish_projects=model(), videos=model(),
        _thumbnail_refresh_running=False, selectedVideoChanged=Mock())


@pytest.mark.parametrize("has_selection", [False, True])
def test_refresh_after_unrelated_deletion_does_not_reload_selected_editor(has_selection):
    video = SimpleNamespace(video_id="kept", project_key="kept", progress=10) if has_selection else None
    host = catalog_host(video)
    workspace = ProjectWorkspaceController(host)
    workspace._apply_catalog(1, [deepcopy(video)] if video else [], [project("kept")], [])
    host.selectedVideoChanged.emit.assert_not_called()
    if video:
        workspace._apply_catalog(2, [SimpleNamespace(video_id="kept", project_key="kept", progress=20)],
                                 [project("kept")], [])
        host.selectedVideoChanged.emit.assert_called_once()


def test_stale_inflight_catalog_is_not_published_after_deletion(monkeypatch):
    from haizflow.services import video_store

    host = catalog_host(None)
    workspace = ProjectWorkspaceController(host)
    monkeypatch.setattr(video_store, "metadata_revision", lambda: 11)
    workspace.refresh_videos = Mock()
    workspace._refresh_events.put(("catalog", (10, [], [project("deleted")], [])))
    workspace.drain_events()
    host.projects.set_projects.assert_not_called()
    workspace.refresh_videos.assert_called_once()
