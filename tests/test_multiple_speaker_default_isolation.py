"""The narrator selector is not an input to source speaker identification."""

import json
import shutil
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from hflow.pipeline import manual_tools, omnivoice_tts, process_video, speaker_identity, tts


@pytest.mark.parametrize("provider", ["omnivoice", "omnivoice-gpu"])
@pytest.mark.parametrize("default_voice", ["omnivoice:female", "omnivoice:male", "omnivoice:deep"])
def test_mapped_voices_ignore_narrator_even_for_uncertain_or_reordered_turns(tmp_path, provider, default_voice):
    source = [{"start": 0, "end": 2, "text": "First person."},
              {"start": 10, "end": 13, "text": "Second person."}]
    translated = [{"start": 11, "end": 12, "text": "Người thứ hai."},
                  {"start": .3, "end": 1.5, "text": "Người thứ nhất."}]
    mapped = [{**item, "speaker_id": f"speaker-{index}", "speaker_voice": voice,
               "speaker_voice_uncertain": True, "speaker_uncertain": True}
              for index, (item, voice) in enumerate(zip(source, ["omnivoice:male", "omnivoice:female_low"]))]
    source_path = tmp_path / "source.json"
    translated_path = tmp_path / "translated.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    translated_path.write_text(json.dumps(translated), encoding="utf-8")
    audio = tmp_path / "audio.wav"
    audio.touch()
    video = SimpleNamespace(speaker_mode="multiple", tts_voice=default_voice,
                            files={"source_segments": str(source_path), "speech_audio": str(audio),
                                   "voice_reference": "unused-clone.wav", "voice_reference_transcript": "Unused."})

    def synthesize(items, *_args, **_kwargs):
        for item in items:
            (tmp_path / "parts" / f"voice_{int(item['index']):04d}.mp3").write_bytes(b"ID3" + bytes(600))

    with (patch.object(tts, "get_video", return_value=video), patch.object(tts, "log_to_video"),
          patch.object(speaker_identity, "prepare_speakers", return_value=mapped) as identify,
          patch.object(omnivoice_tts, "synthesize_batch_to_mp3", side_effect=synthesize) as worker):
        tts.generate_voice_parts(str(translated_path), str(tmp_path / "parts"), default_voice, "fixture",
                                 provider=provider, narrator_anchor_text="An unused narrator anchor.")
    assert identify.call_args.args[:3] == (str(audio), source, "fixture")
    items = worker.call_args.args[0]
    assert [item["voice"] for item in items] == ["omnivoice:female_low", "omnivoice:male"]
    assert all(not item["reference_path"] and not item["source_audio_path"] for item in items)
    assert "narrator_anchor_text" not in worker.call_args.kwargs
    assert worker.call_args.kwargs["device"] == ("gpu" if provider.endswith("-gpu") else "cpu")


@pytest.mark.parametrize("mapped", [[], [{}], [{"speaker_id": "speaker-1", "speaker_voice": "unknown"}]])
def test_incomplete_identity_map_never_falls_back_to_default_female(tmp_path, mapped):
    transcript = tmp_path / "source.json"
    transcript.write_text(json.dumps([{"start": 0, "end": 2, "text": "Hello."}]), encoding="utf-8")
    audio = tmp_path / "source.wav"
    audio.touch()
    video = SimpleNamespace(speaker_mode="multiple", files={"source_segments": str(transcript), "speech_audio": str(audio)})
    with (patch.object(tts, "get_video", return_value=video), patch.object(tts, "log_to_video"),
          patch.object(speaker_identity, "prepare_speakers", return_value=mapped),
          patch.object(omnivoice_tts, "synthesize_batch_to_mp3") as worker):
        with pytest.raises(RuntimeError, match="giọng từng người nói"):
            tts.generate_voice_parts(str(transcript), str(tmp_path / "parts"), "omnivoice:female", "fixture")
    worker.assert_not_called()


