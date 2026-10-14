import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

from hflow.desktop.qml_controller import HFlowController


def host(project="project-a", video="video-a"):
    return SimpleNamespace(
        _selected_project_key=project, _selected_video_id=video,
        _project_session_notices=set(), _show_app_alert=Mock(),
    )


def show(value, key="gemini-cost"):
    return HFlowController.showProjectSessionAlertOnce(value, key, "Gemini", "Billing", "information")


def test_gemini_cost_notice_is_shared_across_models_and_reopening_project():
    value = host()
    assert show(value)
    assert not show(value)  # Same or different Gemini option, same category.
    value._selected_video_id = "another-video-in-project"
    assert not show(value)
    value._selected_project_key = "project-b"
    assert show(value)
    value._selected_project_key = "project-a"
    assert not show(value)
    assert value._show_app_alert.call_count == 2
    assert show(host())  # New app session, no persisted suppression.


def test_setup_and_legacy_video_contexts_have_bounded_independent_notices():
    value = host("", "")
    assert show(value)
    assert not show(value)
    value._selected_video_id = "legacy-video"
    assert show(value)
    assert not show(value)
    assert not show(value, "")
    assert show(value, "different-notice")


def test_normal_error_alerts_and_missing_key_reminders_are_not_suppressed():
    value = host()
    show(value)
    for _ in range(2):
        HFlowController.showAppAlert(value, "Gemini error", "Retry", "critical")
    assert value._show_app_alert.call_count == 3
    value._settings_language = "vi"
    value.appAlertRequested = Mock()
    for _ in range(2):
        HFlowController.requestGeminiSetup(value)
    assert value.appAlertRequested.emit.call_count == 2


def test_production_model_combo_routes_all_gemini_choices_to_shared_session_notice():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])
    value = host()

    class Controller(QObject):
        @Slot(str, str, str, str, result=bool)
        def showProjectSessionAlertOnce(self, key, title, message, severity):
            return HFlowController.showProjectSessionAlertOnce(value, key, title, message, severity)

    controller = Controller()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("TestController", controller)
    qml = Path(__file__).resolve().parents[1] / "src/hflow/desktop/qml/TranslationModelCombo.qml"
    component = QQmlComponent(engine)
    # The registered AppController singleton shadows a same-named context
    # property. Inject only its symbol, retaining the production combo logic.
    component.setData(qml.read_text(encoding="utf-8").replace(
        "AppController.", "TestController.",
    ).encode(), QUrl.fromLocalFile(str(qml)))
    assert component.isReady(), "\n".join(error.toString() for error in component.errors())
    combo = component.create()
    assert combo is not None
    app.processEvents()
    combo.edited.connect(lambda model: combo.setProperty("selectedModel", model))
    try:
        for index in (2, 3, 0, 2, 3):
            combo.setProperty("currentIndex", index)
            app.processEvents()
            combo.activated.emit(index)
        assert value._show_app_alert.call_count == 1
        assert value._show_app_alert.call_args.args[0] == "Chi phí Gemini"
        value._selected_project_key = "project-b"
        combo.setProperty("currentIndex", 2)
        combo.activated.emit(2)
        assert value._show_app_alert.call_count == 2
    finally:
        combo.deleteLater()
        engine.deleteLater()
        app.processEvents()
