"""Replacement must isolate the new media from editor state and idle writes."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.schemas.editor import EditorClip, EditorTrack
from haizflow.schemas.video import VideoConfig
from haizflow.services import editor_documents, editor_view_state, project_store, video_store


def test_manual_replacement_clears_layers_assets_drafts_and_preserves_model_choices(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setattr(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(tmp_path / "legacy"))
    monkeypatch.setattr(editor_documents, "get_video_duration", lambda _: 10)
    config = VideoConfig(project_type="manual", project_name="Reset", project_directory=str(tmp_path),
                         watermark_text="OLD", speech_recognition_model="small-cpu", translation_model="q4",
                         gemini_translation_instructions="Bối cảnh của video cũ",
                         gemini_translation_glossary="Hai nhân vật là vợ chồng",
                         gemini_translation_style="literal")
    video = video_store.create_video(f"reset-{tmp_path.name}", "old.mp4", config)
    Path(video.files["video_input"]).write_bytes(b"old input")
    video.files["background_music"] = str(tmp_path / "old.mp3")
    video_store.save_video(video)
    old = editor_documents.ensure(video)
    old.tracks.append(EditorTrack(track_id="old-cover", kind="ocr", name="Old", order=0))
    old.clips.append(EditorClip(clip_id="old-cover", track_id="old-cover", kind="ocr", duration_ms=4000))
    editor_documents.save(video, old)
    editor_view_state.save(video.video_id, {"stage": 7})
    source = tmp_path / "new.mp4"
    source.write_bytes(b"new input")
    replaced = video_store.replace_video_input(video.video_id, str(source))
    clean = editor_documents.ensure(replaced)
    assert not {"watermark-1", "music-1", "old-cover"}.intersection(c.clip_id for c in clean.clips)
    assert not any(c.kind in {"voice", "subtitle"} for c in clean.clips)
    assert clean.sequence.duration_ms == 10000
    assert replaced.speech_recognition_model == "small-cpu"
    assert replaced.translation_model == "q4"
    assert replaced.gemini_translation_instructions == replaced.gemini_translation_glossary == ""
    assert replaced.gemini_translation_style == "literal"
    assert replaced.manual_tool_generations == {"source": 1}
    # A rollback copy exists, but is never used as the new editor document.
    assert list((editor_documents.document_path(video.video_id).parent / "source-replacements").glob("*.json"))
    other_draft = {"watermark_text": "OTHER"}
    host = SimpleNamespace(_selected_video_id=video.video_id,
                           _manual_settings_drafts={video.video_id: {"watermark_text": "OLD"}, "other": other_draft},
                           _editor_transform_drafts={"watermark-1": {}}, _manual_cache_indexed={video.video_id},
                           _manual_edit_history=Mock(), _manual_editor_document=Mock(), _manual_subtitles=Mock(),
                           _select_video=Mock(), _manual_voice_video_id=video.video_id,
                           _manual_voice_refresh_pending=True, _manual_voice_refresh_enabled=True)
    assert ProjectImportController(host)._reset_replaced_source_view(replaced)
    assert host._manual_settings_drafts == {"other": other_draft}
    assert host._editor_transform_drafts == {}
    assert host._manual_cache_indexed == set()
    assert not host._manual_voice_refresh_pending
    host._manual_editor_document.clear.assert_called_once()
    host._manual_editor_document.load.assert_called_once_with(replaced)
    host._manual_subtitles.reset_source.assert_called_once_with(video.video_id)
    host._select_video.assert_called_once_with(replaced)
    assert editor_view_state.load(video.video_id)["stage"] == 0


def test_source_generation_advances_on_every_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setattr(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(tmp_path / "legacy"))
    video = video_store.create_video(f"generation-{tmp_path.name}", "old.mp4",
                                    VideoConfig(project_type="manual", project_directory=str(tmp_path)))
    source = tmp_path / "same.mp4"
    source.write_bytes(b"same source")
    first = video_store.replace_video_input(video.video_id, str(source))
    second = video_store.replace_video_input(video.video_id, str(source))
    assert first.manual_tool_generations == {"source": 1}
    assert second.manual_tool_generations == {"source": 2}


def test_locked_old_temp_outputs_cannot_be_migrated_into_new_source(tmp_path, monkeypatch):
    import shutil
    from haizflow.pipeline import manual_tools
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setattr(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(tmp_path / "legacy"))
    video = video_store.create_video(f"locked-{tmp_path.name}", "old.mp4",
        VideoConfig(project_type="manual", project_directory=str(tmp_path)))
    temp = Path(video_store.get_video_dir(video.video_id)) / 'temp'
    temp.mkdir(exist_ok=True)
    stale = temp / 'vi_segments.json'
    stale.write_text('[{"start": 0, "end": 1, "text": "OLD SOURCE"}]', encoding='utf-8')
    source = tmp_path / 'new.mp4'
    source.write_bytes(b'new source')
    original = shutil.rmtree
    def locked(path, *args, **kwargs):
        if Path(path).name.startswith('.replace-input-'):
            return  # Simulate deferred cleanup of the quarantined old files.
        return original(path, *args, **kwargs)
    monkeypatch.setattr(video_store.shutil, 'rmtree', locked)
    replaced = video_store.replace_video_input(video.video_id, str(source))
    assert not stale.exists() and replaced.active_artifacts == {} and replaced.checkpoints == {}
    assert list(temp.parent.glob('.replace-input-*/old-temp/vi_segments.json'))
    assert replaced.manual_artifact_migration_version == 1
    assert not manual_tools.migrate_legacy_artifacts(video.video_id)
    assert video_store.get_video(video.video_id).active_artifacts == {}
    monkeypatch.setattr(editor_documents, 'get_video_duration', lambda _: 1)
    document = editor_documents.ensure(replaced)
    assert not any(clip.kind in {'subtitle', 'voice'} for clip in document.clips)


def test_temp_rename_lock_rolls_back_source_metadata_and_music(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(project_store, 'PROJECT_INDEX_PATH', str(tmp_path / 'projects.json'))
    monkeypatch.setattr(video_store, 'LEGACY_VIDEO_WORKSPACES_DIR', str(tmp_path / 'legacy'))
    video = video_store.create_video(f'rollback-{tmp_path.name}', 'old.mp4',
        VideoConfig(project_directory=str(tmp_path)))
    original_input = Path(video.files['video_input'])
    original_input.write_bytes(b'OLD VIDEO')
    music = original_input.parent / 'background_music.wav'
    music.write_bytes(b'OLD MUSIC')
    video.files['background_music'] = str(music)
    video.status = 'done'
    video_store.save_video(video)
    temp = original_input.parent.parent / 'temp'
    temp.mkdir(exist_ok=True)
    old_segments = temp / 'vi_segments.json'
    old_segments.write_text('[]', encoding='utf-8')
    source = tmp_path / 'new.mp4'
    source.write_bytes(b'NEW VIDEO')
    original_replace = os.replace
    def locked(old, new):
        if Path(old) == temp:
            raise PermissionError(32, 'isolated Windows sharing violation')
        return original_replace(old, new)
    monkeypatch.setattr(video_store.os, 'replace', locked)
    with pytest.raises(PermissionError):
        video_store.replace_video_input(video.video_id, str(source))
    restored = video_store.get_video(video.video_id)
    assert restored.status == 'done' and restored.original_filename == 'old.mp4'
    assert original_input.read_bytes() == b'OLD VIDEO' and music.read_bytes() == b'OLD MUSIC'
    assert old_segments.exists() and restored.files['background_music'] == str(music)


@pytest.mark.parametrize('project_type', ['single', 'manual'])
def test_replaced_source_mixes_without_stale_music_then_accepts_new_music(tmp_path, monkeypatch, project_type):
    import subprocess
    from pydub import AudioSegment
    from pydub.generators import Sine
    from haizflow.pipeline import audio_timeline, process_video
    from haizflow.services.desktop_videos import set_desktop_background_music
    from haizflow.utils.ffmpeg import _binary
    monkeypatch.setattr(project_store, 'PROJECT_INDEX_PATH', str(tmp_path / 'projects.json'))
    monkeypatch.setattr(video_store, 'LEGACY_VIDEO_WORKSPACES_DIR', str(tmp_path / 'legacy'))
    video = video_store.create_video(f'mix-{tmp_path.name}', 'old.mp4',
        VideoConfig(project_type=project_type, project_directory=str(tmp_path)))
    Path(video.files['video_input']).write_bytes(b'old input')
    music = tmp_path / 'music.wav'
    Sine(880, sample_rate=48000).to_audio_segment(duration=500).export(music, format='wav')
    old_music = set_desktop_background_music(video, str(music))
    video = video_store.get_video(video.video_id)
    video.checkpoints = {'timeline': 'OLD', 'voice': 'OLD', 'translation': 'OLD'}
    video.active_artifacts = {'tts_manifest': 'OLD', 'ocr_region': 'OLD'}
    video_store.save_video(video)
    source = tmp_path / 'new.mp4'
    subprocess.run([_binary('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'color=blue:size=128x72:rate=5:duration=1', '-f', 'lavfi', '-i',
        'sine=frequency=440:sample_rate=48000:duration=1', '-c:v', 'libx264', '-c:a', 'aac',
        '-shortest', str(source)], check=True, capture_output=True, timeout=20)
    replaced = video_store.replace_video_input(video.video_id, str(source))
    assert 'background_music' not in replaced.files and not Path(old_music).exists()
    assert not process_video._checkpoint_valid(replaced, 'timeline', 'OLD', [replaced.files['voice_output']])
    assert replaced.processing_configuration == {} and replaced.active_artifacts == {}
    segments = tmp_path / 'segments.json'
    segments.write_text('[]', encoding='utf-8')
    monkeypatch.setattr(AudioSegment, 'converter', _binary('ffmpeg'))
    # Real FFmpeg decode and real audio mixing, with no expensive AI models.
    for add_music in (False, True):
        if add_music:
            set_desktop_background_music(replaced, str(music))
            replaced = video_store.get_video(video.video_id)
        output = tmp_path / f'mix-{add_music}.wav'
        audio_timeline.build_audio_timeline(str(segments), str(tmp_path / 'voice-parts'),
            replaced.files['video_input'], str(output), replaced.video_id,
            background_audio_path=replaced.files['video_input'],
            background_music_path=replaced.files.get('background_music'), require_voice_parts=False)
        audio = AudioSegment.from_wav(output)
        assert 900 <= len(audio) <= 1100 and audio.rms > 100
