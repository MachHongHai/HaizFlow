"""Offline tests: stable dialogue context must not add API calls or cross projects."""

import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline import manual_tools, process_video
from haizflow.schemas.video import VideoConfig, VideoInfo
from haizflow.services import batch_settings, gemini_context, project_store, translation, video_export, video_store
from haizflow.services import gemini_translation as gemini
from haizflow.services.processing_resume import configuration_snapshot


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setattr(gemini, "active_key", lambda: "offline-fixture")
    monkeypatch.setattr(gemini, "check_cancellation", lambda _: None)
    monkeypatch.setattr(gemini, "is_paused", lambda _: False)
    monkeypatch.setattr(gemini, "log_to_video", Mock())


def test_later_batches_receive_bilingual_memory_without_an_extra_request(online, monkeypatch):
    contexts = []

    def send(chunk, **kwargs):
        contexts.append(kwargs)
        return ["Vương Minh nói với cậu." for _ in chunk]

    monkeypatch.setattr(gemini, "_request_chunk", send)
    texts = [f"Sentence {index}" for index in range(30)]
    result = gemini.translate_texts(texts, model="gemini-3.8-flash", source_language="English",
        target_language="Vietnamese", video_id="a", translation_instructions="Bối cảnh hiện đại.",
        translation_glossary="王明 → Vương Minh; Minh và Lan: tôi – cậu.")
    assert len(result) == 30 and len(contexts) == 2
    assert contexts[1]["translation_context"]["accepted_examples"][0]["translation"] == "Vương Minh nói với cậu."
    assert all(item["translation_glossary"].startswith("王明") for item in contexts)
    resumed = [*result[:24], *([None] * 6)]
    contexts.clear()
    gemini.translate_texts(texts, model="gemini-3.8-flash", source_language="English",
                          target_language="Vietnamese", video_id="a", initial_translations=resumed)
    assert len(contexts) == 1
    assert contexts[0]["translation_context"]["accepted_examples"]
    contexts.clear()
    gemini.translate_texts(["A different project"], model="gemini-3.8-flash", source_language="English",
                          target_language="Vietnamese", video_id="b")
    assert contexts[0]["translation_context"]["accepted_examples"] == []


def test_http_retries_keep_guidance_and_context_in_separate_payload_parts(online, monkeypatch):
    requests = []

    def unavailable(request, **kwargs):
        requests.append(json.loads(request.data))
        raise HTTPError("https://invalid.test", 503, "Unavailable", {}, None)

    monkeypatch.setattr(gemini.request, "urlopen", unavailable)
    monkeypatch.setattr(gemini, "_retry_delay", lambda *_: None)
    with pytest.raises(RuntimeError, match="503"):
        gemini._request_chunk([(0, "Hello")], key="private-key", model="gemini-3.8-flash",
            source_language="English", target_language="Vietnamese", video_id="a",
            translation_instructions="Không đổi quan hệ nhân vật.", translation_glossary="Minh: tôi – cậu.",
            translation_context={"accepted_examples": [{"source": "Hi", "translation": "Chào cậu"}]})
    assert len(requests) == 3 and all(item == requests[0] for item in requests)
    system = requests[0]["systemInstruction"]["parts"][0]["text"]
    assert "Không đổi quan hệ nhân vật." not in system
    assert "never force one pronoun" in system
    assert json.loads(requests[0]["contents"][0]["parts"][0]["text"]) == [{"id": 0, "text": "Hello"}]
    assert json.loads(requests[0]["contents"][0]["parts"][1]["text"])["translation_guidance"] == {
        "background_and_style": "Không đổi quan hệ nhân vật.", "names_and_address": "Minh: tôi – cậu.", "style": "balanced"}
    assert "translation_context_only" in json.loads(requests[0]["contents"][0]["parts"][2]["text"])
    assert "private-key" not in str(gemini.log_to_video.call_args_list)


