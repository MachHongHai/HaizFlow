import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import srt

from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.pipeline import manual_tools
from haizflow.pipeline.process_video import foreground_capability
from haizflow.schemas.editor import EditorDocument, EditorSequence, SourceEditDecision
from haizflow.schemas.video import VideoConfig, VideoInfo
from haizflow.services import editor_documents, manual_artifacts, subtitle_export, subtitle_import, video_store

SRT = "1\n00:00:01,234 --> 00:00:02,345\nHello world\nSecond line\n\n2\n00:00:03,000 --> 00:00:04,999\n你好\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    config = VideoConfig(project_type="manual", enable_audio_separation=True, translation_model="q4")
    video = VideoInfo(**config.model_dump(), video_id="import-srt", original_filename="video.mp4",
                      status="manual_ready", created_at="2026-10-14T00:00:00Z", updated_at="2026-10-14T00:00:00Z")
    source = tmp_path / "input" / "video.mp4"
    source.parent.mkdir()
    source.write_bytes(b"source identity")
    video.files["video_input"] = str(source)

    def update(_id, **changes):
        for key, value in changes.items():
            setattr(video, key, value)
        return video

    monkeypatch.setattr(video_store, "get_video_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(video_store, "get_video", lambda _: video)
    monkeypatch.setattr(video_store, "update_video", update)
    def save(restored):
        video.__dict__.update(deepcopy(restored.__dict__))
        return video
    monkeypatch.setattr(video_store, "save_video", save)
    monkeypatch.setattr(editor_documents, "get_video_duration", lambda _: 6)
    monkeypatch.setattr(video_store, "log_to_video", Mock())
    path = tmp_path / "external.srt"
    path.write_text(SRT, encoding="utf-8")
    return video, path


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-16-be"])
def test_import_unicode_multiline_and_exact_source_timestamps(encoding):
    data = SRT.encode(encoding)
    if encoding == "utf-16-be":
        data = b"\xfe\xff" + data
    segments = subtitle_import.parse_srt(data, duration_ms=6000)
    assert len(segments) == 2
    assert (segments[0]["start"], segments[0]["end"]) == (1.234, 2.345)
    assert segments[0]["text"] == "Hello world\nSecond line"
    assert segments[1]["text"] == "你好"
    assert segments[0]["segment_id"] != segments[1]["segment_id"]


@pytest.mark.parametrize("data", [b"", b"not SRT", b"\xffbad", SRT.replace("02,345", "00,345").encode(),
                                      SRT.replace("03,000", "00,100").encode(), b"1\n00:00:01,000 --> 00:00:02,000\n\n"])
def test_invalid_inputs_are_rejected_without_silently_skipping_cues(data):
    with pytest.raises(ValueError):
        subtitle_import.parse_srt(data)


def test_out_of_source_range_and_oversize_are_rejected():
    with pytest.raises(ValueError, match="thời lượng"):
        subtitle_import.parse_srt(SRT.encode(), duration_ms=4000)
    with pytest.raises(ValueError, match="8 MiB"):
        subtitle_import.parse_srt(b"x" * (subtitle_import.MAX_BYTES + 1))


def test_owned_import_survives_external_delete_reopen_and_leaves_other_caches_unchanged(project):
    video, path = project
    video.active_artifacts = {"recognition": "old-asr", "translation": "old-translation", "ocr_region": "ocr",
                              "tts_manifest": "voice", "audio_mix": "mix", "export": "render"}
    video.files["background_music"] = "keep music"
    assert subtitle_import.import_srt(video.video_id, str(path)) == 2
    path.unlink()
    reopened = video.model_copy(deep=True)
    assert len(subtitle_import.load_segments(reopened)) == 2
    assert video.active_artifacts.keys() == {"ocr_region", "subtitle_document"}
    assert len(manual_tools._load_segments(video)) == 2
    assert video.files["background_music"] == "keep music"
    assert video.target_language == "vi"


def test_imported_translation_never_calls_whisper_or_demucs_and_reuses_timestamps(project, monkeypatch):
    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    monkeypatch.setattr(manual_tools, "transcribe", Mock(side_effect=AssertionError("Whisper must not run")))
    monkeypatch.setattr(manual_tools, "separate_audio", Mock(side_effect=AssertionError("Demucs must not run")))
    monkeypatch.setattr(manual_tools, "_release_recognition_runtime", Mock())
    monkeypatch.setattr("haizflow.pipeline.omnivoice_tts.clear_runtime", Mock())
    monkeypatch.setattr("haizflow.services.external_engine.shared_external_engine_pool", lambda: SimpleNamespace(release=Mock()))
    captured = []

    def translate(source, target, *_args, **kwargs):
        segments = json.loads(Path(source).read_text(encoding="utf-8"))
        captured.extend(segments)
        for segment in segments:
            segment["source_text"] = segment["text"]
            segment["text"] = "Bản dịch"
        Path(target).write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(manual_tools, "translate_segments", translate)
    # Publication is exercised separately; keep this test free of render/font
    # dependencies and assert the exact translation input/output contract.
    publish = Mock()
    monkeypatch.setattr(manual_tools, "_replace_subtitles_from_translation", publish)
    assert manual_tools.tool_readiness(video, "translation")["canRun"]
    assert foreground_capability(video, "translation") == "translation"
    manual_tools._run_translation(video, SimpleNamespace(update=Mock()))
    assert len(captured) == 2
    assert captured[0]["end"] == 2.345
    assert captured[1]["start"] == 3
    publish.assert_called_once()
    result = json.loads(Path(publish.call_args.args[1]).read_text(encoding="utf-8"))
    assert result[0]["text"] == "Bản dịch"
    assert subtitle_import.load_segments(video)[0]["text"] == "Hello world\nSecond line"
    manual_artifacts.assert_root_idle(Path(video_store.get_video_dir(video.video_id)))


def test_rerun_import_signature_ignores_unused_asr_and_separation_choices(project):
    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    old = manual_tools.recognition_signature(video)
    video.enable_audio_separation = False
    video.speech_recognition_model = "large-v3-turbo"
    assert manual_tools.recognition_signature(video) == old
    video.manual_tool_generations["recognition"] += 1
    assert manual_tools.recognition_signature(video) != old


def test_reimport_invalidates_translation_only_and_invalid_import_keeps_previous(project):
    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    first = manual_tools.translation_signature(video)
    video.active_artifacts = {"ocr_region": "keep"}
    path.write_text("invalid", encoding="utf-8")
    with pytest.raises(ValueError):
        subtitle_import.import_srt(video.video_id, str(path))
    assert manual_tools.translation_signature(video) == first
    path.write_text(SRT.replace("Hello world", "New source"), encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path))
    assert manual_tools.translation_signature(video) != first
    assert video.active_artifacts.keys() == {"ocr_region", "subtitle_document"}


