"""Real QML confirmation lifecycle; isolated from other Qt application tests."""

import os
import subprocess
import sys
from pathlib import Path


def test_delete_confirmation_ui():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                            capture_output=True, text=True, env=env, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    from PySide6.QtCore import QObject, QPointF, Qt, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    app = QGuiApplication([])
    engine = QQmlEngine()
    messages = []
    engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
    directory = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{directory.as_uri()}"
ApplicationWindow {{
    width: 800; height: 600; visible: true
    property int confirmations: 0
    ConfirmDialog {{
        id: dialog; objectName: "dialog"
        title: "Xóa dự án"; message: "Xóa dự án thử nghiệm?"
        closeOnConfirm: false
        onConfirmed: confirmations++
    }}
    function openDialog() {{ dialog.open(); }}
    function finishDeletion() {{ dialog.close(); }}
    function ordinaryQuestion() {{ dialog.busy = false; dialog.closeOnConfirm = true; dialog.open(); }}
}}'''.encode(), QUrl())
    assert component.isReady(), [e.toString() for e in component.errors()]
    window = component.create()
    assert window is not None

    def run(code):
        expression = QQmlExpression(engine.rootContext(), window, code)
        expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        QTest.qWait(180)

    def click(item):
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(180)

    run("openDialog()")
    dialog = window.findChild(QObject, "dialog")
    confirm = dialog.findChild(QQuickItem, "confirmationConfirmButton")
    cancel = dialog.findChild(QQuickItem, "confirmationCancelButton")
    close = dialog.findChild(QQuickItem, "appDialogCloseButton")
    assert dialog.property("visible")
    click(confirm)
    assert window.property("confirmations") == 1
    assert dialog.property("visible") and dialog.property("busy")
    assert confirm.property("text") == "Đang xóa…"
    for button in (confirm, cancel, close):
        assert not button.property("enabled")
        click(button)
    QTest.keyClick(window, Qt.Key_Escape)
    QTest.qWait(100)
    assert dialog.property("visible")
    assert window.property("confirmations") == 1
    run("finishDeletion()")
    assert not dialog.property("visible")
    run("ordinaryQuestion()")
    click(confirm)
    assert not dialog.property("visible")
    assert window.property("confirmations") == 2
    run("ordinaryQuestion()")
    click(close)
    assert not dialog.property("visible")
    assert window.property("confirmations") == 2
    assert not messages, messages
    window.close()
    window.deleteLater()
    app.processEvents()
