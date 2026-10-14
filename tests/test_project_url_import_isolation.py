"""Same remote link belongs independently to each project's import session."""
import queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PySide6.QtGui import QGuiApplication

from hflow.desktop.project_commands_controller import ProjectCommandsController
from hflow.desktop.project_import_controller import ProjectImportController
from hflow.desktop.url_import import ProjectUrlImportRegistry
from hflow.schemas.video import VideoConfig, VideoInfo

_APP = None
URL = 'https://www.douyin.com/video/7684852132029539323'
METADATA = dict(url=URL, title='Same source', platform='Douyin', duration_seconds=10,
                thumbnail_url='', uploader='Creator')


@pytest.fixture(scope='module', autouse=True)
def application():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    yield _APP


def test_same_douyin_link_is_independent_while_other_project_is_downloading():
    ready, finished = Mock(), Mock()
    registry = ProjectUrlImportRegistry(None, None, ready, finished)
    first, second = registry.for_project('ff'), registry.for_project('auto')
    try:
        first._handle_metadata(first._generation, METADATA)
        first._state, first._progress = 'downloading', 20
        first.import_target = {'project_key': 'ff'}
        second.begin('single')
        assert not second.busy and second.url == '' and second.progress == 0
        with patch.object(second, '_start_worker'):
            second.inspect(URL)
        assert second.state == 'inspecting' and first.state == 'downloading'
        second._handle_metadata(second._generation, METADATA)
        assert second.state == 'ready' and second.title == first.title
        second._state = 'downloading'
        second.cancel()
        assert not first._cancel_event.is_set()
        first._handle_download(first._generation, 'fixture.mp4', '')
        ready.assert_called_once_with(first, 'fixture.mp4', '', 'single')
        first.complete_import(True)
        finished.assert_called_once_with(first)
        assert second.state == 'cancelling'
    finally:
        registry.shutdown()


def test_async_storage_completion_targets_original_project_and_coordinator():
    registry = ProjectUrlImportRegistry(None, None, Mock(), Mock())
    first, second = registry.for_project('ff'), registry.for_project('auto')
    video = VideoInfo(**VideoConfig(project_key='ff').model_dump(), video_id='owner-video', original_filename='old.mp4',
                      created_at='', updated_at='', status='done')
    first.import_target = {'project_key': 'ff', 'selected_video_id': video.video_id}
    first._state, second._state = 'importing', 'inspecting'
    host = SimpleNamespace(_selected_project_key='auto', _selected_video_id='other-video',
        _url_importer=second, _media_import_busy=False, _media_import_total=0,
        _media_import_events=queue.Queue(), mediaImportChanged=Mock(),
        _processing_queue=SimpleNamespace(active_video_id='', discard=lambda _: False), refreshVideos=Mock())
    controller = ProjectImportController(host)
    try:
        with patch('hflow.desktop.project_import_controller.video_store.get_video', return_value=video), \
                patch('hflow.desktop.project_import_controller.threading.Thread'):
            controller.handle_url_download_ready('fixture.mp4', '', 'single', importer=first)
        context = controller._tasks[1]
        assert context['project_key'] == 'ff' and context['url_importer'] is first
        assert first.import_target is None
        controller._apply_finished_import(context, [], ['fixture failure'])
        assert first.state == 'error' and second.state == 'inspecting'
    finally:
        registry.shutdown()


def test_deleting_background_owner_cannot_cancel_current_project_import():
    registry = ProjectUrlImportRegistry(None, None, Mock(), Mock())
    first, second = registry.for_project('ff'), registry.for_project('auto')
    first.import_target = {'project_key': 'ff'}
    first._state, second._state = 'downloading', 'inspecting'
    host = SimpleNamespace(_project_url_imports=registry, _url_importer=second)
    try:
        assert ProjectCommandsController(host)._stop_project_url_download('ff')
        assert first.import_target is None and not first.busy
        assert second.state == 'inspecting' and not second._cancel_event.is_set()
        assert registry.busy
        registry.shutdown()
        assert not second.busy
    finally:
        registry.shutdown()


@pytest.mark.parametrize('replacing', [False, True])
def test_late_music_download_cannot_attach_to_replaced_source(tmp_path, replacing):
    current = VideoInfo(**VideoConfig(project_type='manual').model_dump(), video_id='owner-video',
        original_filename='new.mp4', created_at='new', updated_at='', status='pending', manual_tool_generations={'source': 2})
    host = SimpleNamespace(_background_music_import_busy=True, backgroundMusicImportChanged=Mock())
    controller = ProjectImportController(host)
    controller._background_music_task = dict(task_id='music', target='video', video_id=current.video_id,
        source_generation=1, source_created_at='old')
    if replacing:
        controller._tasks[1] = dict(operation='replace', video_id=current.video_id)
    temporary = tmp_path / 'download'
    temporary.mkdir()
    with patch('hflow.desktop.project_import_controller.video_store.get_video', return_value=current), \
            patch('hflow.desktop.project_import_controller.set_desktop_background_music') as apply:
        controller._finish_background_music_download(dict(task_id='music', error='',
            path=str(temporary / 'music.wav'), temporary_directory=str(temporary)))
    apply.assert_not_called()
    assert 'nhập lại nhạc nền' in host._background_music_import_status
    assert not temporary.exists() and not host._background_music_import_busy


def _check_url_dialog_isolation():
    from pathlib import Path
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression, QQmlPropertyMap
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from hflow.desktop.douyin_session_controller import DouyinSessionController

    app = QGuiApplication.instance() or QGuiApplication([])
    owner = QQmlPropertyMap()
    session = DouyinSessionController()
    current = ['ff']
    registry = ProjectUrlImportRegistry(None, None, Mock(),
        lambda importer: finished.append(importer) if importer is registry.for_project(current[0]) else None)
    finished = []
    first, second = registry.for_project('ff'), registry.for_project('auto')
    first._handle_metadata(first._generation, METADATA)
    first._state, first._progress = 'downloading', 20
    owner.insert('urlImporter', first)
    owner.insert('douyinSession', session)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty('AppController', owner)
    qml = Path(__file__).parents[1] / 'src/hflow/desktop/qml'
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import "{qml.as_uri()}"
Window {{ width: 1000; height: 800; visible: true
    UrlImportDialog {{ objectName: "dialog" }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    dialog = window.findChild(QObject, 'dialog')
    try:
        QQmlExpression(engine.rootContext(), dialog, 'openForMode("single")').evaluate()
        QTest.qWait(220)
        assert dialog.property('inspectedText') == URL
        assert dialog.property('importer') is first
        dialog.close()
        QTest.qWait(220)
        current[0] = 'auto'
        owner.insert('urlImporter', second)
        QQmlExpression(engine.rootContext(), dialog, 'openForMode("single")').evaluate()
        QTest.qWait(220)
        assert dialog.property('importer') is second
        assert dialog.property('inspectedText') == '' and not second.busy
        first.complete_import(True)
        assert finished == [] and dialog.property('visible')
    finally:
        dialog.close()
        window.close()
        window.deleteLater()
        app.processEvents()
        registry.shutdown()


def test_url_dialog_does_not_inherit_busy_state_and_can_reopen_own_task():
    import subprocess
    import sys
    from pathlib import Path
    runner = f"import runpy; runpy.run_path({str(Path(__file__).resolve())!r})['_check_url_dialog_isolation']()"
    result = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', runner],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
