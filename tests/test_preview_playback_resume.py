"""Run the real video transport with PCM/caption clocks across stop and refresh."""

import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from haizflow.desktop import manual_preview_audio_controller as pcm
from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer
from haizflow.utils.ffmpeg import _binary

QML = Path(__file__).parents[1] / "src/haizflow/desktop/qml"


class BufferedSink:
    """Bounded realtime output exposing QAudioSink's API, not a device() method."""

    def __init__(self, _device, _format, _parent):
        self.size = 9600
        self.queued = 0
        self.last_tick = time.monotonic()
        self.running = False
        self.nonzero_writes = 0
        self.stops = 0

    def setBufferSize(self, size):
        self.size = size

    def bufferSize(self):
        return self.size

    def bytesFree(self):
        now = time.monotonic()
        if self.running:
            self.queued = max(0, self.queued - int((now - self.last_tick) * pcm.RATE) * 4)
        self.last_tick = now
        return self.size - self.queued

    def start(self):
        self.running = True
        self.last_tick = time.monotonic()
        return self

    def write(self, data):
        written = min(len(data), self.bytesFree()) // 4 * 4
        self.queued += written
        if any(data[:written]):
            self.nonzero_writes += 1
        return written

    def reset(self):
        self.running = False
        self.queued = 0

    def stop(self):
        self.stops += 1
        self.reset()

    def deleteLater(self):
        pass


@pytest.fixture
def audio(monkeypatch):
    app = QGuiApplication.instance() or QGuiApplication([])
    device = SimpleNamespace(id=lambda: b"test-output", isNull=lambda: False)
    monkeypatch.setattr(pcm.QMediaDevices, "defaultAudioOutput", lambda: device)
    monkeypatch.setattr(pcm, "QAudioSink", BufferedSink)
    controller = pcm.ManualPreviewAudioController()
    controller._tracks = [dict(id="voice", kind="voice", start=0, signature="voice-cache",
                              samples=np.full((pcm.RATE * 8, 2), 1000, dtype="<i2"))]
    yield controller
    controller.close()
    app.processEvents()


def wait_until(predicate, timeout=4000):
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        if predicate():
            return
        QTest.qWait(10)
    assert predicate(), "Playback did not reach the expected state"


def test_pcm_resume_keeps_sink_tracks_and_caption_clock(audio):
    tracks = audio._tracks
    for cycle in range(4):
        audio.synchronize(0, True, False)
        wait_until(lambda: audio.positionSeconds > .2)
        sink = audio._sink
        assert sink.nonzero_writes > 0
        assert audio._tracks is tracks
        assert audio._timer.isActive()
        audio.synchronize(0, False, False)
        assert audio._sink is sink
        assert audio.positionSeconds == 0
        assert not audio._timer.isActive()
    assert sink.stops == 0


def test_output_device_change_recreates_only_the_sink(audio, monkeypatch):
    audio.synchronize(0, True, False)
    wait_until(lambda: audio.positionSeconds > .1)
    old_sink = audio._sink
    tracks = audio._tracks
    device = SimpleNamespace(id=lambda: b"headphones", isNull=lambda: False)
    monkeypatch.setattr(pcm.QMediaDevices, "defaultAudioOutput", lambda: device)
    audio._sync_output_device()
    wait_until(lambda: audio._sink is not None)
    assert audio._sink is not old_sink
    assert old_sink.stops == 1
    assert audio._sink_device_id == b"headphones"
    assert audio._tracks is tracks
    wait_until(lambda: audio._sink.nonzero_writes > 0)


def visual_child(item, name):
    if item.objectName() == name:
        return item
    for child in item.childItems():
        found = visual_child(child, name)
        if found is not None:
            return found
    return None


