from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.core.subtitle_fonts import FONT_FILES
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline.render import font_file_fingerprint
from haizflow.pipeline.sequence_compiler import subtitle_style_overrides
from haizflow.schemas.editor import EditorClip, EditorDocument, EditorTextStyle, EditorTrack
from haizflow.schemas.video import SubtitleStyle
from haizflow.services import editor_documents


def old_document():
    return EditorDocument(
        video_id="old-manual", default_subtitle_style_id="subtitle-default",
        tracks=[EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề")],
        styles=[EditorTextStyle(style_id="subtitle-default", font_family="Bangers")],
        clips=[EditorClip(clip_id=f"cue-{index}", segment_id=str(index), track_id="subtitles",
                          kind="subtitle", duration_ms=1000, start_ms=index * 1000,
                          style_id="subtitle-default", name="Xin chào",
                          style_override={"font_family": "Bangers", "font_fingerprint": "old",
                                          "text_color": "#FFCC00"}) for index in range(2)],
    )


@pytest.mark.parametrize("family", FONT_FILES)
@pytest.mark.parametrize("scope", ["project", "segment"])
def test_real_manual_font_command_survives_old_overrides_save_and_reopen(tmp_path, monkeypatch, family, scope):
    document = old_document()
    host = SimpleNamespace(_apply_editor_mutation=lambda _label, callback: (callback(document) or True))
    assert HaizFlowController.applyTextStyle(host, ["cue-0"], {"font_family": family}, scope)
    path = tmp_path / "document.json"
    monkeypatch.setattr(editor_documents, "document_path", lambda _id: path)
    monkeypatch.setattr(editor_documents.video_store, "update_video", Mock())
    editor_documents.save(SimpleNamespace(video_id=document.video_id), document)
    restored = editor_documents.load(document.video_id)
    assert restored is not None
    styles = subtitle_style_overrides(restored)
    assert styles[1]["font_family"] == family
    assert styles[2]["font_family"] == (family if scope == "project" else "Bangers")
    assert all(style["text_color"] == "#FFCC00" for style in styles.values())
    resolved = editor_documents.resolved_text_style(restored, restored.clips[0])
    assert resolved.font_fingerprint == font_file_fingerprint(family)
    if scope == "project":
        assert restored.styles[0].font_family == family
        assert all("font_family" not in clip.style_override for clip in restored.clips)


@pytest.mark.parametrize("family", FONT_FILES)
def test_auto_font_command_preserves_selected_bundled_family(family):
    host = SimpleNamespace(_subtitle_style=SubtitleStyle(), subtitleSettingsChanged=Mock())
    assert HaizFlowController.applySubtitleAppearance(host, {"font_family": family})
    assert host._subtitle_style.font_family == family
