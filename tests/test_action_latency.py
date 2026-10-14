"""Button acknowledgement is immediate; model retirement stays off Qt slots."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QMetaObject, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QSignalSpy, QTest

from hflow.desktop.qml_controller import HFlowController

QML_DIR = Path(__file__).parents[1] / "src/hflow/desktop/qml"
_APP = None


def button():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "DeferredActionButton.qml")))
    component.setParent(engine)
    assert component.isReady(), [error.toString() for error in component.errors()]
    root = component.createWithInitialProperties({"readyText": "Xuất", "width": 170, "height": 42,
                                                "actionContext": {"videoId": "video-a", "preset": "source"}})
    window = QQuickWindow()
    window.resize(250, 120)
    root.setParent(window)
    root.setParentItem(window.contentItem())
    window.show()
    _APP.processEvents()
    return engine, root, window


def dispose(engine, root, window):
    window.close()
    root.setParentItem(None)
    root.deleteLater()
    window.deleteLater()
    engine.deleteLater()
    _APP.processEvents()


def test_button_acknowledges_before_dispatch_and_double_click_runs_once():
    engine, root, window = button()
    try:
        calls = QSignalSpy(root, root.metaObject().method(root.metaObject().indexOfSignal("execute(QVariant)")))
        assert calls.isValid()
        QMetaObject.invokeMethod(root, "clicked", Qt.DirectConnection)
        assert root.property("preparing")
        assert not root.property("enabled")
        assert "chuẩn bị" in root.property("text")
        assert calls.count() == 0
        QMetaObject.invokeMethod(root, "clicked", Qt.DirectConnection)
        root.setProperty("actionContext", {"videoId": "video-b", "preset": "720p"})
        QTest.qWait(70)
        assert calls.count() == 1
        context = calls.at(0)[0]
        assert context.toVariant() == {"videoId": "video-a", "preset": "source"}
        assert not root.property("preparing") and root.property("enabled")
    finally:
        dispose(engine, root, window)


def test_hidden_or_disabled_button_drops_pending_action():
    for property_name in ("visible", "actionEnabled"):
        engine, root, window = button()
        try:
            calls = QSignalSpy(root, root.metaObject().method(root.metaObject().indexOfSignal("execute(QVariant)")))
            assert calls.isValid()
            QMetaObject.invokeMethod(root, "clicked", Qt.DirectConnection)
            root.setProperty(property_name, False)
            QTest.qWait(70)
            assert calls.count() == 0
            assert not root.property("preparing")
        finally:
            dispose(engine, root, window)


def test_queue_click_never_retires_models_or_probes_runtime(monkeypatch):
    enqueue = Mock(return_value=True)
    warmup = SimpleNamespace(foreground_work_requested=Mock(side_effect=AssertionError("GUI model retirement")))
    host = SimpleNamespace(_smart_warmup=warmup, _processing_lifecycle=SimpleNamespace(enqueue_video=enqueue))
    monkeypatch.setattr("hflow.desktop.processing_lifecycle_controller.runtime_profile",
                        Mock(side_effect=AssertionError("GUI runtime probe")))
    assert HFlowController._enqueue_video(host, "video-a")
    enqueue.assert_called_once_with("video-a")
    warmup.foreground_work_requested.assert_not_called()


def test_manual_click_only_peeks_large_published_media():
    import inspect

    source = inspect.getsource(HFlowController.runManualTool)
    assert "ensure_current_subtitle_document(video.video_id, validate=False)" in source
    assert 'manual_artifacts.peek_active(video, "tts_manifest")' in source
    assert 'manual_artifacts.active(video, "tts_manifest")' not in source
    assert "tool_states(" not in source


def test_separation_button_uses_immediate_acknowledgement_with_project_guard():
    source = (QML_DIR / "ManualSourceToolPanel.qml").read_text(encoding="utf-8")
    assert 'objectName: "manualSeparateVoiceButton"' in source
    button_source = source[source.index("    DeferredActionButton {"):]
    assert "actionEnabled:" in button_source
    assert "onExecute: context =>" in button_source
    assert "context.videoId !== AppController.selectedVideoId" in button_source
    assert 'AppController.runManualTool("separation")' in button_source


def test_translation_button_does_not_build_voice_or_export_signatures(monkeypatch):
    from hflow.pipeline import manual_tools

    for name in ("voice_signature", "audio_signature", "export_signature", "published_voice_record"):
        monkeypatch.setattr(manual_tools, name, Mock(side_effect=AssertionError("Unrelated cache computation")))
    video = SimpleNamespace(enable_audio_separation=False)
    assert manual_tools.tool_readiness(video, "translation")["canRun"]


def test_voice_button_retains_required_subtitle_guard(monkeypatch):
    from hflow.pipeline import manual_tools

    subtitles = Mock(return_value=False)
    monkeypatch.setattr(manual_tools, "_subtitle_ready", subtitles)
    state = manual_tools.tool_readiness(SimpleNamespace(), "voice")
    assert not state["canRun"] and state["blockedReason"]
    subtitles.assert_called_once()


def test_document_read_batch_reuses_only_within_one_calculation_and_detects_edits(tmp_path, monkeypatch):
    from hflow.schemas.editor import EditorDocument, EditorSequence
    from hflow.services import editor_documents

    path = tmp_path / "editor.json"
    original = EditorDocument(video_id="video-a", sequence=EditorSequence(duration_ms=60000))
    path.write_text(original.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(editor_documents, "document_path", lambda _: path)
    with editor_documents.read_batch():
        first = editor_documents.load("video-a")
        assert editor_documents.load("video-a") is first
        updated = original.model_copy(deep=True)
        updated.sequence.duration_ms = 120000
        path.write_text(updated.model_dump_json(), encoding="utf-8")
        assert editor_documents.load("video-a").sequence.duration_ms == 120000
        assert editor_documents.load("video-a") is not first
    assert editor_documents.load("video-a") is not first
    path.unlink()
    assert editor_documents.load("video-a") is None


def test_resume_restart_controls_share_immediate_acknowledgement_and_identity_guards():
    for filename, names in {
        "ManualStageInspector.qml": ["manualRestartToolButton", "manualResumeToolButton"],
        "VideoCommandBar.qml": ["autoResumeButton", "autoProcessButton"],
        "BatchPage.qml": ["batchResumeButton", "batchProcessButton"],
        "ResourcePackRow.qml": ["resourceInstallResumeButton"],
    }.items():
        source = (QML_DIR / filename).read_text(encoding="utf-8")
        for name in names:
            index = source.index(f'objectName: "{name}"')
            assert source[source.rfind("{", 0, index) - 30:index].strip().endswith("DeferredActionButton {")
            next_button = source.find("\n            }", index)
            body = source[index:next_button if next_button > index else len(source)]
            assert "actionContext:" in body and "onExecute:" in body
    manual = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
    assert "targetTool: AppController.manualTargetTool" in manual
    assert "AppController.restartManualTool(context.targetTool)" in manual


def test_restart_click_does_not_probe_the_hardware_runtime(monkeypatch):
    from hflow.desktop.project_commands_controller import ProjectCommandsController, QMessageBox
    video = SimpleNamespace(video_id="restart", status="paused")
    host = SimpleNamespace(_selected_video_id=video.video_id, _settings_owner_video_id=video.video_id,
        _processing_queue=SimpleNamespace(contains=lambda _: False), _device_switching=False,
        _apply_setup_to_video=Mock(), _enqueue_video=Mock(), selectedVideoChanged=SimpleNamespace(emit=Mock()))
    controller = ProjectCommandsController(host)
    monkeypatch.setattr(controller, "_resources_ready", lambda *_: True)
    monkeypatch.setattr("hflow.desktop.project_commands_controller.video_store.get_video", lambda _: video)
    monkeypatch.setattr("hflow.desktop.project_commands_controller.QMessageBox.question", lambda *_: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("hflow.desktop.project_commands_controller.video_store.prepare_video_restart", lambda _: video)
    monkeypatch.setattr("hflow.desktop.project_commands_controller.video_store.log_to_video", Mock())
    monkeypatch.setattr("hflow.desktop.project_commands_controller.runtime_profile", Mock(side_effect=AssertionError("GUI hardware probe")))
    controller.restart_selected_video()
    host._enqueue_video.assert_called_once_with(video.video_id)


def test_actual_auto_resume_and_restart_buttons_acknowledge_and_drop_stale_selection():
    from PySide6.QtCore import QObject
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    body = (QML_DIR / "VideoCommandBar.qml").read_text(encoding="utf-8")
    body = "\n".join(line for line in body.splitlines() if not line.startswith("import "))
    body = body.replace("AppController", "testController")
    component = QQmlComponent(engine)
    component.setData((f'''import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "{QML_DIR.as_uri()}"
ApplicationWindow {{ width: 800; height: 200; visible: true
    QtObject {{
        id: testController; objectName: "testController"
        property bool hasSelectedOutput: false
        property bool hasOpenProject: true
        property bool isSelectedVideoProcessing: false
        property bool isSelectedVideoQueued: false
        property bool hasSelectedVideo: true
        property bool videoExportBusy: false
        property string selectedVideoId: "video-a"
        property string selectedStatus: "paused"
        property string selectedElapsed: ""
        property string selectedFailureTitle: ""
        property string selectedStageLabel: ""
        property int calls: 0
        function resumeSelectedVideo() {{ calls++; }}
        function requestAutoProcessing() {{ calls++; }}
    }}
''' + body + "\n}").encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert window is not None
    try:
        control = window.findChild(QObject, "testController")
        for name in ("autoResumeButton", "autoProcessButton"):
            action = window.findChild(QObject, name)
            before = control.property("calls")
            QMetaObject.invokeMethod(action, "clicked", Qt.DirectConnection)
            assert action.property("preparing") and not action.property("enabled")
            assert control.property("calls") == before
            QMetaObject.invokeMethod(action, "clicked", Qt.DirectConnection)
            QTest.qWait(80)
            assert control.property("calls") == before + 1 and not action.property("preparing")
            QMetaObject.invokeMethod(action, "clicked", Qt.DirectConnection)
            control.setProperty("selectedVideoId", "video-b" if control.property("selectedVideoId") == "video-a" else "video-a")
            QTest.qWait(80)
            assert control.property("calls") == before + 1 and not action.property("preparing")
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        _APP.processEvents()
