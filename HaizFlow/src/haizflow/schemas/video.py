from pydantic import BaseModel, Field
from typing import Dict, Literal, Optional


VIDEO_METADATA_SCHEMA_VERSION = 5
VIDEO_METADATA_TYPE = "haizflow.video"
WorkflowMode = Literal["A", "review"]
TranslatorProvider = Literal["hymt2"]
OutputFormat = Literal["keep_ratio", "tiktok_9_16_crop", "blur_background_9_16"]
ProjectType = Literal["single", "batch"]


class MediaSource(BaseModel):
    type: Literal["local_file", "video_url", "channel"] = "local_file"
    platform: str = ""
    remote_video_id: str = ""
    source_url: str = ""
    channel_url: str = ""
    channel_name: str = ""
    import_session_id: str = ""
    imported_at: str = ""


class SubtitleStyle(BaseModel):
    font_size: int = Field(default=36, ge=10, le=160)
    margin_bottom: int = Field(default=40, ge=0, le=1000)
    outline: int = Field(default=2, ge=0, le=20)
    max_chars_per_line: int = Field(default=32, ge=12, le=200)
    position_x_percent: int = Field(default=51, ge=0, le=100)
    position_y_percent: int = Field(default=96, ge=0, le=100)
    box_width_percent: int = Field(default=72, ge=20, le=100)
    box_height_percent: int = Field(default=6, ge=1, le=100)


class CropSettings(BaseModel):
    zoom_percent: int = Field(default=100, ge=1, le=400)
    pan_x_percent: int = Field(default=0, ge=-100, le=100)
    pan_y_percent: int = Field(default=0, ge=-100, le=100)
    left_percent: int = Field(default=0, ge=0, le=84)
    right_percent: int = Field(default=0, ge=0, le=84)
    top_percent: int = Field(default=0, ge=0, le=84)
    bottom_percent: int = Field(default=0, ge=0, le=84)


class VideoConfig(BaseModel):
    mode: WorkflowMode = "A"  # A = full auto, review = pause after translation.
    source_language: str = "auto"  # Automatic detection is performed for every speech segment.
    target_language: str = "vi"
    translator_provider: TranslatorProvider = "hymt2"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    output_format: OutputFormat = "keep_ratio"  # The desktop workflow preserves the original aspect ratio.
    crop: CropSettings = Field(default_factory=CropSettings)
    enable_audio_separation: bool = False
    original_video_volume: int = Field(default=60, ge=0, le=100)
    project_name: str = ""
    project_directory: str = ""
    project_type: ProjectType = "single"
    project_id: str = ""
    project_key: str = ""
    review_approved: bool = False


class VideoInfo(BaseModel):
    schema_version: int = VIDEO_METADATA_SCHEMA_VERSION
    metadata_type: str = VIDEO_METADATA_TYPE
    video_id: str
    original_filename: str
    mode: WorkflowMode
    source_language: str
    target_language: str
    translator_provider: TranslatorProvider = "hymt2"
    tts_voice: str
    subtitle_style: SubtitleStyle
    output_format: OutputFormat
    crop: CropSettings = Field(default_factory=CropSettings)
    enable_audio_separation: bool = False
    original_video_volume: int = Field(default=60, ge=0, le=100)
    project_name: str = ""
    project_directory: str = ""
    project_type: ProjectType = "single"
    project_id: str = ""
    project_key: str = ""
    video_width: int = 0
    video_height: int = 0
    subtitle_override: bool = False
    review_approved: bool = False
    media_source: MediaSource = Field(default_factory=MediaSource)
    status: str  # pending, processing, done, failed
    progress: int = 0
    step: str = "pending"
    resume_step: str = ""
    # Separate from pause/resume checkpoints: this records a single automatic
    # GPU-to-CPU recovery during the current run.
    runtime_recovery_step: str = ""
    gpu_recovery_attempted: bool = False
    checkpoints: Dict[str, str] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    estimated_remaining_seconds: Optional[int] = None
    step_detail: str = ""
    current_item: int = 0
    total_items: int = 0
    error: Optional[str] = None
    files: Dict[str, Optional[str]] = Field(default_factory=dict)
