"""Manual audio/export must honor audible editor clips or fail before rendering."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from hflow.pipeline import manual_tools
from hflow.schemas.editor import EditorAsset, EditorClip, EditorDocument, EditorTrack
from hflow.schemas.video import VideoConfig
from hflow.services import editor_documents


def _video():
    return SimpleNamespace(**VideoConfig().model_dump(), video_id="manual-voice-test",
                           active_artifacts={}, files={})


def _document(voice_path: str, music_path: str = ""):
    assets = [EditorAsset(asset_id="voice-a", kind="audio", path=voice_path)]
    tracks = [EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
              EditorTrack(track_id="voice", kind="voice", name="Giọng đọc")]
    clips = [EditorClip(clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                        segment_id="a", name="Xin chào", start_ms=1000, duration_ms=1000),
             EditorClip(clip_id="voice-a", track_id="voice", kind="voice", asset_id="voice-a",
                        segment_id="a", name="Xin chào", start_ms=1000, duration_ms=1000,
                        metadata={"state": "ready"})]
    if music_path:
        assets.append(EditorAsset(asset_id="music-a", kind="audio", path=music_path))
        tracks.append(EditorTrack(track_id="music", kind="music", name="Nhạc nền"))
        clips.append(EditorClip(clip_id="music-a", track_id="music", kind="audio", asset_id="music-a",
                                duration_ms=3000))
    return EditorDocument(video_id="manual-voice-test", tracks=tracks, clips=clips, assets=assets)


def test_pending_voice_choice_uses_published_editor_asset_even_with_music(tmp_path):
    voice = tmp_path / "voice.mp3"
    voice.write_bytes(b"existing voice")
    music = tmp_path / "music.mp3"
    music.write_bytes(b"music")
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    document = _document(str(voice), str(music))
    video = _video()
    video.files["video_input"] = str(source)
    video.tts_voice = "omnivoice:female"  # A new inspector choice is pending.
    with (patch.object(manual_tools, "published_voice_record", return_value=None),
          patch.object(manual_tools.manual_artifacts, "resolve", return_value=None),
          patch.object(manual_tools, "_audio_background", return_value=(str(source), "", [])),
          patch("hflow.pipeline.sequence_compiler.materialize_source_sequence",
                return_value=(str(source), str(source))),
          patch.object(manual_tools, "build_audio_timeline") as mix):
        manual_tools._compose_manual_audio(video, tmp_path / "mix.wav", tmp_path, document=document)
    assert (tmp_path / "editor-voice-parts" / "voice_0001.mp3").read_bytes() == b"existing voice"
    assert mix.call_args.kwargs["background_music_path"] == str(music)
    assert mix.call_args.kwargs["require_voice_parts"] is True


def test_real_manual_mix_keeps_voice_above_background_music(tmp_path):
    source = tmp_path / "source.wav"
    AudioSegment.silent(duration=3000, frame_rate=48000).export(source, format="wav").close()
    voice = tmp_path / "voice.mp3"
    (Sine(880).to_audio_segment(duration=900) - 3).export(voice, format="mp3").close()
    music = tmp_path / "music.wav"
    (Sine(220).to_audio_segment(duration=3000) - 18).export(music, format="wav").close()
    document = _document(str(voice), str(music))
    video = _video()
    video.files["video_input"] = str(source)
    output = tmp_path / "mix.wav"
    with (patch.object(manual_tools, "_audio_background", return_value=(str(source), "", [])),
          patch("hflow.pipeline.sequence_compiler.materialize_source_sequence",
                return_value=(str(source), str(source)))):
        manual_tools._compose_manual_audio(video, output, tmp_path, document=document)
    mixed = AudioSegment.from_wav(output)
    # The music is present throughout; the spoken window must gain energy.
    assert mixed[1100:1800].dBFS > mixed[100:800].dBFS + 5


@pytest.mark.parametrize("operation", ["audio", "export"])
def test_missing_enabled_voice_blocks_cached_mix_and_export(tmp_path, operation):
    document = _document(str(tmp_path / "missing.mp3"))
    video = _video()
    with (patch.object(editor_documents, "ensure", return_value=document),
          patch.object(manual_tools, "published_voice_record", return_value=None),
          patch.object(manual_tools.manual_artifacts, "resolve", return_value=None),
          patch.object(manual_tools, "build_audio_timeline") as mix,
          patch.object(manual_tools, "render_video") as render):
        with pytest.raises(RuntimeError, match="Thiếu âm thanh giọng đọc"):
            (manual_tools._run_audio if operation == "audio" else manual_tools._run_export)(
                video, SimpleNamespace(update=Mock()))
    mix.assert_not_called()
    render.assert_not_called()


def test_intentionally_muted_voice_allows_source_and_music_only(tmp_path):
    document = _document(str(tmp_path / "missing.mp3"))
    next(track for track in document.tracks if track.track_id == "voice").muted = True
    assert manual_tools._audible_manual_voice_sources(_video(), document) == {}


def test_audio_cache_key_changes_when_editor_voice_asset_changes(tmp_path):
    video = _video()
    document = _document(str(tmp_path / "voice-a.mp3"))
    with (patch.object(manual_tools, "_current_subtitle_record", return_value=None),
          patch.object(manual_tools, "published_voice_record", return_value=None),
          patch.object(manual_tools, "_audio_background", return_value=("", "", [])),
          patch.object(editor_documents, "load", return_value=document)):
        before = manual_tools.audio_signature(video, validate=False)
        document.assets[0].path = str(tmp_path / "voice-b.mp3")
        document.assets[0].fingerprint = "new-voice"
        after = manual_tools.audio_signature(video, validate=False)
    assert before != after


def test_ready_voice_asset_path_update_is_persisted(tmp_path):
    old = tmp_path / "old.mp3"
    old.write_bytes(b"old")
    new = tmp_path / "new.mp3"
    new.write_bytes(b"new")
    document = _document(str(old))
    document.assets[0].asset_id = "voice-asset-a"
    document.clips[1].asset_id = "voice-asset-a"
    with (patch.object(editor_documents, "ensure", return_value=document),
          patch.object(editor_documents, "save", side_effect=lambda _video, changed: changed) as save):
        updated = editor_documents.mark_voice_clips_ready(
            _video(), [{"segment_id": "a", "text": "Xin chào", "revision": 0}], {"a": str(new)})
    save.assert_called_once()
    assert updated.assets[0].path == str(new)


def test_multi_speaker_cache_refresh_does_not_claim_user_changed_voice():
    video = _video()
    video.speaker_mode = "multiple"
    video.status = "done"
    video.manual_target_tool = ""
    video.enable_audio_separation = False
    video.remove_original_subtitles = False
    groups = {("omnivoice", "omnivoice:male"): [1],
              ("omnivoice", "omnivoice:female"): [2]}
    published = {"signature": "older-voice", "resolved_outputs": {"manifest": "older.json"}}
    with (patch.object(manual_tools, "published_voice_record", return_value=published),
          patch.object(manual_tools, "active_voice_record", return_value=published),
          patch.object(manual_tools, "_voice_ready", return_value=False),
          patch.object(manual_tools, "_voice_manifest_payload", return_value={
              "voice_configs": [{"provider": provider, "voice": voice, "segments": indices}
                                for (provider, voice), indices in groups.items()],
              "speaker_mode": "multiple"}),
          patch.object(manual_tools, "_voice_generation_groups", return_value=groups),
          patch.object(manual_tools, "_load_segments", return_value=[{"text": "one"}, {"text": "two"}]),
          patch.object(manual_tools, "_translation_ready", return_value=True),
          patch.object(manual_tools, "_subtitle_ready", return_value=True),
          patch.object(manual_tools, "_audio_ready", return_value=False),
          patch.object(manual_tools, "export_signature", return_value="export-current"),
          patch.object(manual_tools, "_artifact_ready", return_value=False)):
        voice = next(row for row in manual_tools.tool_states(video) if row["toolId"] == "voice")
    assert "Lựa chọn giọng mới" not in voice["voiceNotice"]
    assert "Giọng đã tạo vẫn được dùng" in voice["voiceNotice"]
