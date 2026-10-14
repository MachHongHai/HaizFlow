from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication, QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap
from PySide6.QtQuick import QQuickWindow

from hflow.desktop.douyin_session_controller import DouyinSessionController
from hflow.desktop.media_download_controller import MediaDownloadController

_APP = None
URL = 'https://www.youtube.com/watch?v=abcdefghijk'
METADATA = dict(url=URL, title='Nhạc nền của video', platform='YouTube',
                duration_seconds=120, thumbnail_url='', uploader='Creator')


@pytest.fixture(scope='module', autouse=True)
def application():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    for font in ('SegUIVar.ttf', 'SegoeIcons.ttf'):
        QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts') / font))
    yield _APP


def test_audio_download_requires_matching_inspected_link(tmp_path):
    controller = MediaDownloadController()
    controller.attach_project('audio', str(tmp_path))
    try:
        with patch.object(controller, '_enqueue') as enqueue:
            controller.downloadAudio(URL)
            enqueue.assert_not_called()
            assert 'kiểm tra' in controller.status
            controller._audio_preview._handle_metadata(controller._audio_preview._generation, METADATA)
            controller.downloadAudio(URL + '&different=1')
            enqueue.assert_not_called()
            controller.downloadAudio(URL)
            assert enqueue.call_args.args[0]['kind'] == 'audio'
            controller.clearAudioPreview()
            assert not controller.audioPreviewReady
            controller.downloadAudio(URL)
            assert enqueue.call_count == 1
    finally:
        controller.shutdown()


def test_check_only_inspects_metadata_without_download_or_queue(tmp_path):
    controller = MediaDownloadController()
    controller.attach_project('audio', str(tmp_path))
    try:
        with patch.object(controller._audio_preview, 'inspect') as inspect, \
                patch.object(controller, '_enqueue') as enqueue:
            controller.inspectAudio(URL)
        inspect.assert_called_once_with(URL)
        enqueue.assert_not_called()
        assert not controller.hasWork
        assert not controller.audioPreviewReady
        assert not controller.videoPreviewReady
    finally:
        controller.shutdown()


def test_audio_checkpoint_is_separate_from_video_and_late_results_are_ignored(tmp_path):
    controller = MediaDownloadController()
    controller.attach_project('first', str(tmp_path / 'first'))
    try:
        controller.saveWorkspaceState({'audioUrl': URL})
        controller._audio_preview._handle_metadata(controller._audio_preview._generation, METADATA)
        generation = controller._audio_preview._generation
        controller.attach_project('second', str(tmp_path / 'second'))
        assert not controller.audioPreviewReady
        controller._audio_preview._handle_metadata(generation, METADATA)
        assert not controller.audioPreviewReady
        controller.attach_project('first', str(tmp_path / 'first'))
        assert controller.audioPreviewReady
        assert controller.audioPreview.title == METADATA['title']
        assert not controller.videoPreviewReady
        controller.shutdown()
        restored = MediaDownloadController()
        try:
            restored.attach_project('first', str(tmp_path / 'first'))
            assert restored.audioPreviewReady and not restored.videoPreviewReady
        finally:
            restored.shutdown()
    finally:
        controller.shutdown()


def test_cancel_audio_inspection_rejects_late_metadata_and_can_check_again(tmp_path):
    controller = MediaDownloadController()
    controller.attach_project('audio', str(tmp_path))
    try:
        with patch.object(controller._audio_preview, '_start_worker'):
            controller.inspectAudio(URL)
        assert controller.audioPreviewBusy
        generation = controller._audio_preview._generation
        controller.cancelAudioPreview()
        controller._audio_preview._handle_metadata(generation, METADATA)
        assert not controller.audioPreviewBusy and not controller.audioPreviewReady
        with patch.object(controller, '_enqueue') as enqueue:
            controller.downloadAudio(URL)
            enqueue.assert_not_called()
        with patch.object(controller._audio_preview, '_start_worker'):
            controller.inspectAudio(URL)
        controller._audio_preview._handle_metadata(controller._audio_preview._generation, METADATA)
        assert controller.audioPreviewReady
    finally:
        controller.shutdown()


def test_audio_ui_shows_check_before_download_and_invalidates_when_edited(tmp_path):
    controller = MediaDownloadController()
    controller.attach_project('audio', str(tmp_path / 'project'))
    controller.saveWorkspaceState({'audioUrl': URL, 'audioMode': 'link'})
    engine = QQmlEngine()
    owner = QQmlPropertyMap()
    guest = DouyinSessionController()
    owner.insert('douyinSession', guest)
    engine.rootContext().setContextProperty('AppController', owner)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(Path(__file__).parents[1] /
        'src/hflow/desktop/qml/AudioDownloadPage.qml')))
    assert component.isReady(), [error.toString() for error in component.errors()]
    root = component.createWithInitialProperties({'downloader': controller, 'width': 780, 'height': 680})
    assert root is not None
    window = QQuickWindow()
    window.resize(780, 680)
    root.setParentItem(window.contentItem())
    window.show()
    try:
        _APP.processEvents()
        button = root.findChild(QObject, 'audioDownloadButton')
        check = root.findChild(QObject, 'audioInspectButton')
        card = root.findChild(QObject, 'audioLinkPreview')
        assert check.property('enabled') and not button.property('enabled')
        assert not card.property('visible')
        with patch.object(controller, 'inspectAudio') as inspect:
            check.clicked.emit()
            inspect.assert_called_once_with(URL)
        controller._audio_preview._handle_metadata(controller._audio_preview._generation, METADATA)
        _APP.processEvents()
        assert button.property('enabled') and card.property('visible')
        assert card.property('title') == METADATA['title']
        with patch.object(controller, 'downloadAudio') as download:
            button.clicked.emit()
            download.assert_called_once_with(URL)
        field = next(child for child in root.findChildren(QObject)
                     if child.property('accessibleName') == 'Liên kết video')
        field.setProperty('text', URL + '&changed=1')
        field.textEdited.emit()
        _APP.processEvents()
        assert not button.property('enabled') and not card.property('visible')
        assert controller.workspaceState['audioUrl'] == URL + '&changed=1'
        capture = tmp_path / 'audio-check-preview.png'
        controller._audio_preview._handle_metadata(controller._audio_preview._generation, METADATA)
        _APP.processEvents()
        assert window.grabWindow().save(str(capture))
        import os
        if directory := os.environ.get('HFLOW_UI_CAPTURE_DIR'):
            target = Path(directory)
            target.mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(target / 'audio-check-preview.png'))
    finally:
        window.hide()
        root.setParentItem(None)
        root.deleteLater()
        window.deleteLater()
        _APP.processEvents()
        controller.shutdown()