def test_sentence_repair_keeps_original_context_and_user_rules(tmp_path, monkeypatch):
    source, output = tmp_path / "source.json", tmp_path / "out.json"
    source.write_text(json.dumps([{"start": i, "end": i + .9, "text": text}
                                 for i, text in enumerate(["Hello", "Thanks"])]), encoding="utf-8")
    calls = []

    def fake(texts, **kwargs):
        calls.append(kwargs)
        return ["Chào bạn", "Cảm ơn"] if len(calls) == 1 else ["Cảm ơn cậu"]

    monkeypatch.setattr(gemini, "translate_texts", fake)
    monkeypatch.setattr(translation, "shutdown_hymt2_worker", lambda: None)
    monkeypatch.setattr(translation, "log_to_video", Mock())
    monkeypatch.setattr(translation, "_suspicious_translation_indexes", Mock(side_effect=[{1}, set()]))
    translation.translate_segments(str(source), str(output), "a", provider="gemini",
        translation_model="gemini-3.8-flash", translation_instructions="Hiện đại", translation_glossary="tôi – cậu",
        translation_style="adaptive")
    assert len(calls) == 2
    assert calls[1]["context_texts"] == ["Hello", "Thanks"]
    assert calls[1]["context_indices"] == [1]
    assert calls[1]["context_translations"][0] == "Chào bạn"
    assert calls[1]["translation_glossary"] == "tôi – cậu"
    assert all(call["translation_style"] == "adaptive" for call in calls)


def test_multi_batch_repair_never_anchors_on_rejected_translations(online, monkeypatch):
    contexts = []

    def send(chunk, **kwargs):
        contexts.append(kwargs["translation_context"])
        return ["Repaired name" for _ in chunk]

    monkeypatch.setattr(gemini, "_request_chunk", send)
    source = [f"Source {index}" for index in range(31)]
    gemini.translate_texts(source[:30], model="gemini-3.8-flash", source_language="English",
        target_language="Vietnamese", video_id="a", context_texts=source,
        context_translations=[*(["Rejected name"] * 30), "Accepted name"], context_indices=list(range(30)))
    assert len(contexts) == 2
    assert all(item["translation"] != "Rejected name" for context in contexts for item in context["accepted_examples"])
    assert contexts[0]["accepted_examples"][0]["source_id"] == 30
    assert any(item["translation"] == "Repaired name" for item in contexts[1]["accepted_examples"])


def test_changing_guidance_invalidates_durable_translation_checkpoint(tmp_path, monkeypatch):
    source, output = tmp_path / "source.json", tmp_path / "out.json"
    source.write_text('[{"start":0,"end":1,"text":"Hello"}]', encoding="utf-8")
    send = Mock(return_value=["Xin chào"])
    monkeypatch.setattr(gemini, "translate_texts", send)
    monkeypatch.setattr(translation, "shutdown_hymt2_worker", lambda: None)
    monkeypatch.setattr(translation, "log_to_video", Mock())
    for instructions, glossary, expected in [("A", "Minh", 1), ("A", "Minh", 1), ("B", "Minh", 2), ("B", "Lan", 3)]:
        translation.translate_segments(str(source), str(output), "a", provider="gemini",
            translation_model="gemini-3.8-flash", retain_checkpoint=True,
            translation_instructions=instructions, translation_glossary=glossary)
        assert send.call_count == expected