@pytest.mark.parametrize("voice", [None, "", "unknown", "omnivoice:clone"])
def test_worker_boundaries_reject_missing_or_invalid_speaker_voice_before_loading(tmp_path, voice):
    item = {"text": "Hello.", "voice": voice, "output_path": str(tmp_path / "voice.mp3")}
    with patch.object(omnivoice_tts, "_prepare_isolated_runtime") as prepare:
        with pytest.raises(RuntimeError, match="giọng từng người nói"):
            omnivoice_tts.synthesize_batch_to_mp3([item], "fixture", language_id="vi", speaker_mode="multiple")
    prepare.assert_not_called()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"speaker_mode": "multiple", "items": [item]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="giọng từng người nói"):
        omnivoice_tts._worker_main(str(request_path))


def cache_video():
    return SimpleNamespace(speaker_mode="multiple", tts_voice="omnivoice:female", tts_provider="omnivoice-gpu",
                           target_language="vi", files={}, manual_tool_generations={})


def test_manual_and_auto_cache_keys_ignore_dormant_narrator_and_clone_settings():
    video = cache_video()
    segments = [{"segment_id": "line-1", "start": 11, "end": 13, "text": "Xin chào."}]
    with patch.object(manual_tools, "recognition_signature", return_value="same-source"):
        clips = manual_tools._voice_clip_signatures(video, segments)
        groups = manual_tools._voice_generation_groups(video, segments)
        auto = process_video._voice_checkpoint_signature(video, "same-transcript")
        video.tts_voice = "omnivoice:deep"
        video.files = {"voice_reference": "a-dormant-reference.wav", "voice_reference_transcript": "Unused."}
        assert manual_tools._voice_clip_signatures(video, segments) == clips
        assert manual_tools._voice_generation_groups(video, segments) == groups == {("omnivoice-gpu", "per-speaker"): [1]}
        assert process_video._voice_checkpoint_signature(video, "same-transcript") == auto
        video.tts_provider = "omnivoice"
        assert manual_tools._voice_clip_signatures(video, segments) != clips
        assert process_video._voice_checkpoint_signature(video, "same-transcript") != auto
        video.tts_provider = "omnivoice-gpu"
        with patch.object(manual_tools, "recognition_signature", return_value="new-source"):
            assert manual_tools._voice_clip_signatures(video, segments) != clips


def test_single_narrator_voice_changes_still_invalidate_manual_and_auto_cache():
    video = cache_video()
    video.speaker_mode = "single"
    segments = [{"segment_id": "line-1", "text": "Xin chào."}]
    clips = manual_tools._voice_clip_signatures(video, segments)
    auto = process_video._voice_checkpoint_signature(video, "same-transcript")
    video.tts_voice = "omnivoice:male"
    assert manual_tools._voice_clip_signatures(video, segments) != clips
    assert process_video._voice_checkpoint_signature(video, "same-transcript") != auto
    assert manual_tools._voice_generation_groups(video, segments) == {("omnivoice-gpu", "omnivoice:male"): [1]}


def test_explicit_segment_override_remains_separate_from_default_preset():
    video = cache_video()
    segments = [{"segment_id": "line-1", "text": "Xin chào."}]
    with patch.object(manual_tools, "recognition_signature", return_value="same-source"):
        original = manual_tools._voice_clip_signatures(video, segments)
        video.files = {"manual_voice_overrides": {"line-1": {"voice": "omnivoice:deep"}}}
        changed = manual_tools._voice_clip_signatures(video, segments)
        assert changed != original
        assert manual_tools._voice_generation_groups(video, segments) == {("omnivoice-gpu", "omnivoice:deep"): [1]}
        video.tts_voice = "omnivoice:male"
        assert manual_tools._voice_clip_signatures(video, segments) == changed


