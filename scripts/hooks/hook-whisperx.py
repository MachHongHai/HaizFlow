"""Collect the inference modules hidden behind WhisperX's lazy public API."""

from PyInstaller.utils.hooks import copy_metadata
from pathlib import Path
from importlib.metadata import distributions

# The hash-locked profile contains all runtime distributions. Do not traverse
# optional/build requirements (e.g. setuptools), which need not be installed.
datas = [entry for distribution in distributions() for entry in copy_metadata(distribution.metadata["Name"])]
datas.append((str(Path(__file__).parent / "pyannote-audio/config.yaml"), "pyannote/audio/telemetry"))

hiddenimports = [
    "whisperx.asr",
    "whisperx.alignment",
    "whisperx.audio",
    "whisperx.log_utils",
    "whisperx.schema",
    "whisperx.vads",
    "pyannote.audio.models.segmentation.PyanNet",
]
