"""Dismissing a caller-visible warning must not leave a blank colored panel."""

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QEvent, QMetaObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

QML_DIR = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
_APP = None


@pytest.mark.parametrize("control", ["Xác nhận", "close"])
def test_dismissed_banner_collapses_with_external_visibility_binding_and_can_show_new_warning(control):
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 640; height: 500; visible: true
    property int warningCount: 2
    ColumnLayout {{
        width: 500
        InlineBanner {{
            objectName: "warningBanner"
            Layout.fillWidth: true
            visible: warningCount > 0
            tone: "warning"
            message: qsTr("Đã áp dụng bản dịch. Có %1 câu cần kiểm tra trong Phụ đề.").arg(warningCount)
        }}
        Text {{ objectName: "nextControl"; text: "Model nhận dạng" }}
    }}
}}'''.encode(), QUrl())
    assert component.isReady(), [e.toString() for e in component.errors()]
    window = component.create()
    assert window is not None
    try:
        banner = window.findChild(QObject, "warningBanner")
        following = window.findChild(QObject, "nextControl")
        QTest.qWait(30)
        before_y = following.property("y")
        assert banner.property("height") >= 52
        assert banner.property("color").alpha() > 0
        button = next(child for child in banner.findChildren(QObject)
                      if (child.property("text") == control if control == "Xác nhận"
                          else child.property("iconName") == control))
        assert QMetaObject.invokeMethod(button, "clicked")
        QTest.qWait(30)
        assert banner.property("dismissed")
        assert banner.property("height") == 0
        assert banner.property("color").alpha() == 0
        assert following.property("y") < before_y
        # This is only a dismissed notice: no subtitle warnings are accepted
        # or deleted, and the caller's count/visibility binding stays intact.
        assert window.property("warningCount") == 2
        window.setProperty("warningCount", 3)
        QTest.qWait(30)
        assert not banner.property("dismissed")
        assert banner.property("height") >= 52
        assert banner.property("color").alpha() > 0
        window.setProperty("warningCount", 0)
        QTest.qWait(30)
        assert not banner.property("visible")
    finally:
        window.close()
        window.deleteLater()
        component.deleteLater()
        engine.deleteLater()
        _APP.sendPostedEvents(None, QEvent.DeferredDelete)
        _APP.processEvents()
