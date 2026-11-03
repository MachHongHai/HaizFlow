"""Short replies become independent subtitle cues after trustworthy alignment."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from haizflow.pipeline import transcribe as timing


def mixed_sentence():
    return {"start": 4., "end": 6.3, "text": "I don't feel a thing. Mateo!", "language": "en",
            "words": [{"word": text, "start": start, "end": end, "score": .95}
                      for text, start, end in [
                          ("I", 4., 4.10), ("don't", 4.10, 4.30), ("feel", 4.30, 4.65),
                          ("a", 4.65, 4.80), ("thing.", 4.80, 5.68), ("Mateo!", 5.68, 6.30)]]}


def test_short_reply_restored_without_guessing_timing_or_mutating_alignment():
    source = mixed_sentence()
    original = deepcopy(source)
    result = timing._restore_aligned_sentence_boundaries([source])
    assert [row['text'] for row in result] == ["I don't feel a thing.", "Mateo!"]
    assert [(row['start'], row['end']) for row in result] == [(4., 5.68), (5.68, 6.3)]
    assert all(row['language'] == 'en' for row in result)
    assert all('words' not in row for row in result)
    assert source == original


@pytest.mark.parametrize("change", ["missing", "mismatched-text", "overlap", "too-short"])
def test_unreliable_clocks_never_split_by_estimated_character_weight(change):
    source = mixed_sentence()
    if change == "missing":
        source.pop('words')
    elif change == "mismatched-text":
        source['words'][-1]['word'] = 'Mother!'
    elif change == "overlap":
        source['words'][-1]['start'] = 5.
    else:
        source['words'][-1]['end'] = 5.80
    assert timing._restore_aligned_sentence_boundaries([source]) == [source]


@pytest.mark.parametrize("first,second", [
    ("Không cảm thấy gì.", "Mateo!"),
    ("아무것도 못 느끼는데.", "마테오!"),
    ("何も感じない。", "マテオ！"),
    ("我什么都没感觉到。", "马特奥！"),
    ("No siento nada.", "¡Mateo!"),
])
def test_same_boundary_contract_for_supported_target_scripts(first, second):
    # Native ASR tokens may contain a word, an eojeol or an unspaced phrase.
    source = {'start': 4., 'end': 6.3, 'text': first + ' ' + second,
              'words': [{'word': first, 'start': 4., 'end': 5.68},
                        {'word': second, 'start': 5.68, 'end': 6.3}]}
    result = timing._restore_aligned_sentence_boundaries([source])
    assert [row['text'] for row in result] == [first, second]
    assert [(row['start'], row['end']) for row in result] == [(4., 5.68), (5.68, 6.3)]


def test_a_boundary_inside_one_unspaced_asr_token_is_not_an_exact_clock():
    source = {'start': 4., 'end': 6.3, 'text': '何も感じない。マテオ！',
              'words': [{'word': '何も感じない。マテオ！', 'start': 4., 'end': 6.3}]}
    assert timing._restore_aligned_sentence_boundaries([source]) == [source]


def test_sentence_boundary_is_restored_after_context_alignment_without_an_extra_model_call():
    rough = {'start': 4., 'end': 5.4, 'text': mixed_sentence()['text'], 'language': 'en'}
    assert len(timing._split_segment_proportionally(rough)) == 1  # Provisional 350ms reply was merged.
    align = patch.object(timing, '_align_without_nltk_download', return_value={
        'segments': [{'words': mixed_sentence()['words']}]})
    with (patch.object(timing, '_verified_alignment_asset',
                       return_value=(SimpleNamespace(to=lambda _: object()), {})),
          align as mocked_align, patch.object(timing, '_release_cuda'),
          patch.object(timing, 'log_to_video'), patch.object(timing, 'check_cancellation')):
        result = timing._align_segments_by_language(np.zeros(16000 * 8), [rough], 'cpu', 'fixture')
    assert [row['text'] for row in result] == ["I don't feel a thing.", "Mateo!"]
    assert [(row['start'], row['end']) for row in result] == [(4., 5.68), (5.68, 6.3)]
    assert mocked_align.call_count == 1
