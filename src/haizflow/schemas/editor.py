from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EDITOR_DOCUMENT_SCHEMA_VERSION = 2

TrackKind = Literal[
    "source_video",
    "subtitle",
    "overlay",
    "voice",
    "source_audio",
    "music",
]
ClipKind = Literal[
    "source_video",
    "subtitle",
    "text",
    "image",
    "video",
    "voice",
    "audio",
]
Interpolation = Literal["linear", "ease_in", "ease_out", "ease_in_out"]


class EditorTransform(BaseModel):
    position_x_percent: float = Field(default=50.0, ge=-200, le=300)
    position_y_percent: float = Field(default=50.0, ge=-200, le=300)
    scale_x_percent: float = Field(default=100.0, ge=1, le=1000)
    scale_y_percent: float = Field(default=100.0, ge=1, le=1000)
    rotation_degrees: float = Field(default=0.0, ge=-3600, le=3600)
    opacity_percent: float = Field(default=100.0, ge=0, le=100)
    anchor_x_percent: float = Field(default=50.0, ge=0, le=100)
    anchor_y_percent: float = Field(default=50.0, ge=0, le=100)
    crop_left_percent: float = Field(default=0.0, ge=0, le=99)
    crop_right_percent: float = Field(default=0.0, ge=0, le=99)
    crop_top_percent: float = Field(default=0.0, ge=0, le=99)
    crop_bottom_percent: float = Field(default=0.0, ge=0, le=99)
    lock_aspect_ratio: bool = True


class EditorKeyframe(BaseModel):
    keyframe_id: str
    property_name: Literal["position_x", "position_y", "scale", "rotation", "opacity"]
    time_ms: int = Field(ge=0)
    value: float
    interpolation: Interpolation = "ease_in_out"


class EditorTextStyle(BaseModel):
    style_id: str
    name: str = ""
    target_type: Literal["subtitle", "watermark", "text_overlay"] = "subtitle"
    font_family: str = Field(default="Bangers", max_length=120)
    font_fingerprint: str = ""
    font_weight: int = Field(default=400, ge=100, le=900)
    italic: bool = False
    uppercase: bool = False
    font_size: float = Field(default=60.0, ge=6, le=600)
    letter_spacing: float = Field(default=0.0, ge=-20, le=100)
    line_spacing: float = Field(default=1.0, ge=0.5, le=4)
    alignment: Literal["left", "center", "right"] = "center"
    text_color: str = "#FFFFFF"
    karaoke_color: str = "#FFEF00"
    outline_color: str = "#000000"
    outline_width: float = Field(default=2.0, ge=0, le=40)
    shadow_color: str = "#000000"
    shadow_opacity_percent: int = Field(default=70, ge=0, le=100)
    shadow_offset_x: float = Field(default=2.0, ge=-100, le=100)
    shadow_offset_y: float = Field(default=2.0, ge=-100, le=100)
    shadow_blur: float = Field(default=0.0, ge=0, le=100)
    background_color: str = "#000000"
    background_opacity_percent: int = Field(default=0, ge=0, le=100)
    background_padding: float = Field(default=0.0, ge=0, le=100)
    background_radius: float = Field(default=0.0, ge=0, le=100)
    position_x_percent: float = Field(default=50.0, ge=0, le=100)
    position_y_percent: float = Field(default=88.0, ge=0, le=100)
    max_width_percent: float = Field(default=72.0, ge=10, le=100)
    box_height_percent: float = Field(default=12.0, ge=2, le=100)
    max_lines: int = Field(default=3, ge=1, le=20)
    safe_area_percent: float = Field(default=5.0, ge=0, le=40)


class EditorAsset(BaseModel):
    asset_id: str
    kind: Literal["source", "image", "video", "audio", "font"]
    name: str = ""
    path: str = ""
    fingerprint: str = ""
    duration_ms: int = Field(default=0, ge=0)
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditorClip(BaseModel):
    clip_id: str
    track_id: str
    kind: ClipKind
    asset_id: str = ""
    segment_id: str = ""
    name: str = ""
    start_ms: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    source_in_ms: int = Field(default=0, ge=0)
    source_out_ms: int = Field(default=0, ge=0)
    enabled: bool = True
    transform: EditorTransform = Field(default_factory=EditorTransform)
    style_id: str = ""
    style_override: dict[str, Any] = Field(default_factory=dict)
    keyframes: list[EditorKeyframe] = Field(default_factory=list)
    volume_percent: int = Field(default=100, ge=0, le=200)
    fade_in_ms: int = Field(default=0, ge=0)
    fade_out_ms: int = Field(default=0, ge=0)
    loop: bool = False
    muted: bool = False
    fit_mode: Literal["fit", "fill", "crop"] = "fit"
    border_width: float = Field(default=0.0, ge=0, le=100)
    corner_radius: float = Field(default=0.0, ge=0, le=100)
    shadow_strength: float = Field(default=0.0, ge=0, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditorTrack(BaseModel):
    track_id: str
    kind: TrackKind
    name: str
    order: int = 0
    visible: bool = True
    locked: bool = False
    muted: bool = False
    solo: bool = False


class EditorMarker(BaseModel):
    marker_id: str
    time_ms: int = Field(ge=0)
    name: str = ""
    color: str = "#C4915E"


class SourceEditDecision(BaseModel):
    decision_id: str
    source_start_ms: int = Field(ge=0)
    source_end_ms: int = Field(ge=0)
    sequence_start_ms: int = Field(ge=0)


class EditorSequence(BaseModel):
    duration_ms: int = Field(default=0, ge=0)
    source_asset_id: str = "source"
    edit_decisions: list[SourceEditDecision] = Field(default_factory=list)


class EditorDocument(BaseModel):
    schema_version: int = EDITOR_DOCUMENT_SCHEMA_VERSION
    document_type: str = "haizflow.editor"
    video_id: str
    revision: int = Field(default=1, ge=1)
    sequence: EditorSequence = Field(default_factory=EditorSequence)
    tracks: list[EditorTrack] = Field(default_factory=list)
    clips: list[EditorClip] = Field(default_factory=list)
    assets: list[EditorAsset] = Field(default_factory=list)
    styles: list[EditorTextStyle] = Field(default_factory=list)
    markers: list[EditorMarker] = Field(default_factory=list)
    default_subtitle_style_id: str = "subtitle-default"
    audio_ducking_enabled: bool = False
    audio_ducking_reduction_db: float = Field(default=-12.0, ge=-60, le=0)
    audio_ducking_attack_ms: int = Field(default=180, ge=0, le=10000)
    audio_ducking_release_ms: int = Field(default=420, ge=0, le=10000)
