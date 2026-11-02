"""Option changes do not perform resource scans or rebuild unrelated media UI."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QSignalSpy, QTest

from haizflow.desktop.audio_preview_controller import AudioPreviewController
from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
from haizflow.desktop.manual_tool_state_controller import ManualToolStateController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.resource_pack_controller import ResourcePackController
from haizflow.desktop.translation_api_controller import TranslationApiController

_APP = None


def app():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    return _APP


def test_resource_option_status_reads_inventory_only():
    resources = ResourcePackController.__new__(ResourcePackController)
    resources.model = SimpleNamespace(_operation_state={}, _snapshots={"model": {"status": "installed"}})
    resources.manager = SimpleNamespace(status=Mock(side_effect=AssertionError("GUI disk scan")))
    for _ in range(100):
        assert resources.status_for_ui("model") == "installed"
    resources.model._operation_state["model"] = {"status": "removing"}
    assert resources.status_for_ui("model") == "removing"
    assert resources.status_for_ui("unknown") == "inventory"


def test_recognition_option_does_not_verify_large_models_on_ui_thread():
    host = SimpleNamespace(_settings_processing_device="cpu", _speech_recognition_model="small-gpu",
        _resource_packs=SimpleNamespace(status_for_ui=Mock(return_value="installed"),
            manager=SimpleNamespace(status=Mock(side_effect=AssertionError("GUI integrity verification")))),
        _show_app_alert=Mock(), speechRecognitionModelChanged=Mock())
    HaizFlowController.speechRecognitionModel.fset(host, "small-cpu")
    assert host._speech_recognition_model == "small-cpu"
    host.speechRecognitionModelChanged.emit.assert_called_once()
    host._show_app_alert.assert_not_called()


def test_known_manual_language_never_copies_all_subtitle_rows():
    class Subtitles:
        @property
        def segments(self):
            raise AssertionError("Unrelated full subtitle copy")

    host = SimpleNamespace(_project_type="manual", _target_language="zh", _manual_subtitles=Subtitles(),
        _selected_video=lambda: SimpleNamespace(video_id="manual", subtitle_language="vi"))
    assert HaizFlowController._selected_voice_language(host) == "vi"


def test_unavailable_library_sample_never_rereads_project_per_voice(monkeypatch):
    preview = AudioPreviewController(SimpleNamespace())
    monkeypatch.setattr(preview, "_packaged_sample_path", lambda *args: "")
    monkeypatch.setattr("haizflow.desktop.audio_preview_controller.video_store.get_video",
        Mock(side_effect=AssertionError("Per-library-voice project disk read")))
    for index in range(100):
        assert not preview.has_voice_sample("omnivoice", f"voice-{index}", "ja", selected_video_id="project")


def test_metadata_refresh_updates_ocr_without_resetting_document_or_timeline(monkeypatch):
    app()
    editor = ManualEditorDocumentModel()
    editor._video_id = "manual"
    full_changes, clip_changes = QSignalSpy(editor.changed), QSignalSpy(editor.clipsChanged)
    ocr_changes = QSignalSpy(editor.ocrLayersChanged)
    host = SimpleNamespace(_selected_video_id="manual", _manual_editor_document=editor)
    monkeypatch.setattr("haizflow.desktop.qml_controller.video_store.get_video",
        lambda _: SimpleNamespace(video_id="manual"))
    for _ in range(100):
        HaizFlowController._refresh_selected_video_snapshot(host)
    assert full_changes.count() == clip_changes.count() == 0
    assert ocr_changes.count() == 100
    editor.changed.emit()
    assert clip_changes.count() == 1 and ocr_changes.count() == 101
    editor.close()


def test_reasoning_reuses_metadata_but_invalidates_after_changes(monkeypatch):
    app()
    host = QObject()
    api = TranslationApiController(host)
    calculate = Mock(return_value={"values": ["low", "high"], "default": "low"})
    monkeypatch.setattr("haizflow.services.translation_api_policy.project_configuration", calculate)
    for _ in range(100):
        assert api.reasoningConfiguration("model", "", False)["default"] == "low"
    assert calculate.call_count == 1
    api.changed.emit()
    api.reasoningConfiguration("model", "", False)
    assert calculate.call_count == 2
    api.catalogChanged.emit()
    api.reasoningConfiguration("model", "", False)
    assert calculate.call_count == 3


def test_slow_tool_state_refresh_keeps_event_loop_live_and_coalesces_old_requests(monkeypatch):
    app()
    entered, release = threading.Event(), threading.Event()
    calls = []
    ui_thread = threading.get_ident()

    def calculate(video, *, language):
        assert threading.get_ident() != ui_thread
        calls.append(video.video_id)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return [{"label": video.video_id, "state": language}]

    monkeypatch.setattr("haizflow.pipeline.manual_tools.tool_states", calculate)
    model = ManualToolStateController()
    ticks = []
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    try:
        for index in range(100):
            video = SimpleNamespace(video_id=str(index), project_type="manual", status="manual_ready")
            model.request(video, "vi")
        assert entered.wait(5)
        QTest.qWait(30)
        assert entered.is_set() and ticks and model.rows == []
        release.set()
        deadline = time.monotonic() + 5
        while model.rows != [{"label": "99", "state": "vi"}] and time.monotonic() < deadline:
            QTest.qWait(10)
        assert model.rows == [{"label": "99", "state": "vi"}]
        assert calls == ["0", "99"]
        model.request(None, "vi")
        assert model.rows == []
    finally:
        release.set()
        timer.stop()
        model.close()


def test_tool_state_errors_and_close_do_not_leave_queue_stuck(monkeypatch):
    app()
    calculate = Mock(side_effect=ValueError("missing artifact"))
    monkeypatch.setattr("haizflow.pipeline.manual_tools.tool_states", calculate)
    model = ManualToolStateController()
    model.request(SimpleNamespace(video_id="bad", project_type="manual", status="manual_ready"), "vi")
    deadline = time.monotonic() + 5
    while model._busy and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not model._busy
    model.close()
    model.request(SimpleNamespace(video_id="closed"), "vi")
    assert calculate.call_count == 1


def test_close_drops_pending_state_without_waiting_for_disk_worker(monkeypatch):
    app()
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def calculate(video, *, language):
        entered.set()
        try:
            assert release.wait(5)
            return [{"label": video.video_id}]
        finally:
            finished.set()

    monkeypatch.setattr("haizflow.pipeline.manual_tools.tool_states", calculate)
    model = ManualToolStateController()
    spy = QSignalSpy(model.changed)
    model.request(SimpleNamespace(video_id="first", project_type="manual", status="manual_ready"), "vi")
    assert entered.wait(5)
    model.request(SimpleNamespace(video_id="pending", project_type="manual", status="manual_ready"), "vi")
    try:
        model.close()  # Must return while the worker is still blocked.
        assert not finished.is_set() and model._pending is None
    finally:
        release.set()
        assert finished.wait(5)
        QTest.qWait(10)
    assert spy.count() == 0 and model.rows == []


def test_tool_state_preserves_real_queue_and_corrects_only_phantom_running_snapshot(monkeypatch):
    from haizflow.schemas.video import VideoInfo

    app()
    video = VideoInfo.model_construct(video_id="manual", project_type="manual", status="processing",
                                      manual_target_tool="voice")
    monkeypatch.setattr("haizflow.pipeline.manual_tools.tool_states",
        lambda item, **kwargs: [{"state": item.status, "tool": item.manual_target_tool}])
    model = ManualToolStateController()
    try:
        for queued, expected in [(False, {"state": "manual_ready", "tool": ""}),
                                 (True, {"state": "processing", "tool": "voice"})]:
            model.request(video, "vi", queued)
            deadline = time.monotonic() + 5
            while model._busy and time.monotonic() < deadline:
                QTest.qWait(10)
            assert model.rows == [expected]
            assert video.status == "processing" and video.manual_target_tool == "voice"
    finally:
        model.close()