def test_resume_from_disk_keeps_completed_batches_and_dialogue_memory(online, tmp_path, monkeypatch):
    source, output, checkpoint = (tmp_path / name for name in ("source.json", "out.json", "partial.json"))
    source.write_text(json.dumps([{"start": i * 2, "end": i * 2 + 1.8, "text": f"Sentence {i}"}
                                 for i in range(30)]), encoding="utf-8")
    output.write_text('[{"text":"Published subtitles"}]', encoding="utf-8")
    calls = []

    def interrupted(chunk, **kwargs):
        calls.append((chunk, kwargs))
        if len(calls) == 2:
            raise RuntimeError("Paused fixture")
        return ["Vương Minh chào cậu." for _ in chunk]

    monkeypatch.setattr(gemini, "_request_chunk", interrupted)
    monkeypatch.setattr(translation, "shutdown_hymt2_worker", lambda: None)
    monkeypatch.setattr(translation, "log_to_video", Mock())
    monkeypatch.setattr(translation, "_suspicious_translation_indexes", lambda *_args, **_kwargs: set())
    options = dict(provider="gemini", translation_model="gemini-3.8-flash", checkpoint_path=str(checkpoint),
                   translation_instructions="Hiện đại", translation_glossary="王明 → Vương Minh")
    with pytest.raises(RuntimeError, match="Paused fixture"):
        translation.translate_segments(str(source), str(output), "a", **options)
    assert sum(value is not None for value in json.loads(checkpoint.read_text(encoding="utf-8"))["translations"]) == 24
    assert json.loads(output.read_text(encoding="utf-8"))[0]["text"] == "Published subtitles"
    translation.translate_segments(str(source), str(output), "a", **options)
    assert len(calls) == 3 and [index for index, _ in calls[-1][0]] == list(range(24, 30))
    context = calls[-1][1]["translation_context"]
    assert context["accepted_examples"][0]["translation"] == "Vương Minh chào cậu."
    assert calls[-1][1]["translation_glossary"] == "王明 → Vương Minh"
    assert not checkpoint.exists()


@pytest.mark.parametrize("model", ["q4", "gemini-3.8-flash"])
def test_guidance_changes_only_gemini_cache_and_resume_identity(tmp_path, monkeypatch, model):
    config = VideoConfig(project_type="manual", translation_model=model)
    video = VideoInfo(**config.model_dump(), video_id="a", original_filename="a.mp4",
        status="manual_ready", created_at="2026-10-24T00:00:00Z",
        updated_at="2026-10-24T00:00:00Z", manual_target_tool="translation")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    video.files["video_input"] = str(source)
    monkeypatch.setattr(manual_tools, "recognition_signature", lambda _: "unchanged-asr")
    before = (manual_tools.translation_signature(video), process_video._translation_signature(video, str(source)),
              configuration_snapshot(video, "cpu"))
    video.gemini_translation_instructions = "Không đổi tên nhân vật"
    after = (manual_tools.translation_signature(video), process_video._translation_signature(video, str(source)),
             configuration_snapshot(video, "cpu"))
    assert all((left != right) == model.startswith("gemini-") for left, right in zip(before, after))
    settings = batch_settings.values_for(video)
    assert batch_settings.config_for(settings).gemini_translation_instructions == video.gemini_translation_instructions


def test_context_is_bounded_and_excludes_the_sentences_being_repaired():
    texts = ["x" * 10000] * 1000
    memory = ["y" * 10000] * 1000
    context = gemini_context.request_context(texts, memory, [500])
    assert len(json.dumps(context)) < 10000
    assert all(item["source_id"] != 500 for item in context["accepted_examples"])


@pytest.mark.parametrize("owner,queued", [("other", False), ("a", True)])
def test_guidance_dialog_cannot_save_into_another_or_queued_video(owner, queued):
    host = SimpleNamespace(_selected_project_key="project", _selected_video_id="a",
                           _processing_queue=SimpleNamespace(contains=lambda _: queued))
    assert not HaizFlowController.saveGeminiTranslationGuidance(host, "project", owner, "new", "rules")


@pytest.mark.parametrize("saved", [True, False])
def test_guidance_save_trims_persists_and_restores_draft_on_failure(saved):
    host = SimpleNamespace(_selected_project_key="project", _selected_video_id="a",
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        geminiTranslationInstructions="before", geminiTranslationGlossary="old rules",
        _gemini_translation_instructions="before", _gemini_translation_glossary="old rules",
        _gemini_translation_style="literal",
        persistVideoSettingsFor=Mock(return_value=saved), _show_app_alert=Mock(),
        geminiGuidanceChanged=SimpleNamespace(emit=Mock()))
    assert HaizFlowController.saveGeminiTranslationGuidance(host, "project", "a", " new ", " rules ", "natural") == saved
    host.persistVideoSettingsFor.assert_called_once_with("a")
    assert (host._gemini_translation_instructions, host._gemini_translation_glossary) == (
        ("new", "rules") if saved else ("before", "old rules"))
    assert host._show_app_alert.call_count == int(not saved)
    assert host._gemini_translation_style == ("natural" if saved else "literal")
    host.geminiGuidanceChanged.emit.assert_called_once()


