from pathlib import Path
import pytest
from PySide6.QtGui import QGuiApplication
from haizflow.desktop.media_download_controller import MediaDownloadController

_APP = None


@pytest.fixture(scope='module', autouse=True)
def application():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    yield _APP


def test_download_forms_preview_restore_and_project_isolation(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    controller = MediaDownloadController()
    metadata = dict(url='https://www.youtube.com/watch?v=abcdefghijk', title='Preview',
                    platform='YouTube', duration_seconds=1800, thumbnail_url='', uploader='Creator')
    controller.attach_project('a', str(first))
    controller.saveWorkspaceState(dict(page=1, videoUrl=metadata['url'], channelUrl='https://www.youtube.com/@creator',
        platform='youtube', ranking='popular', limit=20, scanScope=100, audioMode='file', cookie='secret'))
    controller._video_preview._handle_metadata(controller._video_preview._generation, metadata)
    generation = controller._video_preview._generation
    controller.attach_project('b', str(second))
    assert controller.workspaceState.get('page', 0) == 0 and not controller.videoPreviewReady
    controller._video_preview._handle_metadata(generation, metadata)
    assert not controller.videoPreviewReady
    controller.attach_project('a', str(first))
    assert controller.workspaceState['page'] == 1 and controller.videoPreviewTitle == 'Preview'
    assert controller.workspaceState['ranking'] == 'popular'
    assert 'cookie' not in Path(first, 'downloads/workspace.json').read_text()
    controller.shutdown()
    fresh = MediaDownloadController()
    try:
        fresh.attach_project('a', str(first))
        assert fresh.videoPreviewReady and fresh.workspaceState['scanScope'] == 100
        assert not fresh.hasWork
    finally:
        fresh.shutdown()


def test_legacy_channel_scan_restores_form_without_workspace_file(tmp_path):
    from haizflow.schemas.channel_import import ChannelImportRequest, ChannelVideoCandidate
    from haizflow.services.channel_import import new_session, save_session
    session = new_session('a', str(tmp_path), ChannelImportRequest(
        url='https://www.douyin.com/user/demo', platform='douyin', ranking='popular', duration_filter='all'))
    session.state = 'ready'
    session.candidates = [ChannelVideoCandidate(remote_video_id='123', source_url='https://www.douyin.com/video/123',
        title='Video', platform='Douyin')]
    save_session(session)
    controller = MediaDownloadController()
    try:
        controller.attach_project('a', str(tmp_path))
        assert controller.workspaceState['channelUrl'] == session.channel_url
        assert controller.workspaceState['platform'] == 'douyin'
        assert controller.channelCandidateCount == 1 and controller.channelPreviewReady
    finally:
        controller.shutdown()


def test_corrupt_checkpoint_is_safe(tmp_path):
    folder = tmp_path / 'downloads'
    folder.mkdir()
    (folder / 'workspace.json').write_text('{bad json')
    controller = MediaDownloadController()
    try:
        controller.attach_project('a', str(tmp_path))
        assert not controller.videoPreviewReady and not controller.hasWork
    finally:
        controller.shutdown()


def test_channel_qml_restores_visible_results_and_switches_forms(tmp_path):
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap
    from haizflow.desktop.douyin_session_controller import DouyinSessionController
    from haizflow.schemas.channel_import import ChannelImportRequest, ChannelVideoCandidate
    from haizflow.services.channel_import import new_session, save_session
    first = tmp_path / 'first'
    session = new_session('a', str(first), ChannelImportRequest(
        url='https://www.douyin.com/user/demo', platform='douyin', ranking='popular', duration_filter='all'))
    session.state = 'ready'
    session.candidates = [ChannelVideoCandidate(remote_video_id='123', source_url='https://www.douyin.com/video/123',
        title='Video', platform='Douyin')]
    save_session(session)
    controller = MediaDownloadController()
    controller.attach_project('a', str(first))
    engine = QQmlEngine()
    owner = QQmlPropertyMap()
    guest = DouyinSessionController()
    owner.insert('douyinSession', guest)
    engine.rootContext().setContextProperty('AppController', owner)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(
        Path(__file__).parents[1] / 'src/haizflow/desktop/qml/ChannelDownloadPage.qml')))
    assert component.isReady(), [error.toString() for error in component.errors()]
    root = component.createWithInitialProperties({'downloader': controller})
    assert root is not None
    try:
        _APP.processEvents()
        assert root.property('selectedPlatform') == 'douyin'
        assert root.property('matchesSource') and root.property('hasResults')
        controller.attach_project('b', str(tmp_path / 'second'))
        _APP.processEvents()
        assert root.property('selectedPlatform') == 'youtube' and not root.property('hasResults')
        controller.attach_project('a', str(first))
        _APP.processEvents()
        assert root.property('hasResults')
        fields = [child for child in root.findChildren(QObject) if child.property('accessibleName') == 'Liên kết kênh']
        assert fields and fields[0].property('text') == session.channel_url
    finally:
        root.deleteLater()
        _APP.processEvents()
        controller.shutdown()
