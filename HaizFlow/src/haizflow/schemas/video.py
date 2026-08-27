from pydantic import BaseModel, Field
from typing import Dict, Literal, Optional


VIDEO_METADATA_SCHEMA_VERSION = 16
VIDEO_METADATA_TYPE = "haizflow.video"
WorkflowMode = Literal["A", "review"]
TranslatorProvider = Literal["hymt2"]
TTSProvider = Literal["omnivoice", "edge"]
SpeechRecognitionModel = Literal["small", "large-v3-turbo"]
OutputFormat = Literal["keep_ratio", "tiktok_9_16_crop", "blur_background_9_16"]
ProjectType = Literal["single", "manual", "batch"]
OriginalSubtitleRemovalMode = Literal["blur", "patch"]
SpeakerMode = Literal["single", "multiple"]


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
    # Used when OCR finds no source subtitle region. 60 is legible on the
    # standard 1080x1920 vertical export without overwhelming the frame.
    font_size: int = Field(default=60, ge=10, le=160)
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
    speech_recognition_model: SpeechRecognitionModel = "small"
    tts_provider: TTSProvider = "omnivoice"
    tts_voice: str = "omnivoice:female"
    speaker_mode: SpeakerMode = "single"
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    subtitle_layout_override: bool = False
    remove_original_subtitles: bool = True
    original_subtitle_removal_mode: OriginalSubtitleRemovalMode = "patch"
    output_format: OutputFormat = "keep_ratio"  # The desktop workflow preserves the original aspect ratio.
    crop: CropSettings = Field(default_factory=CropSettings)
    enable_audio_separation: bool = True
    original_video_volume: int = Field(default=60, ge=0, le=100)
    background_music_volume: int = Field(default=30, ge=0, le=100)
    tts_volume: int = Field(default=100, ge=0, le=100)
    watermark_text: str = Field(default="", max_length=80)
    # An import request only; the selected file is copied into the workspace.
    background_music_path: str = Field(default="", exclude=True)
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
    speech_recognition_model: SpeechRecognitionModel = "small"
    tts_provider: TTSProvider = "omnivoice"
    tts_voice: str
    speaker_mode: SpeakerMode = "single"
    subtitle_style: SubtitleStyle
    subtitle_layout_override: bool = False
    remove_original_subtitles: bool = True
    original_subtitle_removal_mode: OriginalSubtitleRemovalMode = "patch"
    output_format: OutputFormat
    crop: CropSettings = Field(default_factory=CropSettings)
    enable_audio_separation: bool = True
    original_video_volume: int = Field(default=60, ge=0, le=100)
    background_music_volume: int = Field(default=30, ge=0, le=100)
    tts_volume: int = Field(default=100, ge=0, le=100)
    watermark_text: str = Field(default="", max_length=80)
    project_name: str = ""
    project_directory: str = ""
    project_type: ProjectType = "single"
    project_id: str = ""
    project_key: str = ""
    # Manual projects run the same checkpointed pipeline one stage at a time.
    # ``manual_target_stage`` is the stage currently requested by the UI;
    # ``manual_completed_stage`` is retained as the most recent action for
    # backwards compatibility; ``manual_completed_stages`` is authoritative.
    manual_target_stage: str = ""
    manual_completed_stage: str = ""
    # Manual processing is a dependency graph rather than a linear wizard.
    # Visual work and voice/audio work may therefore be complete independently.
    manual_completed_stages: list[str] = Field(default_factory=list)
    # A stable, project-local position for batch cards.  Processing updates
    # must never affect this, otherwise the queue appears to shuffle.
    batch_import_order: int = 0
    video_width: int = 0
    video_height: int = 0
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
    # Total wall-clock processing time from completed run sessions.  The
    # active session, when any, is represented separately by ``started_at``.
    processing_elapsed_seconds: float = Field(default=0.0, ge=0)
    started_at: Optional[str] = None
    estimated_remaining_seconds: Optional[int] = None
    step_detail: str = ""
    current_item: int = 0
    total_items: int = 0
    error: Optional[str] = None
    files: Dict[str, Optional[str]] = Field(default_factory=dict)