@pytest.mark.parametrize("problem", ["deleted", "modified", "replaced_source", "outside"])
def test_broken_import_never_silently_falls_back_to_whisper(project, monkeypatch, problem):
    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    imported = Path(video.files["imported_source_srt"]["segments"])
    if problem == "deleted":
        imported.unlink()
    elif problem == "modified":
        imported.write_bytes(b"[]")
    elif problem == "replaced_source":
        Path(video.files["video_input"]).write_bytes(b"different source")
    else:
        video.files["imported_source_srt"]["segments"] = str(path)
    transcribe = Mock(side_effect=AssertionError("Whisper fallback"))
    monkeypatch.setattr(manual_tools, "transcribe", transcribe)
    with pytest.raises(ValueError):
        manual_tools._run_recognition(video, SimpleNamespace(update=Mock()))
    transcribe.assert_not_called()


def test_original_export_follows_source_cuts_not_result_text(project):
    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    doc = EditorDocument(video_id=video.video_id, sequence=EditorSequence(duration_ms=2000,
        edit_decisions=[{"decision_id": "cut", "source_start_ms": 3000, "source_end_ms": 5000, "sequence_start_ms": 0}]))
    cue = next(srt.parse(subtitle_export.compose_source_srt(video, doc)))
    assert cue.content == "你好"
    assert cue.start.total_seconds() == 0
    assert cue.end.total_seconds() == 1.999


def test_import_busy_or_picker_cancel_leaves_project_unchanged(project, monkeypatch):
    video, path = project
    host = SimpleNamespace(isProcessing=True, appAlertRequested=SimpleNamespace(emit=Mock()), _selected_video=Mock())
    picker = Mock(return_value=("", ""))
    monkeypatch.setattr("haizflow.desktop.project_commands_controller.QFileDialog.getOpenFileName", picker)
    controller = ProjectCommandsController(host)
    assert not controller.import_selected_srt()
    host._selected_video.assert_not_called()
    picker.assert_not_called()
    host.isProcessing = False
    host._selected_video = lambda: video
    before = deepcopy(vars(video))
    assert not controller.import_selected_srt()
    assert vars(video) == before


