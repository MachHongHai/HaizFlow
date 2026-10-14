"""Exercise actual QML viewport culling, including sub-pixel long-video zoom."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPointF, Property, QUrl, Qt, QMetaObject, Q_ARG
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

QML_DIR = Path(__file__).parents[1] / "src/hflow/desktop/qml"


class TimelineBackend(QObject):
    @Property("QVariantMap", constant=True)
    def manualEditorDocumentModel(self):
        return {"selectedTrackId": "subtitles"}


def visual_child(item, predicate):
    if predicate(item):
        return item
    for child in item.childItems():
        if (found := visual_child(child, predicate)) is not None:
            return found
    return None


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        QTest.qWait(20)
        if predicate():
            return
    assert predicate()


def variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


@pytest.mark.parametrize("width,duration", [(900, 2530), (1800, 2530), (1000, 3600), (1280, 60)])
def test_subtitles_and_voice_cover_fit_zoom_and_survive_zoom_resize(width, duration):
    # Keep QML engine/window lifetimes isolated from the other desktop suites.
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), str(width), str(duration)],
        capture_output=True, text=True, timeout=45,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def exercise_timeline_viewport(width, duration):
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    backend = TimelineBackend()
    engine.rootContext().setContextProperty("AppController", backend)
    # Dense cues expose missing delegates, while an isolated final cue can be
    # clicked without neighbouring minimum-width handles obscuring it.
    count = 440 if duration > 60 else 8
    interval = duration * 0.8 / count
    segments = [{"start": index * interval,
                 "end": index * interval + min(4, interval * 0.7),
                 "text": f"Cue {index}"} for index in range(count)]
    segments.append({"start": duration * 0.9, "end": duration - 1, "text": "Final cue"})
    voice_clips = [{"clip_id": f"voice-{index}", "track_id": "voice", "kind": "voice",
                    "enabled": True, "start_ms": round(segment["start"] * 1000),
                    "duration_ms": round((segment["end"] - segment["start"]) * 1000)}
                   for index, segment in enumerate(segments)]
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: {width}; height: 340; visible: true
    SubtitleTimeline {{
        objectName: "timeline"; anchors.fill: parent; duration: {duration}
        segments: {json.dumps(segments)}
        editorTracks: [{{track_id: "voice", kind: "voice", visible: true, name: "Giọng đọc"}}]
        editorClips: {json.dumps(voice_clips)}
    }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    try:
        timeline = window.findChild(QObject, "timeline")
        selected = []
        timing_changes = []
        timeline.segmentSelected.connect(selected.append)
        timeline.timingCommitted.connect(lambda *args: timing_changes.append(args))

        def assert_final_cues():
            final_subtitle = visual_child(window.contentItem(),
                lambda item: item.objectName() == f"subtitleTimelineClip-{count}")
            assert final_subtitle is not None
            assert final_subtitle.isVisible()
            final_voice = visual_child(window.contentItem(),
                lambda item: item.property("clipId") == f"voice-{count}")
            assert final_voice is not None
            assert final_voice.isVisible()
            assert final_subtitle.x() == pytest.approx(
                timeline.property("trackLeft") + segments[-1]["start"] * timeline.property("pixelsPerSecond"))
            return final_subtitle

        def assert_fit():
            wait_for(lambda: [segment["sourceIndex"] for segment in
                timeline.property("visibleSegments").toVariant()] == list(range(count + 1)))
            visible = timeline.property("visibleSegments").toVariant()
            assert [segment["sourceIndex"] for segment in visible] == list(range(count + 1))
            voice_track = visual_child(window.contentItem(),
                lambda item: item.objectName() == "timelineTrack-voice")
            assert len(voice_track.property("clips").toVariant()) == count + 1
            assert_final_cues()

        assert_fit()
        zoom_in = visual_child(window.contentItem(),
            lambda item: item.objectName() == "timelineZoomInButton")
        zoom_out = visual_child(window.contentItem(),
            lambda item: item.objectName() == "timelineZoomOutButton")
        assert zoom_in is not None and zoom_out is not None
        assert zoom_in.isEnabled() and not zoom_out.isEnabled()
        assert zoom_in.mapToScene(QPointF()).y() < 30  # Above the result track.
        for button, expected in ((zoom_in, 1.5), (zoom_out, 1)):
            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            wait_for(lambda: timeline.property("zoomFactor") == expected)
            assert selected == [] and timing_changes == []
        timeline.setProperty("zoomFactor", 24)
        QTest.qWait(30)
        assert not zoom_in.isEnabled()
        assert zoom_out.mapToScene(QPointF()).x() < timeline.property("trackLeft")
        timeline.setProperty("editingClip", True)
        assert not zoom_out.isEnabled()
        timeline.setProperty("editingClip", False)
        timeline.setProperty("zoomFactor", 1)
        assert_fit()
        # The reported 42-minute video fits at less than one pixel per second.
        if duration > 60:
            assert timeline.property("pixelsPerSecond") < 1
        for resized_width in (700, 1600, width):
            window.setWidth(resized_width)
            assert_fit()

        for zoom in ((1.5, 24) if duration > 60 else (24,)):
            timeline.setProperty("position", 0)
            timeline.setProperty("zoomFactor", zoom)
            QTest.qWait(100)
            timeline.setProperty("position", duration * 0.95)
            def first_is_offscreen():
                first = visual_child(window.contentItem(),
                    lambda item: item.objectName() == "subtitleTimelineClip-0")
                # Buffered delegates may remain allocated outside the viewport.
                return first is None or not first.isVisible()

            wait_for(first_is_offscreen)
            wait_for(lambda: visual_child(window.contentItem(),
                lambda item: item.objectName() == f"subtitleTimelineClip-{count}") is not None)
            assert_final_cues()

        timeline.setProperty("zoomFactor", 1)
        timeline.setProperty("position", 0)
        assert_fit()
        last = assert_final_cues()
        point = last.mapToScene(QPointF(last.width() / 2, last.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(50)
        assert selected == [count]
        assert timing_changes == []
        assert timeline.property("segments").toVariant() == segments
        assert timeline.property("editorClips").toVariant() == voice_clips

        # Stable keyed models must preserve surviving clip objects while
        # continuously panning, not reset every Repeater at each wheel event.
        timeline.setProperty("zoomFactor", 12)
        timeline.setProperty("position", duration * .45)
        QTest.qWait(100)
        visible = timeline.property("visibleSegments").toVariant()
        retained_index = int(visible[len(visible) // 2]["sourceIndex"])
        retained = visual_child(window.contentItem(),
            lambda item: item.objectName() == f"subtitleTimelineClip-{retained_index}")
        voice = visual_child(window.contentItem(), lambda item: item.property("clipId") == f"voice-{retained_index}")
        assert retained is not None and voice is not None
        for _ in range(12):
            assert QMetaObject.invokeMethod(timeline, "panByPixels", Qt.DirectConnection, Q_ARG("QVariant", 1))
            assert QMetaObject.invokeMethod(timeline, "refreshVisibleSegments", Qt.DirectConnection)
            app.processEvents()
        assert visual_child(window.contentItem(),
            lambda item: item.objectName() == f"subtitleTimelineClip-{retained_index}") is retained
        assert visual_child(window.contentItem(), lambda item: item.property("clipId") == f"voice-{retained_index}") is voice

        refreshes = []
        timeline.visibleSegmentsChanged.connect(lambda: refreshes.append(True))
        for _ in range(24):
            assert QMetaObject.invokeMethod(timeline, "panByPixels", Qt.DirectConnection, Q_ARG("QVariant", 1))
            QTest.qWait(5)
        assert len(refreshes) > 1  # Continuous input must not starve viewport updates.

        # High-frequency wheel events accumulate once per frame and preserve
        # the media time under the pointer, rather than losing wheel steps.
        timeline.setProperty("zoomFactor", 3)
        QTest.qWait(50)
        viewport = window.findChild(QObject, "timelineViewport")
        viewport.setProperty("contentX", 400)
        pointer_x = width * .6
        anchor_time = (400 + pointer_x - timeline.property("trackLeft")) / timeline.property("pixelsPerSecond")
        for _ in range(3):
            assert QMetaObject.invokeMethod(timeline, "queueWheelZoom", Qt.DirectConnection,
                                           Q_ARG("QVariant", pointer_x), Q_ARG("QVariant", 1.2))
        assert timeline.property("zoomFactor") == 3
        wait_for(lambda: timeline.property("zoomFactor") == pytest.approx(3 * 1.2 ** 3))
        QTest.qWait(30)
        assert (viewport.property("contentX") + pointer_x - timeline.property("trackLeft")) \
            / timeline.property("pixelsPerSecond") == pytest.approx(anchor_time)

        # Restore the retained cue's viewport before checking source updates.
        timeline.setProperty("zoomFactor", 12)
        timeline.setProperty("position", duration * .45 + .01)
        QTest.qWait(60)
        retained = visual_child(window.contentItem(),
            lambda item: item.objectName() == f"subtitleTimelineClip-{retained_index}")
        voice = visual_child(window.contentItem(), lambda item: item.property("clipId") == f"voice-{retained_index}")
        assert retained is not None and voice is not None

        # Cue data changes update the retained delegate, not stale copied roles.
        updated = [dict(segment) for segment in segments]
        updated[retained_index]["text"] = "Updated cue"
        timeline.setProperty("segments", updated)
        QTest.qWait(40)
        assert visual_child(window.contentItem(),
            lambda item: item.objectName() == f"subtitleTimelineClip-{retained_index}") is retained
        assert variant(retained.property("modelData"))["text"] == "Updated cue"
        timeline.setProperty("editorClips", list(reversed(voice_clips)))
        QTest.qWait(40)
        assert visual_child(window.contentItem(), lambda item: item.property("clipId") == f"voice-{retained_index}") is voice
        assert voice.property("previewStartMs") == voice_clips[retained_index]["start_ms"]

        timeline.setProperty("zoomFactor", 1)
        QTest.qWait(40)
        assert len(timeline.property("visibleTicks").toVariant()) <= width / 56 + 12
        assert variant(timeline.property("segments")) == updated
        assert variant(timeline.property("editorClips")) == list(reversed(voice_clips))
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    exercise_timeline_viewport(int(sys.argv[1]), int(sys.argv[2]))
