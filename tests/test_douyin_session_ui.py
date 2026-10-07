import os
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap

from haizflow.desktop.douyin_session_controller import DouyinSessionController


def test_session_action_loads_without_launching_browser_and_shows_cancel_only_when_busy():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    session = DouyinSessionController()
    owner = QQmlPropertyMap()
    owner.insert("douyinSession", session)
    engine.rootContext().setContextProperty("AppController", owner)
    component = QQmlComponent(engine)
    file = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml/DouyinSessionAction.qml"
    with patch("haizflow.services.douyin_adapter.get_douyin_adapter") as adapter:
        component.loadUrl(QUrl.fromLocalFile(str(file)))
        assert component.isReady(), "\n".join(e.toString() for e in component.errors())
        # Inject before bindings initialize: another suite may have registered
        # the real AppController singleton, which takes precedence over context.
        root = component.createWithInitialProperties({"session": session})
        assert root is not None
        try:
            root.setProperty("width", 500)
            app.processEvents()
            buttons = [obj for obj in root.findChildren(QObject) if obj.property("variant") == "secondary"
                       and obj.property("text") in {"Tạo phiên Douyin", "Hủy"}]
            assert len(buttons) == 2
            cancel = next(obj for obj in buttons if obj.property("text") == "Hủy")
            create = next(obj for obj in buttons if obj.property("text") == "Tạo phiên Douyin")
            assert not cancel.property("visible") and create.property("enabled")
            session._busy = True
            session.changed.emit()
            app.processEvents()
            assert cancel.property("visible") and not create.property("enabled")
            assert create.property("text") == "Đang tạo phiên…"
            session._set_status("Complete verification in the Douyin window.")
            app.processEvents()
            texts = [obj.property("text") for obj in root.findChildren(QObject)]
            # I18n defaults to English in this isolated component test.
            assert "Complete verification in the Douyin window." in texts
            session._complete("Douyin session ready")
            app.processEvents()
            assert session.ready and create.property("text") == "Làm mới phiên"
            adapter.assert_not_called()
        finally:
            root.deleteLater()
            app.processEvents()


def test_controller_does_not_accept_duplicate_create_requests():
    app = QGuiApplication.instance() or QGuiApplication([])
    session = DouyinSessionController()
    with patch("haizflow.desktop.douyin_session_controller.threading.Thread") as thread:
        thread.return_value = Mock()
        session.create()
        session.create()
        assert session.busy
        thread.assert_called_once()
        session.cancel()
        assert session._cancel.is_set()
        session._complete("Douyin session cancelled")
        assert not session.busy
    app.processEvents()


def test_failed_repeated_refresh_retains_readiness_and_real_request_clears_warning():
    QGuiApplication.instance() or QGuiApplication([])
    session = DouyinSessionController()
    session._complete("Douyin session ready")
    with patch("haizflow.desktop.douyin_session_controller.threading.Thread"):
        for _ in range(3):
            session.create()
            assert session.busy and session.ready
            session._complete("The Douyin browser session could not complete the request.")
            assert session.ready and not session.busy
            assert session.status == "Douyin refresh failed; previous session retained"
    session._set_status("Douyin request succeeded")
    assert session.ready and session.status == "Douyin session ready"


def test_initial_failure_is_not_presented_as_a_ready_session():
    QGuiApplication.instance() or QGuiApplication([])
    session = DouyinSessionController()
    with patch("haizflow.desktop.douyin_session_controller.threading.Thread"):
        session.create()
        session._set_status("Douyin session ready")  # SDK probe, not committed refresh
        assert not session.ready
        session._complete("The Douyin browser session could not complete the request.")
    assert not session.ready
    assert session.status == "The Douyin browser session could not complete the request."


def test_successful_request_is_not_overwritten_by_late_refresh_failure():
    QGuiApplication.instance() or QGuiApplication([])
    session = DouyinSessionController()
    with patch("haizflow.desktop.douyin_session_controller.threading.Thread"):
        session.create()
        session._set_status("Douyin request succeeded")
        session._complete("The Douyin browser session could not complete the request.")
    assert session.ready and session.status == "Douyin session ready"


def test_cancelled_refresh_retains_previous_session_but_initial_cancel_does_not():
    QGuiApplication.instance() or QGuiApplication([])
    for was_ready in (False, True):
        session = DouyinSessionController()
        if was_ready:
            session._complete("Douyin session ready")
        with patch("haizflow.desktop.douyin_session_controller.threading.Thread"):
            session.create()
            session.cancel()
            session._complete("Douyin session cancelled")
        assert session.ready == was_ready
        assert session.status == ("Douyin refresh cancelled; previous session retained" if was_ready
                                  else "Douyin session cancelled")
