import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
from PySide6.QtGui import QGuiApplication

from hflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
from hflow.pipeline import manual_tools
from hflow.schemas.video import VideoConfig
from hflow.services import manual_artifacts

_APP = None


@pytest.fixture(scope='module', autouse=True)
def application():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    yield _APP


@pytest.mark.parametrize('provider,voice', [('vieneu', 'vieneu:Hải Đăng'),
    ('vieneu-gpu', 'vieneu:Trúc Ly'), ('vieneu', 'vieneu:clone'), ('omnivoice', 'omnivoice:female')])
def test_published_voice_reuses_manifest_and_only_regenerates_edited_sentence(tmp_path, monkeypatch, provider, voice):
    video = SimpleNamespace(**VideoConfig(tts_provider=provider, tts_voice=voice, project_type='manual').model_dump(),
                            video_id='video', active_artifacts={}, manual_tool_generations={}, files={})
    reference = tmp_path / 'reference.wav'
    reference.write_bytes(b'reference')
    if voice.endswith(':clone'):
        video.files['voice_reference'] = str(reference)
    monkeypatch.setattr(manual_artifacts.video_store, 'get_video_dir', lambda _: str(tmp_path))
    monkeypatch.setattr(manual_artifacts.video_store, 'get_video', lambda _: video)
    def update(_id, **changes):
        vars(video).update(changes)
        return video
    monkeypatch.setattr(manual_artifacts.video_store, 'update_video', update)
    monkeypatch.setattr(manual_tools, 'ensure_narrator_anchor', lambda _: '')
    monkeypatch.setattr(manual_tools, 'shutdown_hymt2_worker', lambda: None)
    monkeypatch.setattr(manual_tools, '_release_recognition_runtime', lambda: None)
    monkeypatch.setattr(manual_tools.editor_documents, 'mark_voice_clips_ready', Mock())
    segments = [{'segment_id': 's1', 'text': 'Xin chào.', 'start': 0, 'end': 2},
                {'segment_id': 's2', 'text': 'Cảm ơn bạn.', 'start': 2, 'end': 4}]

    def publish_subtitles():
        staging = manual_artifacts.create_staging_directory('video', 'subtitle_document')
        (staging / 'segments.json').write_text(json.dumps(segments, ensure_ascii=False), encoding='utf-8')
        return manual_artifacts.publish('video', 'subtitle_document', manual_artifacts.signature(segments),
                                        staging, {'segments': 'segments.json'})

    requested = []
    def generate(_source, directory, _voice, _video_id, **options):
        requested.append(options['segment_indices'])
        for index in options['segment_indices']:
            Path(directory, f'voice_{index:04d}.mp3').write_bytes(b'ID3' + b'0' * 600)
    monkeypatch.setattr(manual_tools, 'generate_voice_parts', generate)
    reporter = SimpleNamespace(update=Mock())
    publish_subtitles()
    manual_tools._run_voice(video, reporter)
    assert requested == [[1, 2]]
    original = manual_tools.published_voice_record(video)
    assert original and original['resolved_outputs']['clip_1']
    manual_tools._run_voice(video, reporter)
    assert requested == [[1, 2]]  # No model call on a completed manifest.
    assert manual_tools.published_voice_record(video)['signature'] == original['signature']
    video.output_speed = 1.5
    manual_tools._run_voice(video, reporter)
    assert requested == [[1, 2]]  # Export speed never regenerates existing speech.
    assert manual_tools.published_voice_record(video)['signature'] == original['signature']
    segments[1]['text'] = 'Cảm ơn bạn rất nhiều.'
    publish_subtitles()
    manual_tools._run_voice(video, reporter)
    assert requested == [[1, 2], [2]]
    assert manual_tools.published_voice_record(video)['signature'] != original['signature']


@pytest.mark.parametrize('provider', ['vieneu', 'vieneu-gpu', 'vieneu:clone', 'omnivoice'])
def test_reopen_fitted_voice_maps_pcm_without_decode_or_silence_trimming(tmp_path, provider):
    import wave
    source = tmp_path / 'voice.wav'
    with wave.open(str(source), 'wb') as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(np.full((4800, 2), 1500, dtype='<i2').tobytes())
    directory = tmp_path / 'manual-preview-pcm'
    directory.mkdir()
    first = ManualPreviewAudioController()
    try:
        first._pcm_cache_directory = directory
        first._decode(source, duration=1000)
    finally:
        first.close()
    reopened = ManualPreviewAudioController()
    try:
        reopened._pcm_cache_directory = directory
        with patch.object(reopened, '_decode_to_pcm', side_effect=AssertionError('Must not decode')), \
                patch('hflow.utils.audio.AudioSegment.from_file', side_effect=AssertionError('Must not trim again')):
            samples = reopened._decode(source, duration=1000)
            assert isinstance(samples, np.memmap) and len(samples) > 0
    finally:
        reopened.close()
