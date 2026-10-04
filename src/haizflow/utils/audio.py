"""Pydub integration: media helpers must never allocate a Windows console."""
import subprocess
from functools import partial

from pydub import AudioSegment
from pydub import audio_segment, utils


def _hidden_popen(*args, **kwargs):
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(*args, **kwargs)


def _hidden_call(name, *args, **kwargs):
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return getattr(subprocess, name)(*args, **kwargs)


class _MediaSubprocess:
    def __getattr__(self, name):
        if name == "Popen":
            return _hidden_popen
        if name in {"run", "check_output", "call", "check_call"}:
            return partial(_hidden_call, name)
        return getattr(subprocess, name)


# Adapt only Pydub's module-local references. Do not monkeypatch the standard
# subprocess module: user-requested installers and external apps stay visible.
audio_segment.subprocess = _MediaSubprocess()
utils.Popen = _hidden_popen

__all__ = ["AudioSegment"]