def test_native_result_plays_embedded_audio_with_one_clock_and_no_second_player(tmp_path):
    import os
    app = QGuiApplication.instance() or QGuiApplication([])
    source, proxy = tmp_path / "source.mp4", tmp_path / "native-preview.mp4"
    subprocess.run([
        _binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", "color=s=64x64:r=25:d=4",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
    ], check=True, capture_output=True, timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os.link(source, proxy)
    audio = pcm.ManualPreviewAudioController()
    audio.setVolumes(0, 100, 30)  # Test routing without playing sound on the host.
    audio._use_streaming_source(str(source), SimpleNamespace(original_video_volume=60), None)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("testAudio", audio)
    component = QQmlComponent(engine)
    component.setData((f'import QtQuick\nimport "{QML.as_uri()}"\n' + '''
        Item {
            QtObject {
                id: host
                property bool canEditSelectedVideo: true
                property var manualPreviewAudio: testAudio
            }
            ManualComparePreview {
                objectName: "preview"
                anchors.fill: parent
                controller: host
                sequenceDurationSeconds: 4
                resultUsesSequenceTimeline: true
                subtitleLivePreviewEnabled: true
            }
        }
    ''').encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    item = component.create()
    window = QQuickWindow()
    window.resize(900, 600)
    item.setParent(window)
    item.setParentItem(window.contentItem())
    item.setSize(window.size())
    window.show()
    preview = item.findChild(QQuickItem, "preview")
    player = preview.findChild(QMediaPlayer, "manualResultPlayer")
    try:
        preview.setProperty("resultBaseSource", QUrl.fromLocalFile(str(proxy)))
        wait_until(lambda: preview.property("embeddedSourceAudio") and not preview.property("resultPriming")
                   and not preview.property("resultSourceSwitching"))
        for _ in range(2):
            QMetaObject.invokeMethod(preview, "togglePlayback", Qt.DirectConnection)
            wait_until(lambda: player.playbackState() == QMediaPlayer.PlayingState and player.position() > 200)
            assert player.hasAudio() and not player.audioOutput().isMuted()
            assert player.audioOutput().volume() == 0
            assert audio._embedded_audio
            assert audio._native_player.playbackState() != QMediaPlayer.PlayingState
            assert not audio._timer.isActive()
            preview.setProperty("resultMuted", True)
            assert player.audioOutput().isMuted()
            preview.setProperty("resultMuted", False)
            preview.setProperty("suppressResultAudio", True)
            assert player.audioOutput().isMuted()
            preview.setProperty("suppressResultAudio", False)
            QMetaObject.invokeMethod(preview, "pausePlayback", Qt.DirectConnection)
            wait_until(lambda: not audio._playing)
        assert audio.canPlayEmbeddedSource(QUrl.fromLocalFile(str(proxy)))
    finally:
        QMetaObject.invokeMethod(preview, "releaseMedia", Qt.DirectConnection)
        window.close()
        item.deleteLater()
        window.deleteLater()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        audio.close()
        app.processEvents()


def test_playing_video_keeps_voice_and_captions_after_stop_pause_and_proxy_swap(audio, tmp_path):
    caption = SubtitleOverlayRenderer()
    sprite = QImage(64, 64, QImage.Format_ARGB32)
    sprite.fill(Qt.white)
    sprite_path = tmp_path / "caption.png"
    assert sprite.save(str(sprite_path))
    # Warm raster entries isolate transport from worker latency. Qt still
    # loads and paints the actual image through the production QML overlay.
    for index in range(8):
        event = dict(start=index, end=index + 1, body=f"cue-{index}", header="header", layout={})
        caption._events.append(event)
        caption._cache[caption._event_key(event)] = dict(
            normal=QUrl.fromLocalFile(str(sprite_path)).toString(), width=64, height=64,
            outputWidth=64, outputHeight=64, fontSize=60)
    caption.seek(0)
    audio.positionChanged.connect(lambda: caption.seek(audio.positionSeconds))
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("testAudio", audio)
    engine.rootContext().setContextProperty("testCaption", caption)
    component = QQmlComponent(engine)
    component.setData((f'import QtQuick\nimport "{QML.as_uri()}"\n' + '''
        Item {
            QtObject {
                id: host
                property bool canEditSelectedVideo: true
                property var manualPreviewAudio: testAudio
            }
            ManualComparePreview {
                objectName: "preview"
                anchors.fill: parent
                controller: host
                sequenceDurationSeconds: 8
                resultUsesSequenceTimeline: true
                subtitleLivePreviewEnabled: true
                subtitleSprite: testCaption.frame
                audioPreparationBusy: testAudio.busy
            }
        }
    ''').encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    item = component.create()
    window = QQuickWindow()
    window.resize(900, 600)
    item.setParent(window)
    item.setParentItem(window.contentItem())
    item.setSize(window.size())
    window.show()
    preview = item.findChild(QQuickItem, "preview")
    player = preview.findChild(QMediaPlayer, "manualResultPlayer")
    viewport = visual_child(preview, "manualResultViewport")
    pane = viewport.parentItem()
    overlay = visual_child(viewport, "inlineSubtitleTransformOverlay")
    tracks = audio._tracks

    def assert_playing():
        start = audio.positionSeconds
        writes = audio._sink.nonzero_writes if audio._sink else 0
        wait_until(lambda: audio.positionSeconds > start + .3)
        assert player.playbackState() == QMediaPlayer.PlayingState
        assert pane.property("overlaysReady")
        assert overlay.isVisible()
        assert caption.frame["text"] == f"cue-{int(audio.positionSeconds)}"
        assert audio._tracks is tracks
        assert audio._sink.nonzero_writes > writes
        image = visual_child(overlay, "subtitleTransformSprite")
        status = QQmlExpression(engine.rootContext(), image, "Number(status)")
        assert status.evaluate()[0] == 1  # Image.Ready: the cached raster was loaded.

    try:
        paths = []
        for color in ("red", "blue"):
            path = tmp_path / f"{color}.mp4"
            subprocess.run([
                _binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                f"color=c={color}:s=64x64:r=25:d=8", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(path),
            ], check=True, capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            paths.append(QUrl.fromLocalFile(str(path)))
        preview.setProperty("resultBaseSource", paths[0])
        wait_until(lambda: pane.property("overlaysReady") and not preview.property("resultPriming"))
        for _ in range(3):
            QMetaObject.invokeMethod(preview, "togglePlayback", Qt.DirectConnection)
            assert_playing()
            # The actual pane Stop action, not a direct audio-controller reset.
            QMetaObject.invokeMethod(pane, "stopRequested", Qt.DirectConnection)
            wait_until(lambda: not audio._playing)
            assert player.playbackState() == QMediaPlayer.StoppedState
        QMetaObject.invokeMethod(preview, "togglePlayback", Qt.DirectConnection)
        assert_playing()
        QMetaObject.invokeMethod(preview, "pausePlayback", Qt.DirectConnection)
        wait_until(lambda: not audio._playing)
        QMetaObject.invokeMethod(preview, "togglePlayback", Qt.DirectConnection)
        assert_playing()
        preview.setProperty("previewBusy", True)
        preview.setProperty("resultBaseSource", paths[1])
        wait_until(lambda: not preview.property("resultSourceSwitching"))
        preview.setProperty("previewBusy", False)
        assert_playing()
        # Mirror the audio preparation boundary of a completed processing
        # step. Keep the existing native sink and resume without reopening.
        audio.synchronize(audio.positionSeconds, False, False)
        audio._busy = True
        audio.busyChanged.emit()
        wait_until(lambda: player.playbackState() == QMediaPlayer.PausedState)
        audio._accept((audio._generation, tracks, ""))
        assert not preview.property("audioPreparationBusy")
        QMetaObject.invokeMethod(preview, "togglePlayback", Qt.DirectConnection)
        assert_playing()
        wait_until(lambda: audio.positionSeconds > 1.1)
        assert caption.frame["text"] == "cue-1"
        assert overlay.isVisible()
        player.setPosition(7800)
        wait_until(lambda: player.mediaStatus() == QMediaPlayer.EndOfMedia)
        assert not audio._playing
        QMetaObject.invokeMethod(preview, "togglePlayback", Qt.DirectConnection)
        wait_until(lambda: audio._playing and audio.positionSeconds < .5)
        assert_playing()
    finally:
        QMetaObject.invokeMethod(preview, "releaseMedia", Qt.DirectConnection)
        window.close()
        item.deleteLater()
        window.deleteLater()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        caption.close()