def test_manual_preflight_needs_translation_pack_but_not_whisper_pack(project, monkeypatch):
    from haizflow.desktop.qml_controller import HaizFlowController

    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    video.speech_recognition_model = "large-v3-turbo"  # unused GPU ASR on a CPU app
    manager = Mock()
    manager.required_packs.return_value = ["translator-pack"]
    manager.missing_packs.return_value = ["translator-pack"]
    manager.requirement_summary.return_value = {"downloadBytes": 0, "requiredBytes": 0}
    host = SimpleNamespace(_selected_video=lambda: video, _project_type="manual",
        _settings_processing_device="cpu", _settings_language="vi", appAlertRequested=Mock(),
        _resource_packs=SimpleNamespace(manager=manager, _hardware_compatibility=lambda _pack: (True, "")))
    assert not HaizFlowController.runManualTool(host, "translation")
    assert [call.args[0] for call in manager.required_packs.call_args_list] == ["translation"]
    host.appAlertRequested.emit.assert_called_once()


def test_translation_publication_detaches_old_voice_and_keeps_ocr_music_and_original(project, monkeypatch):
    video, path = project
    video.subtitle_style = VideoConfig().subtitle_style
    subtitle_import.import_srt(video.video_id, str(path))
    video.active_artifacts = {"tts_manifest": "old", "audio_mix": "mix", "export": "render", "ocr_region": "ocr"}
    video.files.update(background_music="music file", voice_output="old.wav", manual_voice_overrides={})
    translated = path.parent / "translated.json"
    segments = subtitle_import.load_segments(video)
    for segment in segments:
        segment["text"] = "Kết quả dịch"
    translated.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
    manual_tools._replace_subtitles_from_translation(video.video_id, str(translated))
    assert video.active_artifacts["ocr_region"] == "ocr"
    assert not {"tts_manifest", "audio_mix", "export"}.intersection(video.active_artifacts)
    assert video.files["background_music"] == "music file"
    assert "voice_output" not in video.files
    assert video.subtitle_language == "vi"
    assert subtitle_import.load_segments(video)[0]["text"] == "Hello world\nSecond line"


def test_actual_source_replacement_clears_import_and_does_not_reuse_its_cues(tmp_path, monkeypatch):
    from haizflow.services import project_store

    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setattr(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(tmp_path / "legacy"))
    video = video_store.create_video("srt-replace-" + tmp_path.name, "old.mp4",
        VideoConfig(project_type="manual", project_directory=str(tmp_path)))
    Path(video.files["video_input"]).write_bytes(b"old media")
    path = tmp_path / "input.srt"
    path.write_text(SRT, encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path))
    assert subtitle_import.has_import(video_store.get_video(video.video_id))
    replacement = tmp_path / "new.mp4"
    replacement.write_bytes(b"new media")
    replaced = video_store.replace_video_input(video.video_id, str(replacement))
    assert not subtitle_import.has_import(replaced)
    assert subtitle_export.compose_source_srt(replaced) == ""


def test_import_is_immediately_visible_and_voice_ready_without_translation(project):
    video, path = project
    path.write_text(SRT.replace("你好", "Goodbye"), encoding="utf-8")
    video.target_language = "zh"
    subtitle_import.import_srt(video.video_id, str(path), language="en")
    document = editor_documents.load(video.video_id)
    captions = [clip for clip in document.clips if clip.track_id == "subtitles"]
    assert [clip.name for clip in captions] == ["Hello world\nSecond line", "Goodbye"]
    assert captions[0].start_ms == 1234 and captions[1].duration_ms == 1999
    assert manual_tools.tool_readiness(video, "voice")["canRun"]
    assert not subtitle_import.voice_notice(video, "vieneu-gpu", manual_tools._load_segments(video))
    assert video.subtitle_language == "en" and video.target_language == "zh"


