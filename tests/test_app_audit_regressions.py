"""Offline regression cases discovered by the whole-app simulation/audit."""

from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

import pytest

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.services import video_store


def source(generation=1):
    return SimpleNamespace(video_id="a", created_at="2026-10-24T00:00:00Z",
                           manual_tool_generations={"source": generation})


@pytest.mark.parametrize("state", ["same", "replaced", "removed", "replacing"])
def test_guidance_save_is_bound_to_exact_source_and_never_mutates_stale_owner(monkeypatch, state):
    current = source(2 if state == "replaced" else 1) if state != "removed" else None
    monkeypatch.setattr(video_store, "get_video", lambda _: current)
    host = SimpleNamespace(_selected_project_key="project", _selected_video_id="a",
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        _project_import=SimpleNamespace(is_replacing_video=lambda _: state == "replacing"),
        geminiTranslationInstructions="", geminiTranslationGlossary="",
        _gemini_translation_instructions="", _gemini_translation_glossary="",
        _gemini_translation_style="literal", persistVideoSettingsFor=Mock(return_value=True),
        geminiGuidanceChanged=Mock(), _show_app_alert=Mock())
    key = HaizFlowController._video_source_key(source())
    result = HaizFlowController.saveGeminiTranslationGuidance(host, "project", "a", " old story ",
                                                            " old characters ", "literal", key)
    assert result is (state == "same")
    assert host.persistVideoSettingsFor.call_count == int(state == "same")
    assert host._gemini_translation_instructions == ("old story" if state == "same" else "")
    assert host._gemini_translation_glossary == ("old characters" if state == "same" else "")


def test_source_key_survives_settings_edits_but_not_replacement():
    video = source()
    before = HaizFlowController._video_source_key(video)
    video.updated_at = "2026-10-25T01:00:00Z"
    video.watermark_text = "Changed"
    video.gemini_translation_instructions = "Changed"
    assert HaizFlowController._video_source_key(video) == before
    video.manual_tool_generations["source"] += 1
    assert HaizFlowController._video_source_key(video) != before


def test_selected_source_key_uses_cached_selection_without_disk_lookup(monkeypatch):
    monkeypatch.setattr(video_store, "get_video", Mock(side_effect=AssertionError("unexpected disk read")))
    video = source()
    host = SimpleNamespace(_selected_video=lambda: video)
    assert HaizFlowController.selectedVideoSourceKey.fget(host) == HaizFlowController._video_source_key(video)


def test_manual_loading_placeholder_references_its_own_loader():
    source_text = (Path(__file__).parents[1] / "src/haizflow/desktop/qml/RouteHost.qml").read_text(encoding="utf-8")
    manual_loader = source_text.split("id: manualWorkspaceLoader", 1)[1].split("\n    Loader {", 1)[0]
    assert 'active: root.currentRoute === "manual-workspace"' in manual_loader
    assert "visible: manualWorkspaceLoader.active" in manual_loader
    assert "manualWorkspaceLoader.status !== Loader.Ready" in manual_loader
    single_loader = source_text.split("id: singleWorkspaceLoader", 1)[1].split("\n    Loader {", 1)[0]
    assert 'active: root.currentRoute === "single-workspace"' in single_loader
    assert "manualWorkspaceLoader" not in single_loader
