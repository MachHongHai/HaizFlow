from pathlib import Path
import pytest
from PySide6.QtGui import QGuiApplication
from hflow.desktop.media_download_controller import MediaDownloadController

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
    from hflow.schemas.channel_import import ChannelImportRequest, ChannelVideoCandidate
    from hflow.services.channel_import import new_session, save_session
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
    from hflow.desktop.douyin_session_controller import DouyinSessionController
    from hflow.schemas.channel_import import ChannelImportRequest, ChannelVideoCandidate
    from hflow.services.channel_import import new_session, save_session
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
        Path(__file__).parents[1] / 'src/hflow/desktop/qml/ChannelDownloadPage.qml')))
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


def test_video_link_paste_and_typing_survive_preview_notifications(tmp_path):
    from PySide6.QtCore import QObject, Qt, QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from hflow.desktop.douyin_session_controller import DouyinSessionController

    controller = MediaDownloadController()
    controller.attach_project('a', str(tmp_path / 'first'))
    engine = QQmlEngine()
    owner = QQmlPropertyMap()
    guest = DouyinSessionController()
    owner.insert('douyinSession', guest)
    engine.rootContext().setContextProperty('AppController', owner)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(
        Path(__file__).parents[1] / 'src/hflow/desktop/qml/VideoDownloadPage.qml')))
    assert component.isReady(), [error.toString() for error in component.errors()]
    root = component.createWithInitialProperties({'downloader': controller, 'width': 780, 'height': 680})
    assert root is not None
    window = QQuickWindow()
    window.resize(780, 680)
    root.setParentItem(window.contentItem())
    window.show()
    try:
        _APP.processEvents()
        fields = [child for child in root.findChildren(QObject) if child.property('accessibleName') == 'Liên kết video']
        assert fields
        field = fields[0]
        field.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_H)
        _APP.processEvents()
        assert field.property('text') == 'h'
        assert controller.workspaceState['videoUrl'] == 'h'
        url = 'https://www.youtube.com/watch?v=abcdefghijk'
        _APP.clipboard().setText(url)
        QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClick(window, Qt.Key_V, Qt.ControlModifier)
        _APP.processEvents()
        assert field.property('text') == url
        assert controller.workspaceState['videoUrl'] == url
        cursor = field.property('cursorPosition')
        controller.changed.emit()
        _APP.processEvents()
        assert field.property('text') == url and field.property('cursorPosition') == cursor
        controller.attach_project('b', str(tmp_path / 'second'))
        _APP.processEvents()
        assert field.property('text') == ''
        controller.attach_project('a', str(tmp_path / 'first'))
        _APP.processEvents()
        assert field.property('text') == url
    finally:
        window.hide()
        root.setParentItem(None)
        root.deleteLater()
        window.deleteLater()
        _APP.processEvents()
        controller.shutdown()


@pytest.mark.parametrize('ranking', ['newest', 'popular'])
def test_channel_rescan_uses_edited_limit_without_enter(tmp_path, monkeypatch, ranking):
    from PySide6.QtCore import QObject, QPoint, Qt, QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from hflow.desktop.douyin_session_controller import DouyinSessionController
    from hflow.schemas.channel_import import ChannelVideoCandidate

    requests = []

    def scan(request, *_args):
        requests.append((request.limit, request.ranking, request.scan_scope))
        return 'YouTube', 'Creator', [ChannelVideoCandidate(
            remote_video_id=str(index), source_url=f'https://www.youtube.com/watch?v={index}',
            title=f'Video {index}', platform='YouTube', duration_seconds=60)
            for index in range(request.limit)]

    monkeypatch.setattr('hflow.desktop.channel_import.scan_channel', scan)
    controller = MediaDownloadController()
    controller.attach_project('channel-rescan', str(tmp_path))
    controller.saveWorkspaceState({'channelUrl': 'https://www.youtube.com/@creator',
                                   'platform': 'youtube', 'limit': 20,
                                   'ranking': ranking, 'scanScope': 300})
    engine = QQmlEngine()
    owner = QQmlPropertyMap()
    guest = DouyinSessionController()
    owner.insert('douyinSession', guest)
    engine.rootContext().setContextProperty('AppController', owner)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(
        Path(__file__).parents[1] / 'src/hflow/desktop/qml/ChannelDownloadPage.qml')))
    assert component.isReady(), [error.toString() for error in component.errors()]
    root = component.createWithInitialProperties({'downloader': controller, 'width': 1000, 'height': 900})
    assert root is not None
    window = QQuickWindow()
    window.resize(1000, 900)
    root.setParentItem(window.contentItem())
    window.show()

    def scan_button():
        return next(child for child in root.findChildren(QObject)
                    if child.property('text') in ('Xem trước', 'Quét lại'))

    def click(item):
        point = item.mapToScene(item.boundingRect().center())
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))

    def wait_for_count(count):
        for _ in range(100):
            _APP.processEvents()
            if not controller.channelBusy and controller.channelCandidateCount == count:
                return
            QTest.qWait(10)
        assert controller.channelCandidateCount == count

    try:
        _APP.processEvents()
        click(scan_button())
        wait_for_count(20)
        spin = next(child for child in root.findChildren(QObject)
                    if child.property('from') == 1 and child.property('to') == 100)
        input_item = spin.property('contentItem')
        for limit in (50, 10, 100):
            input_item.forceActiveFocus()
            QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
            for digit in str(limit):
                QTest.keyClick(window, getattr(Qt, f'Key_{digit}'))
            _APP.processEvents()
            assert input_item.property('text') == str(limit)
            assert controller.workspaceState['limit'] == limit
            click(scan_button())  # Do not press Enter to commit the edited number.
            wait_for_count(limit)
        scope = 300 if ranking == 'popular' else 0
        assert requests == [(limit, ranking, scope) for limit in (20, 50, 10, 100)]
        controller.attach_project('other', str(tmp_path / 'other'))
        _APP.processEvents()
        assert spin.property('value') == 20
        controller.attach_project('channel-rescan', str(tmp_path))
        _APP.processEvents()
        assert spin.property('value') == 100
        assert controller.channelCandidateCount == 100
    finally:
        window.hide()
        root.setParentItem(None)
        root.deleteLater()
        window.deleteLater()
        _APP.processEvents()
        controller.shutdown()
