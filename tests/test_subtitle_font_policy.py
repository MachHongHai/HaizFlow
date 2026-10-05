from haizflow.schemas.video import SubtitleStyle
from haizflow.schemas.editor import EditorClip, EditorDocument, EditorTextStyle
from haizflow.services.editor_documents import resolved_text_style
from haizflow.pipeline.render import _write_positioned_ass, resolve_subtitle_preview_layout
from haizflow.schemas.video import CropSettings


def test_legacy_subtitle_fonts_normalize_without_affecting_other_text():
    assert SubtitleStyle(font_family="Arial").font_family == "Bangers"
    style = EditorTextStyle(style_id="legacy", font_family="Arial", font_fingerprint="old")
    assert style.font_family == "Bangers"
    assert style.font_fingerprint == ""
    assert EditorTextStyle(style_id="wm", target_type="watermark", font_family="Arial").font_family == "Arial"
    assert EditorTextStyle(style_id="text", target_type="text_overlay", font_family="Segoe UI").font_family == "Segoe UI"


def test_subtitle_clip_cannot_override_font_or_target_type():
    clip = EditorClip(clip_id="cue", track_id="subtitles", kind="subtitle", style_id="shared",
                      style_override={"font_family": "Arial", "font_fingerprint": "old", "font_size": 72})
    assert clip.style_override == {"font_family": "Bangers", "font_size": 72}
    doc = EditorDocument(video_id="video", clips=[clip], styles=[
        EditorTextStyle(style_id="shared", target_type="watermark", font_family="Arial")])
    clip.style_override.update(font_family="Impact", target_type="text_overlay")
    resolved = resolved_text_style(doc, clip)
    assert resolved.font_family == "Bangers" and resolved.target_type == "subtitle"
    assert resolved.font_size == 72
    assert doc.styles[0].font_family == "Arial"


def test_preview_and_ass_normalize_unvalidated_legacy_copies(tmp_path):
    style = SubtitleStyle().model_copy(update={"font_family": "Arial"})
    layout = resolve_subtitle_preview_layout(None, 1080, 1920, "keep_ratio", CropSettings(), style, True)
    assert layout["fontFamily"] == "Bangers"
    srt = tmp_path / "captions.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nXin chào\n", encoding="utf-8")
    ass = tmp_path / "captions.ass"
    _write_positioned_ass(str(srt), str(ass), style, 1080, 1920)
    text = ass.read_text(encoding="utf-8")
    assert "Style: Default,Bangers," in text and "Arial" not in text