def test_manual_current_manifest_stays_ready_after_changing_only_narrator_default():
    video = cache_video()
    segments = [{"segment_id": "line-1", "text": "Xin chào."}]
    payload = {"speaker_mode": "multiple", "voice_configs": [
        {"provider": "omnivoice-gpu", "voice": "per-speaker", "segments": [1]}]}
    with (patch.object(manual_tools, "active_voice_record", return_value={"artifact_id": "voice"}),
          patch.object(manual_tools, "_active_signature", return_value="voice-key"),
          patch.object(manual_tools, "voice_signature", return_value="voice-key"),
          patch.object(manual_tools, "_load_segments", return_value=segments),
          patch.object(manual_tools, "_voice_manifest_payload", return_value=payload)):
        assert manual_tools._voice_ready(video, validate=False)
        video.tts_voice = "omnivoice:male"
        assert manual_tools._voice_ready(video, validate=False)
        video.speaker_mode = "single"
        assert not manual_tools._voice_ready(video, validate=False)


@pytest.mark.parametrize("provider", ["omnivoice", "omnivoice-gpu"])
def test_edited_subtitle_subset_reuses_persisted_source_mapping_after_reopening(tmp_path, provider):
    source = [{"start": index * 3, "end": index * 3 + 2, "text": f"Original speech {index}."}
              for index in range(4)]
    translated = [{**item, "segment_id": f"line-{index}", "text": f"Bản dịch câu {index}."}
                  for index, item in enumerate(source)]
    voices = ["omnivoice:male", "omnivoice:female_low", "omnivoice:male", "omnivoice:female_low"]
    mapped = [{**item, "speaker_id": f"speaker-{index % 2 + 1}", "speaker_voice": voice}
              for index, (item, voice) in enumerate(zip(source, voices))]
    source_path = tmp_path / "source.json"
    translated_path = tmp_path / "translated.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    translated_path.write_text(json.dumps(translated), encoding="utf-8")
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"unchanged source audio")
    video = SimpleNamespace(speaker_mode="multiple", files={"source_segments": str(source_path), "speech_audio": str(audio)})
    first_parts = tmp_path / "published-parts"
    edited_parts = tmp_path / "edited-parts"

    def synthesize(items, *_args, **_kwargs):
        for item in items:
            payload = f"{item['voice']}:{item['text']}".encode()
            from pathlib import Path
            Path(item["output_path"]).write_bytes(b"ID3" + payload + bytes(600))

    with (patch.object(tts, "get_video", return_value=video) as get_video,
          patch.object(tts, "log_to_video"),
          patch.object(speaker_identity, "verify_model") as verify,
          patch("hflow.services.external_tasks.run_external_task", return_value={"segments": mapped}) as engine,
          patch("hflow.services.external_engine.shared_external_engine_pool", return_value=Mock()),
          patch.object(omnivoice_tts, "synthesize_batch_to_mp3", side_effect=synthesize) as worker):
        tts.generate_voice_parts(str(translated_path), str(first_parts), "omnivoice:female", "fixture", provider=provider)
        original_items = {item["index"]: item for item in worker.call_args.args[0]}
        cache = next(tmp_path.glob("speaker-map-*.json"))
        original_cache = cache.read_bytes()
        old_audio = {index: (first_parts / f"voice_{index:04d}.mp3").read_bytes() for index in range(1, 5)}
        edited = [dict(item) for item in translated]
        for index in (1, 3):
            edited[index]["text"] = f"Nội dung đã sửa câu {index}."
        translated_path.write_text(json.dumps(edited), encoding="utf-8")
        edited_parts.mkdir()
        for index in (1, 3):
            shutil.copy2(first_parts / f"voice_{index:04d}.mp3", edited_parts / f"voice_{index:04d}.mp3")
        # A fresh metadata object represents leaving and reopening a project.
        get_video.return_value = SimpleNamespace(speaker_mode="multiple", files=dict(video.files))
        verify.side_effect = AssertionError("Cached source mapping must not need the identity model again")
        tts.generate_voice_parts(str(translated_path), str(edited_parts), "omnivoice:deep", "fixture",
                                 provider=provider, segment_indices=[2, 4])
        assert engine.call_count == 1
        assert verify.call_count == 1
        assert worker.call_count == 2
        regenerated = worker.call_args.args[0]
        assert [item["index"] for item in regenerated] == ["2", "4"]
        for item in regenerated:
            previous = original_items[item["index"]]
            assert (item["speaker_id"], item["voice"]) == (previous["speaker_id"], previous["voice"])
            assert item["source_text"] == previous["source_text"]
            assert item["text"] != previous["text"]
        assert cache.read_bytes() == original_cache
        assert json.loads(source_path.read_text(encoding="utf-8")) == source
        for index in (1, 3):
            assert (edited_parts / f"voice_{index:04d}.mp3").read_bytes() == old_audio[index]


