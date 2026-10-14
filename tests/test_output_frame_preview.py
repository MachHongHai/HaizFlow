"""Live canvas geometry and unchanged long-video source-cache regressions."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hflow.desktop.editor_preview_controller import EditorPreviewController
from hflow.schemas.video import VideoConfig, VideoInfo

QML_DIR = Path(__file__).parents[1] / "src/hflow/desktop/qml"


def test_manual_canvas_switch_reuses_existing_ocr_request_without_worker(tmp_path):
    source = tmp_path / "long.mp4"
    source.write_bytes(b"isolated media")
    video = VideoInfo(**VideoConfig(project_type="manual").model_dump(), video_id="live-frame",
                      original_filename="long.mp4", status="manual_ready", created_at="", updated_at="",
                      video_width=1920, video_height=1080)
    host = SimpleNamespace(_selected_video=lambda: video, _resolve_video_file=lambda *_args: str(source),
                           manualPreviewAudio=object(), editorPreviewChanged=Mock())
    controller = EditorPreviewController(host)
    ocr = {"x_percent": 5, "y_percent": 80, "width_percent": 90, "height_percent": 10}
    with (patch("hflow.desktop.editor_preview_controller.video_store.get_video_dir", return_value=str(tmp_path)),
          patch("hflow.services.editor_documents.load", return_value=None),
          patch.object(controller, "_ocr_region", return_value=ocr),
          patch.object(controller, "_manual_voice_artifact", return_value=None),
          patch.object(controller, "_restore_manual_disk_cache"),
          patch.object(controller, "_published_source_is_intact", return_value=True),
          patch("hflow.desktop.editor_preview_controller.threading.Thread") as worker):
        assert controller.request("[]", 0)
        fingerprint = controller._request_fingerprint
        settings = worker.call_args.kwargs["args"][3]
        assert settings["ocr_region"] == ocr
        assert settings["output_format"] == "keep_ratio"
        controller._busy = False
        controller._stage = "ready"
        controller._source = source.as_uri()
        controller._base_source = source.as_uri()
        for mode in ("blur_background_9_16", "tiktok_9_16_crop", "keep_ratio"):
            video.output_format = mode
            assert controller.request("[]", 1750)
            assert controller._request_fingerprint == fingerprint
            assert not controller.busy
        worker.assert_called_once()


def _check_live_frame_ui():
    from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl, QPointF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor, QFontDatabase
    from PySide6.QtMultimedia import QVideoFrame
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QSignalSpy, QTest

    app = QGuiApplication.instance() or QGuiApplication([])
    for font in ("SegUIVar.ttf", "SegoeIcons.ttf"):
        QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / font))
    engine = QQmlEngine()
    temporary = tempfile.TemporaryDirectory(prefix="frame-thumbnail-")
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 1120; height: 720; visible: true; color: Theme.window
    ManualEditorToolbar {{
        objectName: "toolbar"; width: parent.width; hasVideo: true
        projectTitle: "Video dài"; outputFormat: "blur_background_9_16"
    }}
    OutputFramePreview {{
        objectName: "frame"; x: 20; y: 65; width: 800; height: 600
        outputFormat: "blur_background_9_16"
        thumbnailOutputFormat: "blur_background_9_16"
    }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    try:
        toolbar = window.findChild(QObject, "toolbar")
        combo = window.findChild(QObject, "manualOutputFrameCombo")
        group = window.findChild(QObject, "manualHistoryGroup")
        export = window.findChild(QObject, "manualExportButton")
        spy = QSignalSpy(toolbar.outputFormatEdited)
        for width in (800, 1120, 1600):
            window.setWidth(width)
            QTest.qWait(40)
            assert combo.property("count") == 3 and combo.property("currentIndex") == 1
            combo_right = combo.mapToScene(QPointF(combo.width(), 0)).x()
            combo_left = combo.mapToScene(QPointF()).x()
            assert group.x() + group.width() <= combo_left - 4
            assert combo.width() >= 90
            assert combo.width() <= 160
            assert group.x() + group.width() < export.mapToScene(QPointF()).x()
            speed_button = toolbar.findChild(QObject, "manualOutputSpeedButton")
            assert combo.parentItem() is speed_button.parentItem()
            assert abs(speed_button.mapToScene(QPointF()).x() - combo_right - 8) < 1
            assert group.x() + group.width() < speed_button.mapToScene(QPointF()).x()
        toolbar.setProperty("outputFormat", "tiktok_9_16_crop")
        QTest.qWait(20)
        assert combo.property("currentIndex") == 2 and spy.count() == 0
        assert combo.property("displayText") == "9:16 Đầy khung"
        filled_width = combo.width()
        toolbar.setProperty("outputFormat", "keep_ratio")
        QTest.qWait(20)
        assert combo.property("displayText") == "Tỷ lệ gốc"
        assert combo.width() == filled_width
        toolbar.setProperty("outputFormat", "tiktok_9_16_crop")
        toolbar.setProperty("outputFormatEditable", False)
        assert not combo.property("enabled")
        toolbar.setProperty("outputFormatEditable", True)
        combo.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Space)
        QTest.keyClick(window, Qt.Key_Up)
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(30)
        assert spy.count() == 1 and spy.at(0)[0] == "blur_background_9_16"

        frame = window.findChild(QObject, "frame")
        sink = frame.property("videoSink")
        image = QImage(640, 360, QImage.Format_RGB32)
        painter = QPainter(image)
        painter.fillRect(0, 0, 320, 360, QColor("red"))
        painter.fillRect(320, 0, 320, 360, QColor("blue"))
        painter.end()
        thumbnail_path = Path(temporary.name) / "source.png"
        assert image.save(str(thumbnail_path))
        frame.setProperty("thumbnailSource", QUrl.fromLocalFile(str(thumbnail_path)))
        frame.setProperty("thumbnailOutputFormat", "blur_background_9_16")
        frame.setProperty("showThumbnail", True)
        # Simulate instant project open before a media frame/cache exists.
        # Published outputs already have the format baked in; their source
        # thumbnail still needs the saved ratio during frame priming.
        frame.setProperty("outputFormat", "keep_ratio")
        QTest.qWait(180)
        assert frame.property("thumbnailVisible")
        assert abs(frame.property("contentRect").width() / frame.property("contentRect").height() - 9 / 16) < .00001
        thumbnail = frame.findChild(QObject, "outputFrameThumbnail")
        assert thumbnail.property("visible") and len(frame.findChildren(QObject, "outputFrameVideo")) == 1
        if os.environ.get("HFLOW_FRAME_PIXEL_QA") == "1":
            shot = window.grabWindow()
            rect = frame.property("contentRect")
            point = frame.mapToScene(QPointF(rect.center().x(), rect.y() + 30))
            color = shot.pixelColor(round(point.x() * shot.width() / window.width()),
                                    round(point.y() * shot.height() / window.height()))
            assert color.red() > 20 and color.blue() > 20  # Thumbnail blur fills the portrait frame.
        frame.setProperty("thumbnailOutputFormat", "tiktok_9_16_crop")
        QTest.qWait(30)
        assert abs(frame.property("contentRect").width() / frame.property("contentRect").height() - 9 / 16) < .00001
        frame.setProperty("showThumbnail", False)
        frame.setProperty("outputFormat", "blur_background_9_16")
        sink.setVideoFrame(QVideoFrame(image))
        QTest.qWait(150)
        rect = frame.property("contentRect")
        assert abs(rect.width() / rect.height() - 9 / 16) < .00001
        assert rect.height() == 600 and rect.width() == 337.5
        assert len(frame.findChildren(QObject, "outputFrameVideo")) == 1
        assert not window.findChildren(QObject, "manualInputPlayer")
        capture_dir = os.environ.get("HFLOW_UI_PREVIEWS")
        if capture_dir:
            window.setWidth(1120)
            QTest.qWait(80)
            assert window.grabWindow().save(str(Path(capture_dir) / "live-output-frame.png"))
        if os.environ.get("HFLOW_FRAME_PIXEL_QA") == "1":
            # Native Windows/D3D rendering: offscreen/software only tests geometry.
            shot = window.grabWindow()
            def pixel(x, y):
                point = frame.mapToScene(QPointF(x, y))
                return shot.pixelColor(round(point.x() * shot.width() / window.width()),
                                       round(point.y() * shot.height() / window.height()))
            left = pixel(rect.x() + 30, rect.y() + 30)
            right = pixel(rect.right() - 30, rect.y() + 30)
            assert left.red() > 200 and right.blue() > 200  # Filled background, not letterboxing.
            blurred = pixel(rect.center().x(), rect.y() + 30)
            assert blurred.red() > 20 and blurred.blue() > 20
            image.fill(QColor("green"))
            sink.setVideoFrame(QVideoFrame(image))
            QTest.qWait(150)
            shot = window.grabWindow()
            assert pixel(rect.center().x(), rect.y() + 30).green() > 100  # Paused-frame refresh.
        frame.setProperty("outputFormat", "keep_ratio")
        QTest.qWait(40)
        assert frame.property("contentRect").width() / frame.property("contentRect").height() == 640 / 360
        frame.setProperty("outputFormat", "tiktok_9_16_crop")
        QTest.qWait(30)
        assert abs(frame.property("contentRect").width() / frame.property("contentRect").height() - 9 / 16) < .00001
        assert sink.videoFrame().isValid()
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        temporary.cleanup()


def test_live_frame_and_toolbar_in_isolated_qt_process():
    result = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_panel_no_longer_contains_output_framing():
    panel = (QML_DIR / "ManualSourceToolPanel.qml").read_text(encoding="utf-8")
    assert "OutputFrameSettings" not in panel and "outputFormat" not in panel
    workspace = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
    assert "onOutputFormatEdited:" in workspace and "resultOutputFormat:" in workspace


def test_initial_manual_frame_does_not_wait_for_preview_cache_to_apply_ratio():
    workspace = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
    assert '|| (String(AppController.editorPreviewSource || "").length === 0 && !root.hasTimelineOutput)' in workspace
    assert 'Number(root.previewMedia.outputSpeed || 1) === 1' in workspace
    assert 'resultThumbnailOutputFormat: String(root.previewMedia.liveOutputFormat || "keep_ratio")' in workspace
    pane = (QML_DIR / "ManualComparePreview.qml").read_text(encoding="utf-8")
    assert "showThumbnail: !pane.framePresented" in pane
    assert "thumbnailOutputFormat: pane === resultPane ? root.resultThumbnailOutputFormat" in pane


def _check_cold_ratio_switch():
    from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl
    from PySide6.QtGui import QColor, QGuiApplication, QImage
    from PySide6.QtMultimedia import QVideoFrame
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import "{QML_DIR.as_uri()}"
Window {{
    width: 1280; height: 720; visible: true
    OutputFramePreview {{ objectName: "frame"; anchors.fill: parent }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    frame = window.findChild(QObject, 'frame')
    loader = frame.findChild(QObject, 'outputBackgroundLoader')
    def ready(item):
        return QQmlExpression(engine.rootContext(), item, 'status === 1').evaluate()[0]
    image = QImage(3840, 2160, QImage.Format_RGB32)
    image.fill(QColor('green'))
    sink = frame.property('videoSink')
    sink.setVideoFrame(QVideoFrame(image))
    QTest.qWait(60)
    try:
        assert not loader.property('active')
        start = time.perf_counter()
        frame.setProperty('outputFormat', 'blur_background_9_16')
        for _ in range(100):
            app.processEvents()
            if ready(loader):
                break
            QTest.qWait(10)
        assert ready(loader)
        cold_ms = (time.perf_counter() - start) * 1000
        item = loader.property('item')
        assert item is not None
        capture = item.findChild(QObject, 'outputBackgroundCapture')
        size = capture.property('textureSize')
        assert 0 < size.width() <= 960 and 0 < size.height() <= 540
        assert size.width() * size.height() <= 960 * 540
        assert not capture.property('live')
        assert frame.property('videoSink') is sink  # No decoder/sink replacement.
        QTest.qWait(120)
        if os.environ.get('HFLOW_FRAME_PIXEL_QA') == '1':
            shot = window.grabWindow()
            assert not shot.isNull()
            QTest.qWait(30)
            prerequisite = item.findChild(QObject, 'outputBlurPrerequisite')
            effect_loader = item.findChild(QObject, 'outputBlurEffectLoader')
            assert ready(prerequisite) and ready(effect_loader)
            effect = item.findChild(QObject, 'outputBackgroundBlur')
            assert effect.property('blur') == 1 and 16 < effect.property('blurMax') <= 64
            # The source picture only occupies the middle of the portrait
            # canvas. Green here must come from the actual GPU background.
            color = shot.pixelColor(shot.width() // 2, round(50 * shot.height() / window.height()))
            assert color.green() > 80, color.name()
        # Toggle before incubation completes, including hidden/reopened panes.
        for index in range(60):
            frame.setProperty('outputFormat', 'keep_ratio')
            frame.setProperty('outputFormat', 'blur_background_9_16')
            frame.setProperty('visible', index % 3 != 0)
            window.setWidth(1200 + index % 5 * 10)
            sink.setVideoFrame(QVideoFrame(image))
            frame.setProperty('outputFormat', 'tiktok_9_16_crop')
            frame.setProperty('outputFormat', 'blur_background_9_16')
            QTest.qWait(2)
        frame.setProperty('visible', True)
        QTest.qWait(120)
        assert ready(loader) and sink.videoFrame().isValid()
        item = loader.property('item')
        prerequisite = item.findChild(QObject, 'outputBlurPrerequisite')
        effect_loader = item.findChild(QObject, 'outputBlurEffectLoader')
        assert ready(prerequisite) and ready(effect_loader)
        # A missing/unready internal component must never enter the unchecked
        # native MultiEffect initialization path; the decoder remains valid.
        prerequisite.setProperty('source', QUrl('qrc:/data/missing-blur-test.qml'))
        QTest.qWait(30)
        assert not effect_loader.property('active') and effect_loader.property('item') is None
        capture = item.findChild(QObject, 'outputBackgroundCapture')
        assert capture.property('visible')
        if os.environ.get('HFLOW_FRAME_PIXEL_QA') == '1':
            shot = window.grabWindow()
            color = shot.pixelColor(shot.width() // 2, round(50 * shot.height() / window.height()))
            assert color.green() > 80, color.name()  # Pending native blur must not show black.
        assert sink.videoFrame().isValid()
        prerequisite.setProperty('source', QUrl('qrc:/data/BlurItem.qml'))
        QTest.qWait(120)
        assert ready(prerequisite) and ready(effect_loader)
        frame.setProperty('outputFormat', 'keep_ratio')
        QTest.qWait(30)
        assert not loader.property('active') and loader.property('item') is None
        print(f'Cold 4K ratio switch: {cold_ms:.1f} ms; 60 rapid switches survived')
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_first_ratio_switch_and_rapid_teardown_in_cold_qt_process():
    env = {**os.environ, 'QML_DISABLE_DISK_CACHE': '1'}
    result = subprocess.run([sys.executable, '-X', 'faulthandler', str(Path(__file__).resolve()), '--cold'],
                            env=env, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '60 rapid switches survived' in result.stdout
    assert 'Component is not ready' not in result.stderr


def test_original_background_waits_for_native_blur_component_before_creation():
    preview = (QML_DIR / 'OutputFramePreview.qml').read_text(encoding='utf-8')
    background = (QML_DIR / 'OutputFrameBackground.qml').read_text(encoding='utf-8')
    assert 'MultiEffect' in background and 'blurMax: root.blurRadius' in background
    assert 'source: "qrc:/data/BlurItem.qml"' in background
    assert 'blurPrerequisite.status === Loader.Ready' in background
    assert 'asynchronous: false' in preview and 'interval: 33' in background
    assert 'asynchronous: true' in background
    assert 'visible: !root.blurReady' in background
    assert 'onLoaded: root.requestRefresh()' in background


if __name__ == "__main__":
    if '--cold' in sys.argv:
        _check_cold_ratio_switch()
    else:
        _check_live_frame_ui()
