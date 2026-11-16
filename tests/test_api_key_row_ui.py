"""Credential controls: one check per key, aligned actions and responsive layout."""
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("width,large", [(1000, False), (640, True), (360, False)])
def test_gemini_zernio_key_rows(width, large):
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(width), str(int(large))],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def exercise(width, large):
    from PySide6.QtCore import Property, QObject, QPointF, Qt, QUrl, Signal, Slot
    from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    from PySide6.QtTest import QTest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])
    for name in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Segoe UI", 14 if large else 11))

    class Host(QObject):
        changed = Signal()
        apiKeySettingsRequested = Signal(str)
        apiKeyGuideRequested = Signal(str)
        geminiSetupRequested = Signal()

        def __init__(self):
            super().__init__()
            self.locked = False
            self.calls = []
            self.keys = [dict(id="main", label="Dịch phụ đề", active=True, check_result="verified"),
                         dict(id="backup", label="Dự phòng · " + "Tên kết nối dài " * 8,
                              active=False, check_result="invalid")]

        translationApi = Property(QObject, lambda self: self, constant=True)
        geminiApiKeys = Property("QVariantList", lambda self: self.keys, notify=changed)
        zernioApiKeys = Property("QVariantList", lambda self: self.keys, notify=changed)
        geminiBusy = Property(bool, lambda self: self.locked, notify=changed)
        zernioCredentialBusy = Property(bool, lambda self: self.locked, notify=changed)
        zernioCredentialResult = Property(str, lambda self: "", constant=True)
        zernioApiKeyConfigured = Property(bool, lambda self: True, constant=True)
        tiktokPublishBusy = Property(bool, lambda self: False, constant=True)
        zernioAccountSyncing = Property(bool, lambda self: False, constant=True)

        @Slot(str)
        def verifyGeminiApiKey(self, identifier):
            self.calls.append(("gemini", identifier))

        @Slot(str)
        def verifyZernioApiKey(self, identifier):
            self.calls.append(("zernio", identifier))

        @Slot(str)
        def selectGeminiApiKey(self, identifier):
            self.calls.append(("use-gemini", identifier))

        @Slot(str)
        def selectZernioApiKey(self, identifier):
            self.calls.append(("use-zernio", identifier))

    def visual_items(item):
        assert isinstance(item, QQuickItem)
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    host, engine = Host(), QQmlEngine()
    engine.rootContext().setContextProperty("AppController", host)
    warnings = []
    engine.warnings.connect(lambda values: warnings.extend(value.toString() for value in values))
    root = Path(__file__).parents[1]
    component = QQmlComponent(engine)
    component.setData(b'''import QtQuick
import QtQuick.Controls.Basic
import "."
ApplicationWindow {
    visible: true; color: Theme.window
    ApiKeysPage { objectName: "page"; anchors.fill: parent; anchors.margins: 16 }
}''', QUrl.fromLocalFile(str(root / "src/haizflow/desktop/qml/ApiKeyRowTest.qml")))
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    window.setWidth(width)
    window.setHeight(720)
    QTest.qWait(80)

    def find(name):
        return next((item for item in visual_items(window.contentItem()) if item.objectName() == name), None)

    def right(item):
        return item.mapToItem(window.contentItem(), item.width(), 0).x()

    for provider in ("gemini", "zernio"):
        host.apiKeySettingsRequested.emit(provider)
        QTest.qWait(50)
        assert find("checkAllZernioKeysButton") is None
        checks = [item for item in visual_items(window.contentItem())
                  if item.objectName().startswith("verifyApiKeyButton_") and item.isVisible()]
        assert len(checks) == len(host.keys) == 2
        rows = [item for item in visual_items(window.contentItem()) if item.objectName() == "apiKeyCredentialRow"]
        assert len(rows) == 2
        assert window.grabWindow().save(str(root / "build" / f"api-key-layout-{provider}-{width}.png"))
        assert abs(right(checks[0]) - right(checks[1])) < 1, [
            (item.objectName(), item.x(), item.width(), right(item), item.parentItem().width()) for item in checks]
        assert find("apiKeyDefault_main").isVisible()
        assert not find("apiKeyDefault_backup").isVisible()
        for row in rows:
            row_left = row.mapToItem(window.contentItem(), 0, 0).x()
            row_top = row.mapToItem(window.contentItem(), 0, 0).y()
            for item in visual_items(row):
                if not item.isVisible() or not item.objectName().startswith(("verifyApiKeyButton_", "useApiKeyButton_",
                                                                            "removeApiKeyButton_", "apiKeyName_")):
                    continue
                point = item.mapToItem(window.contentItem(), 0, 0)
                assert point.x() >= row_left + 12
                assert point.x() + item.width() <= row_left + row.width() - 12 + 1
                assert point.y() >= row_top + 12
                assert point.y() + item.height() <= row_top + row.height() - 12 + 1
        # Pointer activation must target this exact key, not the active key.
        button = find("verifyApiKeyButton_backup")
        position = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, position)
        assert host.calls[-1] == (provider, "backup")
        assert len([call for call in host.calls if call == (provider, "backup")]) == 1
        # Keyboard activation remains available on the same per-key action.
        button.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Space)
        assert host.calls[-1] == (provider, "backup")
        host.locked = True
        host.changed.emit()
        QTest.qWait(20)
        assert all(not item.isEnabled() for item in checks)
        host.locked = False
        host.changed.emit()
        QTest.qWait(20)
    assert not any(any(problem in warning for problem in ("Binding loop", "TypeError", "ReferenceError", "recursive"))
                   for warning in warnings), warnings
    window.close()


if __name__ == "__main__":
    exercise(int(sys.argv[1]), bool(int(sys.argv[2])))
