"""Collect the inference modules hidden behind WhisperX's lazy public API."""

from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("whisperx", recursive=True)

hiddenimports = [
    "whisperx.asr",
    "whisperx.alignment",
    "whisperx.audio",
    "whisperx.log_utils",
    "whisperx.schema",
    "whisperx.vads",
    "pyannote.audio.models.segmentation.PyanNet",
]
