"""Isolated real-QML pan/zoom benchmark; no project/cache data is opened."""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from PySide6.QtCore import QObject, QMetaObject, Qt, QUrl, Q_ARG
from PySide6.QtGui import QGuiApplication, QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from test_subtitle_timeline_viewport_ui import QML_DIR, TimelineBackend, visual_child, wait_for


def main():
    app = QGuiApplication([])
    if os.getenv("HFLOW_UI_CAPTURE_DIR"):
        # Offscreen Qt does not enumerate Windows fonts. Register installed
        # fonts for visual QA only; never copy them into project assets.
        for name in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf"):
            font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))
    engine = QQmlEngine()
    backend = TimelineBackend()
    engine.rootContext().setContextProperty("AppController", backend)
    segments = [{"start": i * 2, "end": i * 2 + 1.6, "text": f"Subtitle {i}"} for i in range(1200)]
    clips = [{"clip_id": f"voice-{i}", "track_id": "voice", "kind": "voice", "enabled": True,
              "start_ms": i * 2000, "duration_ms": 1600, "waveform": [.2, .4, .8, .6, .3, .1]}
             for i in range(1200)]
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 1280; height: 340; visible: true
    SubtitleTimeline {{ objectName: "timeline"; anchors.fill: parent; duration: 2530
        segments: {json.dumps(segments)}
        editorTracks: [{{track_id: "voice", kind: "voice", visible: true, name: "Voice"}}]
        editorClips: {json.dumps(clips)}
    }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    try:
        timeline = window.findChild(QObject, "timeline")
        wait_for(lambda: len(timeline.property("visibleSegments").toVariant()) == 1200)
        capture_directory = os.getenv("HFLOW_UI_CAPTURE_DIR")
        if capture_directory:
            directory = Path(capture_directory)
            directory.mkdir(parents=True, exist_ok=True)
            QTest.qWait(100)
            assert window.grabWindow().save(str(directory / "timeline-fit.png"))
        times = []
        for factor in (1.2, 1.5, 2, 3, 4, 6, 8, 12, 18, 24, 12, 6, 3, 1):
            start = time.perf_counter()
            timeline.setProperty("zoomFactor", factor)
            QMetaObject.invokeMethod(timeline, "refreshVisibleSegments", Qt.DirectConnection)
            app.processEvents()
            times.append((time.perf_counter() - start) * 1000)
        timeline.setProperty("zoomFactor", 12)
        QTest.qWait(100)
        retained = visual_child(window.contentItem(), lambda item: item.objectName() == "subtitleTimelineClip-20")
        pans = []
        for _ in range(60):
            start = time.perf_counter()
            QMetaObject.invokeMethod(timeline, "panByPixels", Qt.DirectConnection, Q_ARG("QVariant", 2))
            QMetaObject.invokeMethod(timeline, "refreshVisibleSegments", Qt.DirectConnection)
            app.processEvents()
            pans.append((time.perf_counter() - start) * 1000)
        same = visual_child(window.contentItem(), lambda item: item.objectName() == "subtitleTimelineClip-20")
        print(json.dumps({"subtitles": 1200, "zoom_total_ms": round(sum(times), 1),
                          "pan_total_ms": round(sum(pans), 1), "pan_peak_ms": round(max(pans), 1),
                          "retained_delegate": same is retained,
                          "tick_count": len(timeline.property("visibleTicks").toVariant())}), flush=True)
        if capture_directory:
            QTest.qWait(100)
            assert window.grabWindow().save(str(directory / "timeline-panned.png"))
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    main()
