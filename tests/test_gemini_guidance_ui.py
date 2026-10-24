"""Isolated, rendered Qt checks for the optional Gemini guidance editor."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("width,height,large", [(960, 720, False), (720, 600, True)])
def test_guidance_dialog_layout_unicode_cancel_and_save(width, height, large):
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(width), str(height), str(int(large))],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr


def exercise(width, height, large, snapshot=""):
    from PySide6.QtCore import QByteArray, QObject, QPointF, Qt, QUrl
    from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    from PySide6.QtTest import QTest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])
    for name in ("SegUIVar.ttf", "SegoeIcons.ttf", "msyh.ttc"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Segoe UI Variable", 14 if large else 11))
    directory = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(item.toString() for item in messages))
    component = QQmlComponent(engine)
    component.setData(QByteArray('''
        import QtQuick
        import QtQuick.Controls.Basic
        import "."
        ApplicationWindow {
            id: testWindow
            visible: true
            color: "#11100e"
            property int saves: 0
            property int attempts: 0
            property string savedStyle: ""
            property bool allowSave: false
            property string modelName: "q4"
            property string ownerKey: "project:a"
            GeminiGuidanceButton {
                objectName: "guidanceButton"
                visible: testWindow.modelName.startsWith("gemini-")
                contextKey: testWindow.ownerKey
                instructions: "Bối cảnh hiện đại."
                glossary: "Minh: tôi – cậu."
                saveHandler: function(instructions, glossary, style) {
                    testWindow.attempts += 1;
                    testWindow.savedStyle = style;
                    return testWindow.allowSave;
                }
            }
            GeminiGuidanceDialog {
                objectName: "dialog"
                onConfirmed: function(instructions, glossary, owner, style) {
                    if (instructions === "Boi canh" && owner === "project:a") {
                        saves += 1;
                        testWindow.savedStyle = style;
                        close();
                    }
                }
            }
        }
    '''.encode("utf-8")), QUrl.fromLocalFile(str(directory / "GuidanceTestWindow.qml")))
    assert component.isReady(), [item.toString() for item in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    window.setWidth(width)
    window.setHeight(height)
    dialog = window.findChild(QObject, "dialog")
    dialog.openForGuidance("Bối cảnh hiện đại.", "王明 → Vương Minh\nLan gọi bố: con – bố.", "project:a", "balanced")
    QTest.qWait(250)
    assert 0 < dialog.property("width") <= width - 40
    assert 0 < dialog.property("height") <= height - 40
    instructions = window.findChild(QObject, "geminiInstructionsEditor")
    glossary = window.findChild(QObject, "geminiGlossaryEditor")
    save = window.findChild(QObject, "saveGeminiGuidance")
    assert instructions.property("text") == "Bối cảnh hiện đại."
    assert "Vương Minh" in glossary.property("text")
    assert instructions.property("width") > 200 and glossary.property("width") > 200
    disclosure = window.findChild(QQuickItem, "geminiGuidanceDisclosure")
    footer = window.findChild(QQuickItem, "appDialogFooter")
    assert disclosure.mapToScene(QPointF(0, disclosure.height())).y() <= footer.mapToScene(QPointF(0, 0)).y()
    style_combo = window.findChild(QQuickItem, "geminiStyleCombo")
    assert style_combo.property("count") == 4
    assert style_combo.property("currentValue") == "balanced"
    if snapshot:
        assert window.grabWindow().save(snapshot)
    instructions.setProperty("text", "x" * 4001)
    QTest.qWait(25)
    assert not save.property("enabled")
    dialog.close()
    assert window.property("saves") == 0
    dialog.openForGuidance("Boi canh", "Minh: tôi – cậu.", "project:a", "balanced")
    QTest.qWait(25)
    style_combo.forceActiveFocus()
    QTest.keyClick(window, Qt.Key_Down)
    QTest.keyClick(window, Qt.Key_Down)
    assert dialog.property("translationStyle") == "natural"
    save.clicked.emit()
    QTest.qWait(25)
    assert window.property("saves") == 1
    assert window.property("savedStyle") == "natural"
    assert not dialog.property("visible")
    # Exercise the real lazy launcher: failed persistence must keep the draft,
    # changing owner must destroy it, and a successful save must release it.
    button = window.findChild(QObject, "guidanceButton")
    assert not button.property("visible")
    window.setProperty("modelName", "gemini-3.8-flash")
    assert button.property("visible")
    button.clicked.emit()
    QTest.qWait(30)
    editor = window.findChild(QObject, "geminiGuidanceDialog")
    assert editor and editor.property("visible")
    editor.findChild(QObject, "saveGeminiGuidance").clicked.emit()
    QTest.qWait(30)
    assert window.property("attempts") == 1 and editor.property("visible")
    window.setProperty("ownerKey", "project:b")
    QTest.qWait(30)
    assert not window.findChild(QObject, "geminiGuidanceDialog")
    button.clicked.emit()
    QTest.qWait(30)
    editor = window.findChild(QObject, "geminiGuidanceDialog")
    assert editor.property("owner") == "project:b"
    window.setProperty("allowSave", True)
    editor.findChild(QObject, "saveGeminiGuidance").clicked.emit()
    QTest.qWait(30)
    assert window.property("attempts") == 2
    assert not window.findChild(QObject, "geminiGuidanceDialog")
    assert not warnings, warnings
    window.close()
    window.deleteLater()
    QTest.qWait(20)


if __name__ == "__main__":
    exercise(int(sys.argv[1]), int(sys.argv[2]), bool(int(sys.argv[3])), sys.argv[4] if len(sys.argv) > 4 else "")
