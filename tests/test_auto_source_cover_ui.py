"""Exercise real QML controls and live source preview in an isolated Qt process."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("mode", ["patch", "blur"])
def test_source_cover_dialog_controls_and_preview(mode):
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), mode],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def exercise(mode):
    from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, Property, Qt, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication, QFont, QFontDatabase
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    class Backend(QObject):
        @Slot(str, str, str)
        def presentUserError(self, title, detail, log):
            self.last_error = (title, detail, log)

        selectedVideoChanged = Signal()
        sourceReplacementRequested = Signal(str)
        mediaImportChanged = Signal()
        @Property(str, constant=True)
        def selectedVideoId(self): return "one"
        @Property(str, constant=True)
        def projectKey(self): return "project"
        @Property(bool, constant=True)
        def mediaImportBusy(self): return False

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])
    for name in ("SegUIVar.ttf", "SegoeIcons.ttf"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font.is_file(): QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Segoe UI Variable"))
    directory = Path(__file__).parents[1]
    output = directory / "build/source-cover-ui"
    output.mkdir(parents=True, exist_ok=True)
    video = output / "source.mp4"
    # Real decodable source; no user project or model/network is accessed.
    subprocess.run([str(directory / "runtime/bin/ffmpeg.exe"), "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10:duration=2", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", str(video)], check=True, timeout=20, capture_output=True)
    engine = QQmlEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("AppController", backend)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(e.toString() for e in items))
    component = QQmlComponent(engine)
    component.setData(b'''import QtQuick
import QtQuick.Controls.Basic
import "."
ApplicationWindow {
    width: 1120; height: 840; visible: true; color: Theme.window
    property int saves: 0
    property var savedRegion: ({})
    property bool saveAllowed: true
    SourceCoverDialog {
        id: dialog; objectName: "dialog"
        saveHandler: function(region) {
            if (!parentWindow.saveAllowed) return false;
            parentWindow.saves++;
            parentWindow.savedRegion = region;
            return true;
        }
    }
    id: parentWindow
    function showDialog(source, mode) {
        dialog.openForSource({videoId: "one", projectKey: "project", sourceKey: "source",
            videoSource: source, videoWidth: 640, videoHeight: 360,
            detectedRegion: {x_percent: 10, y_percent: 70, width_percent: 80, height_percent: 12}}, {});
    }
}''', QUrl.fromLocalFile(str(directory / "src/haizflow/desktop/qml/SourceCoverTest.qml")))
    assert component.isReady(), [e.toString() for e in component.errors()]
    window = component.create()
    assert window is not None
    def show():
        assert QMetaObject.invokeMethod(window, "showDialog", Qt.DirectConnection,
            Q_ARG("QVariant", video.as_uri()), Q_ARG("QVariant", mode))
        QTest.qWait(800)
    show()
    dialog = window.findChild(QObject, "dialog")
    region = window.findChild(QObject, "sourceCoverRegion")
    checkbox = window.findChild(QObject, "sourceCoverAutomatic")
    assert dialog.property("automatic")
    assert not region.property("enabled")
    player = window.findChild(QQuickItem, "sourceCoverPlayer")
    assert player.property("inlineFrameReady")
    assert not player.property("playing"), "Opening must remain paused, not autoplay"
    assert QMetaObject.invokeMethod(checkbox, "toggle", Qt.DirectConnection)
    assert QMetaObject.invokeMethod(checkbox, "toggled", Qt.DirectConnection)
    QTest.qWait(50)
    assert not dialog.property("automatic")
    assert region.property("enabled") and region.property("editing")
    assert window.findChild(QObject, "outputBackgroundCapture") is None
    assert not any("ShaderEffect" in obj.metaObject().className() or "MultiEffect" in obj.metaObject().className()
                   for obj in player.findChildren(QObject)), "Preview must show source pixels, never apply coverage"
    edited = dict(x_percent=15, y_percent=55, width_percent=65, height_percent=15)
    assert QMetaObject.invokeMethod(region, "regionEdited", Qt.DirectConnection, Q_ARG("QVariant", edited))
    # Prove movement is not just a decorative box: focus + arrow uses Manual's code.
    rect = player.property("videoRect")
    point = player.mapToScene(QPoint(int(rect.x() + rect.width() * .4), int(rect.y() + rect.height() * .6)))
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
    QTest.keyClick(window, Qt.Key_Right)
    QTest.qWait(100)
    assert window.grabWindow().save(str(output / f"cover-{mode}.png"))
    assert QMetaObject.invokeMethod(dialog, "applyDraft", Qt.DirectConnection)
    QTest.qWait(150)
    assert window.property("saves") == 1
    saved = window.property("savedRegion").toVariant()
    assert saved["x_percent"] > edited["x_percent"]
    show()
    dialog.close()
    QTest.qWait(100)
    assert window.property("saves") == 1, "Close/X/Escape must discard draft"
    show()
    window.setProperty("saveAllowed", False)
    assert QMetaObject.invokeMethod(dialog, "applyDraft", Qt.DirectConnection)
    assert dialog.property("visible") and dialog.property("errorText")
    backend.sourceReplacementRequested.emit("one")
    QTest.qWait(200)
    assert not dialog.property("visible")
    assert warnings == [], "\n".join(warnings)
    window.close()
    app.processEvents()


if __name__ == "__main__":
    exercise(sys.argv[1])
