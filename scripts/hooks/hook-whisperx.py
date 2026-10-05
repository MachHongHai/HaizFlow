"""Collect the inference modules hidden behind WhisperX's lazy public API."""

hiddenimports = [
    "whisperx.asr",
    "whisperx.alignment",
    "whisperx.audio",
    "whisperx.log_utils",
    "whisperx.schema",
    "whisperx.vads",
    "pyannote.audio.models.segmentation.PyanNet",
]
