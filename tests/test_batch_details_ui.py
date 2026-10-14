"""Real Qt layout checks, isolated from the application's singleton engine."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("width,overrides", [(960, False), (1440, True)])
def test_batch_details_layout_and_large_lists(width, overrides):
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(width), str(int(overrides))],
                               capture_output=True, text=True, timeout=40)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def exercise(width, overrides):
    from PySide6.QtCore import QByteArray, QUrl, QObject
    from PySide6.QtGui import QGuiApplication, QFont, QFontDatabase
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])
    # The offscreen Qt platform doesn't enumerate Windows system fonts.
    for name in ("SegUIVar.ttf", "SegoeIcons.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Segoe UI Variable"))
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
    directory = Path(__file__).parents[1] / "src/hflow/desktop/qml"
    component = QQmlComponent(engine)
    component.setData(QByteArray(b'''
        import QtQuick
        import QtQuick.Controls.Basic
        import "."
        ApplicationWindow {
            visible: true
            width: 960; height: 780
            BatchDetailsDialog { id: details; objectName: "batchDetails" }
        }
    '''), QUrl.fromLocalFile(str(directory / "BatchTestWindow.qml")))
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    window.setWidth(width)
    details = window.findChild(QObject, "batchDetails")
    details.setProperty("overrides", overrides)
    details.setProperty("rows", [
        {"fileName": f"Video {index}.mp4", "status": "failed", "error": "Example failure " * 30,
         "differences": ["translationModel", "speakerMode", "watermarkImagePath", "backgroundMusicPath"]}
        for index in range(1000)])
    details.open()
    QTest.qWait(250)
    assert 0 < details.property("height") <= 680
    assert details.property("width") <= width - 48
    assert warnings == [], "\n".join(warnings)
    output = Path(__file__).parents[1] / "build" / f"batch-details-{'settings' if overrides else 'errors'}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    assert window.grabWindow().save(str(output))
    details.close()
    window.close()
    app.processEvents()


if __name__ == "__main__":
    exercise(int(sys.argv[1]), bool(int(sys.argv[2])))
