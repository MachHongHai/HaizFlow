"""Pydub integration: media helpers must never allocate a Windows console."""
from pydub import AudioSegment
from pydub import audio_segment, utils
from haizflow.utils.media_subprocess import _MediaSubprocess, _hidden_popen


# Adapt only Pydub's module-local references. Do not monkeypatch the standard
# subprocess module: user-requested installers and external apps stay visible.
audio_segment.subprocess = _MediaSubprocess()
utils.Popen = _hidden_popen

__all__ = ["AudioSegment"]
