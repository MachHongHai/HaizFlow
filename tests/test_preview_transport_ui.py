"""Transport geometry and nondestructive source-clock GUI regressions."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from PySide6.QtCore import QMetaObject, QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame

from hflow.utils.ffmpeg import _binary


QML_DIR = Path(__file__).resolve().parents[1] / "src/hflow/desktop/qml"


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
                    property real playbackRate: 1.0
                    function setPlaybackRate(rate, seconds) { playbackRate = rate; }
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
                function replaceDuringPrime(source) {
                    preview.primeResultFrame();
                    preview.resultSource = source;
                }
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

    def test_speed_popup_applies_only_on_release_without_playing_or_changing_position(self):
        button = self.child(self.preview, "manualResultSpeedButton")
        self.assertIsNotNone(button)
        self.item.restore(42)
        players = [self.preview.findChild(QMediaPlayer, name)
                   for name in ("manualInputPlayer", "manualResultPlayer")]
        initial_geometry = (button.width(), button.height())
        point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
        self.app.processEvents()
        popup = button.findChild(QObject, "previewSpeedPopup")
        self.assertTrue(popup.property("opened"))
        self.assertEqual(self.preview.property("playbackSpeed"), 1)
        slider = button.findChild(QQuickItem, "previewSpeedSlider")
        origin = slider.mapToScene(QPointF(slider.width() * .2727, slider.height() / 2)).toPoint()
        target = slider.mapToScene(QPointF(slider.width() * .6, slider.height() / 2)).toPoint()
        QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, origin)
        QTest.mouseMove(self.window, target, 20)
        self.app.processEvents()
        self.assertTrue(slider.property("pressed"))
        self.assertEqual(self.preview.property("playbackSpeed"), 1)
        expected = round(slider.property("value"), 2)
        self.assertGreater(expected, 1.5)
        QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, target)
        self.app.processEvents()
        self.assertAlmostEqual(self.preview.property("playbackSpeed"), expected)
        self.assertEqual((button.width(), button.height()), initial_geometry)
        self.assertEqual(self.preview.property("positionSeconds"), 42)
        self.assertFalse(self.preview.property("resultPlaybackRequested"))
        self.assertFalse(self.preview.property("inputPlaybackRequested"))
        for player in players:
            self.assertAlmostEqual(player.playbackRate(), expected)
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
        self.app.processEvents()
        self.assertFalse(popup.property("opened"))
        self.preview.setProperty("playbackSpeed", 2)
        QMetaObject.invokeMethod(self.preview, "pausePlayback", Qt.DirectConnection)
        self.assertEqual(players[1].playbackRate(), 2)
        self.preview.setProperty("activeMonitor", "source")
        source_button = self.child(self.preview, "manualInputSpeedButton")
        self.assertEqual(source_button.property("speed"), 2)

    def test_edited_source_gap_clock_uses_selected_speed(self):
        self.preview.setProperty("sourceEditDecisions", [{
            "source_start_ms": 0, "source_end_ms": 1000, "sequence_start_ms": 4000,
        }])
        self.preview.setProperty("sequenceDurationSeconds", 10)
        self.preview.setProperty("activeMonitor", "source")
        self.preview.setProperty("inputSourceSwitching", False)
        for rate in (.5, 2):
            self.preview.setProperty("playbackSpeed", rate)
            self.item.restore(0)
            QMetaObject.invokeMethod(self.preview, "togglePlayback", Qt.DirectConnection)
            QTest.qWait(240)
            QMetaObject.invokeMethod(self.preview, "pausePlayback", Qt.DirectConnection)
            self.assertGreater(self.preview.property("positionSeconds"), .14 * rate)
            self.assertLess(self.preview.property("positionSeconds"), .4 * rate)

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

    def test_metadata_update_during_first_frame_never_requests_playback(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "preview.mp4"
        subprocess.run([
            _binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
            "color=c=blue:s=64x64:r=25:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ], check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        player = self.preview.findChild(QMediaPlayer, "manualResultPlayer")
        self.preview.setProperty("subtitleLivePreviewEnabled", True)
        self.preview.setProperty("resultBaseSource", QUrl.fromLocalFile(str(path)))
        for _ in range(150):
            QTest.qWait(20)
            if player.playbackState() == QMediaPlayer.PausedState and not self.preview.property("resultPriming"):
                break
        self.assertEqual(player.playbackState(), QMediaPlayer.PausedState)
        # Cache metadata may arrive while the base decoder is painting a frame.
        # The effective source is unchanged; this is not a user Play action.
        self.item.replaceDuringPrime(QUrl.fromLocalFile(str(path)))
        self.assertFalse(self.preview.property("resultPlaying"))
        self.item.restore(1)
        QTest.qWait(900)
        self.assertFalse(self.preview.property("resultPlaybackRequested"))
        self.assertFalse(self.preview.property("resultPlaying"))
        QMetaObject.invokeMethod(self.preview, "releaseMedia", Qt.DirectConnection)
        QTest.qWait(300)

    def test_release_cancels_pending_scrub_resume_before_reopening(self):
        self.preview.setProperty("resultPlaybackRequested", True)
        self.item.restore(1)
        QMetaObject.invokeMethod(self.preview, "releaseMedia", Qt.DirectConnection)
        # A late decoder observation must not resurrect playback in a new project.
        scrub = self.preview.findChild(QQuickItem, "manualPreviewScrubController")
        self.assertFalse(scrub.property("wasPlaying"))
        self.assertFalse(scrub.property("pending"))
        scrub.observe(1000)
        self.assertFalse(self.preview.property("resultPlaybackRequested"))

    def test_explicit_pause_cancels_deferred_resume(self):
        self.preview.setProperty("resultPlaybackRequested", True)
        self.item.restore(1)
        scrub = self.preview.findChild(QQuickItem, "manualPreviewScrubController")
        self.assertTrue(scrub.property("wasPlaying"))
        QMetaObject.invokeMethod(self.preview, "pausePlayback", Qt.DirectConnection)
        scrub.observe(1000)
        self.assertFalse(scrub.property("wasPlaying"))
        self.assertFalse(self.preview.property("resultPlaybackRequested"))

    def test_switch_project_resets_play_intent_and_priming_timers(self):
        self.preview.setProperty("inputPlaybackRequested", True)
        self.preview.setProperty("resultPlaybackRequested", True)
        self.preview.setProperty("inputPriming", True)
        self.preview.setProperty("resultPriming", True)
        self.item.restore(1)
        QMetaObject.invokeMethod(self.preview, "resetPlayback", Qt.DirectConnection)
        QTest.qWait(900)
        for name in ("resultPlaying", "inputPlaying", "inputPriming", "resultPriming"):
            self.assertFalse(self.preview.property(name), name)

    def test_hidden_workspace_does_not_resume_when_shown_again(self):
        self.preview.setProperty("resultPlaybackRequested", True)
        self.item.restore(1)
        self.preview.setVisible(False)
        self.preview.setVisible(True)
        QTest.qWait(900)
        self.assertFalse(self.preview.property("resultPlaying"))
        self.assertFalse(self.preview.property("inputPlaying"))

    def test_play_button_is_not_disabled_by_a_visual_background_refresh(self):
        # A visual cache refresh is independent of usable loaded media/audio.
        self.preview.setProperty("previewBusy", True)
        self.preview.setProperty("audioPreparationBusy", False)
        self.preview.setProperty("resultSourceSwitching", False)
        QMetaObject.invokeMethod(self.preview, "togglePlayback", Qt.DirectConnection)
        self.assertTrue(self.preview.property("resultPlaybackRequested"))
        QMetaObject.invokeMethod(self.preview, "togglePlayback", Qt.DirectConnection)
        self.assertFalse(self.preview.property("resultPlaybackRequested"))
