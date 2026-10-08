"""Transport geometry and nondestructive source-clock GUI regressions."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from PySide6.QtCore import QMetaObject, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame

from haizflow.utils.ffmpeg import _binary


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
        # Native decoders can hold proxy files until QML deferred deletion.
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_audio_preparing_notice_blocks_result_and_compare_playback(self):
        self.preview.setProperty("audioPreparationBusy", True)
        self.preview.setProperty("previewBusy", True)
        self.preview.setProperty("previewProgress", .45)
        self.app.processEvents()
        notice = self.preview.findChild(QQuickItem, "audioPreparationNotice")
        self.assertTrue(notice.isVisible())
        for comparing in (False, True):
            self.preview.setProperty("comparing", comparing)
            QMetaObject.invokeMethod(self.preview, "togglePlayback", Qt.DirectConnection)
            self.assertFalse(self.preview.property("resultPlaybackRequested"))
        self.preview.setProperty("audioPreparationBusy", False)
        self.app.processEvents()
        self.assertFalse(notice.isVisible())

    def test_caption_overlay_stays_visible_during_independent_cache_refresh(self):
        viewport = self.child(self.preview, "manualResultViewport")
        overlay = self.child(viewport, "inlineSubtitleTransformOverlay")
        pane = viewport.parentItem()
        pane.setProperty("framePresented", True)
        pane.setProperty("awaitingMedia", False)
        self.preview.setProperty("resultSourceSwitching", False)
        self.preview.setProperty("resultPriming", False)
        self.preview.setProperty("subtitleLivePreviewEnabled", True)
        for busy in (False, True, False, True):
            self.preview.setProperty("previewBusy", busy)
            self.app.processEvents()
            self.assertTrue(pane.property("overlaysReady"))
            self.assertTrue(overlay.property("livePreviewVisible"))
        self.preview.setProperty("resultSourceSwitching", True)
        self.app.processEvents()
        self.assertFalse(pane.property("overlaysReady"))

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

    def test_new_ocr_proxy_replaces_paused_frame_without_user_seek(self):
        player = self.preview.findChild(QMediaPlayer, "manualResultPlayer")
        output = self.preview.findChild(QQuickItem, "manualResultVideoOutput")
        self.assertIsNotNone(player)
        self.assertIsNotNone(output)
        sink = output.property("videoSink")

        def wait_for_color(channel):
            for _ in range(100):
                QTest.qWait(30)
                frame = sink.videoFrame()
                if not frame.isValid():
                    continue
                image = frame.toImage()
                if image.isNull():
                    continue
                pixel = image.pixelColor(image.width() // 2, image.height() // 2)
                matches = (pixel.red() > 200 and pixel.blue() < 40) if channel == "red" else (pixel.blue() > 200 and pixel.red() < 40)
                if matches:
                    if not self.preview.property("resultPriming"):
                        return
            self.fail(f"Paused preview did not paint the replacement {channel} frame: "
                      f"state={player.playbackState()} status={player.mediaStatus()} position={player.position()} "
                      f"priming={self.preview.property('resultPriming')} switching={self.preview.property('resultSourceSwitching')} "
                      f"source={player.source()} frame={sink.videoFrame().isValid()}")

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        proxies = []
        for color in ("red", "blue"):
            path = Path(folder.name) / f"{color}.mp4"
            subprocess.run([
                _binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                f"color=c={color}:s=64x64:r=25:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
            ], check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            proxies.append(QUrl.fromLocalFile(str(path)))
        self.preview.setProperty("sequenceDurationSeconds", 3)
        self.preview.setProperty("subtitleLivePreviewEnabled", True)
        self.item.restore(1.2)
        self.preview.setProperty("resultBaseSource", proxies[0])
        wait_for_color("red")
        self.assertEqual(player.playbackState(), QMediaPlayer.PausedState)
        self.assertFalse(self.preview.property("resultPlaying"))
        self.assertAlmostEqual(self.preview.property("positionSeconds"), 1.2, delta=.05)
        for index in (1, 0, 1):
            self.preview.setProperty("previewBusy", True)
            self.preview.setProperty("resultSource", proxies[index])
            self.preview.setProperty("resultBaseSource", proxies[index])
            self.preview.setProperty("previewBusy", False)
            wait_for_color("blue" if index else "red")
            self.assertEqual(player.playbackState(), QMediaPlayer.PausedState)
            self.assertFalse(self.preview.property("resultPlaying"))
            self.assertAlmostEqual(self.preview.property("positionSeconds"), 1.2, delta=.05)
            self.assertAlmostEqual(player.position(), 1200, delta=100)
        self.preview.setProperty("resultBaseSource", QUrl())
        player.stop()
        player.setSource(QUrl())
        QMetaObject.invokeMethod(output, "clearOutput")
        sink.setVideoFrame(QVideoFrame())
        QTest.qWait(300)