def test_remove_legacy_srt_clears_text_voice_and_prevents_old_cache_resurrection(project):
    video, path = project
    # Exact legacy descriptor shape found in fkfk: no baseline/restore snapshot.
    subtitle_import.import_srt(video.video_id, str(path), language="zh")
    record = video.files["imported_source_srt"]
    video.files["imported_source_srt"] = {key: record[key] for key in ("segments", "source", "digest", "name")}
    video.active_artifacts.update(recognition="old-asr", translation="old-translation", tts_manifest="old-voice",
                                  audio_mix="old-mix", export="old-export", ocr_region="keep-ocr", separation="keep-separation")
    video.files.update(background_music="keep-music", watermark_image="keep-watermark", source_audio="keep-audio",
                       voice_output="old-voice.wav", final_video="old-render.mp4")
    video.manual_completed_stages = ["source", "image", "translation", "subtitle", "voice", "timeline", "render"]
    before_recognition = manual_tools.recognition_signature(video)
    current = editor_documents.load(video.video_id)
    current.sequence.edit_decisions = [SourceEditDecision(decision_id="cut", source_start_ms=1000,
        source_end_ms=5000, sequence_start_ms=0)]
    editor_documents.save(video, current)
    assert subtitle_import.remove_srt(video.video_id)
    assert not subtitle_import.has_import(video)
    assert not subtitle_import.TEXT_FILES.intersection(video.files)
    assert video.active_artifacts == {"ocr_region": "keep-ocr", "separation": "keep-separation"}
    assert video.files["background_music"] == "keep-music" and video.files["watermark_image"] == "keep-watermark"
    assert video.manual_completed_stages == ["source", "image"]
    assert manual_tools.recognition_signature(video) != before_recognition
    assert not manual_tools._load_segments(video)
    assert not manual_tools.tool_readiness(video, "voice")["canRun"]
    video.enable_audio_separation = False  # Fake separation fixture has no valid media files.
    assert manual_tools.tool_readiness(video, "translation")["canRun"]
    reopened = editor_documents.ensure(video)
    assert not any(clip.track_id in {"subtitles", "voice"} for clip in reopened.clips)
    assert reopened.sequence.edit_decisions == current.sequence.edit_decisions
    assert not Path(record["segments"]).parent.exists()
    assert path.exists()  # External SRT never belongs to the app.
    assert not manual_tools.migrate_legacy_artifacts(video.video_id)
    assert not subtitle_import.remove_srt(video.video_id)


