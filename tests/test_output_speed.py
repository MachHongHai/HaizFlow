import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from pydantic import ValidationError

from hflow.pipeline import sequence_compiler
from hflow.desktop.qml_controller import HFlowController
from hflow.schemas.video import VideoConfig
from hflow.utils.ffmpeg import _binary, get_video_duration, get_media_stream_types

_APP = None


@pytest.fixture(scope='module', autouse=True)
def application():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    yield _APP


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'source.mp4'
    subprocess.run([_binary('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i',
        'testsrc2=size=96x64:rate=30:duration=2', '-f', 'lavfi', '-i',
        'sine=frequency=440:sample_rate=48000:duration=2', '-c:v', 'libx264',
        '-preset', 'ultrafast', '-c:a', 'aac', str(path)], check=True, capture_output=True)
    return path


@pytest.mark.parametrize('speed', [0.25, 0.5, 1, 1.25, 1.5, 2, 3])
def test_real_output_speed_keeps_audio_video_synchronized(source, tmp_path, speed):
    output = tmp_path / 'output.mp4'
    progress = []
    sequence_compiler.finish_export_resolution(str(source), str(output), 'source', 'speed-test',
                                               output_speed=speed, progress_callback=progress.append)
    assert abs(get_video_duration(str(output)) - 2 / speed) < .1
    assert set(get_media_stream_types(str(output))) >= {'video', 'audio'}
    info = json.loads(subprocess.check_output([_binary('ffprobe'), '-v', 'error', '-show_streams',
                                              '-of', 'json', str(output)]))
    lengths = [float(stream['duration']) for stream in info['streams'] if stream['codec_type'] in ('audio', 'video')]
    assert max(lengths) - min(lengths) < .1
    assert progress == sorted(progress) and progress[-1] == 1


@pytest.mark.parametrize('speed', [0, -1, 3.01, float('nan'), float('inf')])
def test_invalid_output_speed_is_rejected(speed):
    with pytest.raises(ValidationError):
        VideoConfig(output_speed=speed)


def test_default_speed_keeps_original_copy_path(tmp_path, monkeypatch):
    copy = Mock()
    monkeypatch.setattr('hflow.utils.ffmpeg.get_video_dimensions', lambda _: (96, 64))
    monkeypatch.setattr(sequence_compiler, '_copy_video', copy)
    monkeypatch.setattr(sequence_compiler, '_run', Mock(side_effect=AssertionError('Must not encode at 1x')))
    sequence_compiler.finish_export_resolution('source', str(tmp_path / 'output.mp4'), 'source', 'test')
    copy.assert_called_once()


@pytest.mark.parametrize('kind', ['manual', 'single'])
@pytest.mark.parametrize('speed', [1.0, 2.0])
def test_scaled_render_never_replaces_original_editor_or_review_clock(tmp_path, monkeypatch, kind, speed):
    rendered = tmp_path / 'rendered.mp4'
    voice = tmp_path / 'voice.wav'
    rendered.write_bytes(b'rendered')
    voice.write_bytes(b'voice')
    monkeypatch.setattr('hflow.services.video_export.render_path', lambda _: str(rendered))
    monkeypatch.setattr('hflow.services.video_store.get_video_dir', lambda _: str(tmp_path))
    monkeypatch.setattr('hflow.services.ocr_regions.effective_region', lambda *_: {})
    monkeypatch.setattr('hflow.pipeline.render.resolve_subtitle_preview_layout', lambda *_: {})
    video = SimpleNamespace(**VideoConfig(project_type=kind, output_speed=speed).model_dump(),
                            video_id='preview-clock', files={'voice_output': str(voice)})
    media = HFlowController._review_preview_media_for(SimpleNamespace(), video)
    assert bool(media['renderedVideoSource']) == (speed == 1.0)
    assert bool(media['finalMixSource']) == (speed == 1.0)
    assert bool(media['voiceSource']) == (speed != 1.0)


def test_output_speed_qml_slider_only_and_popup_toggle():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(Path(__file__).parents[1] /
        'src/hflow/desktop/qml/OutputSpeedButton.qml')))
    assert component.isReady(), [error.toString() for error in component.errors()]
    root = component.createWithInitialProperties({'width': 130, 'height': 42})
    assert root is not None
    window = QQuickWindow()
    window.resize(400, 400)
    root.setParentItem(window.contentItem())
    window.show()
    selected = []
    root.edited.connect(selected.append)
    try:
        app.processEvents()
        root.clicked.emit()
        app.processEvents()
        popup = root.findChild(QObject, 'outputSpeedPopup')
        assert popup.property('opened')

        def items(item):
            yield item
            for child in item.childItems():
                yield from items(child)

        buttons = [child for child in items(popup.property('contentItem')) if child.property('text') == '1.5×']
        assert not buttons
        root.setProperty('speed', 1.5)
        assert root.property('text') == 'Tốc độ 1.5×'
        slider = root.findChild(QObject, 'outputSpeedSlider')
        assert slider.property('value') == 1.5 and slider.property('stepSize') == .05
        slider.setProperty('value', 1.75)
        slider.moved.emit()
        assert selected == [1.75]
        root.clicked.emit()
        app.processEvents()
        assert not popup.property('opened')
    finally:
        window.hide()
        root.setParentItem(None)
        root.deleteLater()
        window.deleteLater()
        app.processEvents()