@pytest.mark.parametrize("model", ["q4", "gemini-3.8-flash"])
def test_empty_guidance_preserves_existing_render_identity(model, monkeypatch):
    video = VideoInfo(**VideoConfig(translation_model=model).model_dump(), video_id="a",
        original_filename="a.mp4", status="completed", created_at="2026-10-24T00:00:00Z",
        updated_at="2026-10-24T00:00:00Z")
    capture = Mock(return_value="render")
    monkeypatch.setattr(video_export.manual_artifacts, "signature", capture)
    monkeypatch.setattr(video_export.manual_artifacts, "file_state", lambda _: None)
    video_export.render_revision(video)
    config = capture.call_args.args[1]
    assert "gemini_translation_instructions" not in config
    assert "gemini_translation_glossary" not in config
    assert "gemini_translation_style" not in config
    assert "gemini_translation_guidance" not in config
    video.gemini_translation_instructions = "Modern setting"
    video_export.render_revision(video)
    configured = capture.call_args.args[1]
    if model.startswith("gemini-"):
        assert configured["gemini_translation_guidance"] == ("Modern setting", "")
    else:
        assert configured == config


def test_legacy_shared_batch_defaults_do_not_adopt_individual_guidance(monkeypatch):
    monkeypatch.setattr(batch_settings.project_store, "get_project", lambda _: {
        "project_type": "batch", "batch_settings": {"values": {"translationModel": "gemini-3.8-flash"}}})
    settings = batch_settings.stable_values("project", {
        "geminiTranslationInstructions": "An individual override", "geminiTranslationGlossary": "Minh"}, [])
    assert settings["geminiTranslationInstructions"] == settings["geminiTranslationGlossary"] == ""
    assert settings["geminiTranslationStyle"] == "balanced"


@pytest.mark.parametrize("project_type", ["manual", "single", "batch"])
def test_imported_video_retains_guidance_after_metadata_reload(tmp_path, monkeypatch, project_type):
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setattr(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(tmp_path / "legacy"))
    config = VideoConfig(project_type=project_type, project_directory=str(tmp_path),
        translation_model="gemini-3.8-flash", gemini_translation_instructions="Bối cảnh hiện đại.",
        gemini_translation_glossary="王明 → Vương Minh", gemini_translation_style="natural")
    video = video_store.create_video("guidance-import-" + tmp_path.name, "video.mp4", config)
    video_store._VIDEO_METADATA_CACHE.pop(video.video_id, None)
    loaded = video_store.get_video(video.video_id)
    assert loaded.gemini_translation_instructions == config.gemini_translation_instructions
    assert loaded.gemini_translation_glossary == config.gemini_translation_glossary
    assert loaded.gemini_translation_style == "natural"


def test_editing_guidance_preserves_published_voice_subtitles_and_recognition(monkeypatch):
    config = VideoConfig(project_type="manual", translation_model="gemini-3.8-flash")
    video = VideoInfo(**config.model_dump(), video_id="a", original_filename="a.mp4", status="manual_ready",
        created_at="2026-10-24T00:00:00Z", updated_at="2026-10-24T00:00:00Z",
        files={"voice_output": "published.wav", "srt_output": "published.srt"},
        manual_completed_stages=["translation", "subtitles", "voice", "timeline", "render"])
    config.gemini_translation_instructions = "New context"
    update, deactivate = Mock(), Mock()
    monkeypatch.setattr(video_store, "update_video", update)
    monkeypatch.setattr(manual_tools.manual_artifacts, "deactivate", deactivate)
    HaizFlowController._apply_config_to_video(SimpleNamespace(), video, config)
    deactivate.assert_called_once_with("a", {"translation"})
    changes = update.call_args.kwargs
    assert changes["gemini_translation_instructions"] == "New context"
    assert "files" not in changes
    assert changes.get("status", video.status) == "manual_ready"
    assert video.files["voice_output"] == "published.wav"