def test_manual_scheduler_regenerates_only_text_edited_multispeaker_clips(tmp_path):
    video = cache_video()
    video.video_id = "edited-subset"
    video.project_type = "manual"
    video.active_artifacts = {}
    before = [{"segment_id": f"line-{index}", "start": index * 3, "end": index * 3 + 2,
               "text": f"Câu {index}."} for index in range(4)]
    after = [dict(item) for item in before]
    for index in (1, 3):
        after[index]["text"] = f"Câu đã sửa {index}."
    subtitle = {"artifact_id": "subtitle_document:edited", "resolved_outputs": {"segments": "edited.json"}}
    stage = tmp_path / "stage"
    stage.mkdir()
    published_audio = []
    for index in range(4):
        path = tmp_path / f"published-{index}.mp3"
        path.write_bytes(b"ID3" + bytes([index]) * 600)
        published_audio.append(path)
    with (patch.object(manual_tools, "recognition_signature", return_value="unchanged-source"),
          patch.object(manual_tools, "_load_segments", return_value=after),
          patch.object(manual_tools, "_current_subtitle_record", return_value=subtitle),
          patch.object(manual_tools, "ensure_narrator_anchor", return_value=""),
          patch.object(manual_tools.video_store, "get_video", return_value=video),
          patch.object(manual_tools, "published_voice_record", return_value={"signature": "old"}),
          patch.object(manual_tools, "published_voice_source_segments", return_value=before)):
        old_signatures = manual_tools._voice_clip_signatures(video, before)
        expected = manual_tools.voice_signature(video)

        def resolve(_video_id, kind, signature):
            if kind == "tts_clip" and signature in old_signatures:
                return {"resolved_outputs": {"audio": str(published_audio[old_signatures.index(signature)])}}
            return None

        def generate(_transcript, parts, _voice, _video_id, **options):
            from pathlib import Path
            for index in options["segment_indices"]:
                Path(parts, f"voice_{index:04d}.mp3").write_bytes(b"ID3" + b"regenerated" + bytes(600))

        def publish(*_args, **_kwargs):
            assert (stage / "parts/voice_0001.mp3").read_bytes() == published_audio[0].read_bytes()
            assert (stage / "parts/voice_0003.mp3").read_bytes() == published_audio[2].read_bytes()
            return {"resolved_outputs": {"manifest": str(stage / "manifest.json")}}

        with (patch.object(manual_tools.manual_artifacts, "resolve", side_effect=resolve),
              patch.object(manual_tools.manual_artifacts, "create_staging_directory", return_value=stage),
              patch.object(manual_tools.manual_artifacts, "publish", side_effect=publish),
              patch.object(manual_tools.manual_artifacts, "activate"),
              patch.object(manual_tools, "_publish_completed_voice_clips"),
              patch.object(manual_tools, "generate_voice_parts", side_effect=generate) as worker,
              patch.object(manual_tools, "voice_signature", return_value=expected),
              patch.object(manual_tools, "_update_files"),
              patch.object(manual_tools, "shutdown_hymt2_worker"),
              patch.object(manual_tools, "_release_recognition_runtime"),
              patch("hflow.core.memory.cpu_memory_constrained", return_value=False),
              patch.object(manual_tools.editor_documents, "mark_voice_clips_ready")):
            manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
        worker.assert_called_once()
        assert worker.call_args.kwargs["segment_indices"] == [2, 4]
