"""Native mouse/keyboard coverage for the shared watermark controls."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["manual", "auto"])
def test_watermark_motion_checkbox_edits_without_breaking_binding(mode):
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), mode], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def exercise(mode):
    from PySide6.QtCore import QByteArray, QObject, QPoint, QPointF, Qt, QUrl
    from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication, QImage
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])
    for name in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    controller = QQmlPropertyMap()
    defaults = dict(selectedVideoId="test", watermarkKind="text", watermarkText="HONGNGUYENKY",
                    watermarkImagePath="", watermarkVideoPath="", watermarkImageSource=QUrl(),
                    watermarkVideoSource=QUrl(), videoThumbnailSource=QUrl(), canEditSelectedVideo=True,
                    watermarkFontFamily="Arial", watermarkTextColor="#FFFFFF", watermarkBold=True,
                    watermarkItalic=True, watermarkScalePercent=100, watermarkOpacityPercent=46,
                    watermarkOutlinePercent=100, watermarkMoving=True, watermarkPosition={})
    for key, value in defaults.items():
        controller.insert(key, value)
    image_path = Path(__file__).parents[1] / "build" / "watermark-position-source.png"
    source = QImage(1080, 1920, QImage.Format_RGB32)
    source.fill(QColor("#485461"))
    assert source.save(str(image_path))
    controller.insert("videoThumbnailSource", QUrl.fromLocalFile(str(image_path)))
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("AppController", controller)
    warnings = []
    engine.warnings.connect(lambda values: warnings.extend(value.toString() for value in values))
    qml = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
    component = QQmlComponent(engine)
    content = '''
        import QtQuick
        import QtQuick.Controls.Basic
        import "."
        ApplicationWindow {
            id: window
            width: 1100; height: 800
            visible: true
            color: Theme.window
            property int saves: 0
            QtObject {
                id: inspector
                property bool editable: true
                property bool taskQueued: false
                function scheduleSave() { window.saves++; }
                function saveNow() { window.saves++; }
            }
            ManualWatermarkToolPanel {
                visible: MODE === "manual"
                x: 24; y: 24; width: 320
                inspector: inspector
            }
            WatermarkTransformOverlay {
                visible: MODE === "manual"
                x: 370; y: 24; width: 600; height: 700
                videoRect: Qt.rect(0, 0, width, height)
                watermarkText: AppController.watermarkText
                moving: AppController.watermarkMoving
                position: AppController.watermarkPosition
                interactive: true
                editing: true
                onPositionCommitted: function(value) {
                    AppController.watermarkPosition = value;
                    AppController.watermarkMoving = false;
                    window.saves++;
                }
            }
            AutoWatermarkPreviewDialog {
                id: dialog
                objectName: "watermarkDialog"
                onWatermarkSettingsEdited: window.saves++
            }
            Component.onCompleted: if (MODE === "auto") dialog.openForSelectedVideo()
        }
    '''.replace("MODE", '"' + mode + '"')
    component.setData(QByteArray(content.encode()), QUrl.fromLocalFile(str(qml / "WatermarkMotionTest.qml")))
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert window is not None
    QTest.qWait(100)
    owner = window if mode == "manual" else window.findChild(QObject, "watermarkDialog")
    checkbox = owner.findChild(QQuickItem, mode + "WatermarkMovingCheckBox")
    assert checkbox and checkbox.isVisible() and checkbox.property("checked") is True
    assert checkbox.property("text") == "Di chuyển"
    point = checkbox.mapToScene(QPointF(10, checkbox.height() / 2))
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
    QTest.qWait(20)
    assert controller.value("watermarkMoving") is False
    assert window.property("saves") == 1
    checkbox.forceActiveFocus()
    QTest.keyClick(window, Qt.Key_Space)
    QTest.qWait(20)
    assert controller.value("watermarkMoving") is True
    assert window.property("saves") == 2
    controller.insert("watermarkMoving", False)
    QTest.qWait(20)
    assert checkbox.property("checked") is False  # Project changes still update it after interaction.
    assert window.property("saves") == 2  # Loading a project must not write its settings back.
    controller.insert("watermarkMoving", True)
    QTest.qWait(20)
    mark = next((item for item in owner.findChildren(QQuickItem, "watermarkTransformMark") if item.isVisible()), None)
    assert mark and mark.isVisible()
    point = mark.mapToScene(QPointF(mark.width() / 2, mark.height() / 2))
    start = QPoint(round(point.x()), round(point.y()))
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(window, QPoint(start.x() + 50, start.y() - 80), 20)
    assert window.property("saves") == 2  # Pointer movement is a local draft, not repeated writes.
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(start.x() + 50, start.y() - 80))
    QTest.qWait(20)
    assert window.property("saves") == 3
    assert controller.value("watermarkMoving") is False and checkbox.property("checked") is False
    position = controller.value("watermarkPosition")
    if hasattr(position, "toVariant"):
        position = position.toVariant()
    assert 0 <= position["x_percent"] <= 100 and 0 <= position["y_percent"] <= 100
    if mode == "auto":
        controller.insert("canEditSelectedVideo", False)
        QTest.qWait(20)
        assert not checkbox.isEnabled()
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(window, QPoint(start.x() + 30, start.y() - 30), 20)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(start.x() + 30, start.y() - 30))
        assert window.property("saves") == 3
    assert not warnings, warnings
    target = Path(__file__).parents[1] / "build" / ("watermark-motion-" + mode + ".png")
    window.grabWindow().save(str(target))
    window.close()
    del window, component
    engine.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    exercise(sys.argv[1])