def test_remove_does_not_restore_old_results_and_reimport_starts_clean(project):
    video, path = project
    video.active_artifacts = {"recognition": "prior", "tts_manifest": "prior-voice", "ocr_region": "keep"}
    subtitle_import.import_srt(video.video_id, str(path))
    first = Path(video.files["imported_source_srt"]["segments"]).parent
    assert subtitle_import.remove_srt(video.video_id)
    assert video.active_artifacts == {"ocr_region": "keep"}
    assert not first.exists()
    path.write_text("1\n00:00:02,000 --> 00:00:04,000\nXin chào\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language="vi")
    assert [item["text"] for item in manual_tools._load_segments(video)] == ["Xin chào"]
    assert len([clip for clip in editor_documents.load(video.video_id).clips if clip.track_id == "subtitles"]) == 1


def test_reimport_removes_only_previous_owned_input_and_detaches_voice(project):
    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    first = Path(video.files["imported_source_srt"]["segments"]).parent
    prior_generation = video.manual_tool_generations["voice"]
    video.active_artifacts["tts_manifest"] = "existing-voice"
    subtitle_import.import_srt(video.video_id, str(path))
    second = Path(video.files["imported_source_srt"]["segments"]).parent
    assert first != second and not first.exists() and second.exists()
    assert "tts_manifest" not in video.active_artifacts
    assert video.manual_tool_generations["voice"] == prior_generation + 1
    assert path.exists()


@pytest.mark.parametrize("operation", ["import", "remove"])
def test_editor_save_failure_rolls_back_metadata_and_existing_document(project, monkeypatch, operation):
    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    before_video = video.model_dump()
    before_document = editor_documents.load(video.video_id).model_dump()
    save = editor_documents.save
    calls = 0
    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("WinError 32: test lock")
        return save(*args, **kwargs)
    monkeypatch.setattr(editor_documents, "save", fail_once)
    with pytest.raises(PermissionError):
        if operation == "import":
            path.write_text(SRT.replace("Hello", "New"), encoding="utf-8")
            subtitle_import.import_srt(video.video_id, str(path))
        else:
            subtitle_import.remove_srt(video.video_id)
    assert video.model_dump() == before_video
    assert editor_documents.load(video.video_id).model_dump() == before_document
    assert len(list((path.parent / "input" / "subtitles").iterdir())) == 1


@pytest.mark.parametrize("language,text,provider,blocked", [
    ("vi", "Xin chào", "vieneu-gpu", False), ("en", "Hello", "vieneu-cpu", False),
    ("zh", "你好", "vieneu-gpu", True), ("en", "你好", "vieneu-cpu", True),
    ("zh", "你好", "omnivoice", False), ("zh", "你好", "edge-tts", False),
    ("und", "Bonjour", "omnivoice", True), ("en", "こんにちは", "omnivoice", True)])
def test_direct_voice_validates_actual_srt_language(project, language, text, provider, blocked):
    video, path = project
    path.write_text(f"1\n00:00:01,000 --> 00:00:02,000\n{text}\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language=language)
    assert bool(subtitle_import.voice_notice(video, provider, manual_tools._load_segments(video))) == blocked


def test_import_maps_source_cues_through_current_cuts(project):
    video, path = project
    document = EditorDocument(video_id=video.video_id, sequence=EditorSequence(duration_ms=2000,
        edit_decisions=[{"decision_id": "cut", "source_start_ms": 3000, "source_end_ms": 5000, "sequence_start_ms": 0}]))
    editor_documents.save(video, document)
    subtitle_import.import_srt(video.video_id, str(path), language="zh")
    result = manual_tools._load_segments(video)
    assert len(result) == 1 and result[0]["text"] == "你好"
    assert (result[0]["start"], result[0]["end"]) == (0, 1.999)
    assert subtitle_import.load_segments(video)[1]["start"] == 3


@pytest.mark.parametrize("cancel,busy,stale", [(True, False, False), (False, True, False), (False, False, True), (False, False, False)])
def test_remove_controller_confirms_guards_and_refreshes(project, monkeypatch, cancel, busy, stale):
    from haizflow.desktop.localization import QMessageBox
    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    host = SimpleNamespace(isProcessing=busy, _selected_video=lambda: video,
                           appAlertRequested=SimpleNamespace(emit=Mock()))
    controller = ProjectCommandsController(host)
    refresh = Mock()
    monkeypatch.setattr(controller, "_refresh_srt_workspace", refresh)
    question = Mock(return_value=QMessageBox.StandardButton.No if cancel else QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "question", question)
    success = not (cancel or busy or stale)
    assert controller.remove_selected_srt("another-project" if stale else video.video_id) == success
    assert subtitle_import.has_import(video) != success
    assert refresh.call_count == int(success)
    assert question.call_count == int(not (busy or stale))


def test_subtitle_autosave_blocks_import_remove_but_does_not_block_export():
    host = SimpleNamespace(_manual_subtitles=SimpleNamespace(_states={"cue": "saving"}))
    controller = ProjectCommandsController(host)
    assert controller._srt_busy(editing=True)
    assert not controller._srt_busy()


def test_remove_never_deletes_external_or_other_project_files(project):
    video, path = project
    subtitle_import.import_srt(video.video_id, str(path))
    video.files["imported_source_srt"]["segments"] = str(path)
    assert subtitle_import.remove_srt(video.video_id)
    assert path.exists()


def test_remove_action_workspace_order_and_not_a_pipeline_stage():
    qml = Path("src/haizflow/desktop/qml/ManualWorkspace.qml").read_text(encoding="utf-8")
    assert qml.index('label: qsTr("Nhập SRT")') < qml.index('label: qsTr("Xóa SRT")') < qml.index('label: qsTr("Xuất SRT")')
    assert 'else if (index === 10)' in qml and 'AppController.removeSelectedSrt(AppController.selectedVideoId)' in qml
    assert 'qsTr("Xóa SRT")' not in Path("src/haizflow/desktop/qml/SrtImportDialog.qml").read_text(encoding="utf-8")


@pytest.mark.parametrize("provider,fallback", [("vieneu", "omnivoice"), ("vieneu-gpu", "omnivoice-gpu")])
@pytest.mark.parametrize("declared", ["zh", "en", "und", ""])
def test_chinese_srt_import_selects_compatible_voice_before_dialog(project, provider, fallback, declared):
    video, path = project
    video.tts_provider = provider
    video.tts_voice = "vieneu:Hải Đăng"
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好世界\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language=declared)
    assert video.subtitle_language == "zh"
    assert video.tts_provider == fallback and video.tts_voice == "omnivoice:female_gentle"
    assert video.target_language == "vi"


@pytest.mark.parametrize("language,text", [("vi", "Xin chào"), ("en", "Hello")])
def test_supported_import_does_not_change_vieneu_choice(project, language, text):
    video, path = project
    video.tts_provider = "vieneu-gpu"
    video.tts_voice = "vieneu:Hải Đăng"
    path.write_text(f"1\n00:00:01,000 --> 00:00:02,000\n{text}\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language=language)
    assert video.tts_provider == "vieneu-gpu" and video.tts_voice == "vieneu:Hải Đăng"


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
@pytest.mark.parametrize("text", [
    "Tôi cảm ơn bạn đã đến thăm gia đình tôi hôm nay.",
    "Tôi cảm ơn bạn 王 đã đến thăm gia đình tôi hôm nay.",
    "Tôi cảm ơn bạn ユキ đã đến thăm gia đình tôi hôm nay.",
    "Tôi cảm ơn bạn 민 đã đến thăm gia đình tôi hôm nay.",
])
def test_vietnamese_srt_on_chinese_source_keeps_supported_vieneu(project, provider, text):
    from haizflow.services.subtitle_language import manual_subtitle_language

    video, path = project
    video.source_language = "zh"
    video.target_language = "zh"  # The next translation is not the imported captions.
    video.tts_provider, video.tts_voice = provider, "vieneu:Trúc Ly"
    path.write_text(f"1\n00:00:01,000 --> 00:00:02,000\n{text}\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language="vi")
    segments = manual_tools._load_segments(video)
    assert manual_subtitle_language(video, segments) == "vi"
    assert bool(subtitle_import.voice_notice(video, provider, segments)) == ("王" in text)
    assert video.tts_provider == provider and video.tts_voice == "vieneu:Trúc Ly"
    assert video.source_language == "zh" and video.target_language == "zh"


def test_decomposed_vietnamese_srt_is_detected_without_using_source_language(project):
    import unicodedata

    video, path = project
    video.source_language = "zh"
    video.tts_provider, video.tts_voice = "vieneu-gpu", "vieneu:Trúc Ly"
    text = unicodedata.normalize("NFD", "Người bạn trở về.")
    path.write_text(f"1\n00:00:01,000 --> 00:00:02,000\n{text}\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path))
    assert video.subtitle_language == "vi"
    assert subtitle_import.voice_notice(video, "vieneu-gpu", manual_tools._load_segments(video)) is None


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
def test_imported_vietnamese_reaches_voice_worker_as_vietnamese_on_chinese_video(project, monkeypatch, provider):
    video, path = project
    video.source_language = video.target_language = "zh"
    video.tts_provider, video.tts_voice = provider, "vieneu:Trúc Ly"
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\nTôi cảm ơn bạn Vương vì tất cả.\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language="vi")
    monkeypatch.setattr(manual_tools, "ensure_narrator_anchor", lambda _: "")
    monkeypatch.setattr(manual_tools, "shutdown_hymt2_worker", Mock())
    monkeypatch.setattr(manual_tools, "_release_recognition_runtime", Mock())
    monkeypatch.setattr(manual_tools, "_is_valid_mp3", lambda value: Path(value).is_file() and Path(value).stat().st_size > 0)
    monkeypatch.setattr(editor_documents, "mark_voice_clips_ready", Mock())
    monkeypatch.setattr("haizflow.core.memory.cpu_memory_constrained", lambda: False)
    requests = []

    def synthesize(source, output, voice, _identifier, **kwargs):
        requests.append((voice, kwargs["provider"], kwargs["target_language"]))
        for index in kwargs["segment_indices"]:
            Path(output, f"voice_{index:04d}.mp3").write_bytes(b"ID3 offline fixture")

    monkeypatch.setattr(manual_tools, "generate_voice_parts", synthesize)
    manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert requests == [("vieneu:Trúc Ly", provider, "vi")]
    assert manual_tools.published_voice_record(video, validate=True)
    assert video.source_language == video.target_language == "zh"


@pytest.mark.parametrize("language,text", [
    ("zh", "你好世界，这是中文字幕。"), ("ja", "私は日本語の字幕です。"),
    ("ko", "이것은 한국어 자막입니다"), ("ru", "Это русские субтитры"),
    ("ar", "هذه ترجمة باللغة العربية"), ("th", "นี่คือคำบรรยายภาษาไทย"),
    ("hi", "यह हिंदी उपशीर्षक है"),
])
def test_predominant_foreign_script_stays_detected_and_blocked_for_vieneu(project, language, text):
    video, path = project
    assert subtitle_import.detect_language([{"text": text}]) == language
    path.write_text(f"1\n00:00:01,000 --> 00:00:02,000\n{text}\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language="vi")
    assert subtitle_import.voice_notice(video, "vieneu-gpu", manual_tools._load_segments(video))


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
@pytest.mark.parametrize("ui_language", ["vi", "en"])
def test_blocking_chinese_notice_identifies_srt_and_actionable_cue(project, provider, ui_language):
    video, path = project
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好世界\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language="vi")
    title, message = subtitle_import.voice_notice(video, provider, manual_tools._load_segments(video), ui_language)
    assert "SRT" in title and "SRT" in message
    assert "1: “你好世界”" in message
    assert "OmniVoice/Edge TTS" in message
    assert "không hỗ trợ giọng đọc tiếng Việt" not in message
    if ui_language == "vi":
        assert "VieNeu hỗ trợ tiếng Việt" in message
        assert "không tự dịch nội dung SRT" in message
    else:
        assert "VieNeu supports Vietnamese" in message
        assert "does not translate the SRT" in message


def test_mixed_srt_blocks_vieneu_until_all_han_characters_are_removed(project):
    video, path = project
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\nTôi cảm ơn bạn đã giúp đỡ.\n\n"
                    "2\n00:00:03,000 --> 00:00:04,000\nChào bạn 王明.\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language="vi")
    segments = manual_tools._load_segments(video)
    assert subtitle_import.voice_notice(video, "vieneu-gpu", segments)
    assert subtitle_import.voice_notice(video, "vieneu", segments)
    assert subtitle_import.voice_notice(video, "omnivoice", segments) is None
    assert subtitle_import.voice_notice(video, "edge", segments) is None
    _title, message = subtitle_import.chinese_text_notice(video, segments)
    assert "2: “王明”" in message
    assert "Không thể tạo giọng VieNeu" in message and "phiên âm" in message
    assert subtitle_import.chinese_text_notice(video, [{"text": "Đã dịch hết sang tiếng Việt."}]) is None
    assert subtitle_import.voice_notice(video, "vieneu-gpu", [{"text": "Đã dịch hết sang tiếng Việt."}]) is None


def test_srt_script_notice_is_bounded_and_does_not_blame_chinese_source_video():
    video = SimpleNamespace(files={"imported_source_srt": {}}, source_language="zh")
    assert subtitle_import.chinese_text_notice(video, [{"text": "你好"}]) is None
    video.files["imported_source_srt"] = {"name": "captions.srt"}
    assert subtitle_import.chinese_text_notice(video, [{"text": "Phụ đề tiếng Việt."}]) is None
    title, message = subtitle_import.chinese_text_notice(video, [{"text": "王" * 1000}] * 50000)
    assert len(message) < 800
    assert "1: “" in message and "3: “" in message and "4: “" not in message
    assert "SRT" in title


def test_declared_chinese_without_han_explains_srt_language_setting():
    video = SimpleNamespace(files={"imported_source_srt": {"name": "captions.srt"}}, subtitle_language="zh")
    title, message = subtitle_import.voice_notice(video, "vieneu", [{"text": "Xin chào bạn."}])
    assert "SRT" in title and "được gán ngôn ngữ tiếng Trung" in message
    assert "nhập lại SRT" in message
    assert "còn chữ Hán" not in message


def test_chinese_srt_ui_and_worker_use_same_reason_before_loading_tts(project, monkeypatch):
    from haizflow.desktop.qml_controller import HaizFlowController

    video, path = project
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好世界\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language="vi")
    video.tts_provider = "vieneu-gpu"
    host = SimpleNamespace(_selected_video=lambda: video, _settings_language="vi", appAlertRequested=Mock())
    assert not HaizFlowController.validateTtsProviderForLanguage(host, "vi", "vieneu-gpu")
    title, message, severity = host.appAlertRequested.emit.call_args.args
    assert "SRT" in title and "你好世界" in message and severity == "warning"
    anchor = Mock(side_effect=AssertionError("TTS preparation must not start"))
    monkeypatch.setattr(manual_tools, "ensure_narrator_anchor", anchor)
    with pytest.raises(ValueError) as failure:
        manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
    assert str(failure.value) == message
    anchor.assert_not_called()


@pytest.mark.parametrize("provider,han,warning", [("vieneu-gpu", True, True), ("vieneu", False, False),
                                                 ("omnivoice", True, False)])
def test_import_success_warns_once_about_mixed_srt_without_rejecting_it(project, monkeypatch, provider, han, warning):
    video, path = project
    video.tts_provider = provider
    text = "Tôi cảm ơn bạn 王明 đã giúp đỡ gia đình." if han else "Tôi cảm ơn bạn đã giúp đỡ gia đình."
    path.write_text(f"1\n00:00:01,000 --> 00:00:02,000\n{text}\n", encoding="utf-8")
    host = SimpleNamespace(_selected_video=lambda: video, _settings_language="vi",
                           appAlertRequested=SimpleNamespace(emit=Mock()))
    controller = ProjectCommandsController(host)
    monkeypatch.setattr(controller, "_srt_busy", lambda **_: False)
    monkeypatch.setattr(controller, "_srt_duration", lambda _: 6000)
    monkeypatch.setattr(controller, "_refresh_srt_workspace", Mock())
    assert controller.import_selected_srt(str(path), "vi", video.video_id)
    assert subtitle_import.has_import(video)
    host.appAlertRequested.emit.assert_called_once()
    title, message, severity = host.appAlertRequested.emit.call_args.args
    assert title.startswith("Đã nhập SRT")
    assert severity == ("warning" if warning else "info")
    if warning:
        assert "王明" in message and "SRT" in message


def test_srt_refresh_synchronizes_fallback_voice_without_discarding_other_drafts(project):
    video, path = project
    video.tts_provider = "omnivoice-gpu"
    video.tts_voice = "omnivoice:female_gentle"
    host = SimpleNamespace(_tts_provider="vieneu-gpu", _tts_voice="vieneu:Hải Đăng",
        _manual_settings_drafts={video.video_id: VideoConfig(watermark_text="pending watermark", output_speed=1.5)},
        selectedVideoChanged=Mock(), refreshVideos=Mock(), ttsProviderChanged=Mock(), ttsVoiceChanged=Mock(),
        ttsProviderOptionsChanged=Mock(), ttsVoiceOptionsChanged=Mock())
    ProjectCommandsController(host)._refresh_srt_workspace(video.video_id)
    assert host._tts_provider == "omnivoice-gpu" and host._tts_voice == "omnivoice:female_gentle"
    draft = host._manual_settings_drafts[video.video_id]
    assert draft.tts_provider == "omnivoice-gpu" and draft.watermark_text == "pending watermark" and draft.output_speed == 1.5


def test_force_full_voice_rerun_bypasses_old_sentence_cache_even_without_manifest(project, monkeypatch):
    video, path = project
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\nXin chào\n", encoding="utf-8")
    subtitle_import.import_srt(video.video_id, str(path), language="vi")
    video.speaker_mode = "multiple"
    before = manual_tools._voice_clip_signatures(video, manual_tools._load_segments(video))
    staging = manual_artifacts.create_staging_directory(video.video_id, "tts_clip")
    (staging / "voice.mp3").write_bytes(b"historical audio")
    cached = manual_artifacts.publish(video.video_id, "tts_clip", before[0], staging, {"audio": "voice.mp3"}, activate_artifact=False)
    unrelated = dict(video.active_artifacts)
    assert "tts_manifest" not in video.active_artifacts
    monkeypatch.setattr(manual_tools, "_requested_artifact", Mock(side_effect=AssertionError("Forced action must not require a manifest hit")))
    assert manual_tools.prepare_manual_rerun(video.video_id, "voice", force=True)
    after = manual_tools._voice_clip_signatures(video, manual_tools._load_segments(video))
    assert after != before and manual_artifacts.resolve(video.video_id, "tts_clip", after[0]) is None
    assert Path(cached["resolved_outputs"]["audio"]).read_bytes() == b"historical audio"
    assert video.active_artifacts == unrelated
