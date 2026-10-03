from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from haizflow.pipeline.transcribe import _refine_suspicious_sentence_timing


def verify_timing(text="Please, just give me something to eat.", confidence=0.9):
    words = [SimpleNamespace(start=0.23, end=0.8, probability=confidence),
             SimpleNamespace(start=1.9, end=2.53, probability=confidence)]
    decoder = Mock()
    decoder.transcribe.return_value = (iter([SimpleNamespace(text=text, words=words)]), None)
    sentence = {"start": 21.647, "end": 28.609,
                "text": "Please, just give me something to eat.", "language": "en"}
    with patch("haizflow.pipeline.transcribe.check_cancellation"), patch("haizflow.pipeline.transcribe.log_to_video"):
        _refine_suspicious_sentence_timing(SimpleNamespace(model=decoder),
                                         np.zeros(31 * 16000), [sentence], "test")
    return sentence, decoder


def test_matching_words_shorten_new_stretched_alignment():
    sentence, decoder = verify_timing()
    assert abs(sentence["end"] - 23.577) < 0.001
    assert sentence["text"] == "Please, just give me something to eat."
    assert decoder.transcribe.call_count == 1


def test_different_decode_never_replaces_alignment():
    sentence, _ = verify_timing(text="Please give me something else.")
    assert sentence["end"] == 28.609


def test_uncertain_words_never_replace_alignment():
    sentence, _ = verify_timing(confidence=0.1)
    assert sentence["end"] == 28.609


def test_normal_sentence_needs_no_additional_decode():
    decoder = Mock()
    sentence = {"start": 1, "end": 3, "text": "A normal short sentence."}
    _refine_suspicious_sentence_timing(SimpleNamespace(model=decoder), np.zeros(64000), [sentence], "test")
    decoder.transcribe.assert_not_called()
