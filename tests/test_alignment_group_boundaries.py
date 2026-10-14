from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from hflow.pipeline import transcribe as timing


def sentence(start, end, text="One sentence.", language="en"):
    return dict(start=start, end=end, text=text, language=language)


def words_for(segments):
    result = []
    for item in segments:
        words = item["text"].split()
        step = (item["end"] - item["start"]) / len(words)
        result.extend(dict(word=word, start=item["start"] + index * step,
                           end=item["start"] + (index + 0.9) * step, score=0.9)
                      for index, word in enumerate(words))
    return result


def test_corrected_neighbours_replace_proportional_source_boundaries():
    first = [sentence(0, 4)]
    second = [sentence(4, 8, "Another sentence.")]
    corrected_first = [sentence(0, 2)]
    corrected_second = [sentence(2.2, 6, "Another sentence.")]
    assert timing._alignment_intrusion_detail(second, corrected_second, first)
    with patch.object(timing, "log_to_video"), patch.object(timing, "check_cancellation"):
        result = timing._resolve_context_alignments(
            [(first, corrected_first), (second, corrected_second)], "test")
    assert result == corrected_first + corrected_second


def test_real_intrusion_into_unaligned_foreign_speech_still_rejects_candidate():
    first = [sentence(0, 3)]
    foreign = [sentence(3, 6, "Autre phrase.", "fr")]
    candidate = [sentence(0, 4)]
    with patch.object(timing, "log_to_video"), patch.object(timing, "check_cancellation"):
        result = timing._resolve_context_alignments([(first, candidate), (foreign, None)], "test")
    assert result == first + foreign


def test_rejected_candidate_falls_back_before_resolving_other_groups():
    first = [sentence(0, 3)]
    second = [sentence(3, 6, "Another sentence.")]
    with patch.object(timing, "log_to_video"), patch.object(timing, "check_cancellation"):
        result = timing._resolve_context_alignments(
            [(first, [sentence(0, 4)]), (second, [sentence(3, 5, "Another sentence.")])], "test")
    assert result == first + [sentence(3, 5, "Another sentence.")]


def test_nonoverlapping_boundary_adds_no_model_call():
    with patch.object(timing, "_align_without_nltk_download") as align:
        timing._repair_alignment_group_boundary(
            [sentence(0, 2)], [sentence(0, 2)], [sentence(3, 4)], [sentence(3, 4)],
            np.zeros(16000 * 5), None, {}, "cpu", "test")
    align.assert_not_called()


def test_incomplete_boundary_alignment_does_not_mutate_either_candidate():
    previous, current = [sentence(0, 4)], [sentence(3, 6, "Another sentence.")]
    with patch.object(timing, "_align_without_nltk_download", return_value={"segments": []}), \
            patch.object(timing, "check_cancellation"):
        timing._repair_alignment_group_boundary(previous, previous, current, current,
            np.zeros(16000 * 8), None, {}, "cpu", "test")
    assert previous == [sentence(0, 4)]
    assert current == [sentence(3, 6, "Another sentence.")]


def test_disputed_group_boundary_is_repaired_once_without_changing_text():
    source = [sentence(0, 4, "First sentence."), sentence(7, 8, "Second sentence.")]
    calls = []

    def align(context, *_args, **_kwargs):
        calls.append(context[0]["text"])
        if len(calls) == 1:
            words = [dict(word="First", start=0.5, end=1, score=0.9),
                     dict(word="sentence.", start=1.1, end=5.5, score=0.9)]
        elif len(calls) == 2:
            words = [dict(word="Second", start=5, end=6, score=0.9),
                     dict(word="sentence.", start=6.1, end=7.5, score=0.9)]
        else:
            words = words_for([sentence(0.5, 1, "First sentence."),
                               sentence(6.5, 7.5, "Second sentence.")])
        return {"segments": [{"words": words}]}

    with patch.object(timing, "_verified_alignment_asset",
                      return_value=(SimpleNamespace(to=lambda _: object()), {})), \
            patch.object(timing, "_align_without_nltk_download", side_effect=align), \
            patch.object(timing, "_release_cuda"), patch.object(timing, "log_to_video"), \
            patch.object(timing, "check_cancellation"):
        result = timing._align_segments_by_language(np.zeros(16000 * 10), source, "cpu", "test")
    assert calls == ["First sentence.", "Second sentence.", "First sentence. Second sentence."]
    assert [item["text"] for item in result] == [item["text"] for item in source]
    assert result[0]["end"] < result[1]["start"]
    assert result[1]["start"] == 6.5
    assert all(item.get("words") for item in result)


def test_real_testcu_boundary_preserves_all_other_aligned_sentences():
    previous_source = [sentence(66.655, 71.845, "It disgusts me to look at you!")]
    source = [sentence(71.845, 75.194, "My grandson."), sentence(139.194, 145.038, "Nothing left.")]
    previous = [sentence(70.385, 71.485, previous_source[0]["text"])]
    current = [sentence(70.925, 75.244, source[0]["text"]), sentence(134.669, 138.330, source[1]["text"])]
    boundary = [sentence(70.4, 71.516, previous_source[0]["text"]), sentence(71.656, 75.243, source[0]["text"])]
    alignment_result = {"segments": [{"words": words_for(boundary)}]}
    with patch.object(timing, "_align_without_nltk_download", return_value=alignment_result), \
            patch.object(timing, "log_to_video"), patch.object(timing, "check_cancellation"):
        timing._repair_alignment_group_boundary(previous_source, previous, source, current,
            np.zeros(16000 * 150), None, {}, "cpu", "test")
        resolved = timing._resolve_context_alignments([(previous_source, previous), (source, current)], "test")
    assert resolved[-1]["start"] == 134.669
    assert resolved[-1]["end"] == 138.330
    assert [item["text"] for item in resolved] == [item["text"] for item in previous_source + source]


def test_short_turbo_boundary_search_excludes_already_aligned_neighbours():
    previous_source = [sentence(68, 70.3, "You have nothing."), sentence(70.562, 71.845, "It disgusts me.")]
    source = [sentence(71.845, 75.194, "My grandson."), sentence(75.194, 80, "Your father.")]
    previous = [sentence(68, 70.365, "You have nothing."), sentence(70.385, 71.485, "It disgusts me.")]
    current = [sentence(70.925, 75.244, "My grandson."), sentence(75.444, 80, "Your father.")]
    repaired = [sentence(70.39, 71.51, "It disgusts me."), sentence(71.65, 75.24, "My grandson.")]
    with patch.object(timing, "_align_without_nltk_download",
                      return_value={"segments": [{"words": words_for(repaired)}]}) as align, \
            patch.object(timing, "log_to_video"), patch.object(timing, "check_cancellation"):
        timing._repair_alignment_group_boundary(previous_source, previous, source, current,
            np.zeros(16000 * 82), None, {}, "cpu", "test")
    window = align.call_args.args[0][0]
    assert window['start'] == 70.365
    assert window['end'] == 75.444
    assert current[0]['start'] == 71.65
    assert previous[0] == sentence(68, 70.365, "You have nothing.")
