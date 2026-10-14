import os
import shutil
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from hflow.pipeline import tts
from hflow.pipeline.tts_quality import (
    active_speech_rms, is_level_reference_text, peer_speech_target,
)


def test_robust_target_requires_three_valid_peers_not_the_loudest_one():
    assert peer_speech_target([.08,.10,.12,.29]) == pytest.approx(.11)
    assert peer_speech_target([.1,.12,np.nan,np.inf,0]) == 0
    assert not is_level_reference_text('90.000 đô la.','vi')
    assert not is_level_reference_text('Tôi có rất nhiều tiền đây!','vi')
    assert not is_level_reference_text('Cảm ơn cậu.','vi')
    assert is_level_reference_text('Đây là một câu bình thường.','vi')


def write_clip(tmp_path,index,level,speaker='a',text='Đây là một câu bình thường.'):
    path = tmp_path/f'{index}.mp3'
    wave = np.random.default_rng(11).normal(0,level,24000).astype(np.float32)
    sf.write(path,wave,24000,format='WAV',subtype='FLOAT')
    return {'text':text,'voice':'omnivoice:male','speaker_id':speaker,'output_path':str(path)}


def fake_encode(wav,destination,_id):
    temp = Path(str(destination)+'.part')
    shutil.copy2(wav,temp)
    os.replace(temp,destination)


def test_partial_edit_levels_only_requested_clip_and_keeps_speaker_cache_immutable(tmp_path):
    peers = [write_clip(tmp_path,i,.12) for i in range(3)]
    quiet = write_clip(tmp_path,3,.055,text='90.000 đô la.')
    other = write_clip(tmp_path,4,.04,speaker='b')
    peers.extend([quiet,other])
    original = tmp_path/'immutable-cache.wav'
    os.link(quiet['output_path'],original)
    originals = {item['output_path']:Path(item['output_path']).read_bytes() for item in peers}
    with patch.object(tts,'_is_valid_mp3',return_value=True), patch.object(tts,'log_to_video'), \
            patch('hflow.pipeline.omnivoice_tts._encode_mp3',side_effect=fake_encode):
        changed = tts._level_voice_peers(peers,[quiet,other],'fixture','vi')
        assert changed == {quiet['output_path']}
        first = Path(quiet['output_path']).read_bytes()
        assert tts._level_voice_peers(peers,[quiet],'fixture','vi') == set()
        assert Path(quiet['output_path']).read_bytes()==first
    wave,rate = sf.read(quiet['output_path'],dtype='float32')
    assert active_speech_rms(wave,rate) == pytest.approx(.12,abs=.002)
    assert len(wave)==24000 and max(abs(wave)) < 10**(-1/20)
    assert original.read_bytes()==originals[quiet['output_path']]
    for item in peers:
        if item is not quiet:
            assert Path(item['output_path']).read_bytes()==originals[item['output_path']]
    assert not list(tmp_path.glob('voice-level-*'))


def test_shouts_are_not_calibration_references_and_peak_cap_is_preserved(tmp_path):
    peers = [write_clip(tmp_path,i,.1) for i in range(3)]
    peers.extend(write_clip(tmp_path,i,.23,text='Đây là một câu hét lớn!') for i in range(3,7))
    quiet = write_clip(tmp_path,8,.05,text='Một câu hơi nhỏ.')
    wave,rate = sf.read(quiet['output_path'],dtype='float32')
    wave[1000] = .85
    sf.write(quiet['output_path'],wave,rate,format='WAV',subtype='FLOAT')
    with patch.object(tts,'_is_valid_mp3',return_value=True), patch.object(tts,'log_to_video'), \
            patch('hflow.pipeline.omnivoice_tts._encode_mp3',side_effect=fake_encode):
        tts._level_voice_peers(peers,[quiet],'fixture','vi')
    corrected,_ = sf.read(quiet['output_path'],dtype='float32')
    assert max(abs(corrected)) <= 10**(-1/20)+1e-6
    assert np.allclose(corrected,wave*(corrected[1000]/wave[1000]))


def test_cancellation_during_metering_is_not_swallowed(tmp_path):
    peers = [write_clip(tmp_path,i,.1) for i in range(3)]
    with patch.object(tts,'_is_valid_mp3',return_value=True), \
            patch('hflow.pipeline.process_registry.check_cancellation',side_effect=RuntimeError('cancelled')):
        with pytest.raises(RuntimeError,match='cancelled'):
            tts._level_voice_peers(peers,[peers[0]],'fixture','vi')


def test_peer_policy_changes_manual_and_auto_voice_keys_but_not_edge():
    from types import SimpleNamespace
    from hflow.pipeline import manual_tools,process_video,tts_quality
    video = SimpleNamespace(speaker_mode='single',tts_voice='omnivoice:male',tts_provider='omnivoice-gpu',
                            target_language='vi',files={},manual_tool_generations={})
    segments = [{'text':'Đây là một câu nói bình thường.'}]
    manual = manual_tools._voice_clip_signatures(video,segments)
    auto = process_video._voice_checkpoint_signature(video,'same-transcript',segments=segments)
    with patch.object(tts_quality,'VOICE_AUDIO_VERSION','different-peer-policy'):
        assert manual != manual_tools._voice_clip_signatures(video,segments)
        assert auto != process_video._voice_checkpoint_signature(video,'same-transcript',segments=segments)
    video.tts_provider = 'edge'
    manual = manual_tools._voice_clip_signatures(video,segments)
    auto = process_video._voice_checkpoint_signature(video,'same-transcript',segments=segments)
    with patch.object(tts_quality,'VOICE_AUDIO_VERSION','different-peer-policy'):
        assert manual == manual_tools._voice_clip_signatures(video,segments)
        assert auto == process_video._voice_checkpoint_signature(video,'same-transcript',segments=segments)
