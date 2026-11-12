"""A real artifact graph with a fake synthesizer: edits retain correct speech."""
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline import manual_tools
from haizflow.schemas.video import VideoConfig, VideoInfo
from haizflow.services import editor_documents, manual_artifacts, video_store
from haizflow.services.subtitle_identity import voice_source_indices


@pytest.fixture
def voice_project(tmp_path, monkeypatch):
    video = VideoInfo(**VideoConfig(project_type="manual", tts_provider="vieneu-gpu",
        tts_voice="vieneu:Hải Đăng", speaker_mode="multiple", enable_audio_separation=False).model_dump(),
        video_id="incremental", original_filename="source.mp4", status="manual_ready",
        subtitle_language="vi", created_at="2026-10-14T00:00:00Z", updated_at="2026-10-14T00:00:00Z")
    source = tmp_path / "input" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"unchanged source video")
    video.files["video_input"] = str(source)
    def update(_id, **changes):
        for key, value in changes.items():
            setattr(video, key, value)
        return video
    monkeypatch.setattr(video_store, "get_video_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(video_store, "get_video", lambda _: video)
    monkeypatch.setattr(video_store, "update_video", update)
    monkeypatch.setattr(video_store, "log_to_video", Mock())
    monkeypatch.setattr(editor_documents, "mark_voice_clips_ready", Mock(wraps=editor_documents.mark_voice_clips_ready))
    monkeypatch.setattr(manual_tools, "_is_valid_mp3", lambda path: Path(path).is_file() and Path(path).stat().st_size > 0)
    monkeypatch.setattr(manual_tools, "ensure_narrator_anchor", lambda _: "stable narrator")
    monkeypatch.setattr(manual_tools, "shutdown_hymt2_worker", Mock())
    monkeypatch.setattr(manual_tools, "_release_recognition_runtime", Mock())
    monkeypatch.setattr("haizflow.core.memory.cpu_memory_constrained", lambda: False)
    requests = []
    def synthesize(segments_path, parts_dir, _voice, _id, **kwargs):
        segments = json.loads(Path(segments_path).read_text(encoding="utf-8"))
        indices = list(kwargs["segment_indices"])
        requests.append({"indices": indices, "segments": segments, "provider": kwargs["provider"],
                         "voice": _voice, "speaker_mode": kwargs.get("speaker_mode_override")})
        for index in indices:
            Path(parts_dir, f"voice_{index:04d}.mp3").write_bytes(
                f"ID3 generated voice={_voice} request={len(requests)} sentence={index} text={segments[index-1]['text']}".encode())
    monkeypatch.setattr(manual_tools, "generate_voice_parts", synthesize)
    segments = [{"segment_id": f"cue-{index}", "start": index * 2, "end": index * 2 + 1.5,
        "text": "Cảm ơn mẹ" if index == 5 else f"Câu nói {index+1}",
        "speaker_id": f"speaker-{index % 2}", "speaker_voice": "vieneu:Hải Đăng" if index % 2 else "vieneu:Trúc Ly"}
        for index in range(22)]
    manual_tools.publish_edited_subtitles(video.video_id, segments)
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert requests[0]["indices"] == list(range(1, 23))
    requests.clear()
    return video, segments, requests


@pytest.mark.parametrize("changed", [[6], [6, 15]])
def test_edit_only_generates_changed_sentences_and_preserves_other_audio_and_mapping(voice_project, changed):
    video, original, requests = voice_project
    prior = manual_tools.published_voice_record(video, validate=True)
    old_outputs = prior["resolved_outputs"]
    audio = {index: Path(old_outputs[f"clip_{index}"]).read_bytes() for index in range(1, 23)}
    edited = deepcopy(original)
    for index in changed:
        edited[index-1]["text"] += "! Mẹ ơi"
    manual_tools.publish_edited_subtitles(video.video_id, edited)
    generation = dict(video.manual_tool_generations)
    assert manual_tools.incremental_voice_refresh(video)
    assert not manual_tools.prepare_manual_rerun(video.video_id, "voice")
    assert video.manual_tool_generations == generation
    reporter = SimpleNamespace(update=Mock())
    manual_tools._run_voice(video, reporter)
    assert [index for request in requests for index in request["indices"]] == changed
    assert reporter.update.call_args_list[0].args[4] == len(changed)
    current = manual_tools.published_voice_record(video, validate=True)
    for index in range(1, 23):
        output = Path(current["resolved_outputs"][f"clip_{index}"]).read_bytes()
        assert (output != audio[index]) == (index in changed)
        assert Path(old_outputs[f"clip_{index}"]).read_bytes() == audio[index]
    sent = requests[0]["segments"]
    assert [(item["speaker_id"], item["speaker_voice"]) for item in sent] == [
        (item["speaker_id"], item["speaker_voice"]) for item in original]


def test_unchanged_explicit_rerun_really_synthesizes_every_sentence(voice_project):
    video, _segments, requests = voice_project
    assert not manual_tools.incremental_voice_refresh(video)
    assert manual_tools.prepare_manual_rerun(video.video_id, "voice", force=True)
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert requests[0]["indices"] == list(range(1, 23))


def test_one_missing_cached_audio_plus_one_edit_only_regenerates_those_two_sentences(voice_project):
    video, segments, requests = voice_project
    prior = manual_tools.published_voice_record(video, validate=True)
    # Remove both the manifest's independent copy and its sentence cache.
    keys = manual_tools._voice_manifest_payload(prior)["clips"]
    clip = manual_artifacts.resolve(video.video_id, "tts_clip", keys[5])
    Path(prior["resolved_outputs"]["clip_6"]).unlink()
    Path(clip["resolved_outputs"]["audio"]).unlink()
    edited = deepcopy(segments)
    edited[8]["text"] += "!"
    manual_tools.publish_edited_subtitles(video.video_id, edited)
    assert manual_tools.published_voice_record(video, validate=False) is None
    assert manual_tools.incremental_voice_refresh(video)
    assert not manual_tools.prepare_manual_rerun(video.video_id, "voice")
    reporter = SimpleNamespace(update=Mock())
    manual_tools._run_voice(video, reporter)
    assert requests[0]["indices"] == [6, 9]
    assert reporter.update.call_args_list[0].args[4] == 2


def test_voice_configuration_change_with_edited_subtitle_is_not_incremental(voice_project):
    video, segments, requests = voice_project
    edited = deepcopy(segments)
    edited[5]["text"] += "!"
    manual_tools.publish_edited_subtitles(video.video_id, edited)
    video.tts_provider = "vieneu"
    assert not manual_tools.incremental_voice_refresh(video)
    assert manual_tools.prepare_manual_rerun(video.video_id, "voice", force=True)
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert requests[0]["indices"] == list(range(1, 23))
    assert requests[0]["provider"] == "vieneu"


def test_historical_manifest_hit_does_not_turn_an_edit_into_a_full_rerun(voice_project, monkeypatch):
    video, segments, _requests = voice_project
    edited = deepcopy(segments)
    edited[5]["text"] += "!"
    manual_tools.publish_edited_subtitles(video.video_id, edited)
    assert manual_tools.incremental_voice_refresh(video)
    monkeypatch.setattr(manual_tools, "_requested_artifact", Mock(side_effect=AssertionError("Incremental edit must not advance generation on a manifest hit")))
    generation = dict(video.manual_tool_generations)
    assert not manual_tools.prepare_manual_rerun(video.video_id, "voice")
    assert video.manual_tool_generations == generation


def test_full_voice_dialog_routes_a_subtitle_edit_to_incremental_processing(voice_project):
    video, segments, _requests = voice_project
    edited = deepcopy(segments)
    edited[5]["text"] += "!"
    manual_tools.publish_edited_subtitles(video.video_id, edited)
    host = SimpleNamespace(_project_type="manual", _selected_video=lambda: video,
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        _normalized_tts_provider=HaizFlowController._normalized_tts_provider,
        _normalized_voice_for_language=lambda _lang, value, _provider: value,
        _manual_subtitles=SimpleNamespace(video_id=video.video_id, segments=edited),
        voiceCloneReferencePath="", appAlertRequested=Mock(), ttsProviderChanged=Mock(), ttsVoiceChanged=Mock(),
        ttsProviderOptionsChanged=Mock(), ttsVoiceOptionsChanged=Mock(), _apply_setup_to_video=Mock(),
        speakerModeChanged=Mock(), _manual_voice_configuration_snapshot=HaizFlowController._manual_voice_configuration_snapshot,
        _record_manual_voice_configuration_change=Mock(), runManualTool=Mock(return_value=True))
    assert HaizFlowController.configureAndRunManualVoice(host, "vieneu-gpu", "vieneu:Hải Đăng", "all", "", "multiple")
    host.runManualTool.assert_called_once_with("voice", False)


@pytest.mark.parametrize("operation", ["delete", "merge"])
def test_legacy_idless_manifest_reuses_unchanged_multi_speaker_parts_after_structure_edit(
    voice_project, monkeypatch, operation,
):
    video, segments, requests = voice_project
    before = manual_tools.published_voice_record(video, validate=True)
    old_bytes = [Path(before["resolved_outputs"][f"clip_{index}"]).read_bytes() for index in range(1, 23)]
    legacy = [{key: value for key, value in item.items() if key != "segment_id"} for item in segments]
    edited = deepcopy(segments)
    if operation == "merge":
        edited[4]["text"] += " " + edited[5]["text"]
        edited[4]["end"] = edited[5]["end"]
    del edited[5]
    manual_tools.publish_edited_subtitles(video.video_id, edited)
    monkeypatch.setattr(manual_tools, "published_voice_source_segments", lambda *_args, **_kwargs: legacy)
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert [index for request in requests for index in request["indices"]] == ([5] if operation == "merge" else [])
    current = manual_tools.published_voice_record(video, validate=True)
    mapping = voice_source_indices(video.video_id, edited, legacy)
    assert len(mapping) == len(edited) - (operation == "merge")
    for new_index, old_index in mapping.items():
        assert Path(current["resolved_outputs"][f"clip_{new_index + 1}"]).read_bytes() == old_bytes[old_index]


def select_voice_cues(video, indices, *, token="new-attempt", provider="vieneu-gpu", voice="vieneu:Trúc Ly"):
    files = dict(video.files)
    files["manual_voice_selection"] = [f"cue-{index - 1}" for index in indices]
    overrides = dict(files.get("manual_voice_overrides") or {})
    for key in files["manual_voice_selection"]:
        overrides[key] = {"provider": provider, "voice": voice,
                          "speaker_mode": "single", "generation": token}
    files["manual_voice_overrides"] = overrides
    video_store.update_video(video.video_id, files=files)


@pytest.mark.parametrize("indices", [[6], [6, 15]])
@pytest.mark.parametrize("provider,voice", [("vieneu-gpu", "vieneu:Trúc Ly"), ("omnivoice-gpu", "omnivoice:female")])
def test_explicit_scope_only_generates_targets_and_preserves_other_bytes(voice_project, indices, provider, voice, monkeypatch):
    video, _segments, requests = voice_project
    old = manual_tools.published_voice_record(video, validate=True)
    audio = {i: Path(old["resolved_outputs"][f"clip_{i}"]).read_bytes() for i in range(1, 23)}
    select_voice_cues(video, indices, provider=provider, voice=voice)
    register = Mock(wraps=manual_artifacts.register_existing)
    monkeypatch.setattr(manual_artifacts, "register_existing", register)
    generations = dict(video.manual_tool_generations)
    assert not manual_tools.prepare_manual_rerun(video.video_id, "voice", force=True)
    assert video.manual_tool_generations == generations
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert [i for request in requests for i in request["indices"]] == indices
    assert all(request["voice"] == voice and request["speaker_mode"] == "single" for request in requests)
    assert [call.args[1] for call in register.call_args_list] == ["tts_clip"] * len(indices)
    current = manual_tools.published_voice_record(video, validate=True)
    for i in range(1, 23):
        assert (Path(current["resolved_outputs"][f"clip_{i}"]).read_bytes() != audio[i]) == (i in indices)
        assert Path(old["resolved_outputs"][f"clip_{i}"]).read_bytes() == audio[i]
    assert "manual_voice_selection" not in video.files
    assert video.speaker_mode == "multiple" and video.tts_voice == "vieneu:Hải Đăng"


def test_first_partial_generation_and_later_selection_are_cumulative(voice_project):
    video, _segments, requests = voice_project
    video.active_artifacts.pop("tts_manifest", None)
    video.manual_tool_generations["voice"] = 100
    select_voice_cues(video, [6])
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    first = manual_tools.published_voice_record(video, validate=True)
    assert set(first["resolved_outputs"]) == {"manifest", "clip_6"}
    assert manual_tools._voice_manifest_payload(first)["partial"]
    audio = Path(first["resolved_outputs"]["clip_6"]).read_bytes()
    select_voice_cues(video, [15], token="second")
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    current = manual_tools.published_voice_record(video, validate=True)
    assert set(current["resolved_outputs"]) == {"manifest", "clip_6", "clip_15"}
    assert Path(current["resolved_outputs"]["clip_6"]).read_bytes() == audio
    assert [i for request in requests for i in request["indices"]] == [6, 15]
    # Real editor reconciliation must not compact sparse paths to cue 1/2.
    document = editor_documents.ensure(video)
    enabled = {clip.segment_id: clip for clip in document.clips if clip.track_id == "voice" and clip.enabled}
    assert set(enabled) == {"cue-5", "cue-14"}
    for segment_id, index in (("cue-5", 6), ("cue-14", 15)):
        asset = editor_documents.asset_by_id(document, enabled[segment_id].asset_id)
        assert asset.path == current["resolved_outputs"][f"clip_{index}"]
    sources = manual_tools._audible_manual_voice_sources(video, document)
    assert set(sources) == {"cue-5", "cue-14"}
    again = editor_documents.ensure(video)
    assert {clip.segment_id for clip in again.clips if clip.track_id == "voice" and clip.enabled} == set(enabled)


def test_scope_does_not_fill_an_unselected_missing_clip(voice_project):
    video, _segments, requests = voice_project
    prior = manual_tools.published_voice_record(video, validate=True)
    key = manual_tools._voice_manifest_payload(prior)["clips"][1]
    Path(prior["resolved_outputs"]["clip_2"]).unlink()
    Path(manual_artifacts.resolve(video.video_id, "tts_clip", key)["resolved_outputs"]["audio"]).unlink()
    select_voice_cues(video, [6, 15])
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert [i for request in requests for i in request["indices"]] == [6, 15]
    assert "clip_2" not in manual_tools.published_voice_record(video, validate=True)["resolved_outputs"]


def test_failed_selection_keeps_published_manifest_and_resumes_completed_cues(voice_project, monkeypatch):
    video, _segments, requests = voice_project
    old = video.active_artifacts["tts_manifest"]
    select_voice_cues(video, [6, 15])
    original = manual_tools.generate_voice_parts
    def fail(path, output, voice, key, **kwargs):
        original(path, output, voice, key, **{**kwargs, "segment_indices": [6]})
        raise RuntimeError("Simulated cancellation")
    monkeypatch.setattr(manual_tools, "generate_voice_parts", fail)
    with pytest.raises(RuntimeError, match="cancellation"):
        manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert video.active_artifacts["tts_manifest"] == old
    assert video.files["manual_voice_selection"] == ["cue-5", "cue-14"]
    monkeypatch.setattr(manual_tools, "generate_voice_parts", original)
    requests.clear()
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert [i for request in requests for i in request["indices"]] == [15]


def test_scope_supports_legacy_idless_subtitle_documents(voice_project):
    from haizflow.services.subtitle_identity import legacy_segment_id

    video, segments, requests = voice_project
    legacy = [{key: value for key, value in item.items() if key != "segment_id"} for item in segments]
    manual_tools.publish_edited_subtitles(video.video_id, legacy)
    video.manual_tool_generations["voice"] = 50
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    old = manual_tools.published_voice_record(video, validate=True)
    before = {i: Path(old["resolved_outputs"][f"clip_{i}"]).read_bytes() for i in range(1, 23)}
    requests.clear()
    cue_id = legacy_segment_id(video.video_id, 5, legacy[5])
    video.files["manual_voice_selection"] = [cue_id]
    video.files["manual_voice_overrides"] = {cue_id: {
        "provider": "vieneu-gpu", "voice": "vieneu:Trúc Ly", "speaker_mode": "single", "generation": "legacy-test"}}
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert [i for request in requests for i in request["indices"]] == [6], {
        "overrides": video.files.get("manual_voice_overrides"),
        "selected": video.files.get("manual_voice_selection"),
        "segments": manual_tools._load_segments(video)[5],
        "manifest": manual_tools._voice_manifest_payload(manual_tools.published_voice_record(video))}
    current = manual_tools.published_voice_record(video, validate=True)
    for index in range(1, 23):
        if index != 6:
            assert Path(current["resolved_outputs"][f"clip_{index}"]).read_bytes() == before[index]


def test_explicit_restart_discards_selected_progress_without_global_regeneration(voice_project, monkeypatch):
    from haizflow.services.processing_resume import configuration_snapshot

    video, _segments, requests = voice_project
    select_voice_cues(video, [6, 15])
    original = manual_tools.generate_voice_parts
    def fail(path, output, voice, key, **kwargs):
        original(path, output, voice, key, **{**kwargs, "segment_indices": [6]})
        raise RuntimeError("Simulated pause")
    monkeypatch.setattr(manual_tools, "generate_voice_parts", fail)
    with pytest.raises(RuntimeError, match="pause"):
        manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    video.manual_target_tool = "voice"
    video.status = "paused"
    video.processing_configuration = configuration_snapshot(video, "cpu")
    generation = dict(video.manual_tool_generations)
    assert manual_tools.prepare_manual_rerun(video.video_id, "voice", force=True)
    assert video.manual_tool_generations == generation
    monkeypatch.setattr(manual_tools, "generate_voice_parts", original)
    requests.clear()
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert [i for request in requests for i in request["indices"]] == [6, 15]
