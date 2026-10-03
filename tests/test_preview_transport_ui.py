"""Transport geometry and nondestructive source-clock GUI regressions."""

from pathlib import Path
import unittest

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest


QML_DIR = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"


class PreviewTransportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlEngine()
        component = QQmlComponent(self.engine)
        component.setData((f'import QtQuick\nimport "{QML_DIR.as_uri()}"\n' + '''
            Item {
                property alias preview: preview
                QtObject {
                    id: audio
                    function seek(seconds) {}
                    function synchronize(seconds, playing, muted) {}
                }
                QtObject {
                    id: host
                    property bool canEditSelectedVideo: true
                    property var manualPreviewAudio: audio
                }
                ManualComparePreview {
                    id: preview
                    objectName: "preview"
                    anchors.fill: parent
                    controller: host
                    sequenceDurationSeconds: 100
                    resultUsesSequenceTimeline: true
                }
                function restore(seconds) { preview.restorePosition(seconds); }
                function stopSource() { preview.pausePlayback(); preview.seekTo(0); }
            }
        ''').encode(), QUrl())
        self.assertTrue(component.isReady(), "\n".join(e.toString() for e in component.errors()))
        self.item = component.create()
        self.assertIsNotNone(self.item)
        self.window = QQuickWindow()
        self.window.resize(1100, 620)
        self.item.setParent(self.window)
        self.item.setParentItem(self.window.contentItem())
        self.item.setSize(self.window.size())
        self.window.show()
        QTest.qWait(30)
        self.preview = self.item.findChild(QQuickItem, "preview")

    def tearDown(self):
        self.window.close()
        self.item.deleteLater()
        self.window.deleteLater()
        self.engine.deleteLater()
        self.app.processEvents()

    @staticmethod
    def child(item, name):
        if item.objectName() == name:
            return item
        for child in item.childItems():
            result = PreviewTransportUiTests.child(child, name)
            if result is not None:
                return result
        return None

    def test_seekbar_does_not_resize_on_play_pause_or_mouse_scrub(self):
        slider = self.child(self.preview, "manualPreviewSeekSlider")
        button = self.child(self.preview, "manualPreviewTransportButton")
        self.assertIsNotNone(slider)
        geometry = (slider.x(), slider.width(), button.width())
        for playing in (True, False, True):
            self.preview.setProperty("resultPlaybackRequested", playing)
            QTest.qWait(10)
            self.assertEqual((slider.x(), slider.width(), button.width()), geometry)
        press = slider.mapToScene(QPointF(slider.width() * .3, slider.height() / 2)).toPoint()
        end = slider.mapToScene(QPointF(slider.width() * .8, slider.height() / 2)).toPoint()
        QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, press)
        self.assertTrue(slider.property("pressed"))
        QTest.mouseMove(self.window, end)
        QTest.qWait(20)
        self.assertEqual((slider.x(), slider.width(), button.width()), geometry)
        self.assertGreater(slider.property("value"), 70)
        QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, end)
        self.assertFalse(slider.property("pressed"))

    def test_switching_monitors_preserves_source_gap_position(self):
        self.preview.setProperty("sourceEditDecisions", [{
            "source_start_ms": 3000, "source_end_ms": 8000, "sequence_start_ms": 2000,
        }])
        self.preview.setProperty("sequenceDurationSeconds", 7)
        self.preview.setProperty("activeMonitor", "source")
        self.item.restore(1)
        self.assertTrue(self.preview.property("sourceGap"))
        self.preview.setProperty("activeMonitor", "result")
        self.assertEqual(self.preview.property("positionSeconds"), 1)
        self.assertTrue(self.preview.property("sourceGap"))
        self.item.restore(4)
        self.assertFalse(self.preview.property("sourceGap"))
        self.preview.setProperty("activeMonitor", "source")
        self.preview.setProperty("activeMonitor", "result")
        self.assertEqual(self.preview.property("positionSeconds"), 4)
