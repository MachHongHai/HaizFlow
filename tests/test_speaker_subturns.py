import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from hflow.pipeline import speaker_identity as identity, tts
from hflow.pipeline.tts_quality import validate_speech_waveform


def test_clause_candidates_follow_a_quiet_gap_not_equal_halves():
    wave = np.full(17600, 5000, dtype=np.float32)
    wave[9600:11200] = 0
    source = {'start':10,'end':11.1,'text':"Don't do it! No!"}
    clauses = identity._clause_candidates(source,wave)
    assert len(clauses)==2 and 10.60 <= clauses[0]['end'] <= 10.70
    assert clauses[0]['end']==clauses[1]['start']
    assert [c['text'] for c in clauses]==["Don't do it!",'No!']
    assert identity._clause_candidates(source,np.full(17600,5000,dtype=np.float32))==[]


def test_very_short_embedding_repeats_own_features_without_borrowing_next_voice():
    audio = np.sin(2*np.pi*120*np.arange(6080)/16000)*2000
    features = identity._features(audio)
    padded = identity._embedding_input(audio)
    assert padded.shape==(150,80)
    np.testing.assert_array_equal(padded[:len(features)],features)
    normal = np.tile(audio,2)
    np.testing.assert_array_equal(identity._embedding_input(normal),identity._features(normal))


def test_childlike_style_needs_multiple_references_and_margin_over_adults():
    bank = {'child':np.array([[1,0],[.999,.01]]),'adult':np.array([[0,1],[.01,.999]])}
    values = np.array([[1,0],[0,1],[.707,.707]])
    assert identity._childlike_evidence(values,bank).tolist()==[True,False,False]
    assert not identity._childlike_evidence(values,{}).any()


def test_corroborated_change_and_child_style_cannot_collapse_into_one_actor():
    vectors = np.array([[1.,0],[.99,.01],[.99,.01]],dtype=np.float32)
    vectors /= np.linalg.norm(vectors,axis=1,keepdims=True)
    labels,scores = identity._separate_turn_constraints(vectors,[0,0,0],[0,1,2],[(0,1),(1,2)],np.array([False]*3))
    assert labels[0]!=labels[1] and labels[2]==labels[0]  # A-B-A, not three actors.
    assert scores.shape[1]==2
    labels,_ = identity._separate_turn_constraints(vectors,[0,0,0],[0,1,2],[],np.array([False,True,False]))
    assert labels[0]==labels[2]!=labels[1]


def mixed_source():
    return {'start':4.,'end':5.,'text':"Don't do it! No!",'speaker_id':'speaker-1','speaker_voice':'omnivoice:male',
            'speaker_turns':[{'start':4.,'end':4.6,'text':"Don't do it!",'speaker_id':'speaker-1','speaker_voice':'omnivoice:male'},
                             {'start':4.6,'end':5.,'text':'No!','speaker_id':'speaker-2','speaker_voice':'omnivoice:female'}]}


def test_subturn_map_rejects_broken_bounds_and_conflicting_voice_ids():
    source = mixed_source()
    original = [{k:v for k,v in source.items() if not k.startswith('speaker_')}]
    assert identity._valid_map([source],original)
    broken = json.loads(json.dumps(source));broken['speaker_turns'][1]['start']=4.9
    assert not identity._valid_map([broken],original)
    broken = json.loads(json.dumps(source));broken['speaker_turns'][1]['speaker_id']='speaker-1'
    assert not identity._valid_map([broken],original)


def test_edited_caption_retains_source_subturn_voices_and_relative_windows():
    segment = {'start':10.,'end':12.,'text':'Xin đừng làm vậy! Không!'}
    plan = tts._speaker_utterance_plan(segment,mixed_source())
    assert [p['voice'] for p in plan]==['omnivoice:male','omnivoice:female']
    assert [(p['offset_ms'],p['duration_ms']) for p in plan]==[(0,1200),(1200,800)]
    with pytest.raises(ValueError,match='ranh giới'):
        tts._speaker_utterance_plan({**segment,'text':'Đừng làm vậy, không'},mixed_source())


def test_single_short_turn_keeps_millisecond_duration():
    segment = {'start':49.136,'end':49.516,'text':'Cảm ơn cậu.'}
    plan = tts._speaker_utterance_plan(segment,{'speaker_voice':'omnivoice:male_soft','speaker_id':'speaker-3'})
    assert plan[0]['duration_ms']==380
    assert plan[0]['voice']=='omnivoice:male_soft'


def test_composite_counts_one_caption_and_never_uses_default_female(tmp_path):
    segments = [{'start':4.,'end':5.,'text':'Đừng làm vậy! Không!'}]
    transcript = tmp_path/'segments.json';transcript.write_text(json.dumps(segments),encoding='utf-8')
    source = tmp_path/'source.json';source.write_text(json.dumps([mixed_source()]),encoding='utf-8')
    audio = tmp_path/'audio.wav';audio.write_bytes(b'fixture')
    video = SimpleNamespace(speaker_mode='multiple',files={'source_segments':str(source),'speech_audio':str(audio)})
    progress,compositions = [],[]
    def synthesize(items,_video,**kwargs):
        assert [item['voice'] for item in items]==['omnivoice:male','omnivoice:female']
        for i,item in enumerate(items,1):
            Path(item['output_path']).write_bytes(b'ID3'+bytes(600))
            kwargs['progress_callback'](i,len(items),'synthesizing')
    def compose(parts,destination,_id):
        compositions.append(parts)
        Path(destination).write_bytes(b'ID3'+bytes(600))
    with (patch.object(tts,'get_video',return_value=video),patch.object(tts,'log_to_video'),
          patch.object(identity,'prepare_speakers',return_value=[mixed_source()]),
          patch('hflow.pipeline.omnivoice_tts.synthesize_batch_to_mp3',side_effect=synthesize),
          patch.object(tts,'_compose_speaker_utterances',side_effect=compose)):
        tts.generate_voice_parts(str(transcript),str(tmp_path/'parts'),'omnivoice:female','fixture',
                                 status_callback=lambda _stage,current,total:progress.append((current,total)))
    assert progress[:2]==[(0,1),(1,1)]
    assert len(compositions)==1 and (tmp_path/'parts'/'voice_0001.mp3').exists()
    assert not list((tmp_path/'parts').glob('speaker-phrases-*'))


def test_stationary_tone_before_valid_speech_is_not_accepted_as_a_voice_clip():
    rate = 24000
    tone = .2*np.sin(2*np.pi*1975*np.arange(12000)/rate)
    # Sidebands defeated the previous pure-tone/whole-file entropy tests.
    tone += .08*np.sin(2*np.pi*2050*np.arange(12000)/rate)
    speech = np.random.default_rng(42).normal(0,.1,24000)
    with pytest.raises(RuntimeError,match='sustained high-frequency tone'):
        validate_speech_waveform(np.concatenate([np.zeros(2400),tone,np.zeros(7200),speech]),rate)
