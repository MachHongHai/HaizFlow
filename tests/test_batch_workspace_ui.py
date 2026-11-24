"""Render and exercise the batch workspace without touching user projects."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "width,height,state",
    [
        (1440, 900, "ready"),
        (960, 700, "running"),
        (620, 700, "paused"),
        (960, 700, "empty"),
        (960, 700, "large"),
        (960, 700, "pausing"),
        (1280, 720, "done"),
        (960, 700, "english"),
        (960, 700, "importing"),
    ],
)
def test_batch_workspace_layout_and_actions(width, height, state):
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), str(width), str(height), state],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def exercise(width, height, state):
    from PySide6.QtCore import (
        Property,
        QAbstractListModel,
        QByteArray,
        QModelIndex,
        QObject,
        QPoint,
        QPointF,
        Qt,
        QTranslator,
        QUrl,
        Signal,
        Slot,
    )
    from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    from PySide6.QtTest import QSignalSpy, QTest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])
    for name in ("SegUIVar.ttf", "SegoeIcons.ttf", "malgun.ttf"):
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Segoe UI Variable"))
    if state == "english":
        translator = QTranslator(app)
        assert translator.load(str(Path(__file__).parents[1] / "src/haizflow/desktop/translations/haizflow_en.qm"))
        app.installTranslator(translator)

    class VideoModel(QAbstractListModel):
        names = ["videoId", "fileName", "status", "progress", "thumbnailSource", "videoSize"]

        def __init__(self):
            super().__init__()
            count = 0 if state == "empty" else 1000 if state == "large" else 8
            statuses = ["done", "processing", "pending", "failed", "paused", "awaiting_review", "cancelled", "pending"]
            self.rows = [
                dict(
                    videoId=f"video-{index}",
                    fileName=[
                        "Phần 1 · Một cuộc gặp bất ngờ.mp4",
                        "Phần 2 · Câu chuyện vẫn còn tiếp diễn với tên video rất dài.mp4",
                        "Video_03.mp4",
                        "Tiếng Hàn · 한국어 자막 영상.mp4",
                    ][index % 4],
                    status="done" if state == "done" else statuses[index % 8],
                    progress=100 if state == "done" or index % 8 == 0 else 42 if index % 8 == 1 else 0,
                    thumbnailSource="",
                    videoSize="1080 × 1920" if index % 2 else "1920 × 1080",
                )
                for index in range(count)
            ]

        def rowCount(self, parent=QModelIndex()):
            return 0 if parent.isValid() else len(self.rows)

        def roleNames(self):
            return {Qt.UserRole + index + 1: QByteArray(name.encode()) for index, name in enumerate(self.names)}

        def data(self, index, role):
            offset = role - Qt.UserRole - 1
            if index.isValid() and 0 <= offset < len(self.names):
                return self.rows[index.row()][self.names[offset]]
            return None

    model = VideoModel()

    def field(name, kind):
        return Property(kind, lambda self: self.values[name], constant=True)

    class Backend(QObject):
        changed = Signal()
        batchChanged = Signal()
        batchResultsChanged = Signal()
        removalBlocksChanged = Signal()
        projectName = field("projectName", str)
        projectKey = Property(str, lambda self: self.values["projectKey"], notify=changed)
        hasOpenProject = field("hasOpenProject", bool)
        batchTargetLanguageLabel = field("batchTargetLanguageLabel", str)
        batchCount = field("batchCount", int)
        batchPausedCount = field("batchPausedCount", int)
        batchProgress = field("batchProgress", int)
        isBatchRunning = field("isBatchRunning", bool)
        isBatchPausing = field("isBatchPausing", bool)
        mediaImportBusy = field("mediaImportBusy", bool)
        mediaImportCompleted = field("mediaImportCompleted", int)
        mediaImportTotal = field("mediaImportTotal", int)
        videoExportBusy = field("videoExportBusy", bool)
        videoExportJobs = field("videoExportJobs", "QVariantList")
        videoExportScope = field("videoExportScope", "QVariantList")
        batchVideoRemovalBlockedIds = Property("QVariantList", lambda self: self.removal_blocks,
                                              notify=removalBlocksChanged)
        batchVideoModel = field("batchVideoModel", QObject)

        def __init__(self):
            super().__init__()
            self.calls = []
            self.removal_blocks = ["video-1", "video-2"] if state in ("running", "pausing") else []
            self.values = dict(
                projectName="work · Bộ video mới",
                projectKey="batch-test",
                hasOpenProject=True,
                batchTargetLanguageLabel="Tiếng Việt",
                batchCount=len(model.rows),
                batchPausedCount=2 if state == "paused" else 0,
                batchProgress=100 if state == "done" else 36,
                isBatchRunning=state in ("running", "pausing"),
                isBatchPausing=state == "pausing",
                mediaImportBusy=state == "importing",
                mediaImportCompleted=2,
                mediaImportTotal=12,
                videoExportBusy=state in ("running", "pausing"),
                videoExportJobs=[],
                videoExportScope=[],
                batchVideoModel=model,
            )

        @Slot(result="QVariantList")
        def batchSettingOverrides(self):
            return [] if state in ("empty", "done") else [{"videoId": "video-1", "fileName": model.rows[1]["fileName"]}]

        @Slot(result="QVariantMap")
        def batchResults(self):
            return dict(
                succeeded=len(model.rows) if state == "done" else 1,
                failed=0 if state == "done" else 1,
                rows=[dict(fileName="Example.mp4", status="failed", error="Example test error")],
            )

        @Slot(str, result=bool)
        def batchVideoRemovalPending(self, video_id):
            return False

        @Slot(str, str, result=bool)
        def removeBatchVideo(self, project_key, video_id):
            self.calls.append(("remove", project_key, video_id))
            return True

        @Slot(int)
        def selectBatchVideo(self, index):
            self.calls.append(("select", index))

        @Slot()
        def requestBatchProcessing(self):
            self.calls.append("process")

        @Slot()
        def resumeBatch(self):
            self.calls.append("resume")

        @Slot()
        def stopBatch(self):
            self.calls.append("pause")

        @Slot()
        def browseBatchVideos(self):
            self.calls.append("browse")

        @Slot(str, str, str)
        def presentUserError(self, title, detail, log):
            self.calls.append(("error", title))

    backend = Backend()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("AppController", backend)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
    directory = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
    component = QQmlComponent(engine)
    component.setData(
        QByteArray(b"""
        import QtQuick
        import QtQuick.Controls.Basic
        import "."
        ApplicationWindow {
            visible: true
            width: 1440; height: 900
            color: Theme.window
            Component.onCompleted: { Theme.motionEnabled = false; I18n.language = "vi"; }
            BatchPage { objectName: "workspace"; anchors.fill: parent }
        }
    """),
        QUrl.fromLocalFile(str(directory / "BatchWorkspaceTestWindow.qml")),
    )
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    window.resize(width, height)
    QTest.qWait(250)
    page = window.findChild(QQuickItem, "workspace")

    def item(name):
        result = window.findChild(QQuickItem, name)
        if result is None:
            result = next((child for child in visual_items(window.contentItem()) if child.objectName() == name), None)
        assert result is not None, name
        return result

    def visual_items(parent):
        for child in parent.childItems():
            yield child
            yield from visual_items(child)

    def click(target):
        position = target.mapToScene(QPointF(target.width() / 2, target.height() / 2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(position.x()), round(position.y())))
        QTest.qWait(80)

    def bounds(target):
        top = target.mapToScene(QPointF(0, 0))
        return top.x(), top.y(), top.x() + target.width(), top.y() + target.height()

    for name in (
        "pageHeader",
        "batchQueueToolbar",
        "batchQueuePanel",
        "batchImportButton",
        "batchSettingsButton",
        "batchCommandBar",
    ):
        target = item(name)
        if target.isVisible():
            x1, y1, x2, y2 = bounds(target)
            assert 0 <= x1 < x2 <= width, (name, x1, x2, width)
            assert 0 <= y1 < y2 <= height, (name, y1, y2, height)
    assert item("batchQueuePanel").height() >= 160
    if state != "empty":
        assert item("batchCommandBar").height() == 44
        assert bounds(item("batchQueuePanel"))[3] < bounds(item("batchCommandBar"))[1]
        for name in ("batchProcessButton", "batchResumeButton", "batchPauseButton"):
            target = item(name)
            if target.isVisible():
                x1, y1, x2, y2 = bounds(target)
                assert 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height, (name, x1, y1, x2, y2)
    assert item("batchProcessButton").isVisible() == (state not in ("empty", "running", "pausing"))
    assert item("batchPauseButton").isVisible() == (state in ("running", "pausing"))
    assert item("batchSettingsButton").isEnabled() == (state not in ("running", "pausing"))
    if state == "importing":
        assert not item("batchImportButton").isEnabled()
        assert not item("batchProcessButton").isEnabled()

    settings_spy = QSignalSpy(page.requestBatchSettings)
    if item("batchSettingsButton").isEnabled():
        click(item("batchSettingsButton"))
        assert settings_spy.count() == 1
    if state in ("ready", "paused", "done", "english"):
        click(item("batchProcessButton"))
        assert "process" in backend.calls
    if state == "paused":
        click(item("batchResumeButton"))
        assert "resume" in backend.calls
    if state == "running":
        click(item("batchPauseButton"))
        assert "pause" in backend.calls
        detail_spy = QSignalSpy(page.openVideoDetail)
        completed = item("batchVideoRemove_0")
        active = item("batchVideoRemove_1")
        queued = item("batchVideoRemove_2")
        assert completed.isEnabled() and completed.property("iconName") == "delete"
        assert active.isVisible() and not active.isEnabled()
        assert queued.isVisible() and not queued.isEnabled()
        click(queued)
        assert detail_spy.count() == 0
        click(completed)
        assert detail_spy.count() == 0
        confirm = item("confirmBatchVideoRemoval")
        assert confirm.isVisible() and confirm.isEnabled()
        backend.removal_blocks.append("video-0")
        backend.removalBlocksChanged.emit()
        assert not confirm.isEnabled()  # Work claimed after the dialog opened.
        backend.removal_blocks.remove("video-0")
        backend.removalBlocksChanged.emit()
        assert confirm.isEnabled()
        click(confirm)
        assert backend.calls[-1] == ("remove", "batch-test", "video-0")
        backend.batchChanged.emit()
    if state == "pausing":
        assert not item("batchPauseButton").isEnabled()
    if state in ("ready", "english"):
        # A card opens only its own detail; its delete button must not navigate.
        detail_spy = QSignalSpy(page.openVideoDetail)
        click(item("batchVideoCard_0"))
        assert backend.calls[-1] == ("select", 0)
        assert detail_spy.count() == 1
        click(item("batchVideoRemove_0"))
        assert detail_spy.count() == 1
        QTest.keyClick(window, Qt.Key_Escape)
        # All three import routes remain reachable through the compact menu.
        url_spy = QSignalSpy(page.requestUrlImport)
        download_spy = QSignalSpy(page.requestDownloadProjectImport)
        for labels in (("Tệp", "File"), ("Liên kết", "Link"), ("Từ dự án tải xuống", "From download project")):
            click(item("batchImportButton"))
            entry = next(
                child
                for child in visual_items(window.contentItem())
                if child.isVisible()
                and child.property("text") in labels
                and child.metaObject().indexOfSignal("triggered()") >= 0
            )
            click(entry)
        assert "browse" in backend.calls
        assert url_spy.count() == 1
        assert download_spy.count() == 1
    if state != "empty":
        cards = [
            child
            for child in visual_items(page)
            if child.objectName().startswith("batchVideoCard_") and child.isVisible()
        ]
        assert cards
        first_row = [card for card in cards if abs(card.y() - cards[0].y()) < 1]
        assert len(first_row) == min(len(model.rows), item("batchQueueList").property("columnCount"))
    if state == "large":
        grid = item("batchQueueList")
        grid.setProperty("contentY", grid.property("contentHeight") - grid.height())
        QTest.qWait(100)
        cards = [child for child in visual_items(page) if child.objectName().startswith("batchVideoCard_")]
        assert 0 < len(cards) < 100
        grid.setProperty("contentY", 0)
        QTest.qWait(100)

    if state == "ready":
        # Deferred actions captured on the previous project must not execute on the next one.
        before = backend.calls.count("process")
        target = item("batchProcessButton")
        position = target.mapToScene(QPointF(target.width() / 2, target.height() / 2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(position.x()), round(position.y())))
        backend.values["projectKey"] = "next-project"
        backend.changed.emit()
        QTest.qWait(80)
        assert backend.calls.count("process") == before

    assert warnings == [], "\n".join(warnings)
    output = Path(__file__).parents[1] / "build" / "ui-previews" / f"batch-{width}-{state}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    assert window.grabWindow().save(str(output))
    window.close()
    app.processEvents()


if __name__ == "__main__":
    exercise(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
